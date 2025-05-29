print("bot.pyが読み込まれました")

import os
from dotenv import load_dotenv
load_dotenv()

from keep_alive import keep_alive
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import json

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
    with open(money_file, "w", encoding="utf-8") as f:
        json.dump(money, f, ensure_ascii=False, indent=2)


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


# --- Bot起動時処理 ---
@bot.event
async def on_ready():
    load_money()
    await bot.change_presence(activity=discord.Game(name="通貨bot起動中"))
    try:
        synced = await bot.tree.sync()
        print(f"✅ スラッシュコマンド {len(synced)} 件同期しました")
    except Exception as e:
        print(f"同期エラー: {e}")
    print(f"✅ Botログイン: {bot.user}")
    月初め給料支払い.start()


# --- 自分の残高を確認 ---
@bot.tree.command(name="通貨スタック", description="スタックを確認します")
async def money_check(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    user = interaction.user
    amount = money.get(user.id, 0)
    await interaction.followup.send(
        f"{user.display_name} のスタックは {amount} lactip です。", ephemeral=True)


# --- 他人に送金 ---
@bot.tree.command(name="通貨送金", description="lactipを送金します")
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
    save_money()

    reason_text = f" 理由: {理由}" if 理由 else " 理由: なし"
    await interaction.followup.send(
        f"{相手.display_name} に {金額} lactipを送金しました。{reason_text}")


# --- 娯楽部の支払い ---
from datetime import datetime, timedelta
from discord import app_commands

period_choices = [
    app_commands.Choice(name="24時間", value="24h"),
    app_commands.Choice(name="1週間", value="1w"),
    app_commands.Choice(name="1ヶ月", value="1m"),
]


@bot.tree.command(name="通貨娯楽部お支払い", description="娯楽部の支払いを自動化します")
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


# --- 管理者: lactip贈与 ---


@app_commands.default_permissions(administrator=True)
@bot.tree.command(name="lact贈与",
                  description="Dealerからユーザーにlacttipを贈与します（管理者限定）")
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

    save_money()  # 非同期なら await を忘れずに

    await interaction.followup.send(
        f"{target.mention} に {amount} lacttip を贈与しました。\n"
        f"Dealerの残高: {money[dealer_id]} lacttip")


# --- 管理者: lactip徴収 ---
@app_commands.default_permissions(administrator=True)
@bot.tree.command(name="lact徴収",
                  description="ユーザーからDealerにlactipを徴収します（管理者限定）")
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
    save_money()

    dealer_balance_after = money[dealer_id]
    await interaction.followup.send(
        f"{対象.mention} から {actual_deduction} lactipを徴収しました。\n"
        f"Dealerの残高: {dealer_balance_after} lacttip")


# --- 管理者: Dealerの所持金を設定 ---
@app_commands.default_permissions(administrator=True)
@bot.tree.command(name="lact設定", description="Dealerの所持金を設定します（管理者限定）")
@app_commands.describe(金額="設定したいlacttip（整数）")
async def set_bot_money(interaction: discord.Interaction, 金額: int):
    if 金額 < 0:
        await interaction.response.send_message("tipは0以上を指定してください。",
                                                ephemeral=True)
        return

    money[bot.user.id] = 金額
    save_money()
    await interaction.response.send_message(
        f"Dealerの所持金を {金額} lacttip に設定しました。", ephemeral=True)


# --- 管理者: 手動で保存 ---
@app_commands.default_permissions(administrator=True)
@bot.tree.command(name="lact保存", description="現在の通貨データを手動で保存します（管理者限定）")
async def save_data(interaction: discord.Interaction):
    save_money()
    await interaction.response.send_message("通貨データを保存しました！", ephemeral=True)


# --- 月初め給料支払い ---
@tasks.loop(hours=24)
async def 月初め給料支払い():
    await bot.wait_until_ready()
    today = datetime.now()

    if today.day != 1:
        return

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
            money[member.id] = money.get(member.id, 0) + total_amount
            # save_money() ← 削除！

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

    # ✅ ループの外で一括保存
    save_money()

    if channel:
        await channel.send(f"今月の給料支払いが完了しました。\n"
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
    money[member.id] = money.get(member.id, 0) + 初期tip
    save_money()

    welcome_channel_id = 1376444952233377872
    channel = bot.get_channel(welcome_channel_id)
    if channel:
        await channel.send(f"{member.mention} が参加。初期tip {初期tip} lacttip を付与。")


# --- 管理者: Dealerの所持金を確認 ---
@app_commands.default_permissions(administrator=True)
@bot.tree.command(name="lact残高", description="Dealerの所持金を確認します（管理者限定）")
async def check_dealer_balance(interaction: discord.Interaction):
    dealer_id = bot.user.id
    amount = money.get(dealer_id, 0)
    await interaction.response.send_message(f"Dealer残高は {amount} lacttip です。",
                                            ephemeral=True)


# --- 管理者: Dealerの残高を増やす ---
@app_commands.default_permissions(administrator=True)
@bot.tree.command(name="lact増加", description="Dealerの残高を増やします（管理者限定）")
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
    save_money()

    await interaction.followup.send(
        f"Dealerの残高を {金額} lacttip 増加しました。\n"
        f"旧残高: {old_balance} → 新残高: {new_balance} lacttip",
        ephemeral=True)


import os
import shutil
from datetime import datetime, timedelta
from discord.ext import tasks

# バックアップ先フォルダ（なければ作る）
BACKUP_FOLDER = "./backup_money"
os.makedirs(BACKUP_FOLDER, exist_ok=True)


@tasks.loop(hours=24)
async def 自動バックアップ():
    try:
        # money.jsonのバックアップファイル名（日時付き）
        now_str = datetime.now().strftime("%Y%m%d")
        backup_filename = f"money_backup_{now_str}.json"
        backup_path = os.path.join(BACKUP_FOLDER, backup_filename)

        # money.jsonをバックアップフォルダにコピー
        shutil.copy("money.json", backup_path)
        print(f"✅ money.jsonをバックアップしました: {backup_path}")

        # 7日より古いバックアップを削除
        threshold = datetime.now() - timedelta(days=7)
        for fname in os.listdir(BACKUP_FOLDER):
            if fname.startswith("money_backup_") and fname.endswith(".json"):
                fpath = os.path.join(BACKUP_FOLDER, fname)
                file_time = datetime.fromtimestamp(os.path.getmtime(fpath))
                if file_time < threshold:
                    os.remove(fpath)
                    print(f"🗑 古いバックアップを削除しました: {fname}")

    except Exception as e:
        print(f"❌ 自動バックアップでエラー発生: {e}")


@bot.event
async def on_ready():
    load_money()
    await bot.change_presence(activity=discord.Game(name="通貨bot起動中"))

    # スラッシュコマンド同期
    try:
        synced = await bot.tree.sync()
        print(f"✅ スラッシュコマンド {len(synced)} 件同期しました")
    except Exception as e:
        print(f"同期エラー: {e}")

    print(f"✅ Botログイン: {bot.user}")

    # 月初め給料支払いのループ開始（重複防止チェック付き）
    if not 月初め給料支払い.is_running():
        月初め給料支払い.start()

    # 自動バックアップのループ開始（重複防止チェック付き）
    if not 自動バックアップ.is_running():
        自動バックアップ.start()

    print("月初め給料支払い & 自動バックアップ 起動完了")


# --- Botトークンで起動 ---
import os
import discord
from discord.ext import commands

import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

if __name__== "__main__":
    keep_alive()

bot.run(os.getenv("DISCORD_TOKEN"))  # ← このままでOK（Renderで環境変数DISCORD_TOKENを登録するので）
