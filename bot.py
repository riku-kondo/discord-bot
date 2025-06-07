print("bot.pyが読み込まれました")

import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

# Firebaseの初期化（最初の一度だけ行う）
if not firebase_admin._apps:
    firebase_creds_json = os.environ.get("FIREBASE_CREDENTIALS")
    if not firebase_creds_json:
        raise Exception("FIREBASE_CREDENTIALS environment variable is not set")
    cred_dict = json.loads(firebase_creds_json)
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)

# Firestoreクライアントの作成
db = firestore.client()

import shutil
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from dotenv import load_dotenv
from keep_alive import keep_alive

load_dotenv()

# --- インテント設定 ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

money = {}  # 所持金の保存用辞書
money_file = "money.json"


# --- 保存・読み込み ---
def load_money():
    global money
    if os.path.exists(money_file):
        with open(money_file, "r", encoding="utf-8") as f:
            money = json.load(f)
            money = {int(k): v for k, v in money.items()}


def save_money():
    save_all_money_to_firestore()  # Firestoreへ保存
    # 任意：バックアップでJSONにも保存（必要な場合のみ）
    with open(money_file, "w", encoding="utf-8") as f:
        json.dump(money, f, ensure_ascii=False, indent=2)


def load_money_from_firestore_sync():
    global money
    money.clear()
    docs = db.collection("user_balances").stream()
    for doc in docs:
        user_id = int(doc.id)
        data = doc.to_dict()
        money[user_id] = data.get("balance", 0)


def save_user_balance_to_firestore(user_id: int, balance: int):
    doc_ref = db.collection("user_balances").document(str(user_id))
    doc_ref.set({"balance": balance})


def save_all_money_to_firestore():
    batch = db.batch()
    for user_id, balance in money.items():
        doc_ref = db.collection("user_balances").document(str(user_id))
        batch.set(doc_ref, {"balance": balance})
    batch.commit()


# --- 給料テーブル ---
給料テーブル = {
    "fée des l’eau": 47,
    "General": 200000,
    "マスター": 80000,
    "プレイヤー": 50000,
    "vip": 30000,
    "Silver": 10000,
    "Gold": 20000,
    "Platinum": 30000,
    "Diamond": 40000,
    "Ruby": 50000,
    "Black": 60000,
    "静観者": 10000,
    "監査官": 60000,
    "監査官の卵": 30000,
    "賭制官": 50000,
    "賭制官の卵": 30000,
    "規制官": 50000,
    "規制官の卵": 30000,
    "案内官": 65000,
    "ベル": 30000,
    "ベルの卵": 20000
}


@bot.event
async def on_ready():
    load_money()
    await bot.change_presence(activity=discord.Game(name="テーブルをセット"))

    load_money_from_firestore_sync()  # ←これを追加
    print("Firestoreから残高をロードしました")
    # 既存のon_readyの内容もそのままでOK

    try:
        guild = discord.Object(id=1351599305932275832)

        synced = await bot.tree.sync(guild=guild)
        print(f"✅ ギルドコマンドを {len(synced)} 件同期しました")

    except Exception as e:
        print(f"⚠️ ギルド同期エラー: {e}")

    print(f"✅ Botログイン: {bot.user}")

    print("登録されているコマンド一覧:")
    for command in bot.tree.get_commands():
        print(f"- {command.name}")

    if not 月初め給料支払い.is_running():
        月初め給料支払い.start()

    if not 自動バックアップ.is_running():
        自動バックアップ.start()

    print("月初め給料支払い & 自動バックアップ 起動完了")


# --- 自分の残高を確認 ---


