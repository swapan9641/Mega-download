import os

API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
MONGO_URI = os.environ.get("MONGO_URI", "")
DUMP_CHANNEL = int(os.environ.get("DUMP_CHANNEL", "0"))
ADMINS = [int(x) for x in os.environ.get("ADMINS", "").split()]
CREDIT_TEXT = os.environ.get("BOT_ZONE", "\n\n**Downloaded by @mega_nzleech_bot")
DOWNLOAD_DIR = "downloads"
PORT = int(os.environ.get("PORT", "8080")) # Added Port Variable

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)
