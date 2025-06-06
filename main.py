
from bot import bot  # bot.pyからbotインスタンスを読み込む

# botの起動（トークンは環境変数から）
import os
bot.run(os.getenv("DISCORD_TOKEN"))