@bot.tree.command(name="通貨スタック", description="スタックを確認します")
@app_commands.guilds(discord.Object(id=1351599305932275832))
async def money_check(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    user = interaction.user
    amount = money.get(user.id, 0)
    await interaction.followup.send(
        f"{user.display_name} のスタックは {amount} lactip です。", ephemeral=True)


# --- 他人に送金 ---
@bot.tree.command(name="通貨送金", description="lactipを送金します")
@app_commands.guilds(discord.Object(id=1351599305932275832))
@app_commands.describe(相手="送金先のユーザーを指定します",
                       金額="送金するtip量を指定します",
                       理由="送金の理由を記載します")
async def send_money(interaction: discord.Interaction,
                     相手: discord.User,
                     金額: int,
                     理由: str = ""):
    await interaction.response.defer()
    送信者 = interaction.user

    if 送信者.id == 相手.id:
        await interaction.followup.send("自分自身に送金はできません。", ephemeral=True)
        return

    if 金額 <= 0:
        await interaction.followup.send("tipは1以上を指定してください。", ephemeral=True)
        return

    送信者残高 = money.get(送信者.id, 0)
    if 送信者残高 < 金額:
        await interaction.followup.send("送金エラー：スタックが不足しています", ephemeral=True)
        return

    money[送信者.id] = 送信者残高 - 金額
    money[相手.id] = money.get(相手.id, 0) + 金額

    # Firestore保存
    save_user_balance_to_firestore(送信者.id, money[送信者.id])
    save_user_balance_to_firestore(相手.id, money[相手.id])
    save_money()

    reason_text = f" 理由: {理由}" if 理由 else " 理由: なし"
    await interaction.followup.send(
        f"{相手.display_name} に {金額} lactipを送金しました。{reason_text}")


# --- 娯楽部の支払い ---

period_choices = [
    app_commands.Choice(name="24時間", value="24h"),
    app_commands.Choice(name="1週間", value="1w"),
    app_commands.Choice(name="1ヶ月", value="1m"),
]


@bot.tree.command(name="通貨娯楽部お支払い", description="娯楽部の支払いを自動化します")
@app_commands.guilds(discord.Object(id=1351599305932275832))
@app_commands.describe(期間="利用期間を指定します", 理由="支援するユーザーの名前を記載")
@app_commands.choices(期間=period_choices)
async def payment(interaction: discord.Interaction,
                  期間: app_commands.Choice[str],
                  理由: str = ""):
    await interaction.response.defer(ephemeral=True)
    now = datetime.now()

    if 期間.value == "24h":
        end_date = now + timedelta(hours=24)
        amount = 10000
    elif 期間.value == "1w":
        end_date = now + timedelta(weeks=1)
        amount = 30000
    elif 期間.value == "1m":
        end_date = now + timedelta(days=30)
        amount = 50000
    else:
        await interaction.followup.send("不正な期間です", ephemeral=True)
        return

    user_id = interaction.user.id
    dealer_id = bot.user.id

    if money.get(user_id, 0) < amount:
        await interaction.followup.send("スタックが不足しています！", ephemeral=True)
        return

    # 支払い処理（ユーザー → Dealer）
    money[user_id] -= amount
    money[dealer_id] = money.get(dealer_id, 0) + amount

    # Firestore保存
    save_user_balance_to_firestore(user_id, money[user_id])
    save_user_balance_to_firestore(dealer_id, money[dealer_id])
    save_money()

    reason_text = f"理由: {理由}" if 理由 else "理由:"

    embed = discord.Embed(
        description=
        f"{interaction.user.display_name}が娯楽費の支払いに成功しました。\n期間: {期間.name}、{reason_text}",
        color=discord.Color.blue())

    # Embed通知（みんなに見える）
    await interaction.channel.send(embed=embed)

    # 支払い完了（本人にだけ見える）
    await interaction.followup.send("支払い完了", ephemeral=True)

    # 通知チャンネルに有効期限を表示
    target_channel_id = 1372394135230611516
    channel = bot.get_channel(target_channel_id)
    if channel:
        end_str = end_date.strftime("%Y-%m/%d")
        await channel.send(f"{interaction.user.mention} - {end_str}")
    else:
        print("❌ 通知チャンネルが見つかりません。")


# --- 定数設定 ---
CHALLENGE_ROLE_NAME = "挑戦者"
CHALLENGE_CHANNEL_ID = 1373865991200833536  # ← #ゼネラル部屋のチャンネルIDに置き換えてください
CHALLENGE_COSTS = {"挑戦": 50000, "再挑戦": 10000}

挑戦モード = [
    app_commands.Choice(name="挑戦", value="挑戦"),
    app_commands.Choice(name="再挑戦", value="再挑戦")
]


# --- 通貨挑戦状コマンド ---
@bot.tree.command(name="通貨挑戦状", description="挑戦状を送ります")
@app_commands.guilds(discord.Object(id=1351599305932275832))  # ← サーバーID
@app_commands.describe(対象ユーザー="挑戦相手", モード="挑戦 or 再挑戦", 種目="挑戦する種目を記入")
@app_commands.choices(モード=挑戦モード)
async def 挑戦状(interaction: discord.Interaction, 対象ユーザー: discord.Member,
              モード: app_commands.Choice[str], 種目: str):
    await interaction.response.defer(ephemeral=True)
    実行者 = interaction.user
    user_id = 実行者.id
    mode_value = モード.value
    now = datetime.now()

    # --- モードと残高チェック ---
    cost = CHALLENGE_COSTS.get(mode_value)
    if money.get(user_id, 0) < cost:
        await interaction.followup.send(f"残高が不足しています（必要：{cost}）",
                                        ephemeral=True)
        return

    # --- ロール取得または作成 ---
    guild = interaction.guild
    role = discord.utils.get(guild.roles, name=CHALLENGE_ROLE_NAME)
    if not role:
        role = await guild.create_role(name=CHALLENGE_ROLE_NAME)

    # --- 再挑戦 → 挑戦者ロールがないなら拒否 ---
    if mode_value == "再挑戦" and role not in 実行者.roles:
        await interaction.followup.send("再挑戦には「挑戦者」が必要です。", ephemeral=True)
        return

    # --- 支払い処理 ---
    dealer_id = bot.user.id
    money[user_id] -= cost
    money[dealer_id] = money.get(dealer_id, 0) + cost
    save_user_balance_to_firestore(user_id, money[user_id])
    save_user_balance_to_firestore(dealer_id, money[dealer_id])
    save_money()

    # --- 挑戦者ロール付与 ---
    if role not in 実行者.roles:
        await 実行者.add_roles(role)

    # --- 支払いチャンネルにEmbed通知 ---
    embed_all = discord.Embed(description=(f"✉️ ⊰{対象ユーザー.mention} に挑戦状を送りました⊱\n"
                                           f"**種目**: {種目}"),
                              color=discord.Color.red(),
                              timestamp=now)
    await interaction.channel.send(embed=embed_all)

    # --- ゼネラル部屋にEmbed通知（2行構成） ---
    embed_general = discord.Embed(
        description=(f"✉️ ⊰{実行者.display_name} から挑戦状が届きました⊱\n"
                     f"種目：{種目}"),
        color=discord.Color.red(),
        timestamp=now)
    general_channel = bot.get_channel(CHALLENGE_CHANNEL_ID)
    if general_channel:
        await general_channel.send(embed=embed_general)

    # --- 実行者にだけ通知 ---
    await interaction.followup.send("支払い成功", ephemeral=True)


# --- 月末に「挑戦者」ロールを全員から削除するタスク ---
@tasks.loop(hours=24)
async def remove_challenger_roles():
    now = datetime.now()
    if now.day != 1:
        return  # 毎月1日のみ実行

    for guild in bot.guilds:
        role = discord.utils.get(guild.roles, name=CHALLENGE_ROLE_NAME)
        if not role:
            continue

        for member in role.members:
            try:
                await member.remove_roles(role)
                print(f" {member.display_name} から挑戦者ロールを削除しました")
            except Exception as e:
                print(f"❌ ロール削除失敗: {member.display_name} - {e}")


#lact全体贈与


@app_commands.default_permissions(administrator=True)
@bot.tree.command(name="lact全体贈与",
                  description="プレイヤーとマスター全体にlacttipを贈与します（ワンペア除外・管理者限定）")
@app_commands.guilds(
    discord.Object(id=1351599305932275832))  # ← あなたのギルドIDに合わせています
@app_commands.describe(amount="贈与するlacttip量（1人あたり）")
async def mass_tip(interaction: discord.Interaction, amount: int):
    await interaction.response.defer(ephemeral=True)

    if amount <= 0:
        await interaction.followup.send("贈与するtipは1以上にしてください。")
        return

    guild = interaction.guild
    if not guild:
        await interaction.followup.send("このコマンドはサーバー内でのみ使用できます。")
        return

    # ロール取得
    role_player = discord.utils.get(guild.roles, name="プレイヤー")
    role_master = discord.utils.get(guild.roles, name="マスター")
    role_exclude = discord.utils.get(guild.roles, name="ワンペア")

    # 対象ユーザーを抽出
    targets = [
        member for member in guild.members if not member.bot and (
            role_player in member.roles or role_master in member.roles) and (
                role_exclude not in member.roles)
    ]

    if not targets:
        await interaction.followup.send("贈与対象のユーザーが見つかりませんでした。")
        return

    dealer_id = bot.user.id
    money.setdefault(dealer_id, 0)
    dealer_balance = money[dealer_id]

    total_required = amount * len(targets)
    if dealer_balance < total_required:
        await interaction.followup.send(
            f"Dealerの残高が不足しています。\n必要: {total_required} / 保有: {dealer_balance}",
            ephemeral=True)
        return

    # 贈与処理
    for member in targets:
        money[member.id] = money.get(member.id, 0) + amount
        save_user_balance_to_firestore(member.id, money[member.id])

    # Dealerの残高更新
    money[dealer_id] -= total_required
    save_user_balance_to_firestore(dealer_id, money[dealer_id])

    save_money()  # 保存（非同期であれば await）

    # 結果通知
    await interaction.followup.send(
        f"{len(targets)}人にそれぞれ {amount:,} lacttip を贈与しました。\n"
        f"Dealerの残高: {money[dealer_id]:,} lacttip")


# --- 管理者: lactip贈与 ---


@app_commands.default_permissions(administrator=True)
@bot.tree.command(name="lact贈与",
                  description="Dealerからユーザーにlacttipを贈与します（管理者限定）")
@app_commands.guilds(discord.Object(id=1351599305932275832))
@app_commands.describe(target="贈与先を指定します", amount="贈与するlacttip量")
async def add_money(interaction: discord.Interaction, target: discord.User,
                    amount: int):
    await interaction.response.defer()

    if amount <= 0:
        await interaction.followup.send("贈与するtipは1以上にしてください。", ephemeral=True)
        return

    dealer_id = bot.user.id
    money.setdefault(dealer_id, 0)
    dealer_balance = money[dealer_id]

    if dealer_balance < amount:
        await interaction.followup.send("Dealerの残高が不足しています。", ephemeral=True)
        return

    money[dealer_id] -= amount
    money[target.id] = money.get(target.id, 0) + amount

    # Firestore保存
    save_user_balance_to_firestore(dealer_id, money[dealer_id])
    save_user_balance_to_firestore(target.id, money[target.id])

    save_money()  # 非同期なら await を忘れずに

    await interaction.followup.send(
        f"{target.mention} に {amount} lacttip を贈与しました。\n"
        f"Dealerの残高: {money[dealer_id]} lacttip")


# --- 管理者: lactip徴収 ---
@app_commands.default_permissions(administrator=True)
@bot.tree.command(name="lact徴収",
                  description="ユーザーからDealerにlactipを徴収します（管理者限定）")
@app_commands.guilds(discord.Object(id=1351599305932275832))
@app_commands.describe(対象="徴収先を指定します", 金額="徴収するlacttip量")
async def remove_money(interaction: discord.Interaction, 対象: discord.User,
                       金額: int):
    await interaction.response.defer()

    if 金額 <= 0:
        await interaction.followup.send("徴収するtipは1以上にしてください。", ephemeral=True)
        return

    user_balance = money.get(対象.id, 0)
    if user_balance == 0:
        await interaction.followup.send(
            f"{対象.display_name} のスタックはすでに 0 lactip です。", ephemeral=True)
        return

    actual_deduction = min(金額, user_balance)
    money[対象.id] = user_balance - actual_deduction

    dealer_id = bot.user.id
    money[dealer_id] = money.get(dealer_id, 0) + actual_deduction

    # Firestore保存
    save_user_balance_to_firestore(対象.id, money[対象.id])
    save_user_balance_to_firestore(dealer_id, money[dealer_id])

    save_money()

    dealer_balance_after = money[dealer_id]
    await interaction.followup.send(
        f"{対象.mention} から {actual_deduction} lactipを徴収しました。\n"
        f"Dealerの残高: {dealer_balance_after} lacttip")


# --- 管理者: 手動で保存 ---
@app_commands.default_permissions(administrator=True)
@bot.tree.command(name="lact保存", description="現在の通貨データを手動で保存します（管理者限定）")
@app_commands.guilds(discord.Object(id=1351599305932275832))
async def save_data(interaction: discord.Interaction):
    save_money()

    # Firestoreにも保存（全ユーザー）
    for user_id, balance in money.items():
        save_user_balance_to_firestore(user_id, balance)
    await interaction.response.send_message("通貨データを保存しました！", ephemeral=True)


# --- 月初め給料支払い設定（JSTで動作） ---
JST = timezone(timedelta(hours=9))
last_salary_paid_date = None  # 支払い済み日付を記録


@tasks.loop(minutes=10)
async def 月初め給料支払い():
    global last_salary_paid_date

    await bot.wait_until_ready()

    now = datetime.now(JST)
    today_str = now.strftime("%Y-%m-%d")

    # ▶ JSTで 1日 の 0:00〜0:09 にのみ実行
    if now.day != 1 or now.hour != 0 or now.minute >= 10:
        return

    if last_salary_paid_date == today_str:
        return  # 同じ日ならスキップ

    dealer_id = bot.user.id
    salary_log_channel_id = 1376374892055887883
    channel = bot.get_channel(salary_log_channel_id)

    支払い成功者数 = 0
    支払い失敗者数 = 0

    for guild in bot.guilds:
        for member in guild.members:
            if member.bot:
                continue

            total_amount = 0
            for role in member.roles:
                if role.name in 給料テーブル:
                    total_amount += 給料テーブル[role.name]

            if total_amount == 0:
                continue

            dealer_balance = money.get(dealer_id, 0)
            if dealer_balance < total_amount:
                支払い失敗者数 += 1
                continue

            money[dealer_id] = dealer_balance - total_amount
            save_user_balance_to_firestore(dealer_id,
                                           money[dealer_id])  # Dealerの残高も保存

            money[member.id] = money.get(member.id, 0) + total_amount
            save_user_balance_to_firestore(member.id,
                                           money[member.id])  # メンバーの残高も保存

            try:
                details = [
                    f"{role.name}: {給料テーブル[role.name]}"
                    for role in member.roles if role.name in 給料テーブル
                ]
                detail_text = "\n".join(details)
                await member.send(f"＝あなたに以下の給料が支払われました＝\n\n"
                                  f"{detail_text}\n\n"
                                  f"合計額: {total_amount} LACTtip")
            except discord.Forbidden:
                print(f"❌ {member.display_name} にDMできませんでした。")

            支払い成功者数 += 1

    save_money()
    last_salary_paid_date = today_str

    if channel:
        await channel.send(f"✅ 今月の給料支払いが完了しました（JST）\n"
                           f"支払い成功者数: {支払い成功者数}\n"
                           f"支払い失敗者数: {支払い失敗者数}\n"
                           f"Dealer残高: {money[dealer_id]} lacttip")
    else:
        print("❌ 給料ログチャンネルが見つかりません。")


# --- 新規参加者に初期付与 ---
@bot.event
async def on_member_join(member: discord.Member):
    if member.bot:
        return

    初期tip = 50000
    dealer_id = bot.user.id

    dealer_balance = money.get(dealer_id, 0)
    if dealer_balance < 初期tip:
        print(f"Dealerの残高不足で {member.display_name} に初期tipを付与できませんでした。")
        return

    # Dealerから引いてメンバーに付与
    money[dealer_id] = dealer_balance - 初期tip
    save_user_balance_to_firestore(dealer_id, money[dealer_id])  # Firestore保存
    money[member.id] = money.get(member.id, 0) + 初期tip
    save_user_balance_to_firestore(member.id, money[member.id])  # Firestore保存
    save_money()

    welcome_channel_id = 1376444952233377872
    channel = bot.get_channel(welcome_channel_id)
    if channel:
        await channel.send(f"{member.mention} が参加。初期tip {初期tip} lacttip を付与。")


# --- 管理者: Dealerの所持金を確認 ---
@app_commands.default_permissions(administrator=True)
@bot.tree.command(name="lact残高", description="Dealerの所持金を確認します（管理者限定）")
@app_commands.guilds(discord.Object(id=1351599305932275832))
async def check_dealer_balance(interaction: discord.Interaction):
    dealer_id = bot.user.id
    amount = money.get(dealer_id, 0)
    await interaction.response.send_message(f"Dealer残高は {amount} lacttip です。",
                                            ephemeral=True)


# --- 管理者: Dealerの残高を増やす ---
@app_commands.default_permissions(administrator=True)
@bot.tree.command(name="lact増加", description="Dealerの残高を増やします（管理者限定）")
@app_commands.guilds(discord.Object(id=1351599305932275832))
@app_commands.describe(金額="Dealerの残高に追加するlacttipの量（整数）")
async def increase_dealer_balance(interaction: discord.Interaction, 金額: int):
    await interaction.response.defer(ephemeral=True)

    if 金額 <= 0:
        await interaction.followup.send("追加するlacttipは1以上にしてください。",
                                        ephemeral=True)
        return

    dealer_id = bot.user.id
    old_balance = money.get(dealer_id, 0)
    new_balance = old_balance + 金額
    money[dealer_id] = new_balance
    save_user_balance_to_firestore(dealer_id, new_balance)  # Firestore保存
    save_money()

    await interaction.followup.send(
        f"Dealerの残高を {金額} lacttip 増加しました。\n"
        f"旧残高: {old_balance} → 新残高: {new_balance} lacttip",
        ephemeral=True)


# --- 自動バックアップ設定（24時間ごと） ---
# バックアップ先フォルダ
BACKUP_FOLDER = "./backup_money"
os.makedirs(BACKUP_FOLDER, exist_ok=True)


@tasks.loop(hours=24)
async def 自動バックアップ():
    try:
        # 現在の日時でバックアップファイル名を作成
        now_str = datetime.now().strftime("%Y%m%d")
        backup_filename = f"money_backup_{now_str}.json"
        backup_path = os.path.join(BACKUP_FOLDER, backup_filename)

        # money.json をバックアップフォルダにコピー
        shutil.copy("money.json", backup_path)
        print(f" money.json をバックアップしました: {backup_path}")

        # 7日より古いバックアップを自動削除
        threshold = datetime.now() - timedelta(days=7)
        for fname in os.listdir(BACKUP_FOLDER):
            if fname.startswith("money_backup_") and fname.endswith(".json"):
                fpath = os.path.join(BACKUP_FOLDER, fname)
                file_time = datetime.fromtimestamp(os.path.getmtime(fpath))
                if file_time < threshold:
                    os.remove(fpath)
                    print(f"🗑 古いバックアップを削除しました: {fname}")

    except Exception as e:
        print(f"❌ 自動バックアップ中にエラーが発生しました: {e}")


# --- VC報酬関連の設定 ---
VC_CHANNEL_IDS = [
    1353365807031390248, 1353365963919331338, 1353366017711018155,
    1353366509229183017, 1353366552912597033
]  # 対象VCチャンネルIDを指定（複数OK）

VC_REWARD_UNIT = 97  # 5分ごとの報酬額（lacttip）
VC_REWARD_INTERVAL = 300  # 5分（秒）
VC_MIN_DURATION = 600  # 最低滞在時間（秒）＝10分
VC_DAILY_LIMIT = 1164  # 1日あたりの最大報酬額（lacttip）

# --- VCセッション記録・日次報酬記録 ---
vc_sessions = {}  # {user_id: {"channel": id, "start": datetime}}
vc_reward_today = {}  # {user_id: {"date": "YYYY-MM-DD", "total": int}}


@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return

    now = datetime.now()
    user_id = member.id

    # --- VC退出またはチャンネル移動処理 ---
    if before.channel and (not after.channel
                           or before.channel.id != after.channel.id):
        if user_id in vc_sessions:
            session = vc_sessions.pop(user_id)
            start = session["start"]
            joined_channel_id = session["channel"]

            # ✅ 実際にいたVCが対象チャンネルだったかチェック
            if joined_channel_id in VC_CHANNEL_IDS:
                duration = (now - start).total_seconds()

                if duration >= VC_MIN_DURATION:
                    reward_units = int(duration // VC_REWARD_INTERVAL)
                    reward_amount = reward_units * VC_REWARD_UNIT

                    today_str = now.strftime("%Y-%m-%d")
                    daily = vc_reward_today.get(user_id, {
                        "date": today_str,
                        "total": 0
                    })

                    # 日付が変わったらリセット
                    if daily["date"] != today_str:
                        daily = {"date": today_str, "total": 0}

                    remaining = VC_DAILY_LIMIT - daily["total"]
                    granted = min(reward_amount, remaining)

                    if granted > 0:
                        money[user_id] = money.get(user_id, 0) + granted
                        save_user_balance_to_firestore(
                            user_id, money[user_id])  # Firestore保存
                        vc_reward_today[user_id] = {
                            "date": today_str,
                            "total": daily["total"] + granted
                        }
                        save_money()  # 外部関数：残高を保存する既存関数

    # --- VC入室または移動後の処理 ---
    if after.channel and after.channel.id in VC_CHANNEL_IDS:
        vc_sessions[user_id] = {"channel": after.channel.id, "start": now}


# --- Botトークンで起動 ---

if __name__ == "__main__":
    keep_alive()

bot.run(
    os.getenv("DISCORD_TOKEN"))  # ← このままでOK（Renderで環境変数DISCORD_TOKENを登録するので）
