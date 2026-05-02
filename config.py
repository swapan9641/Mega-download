import os
import logging

# ==========================================
# ADVANCED LOGGING CONFIGURATION
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("MegaBot")
logging.getLogger("pyrogram").setLevel(logging.WARNING)

# ==========================================
# ENVIRONMENT VARIABLES
# ==========================================
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
MONGO_URI = os.environ.get("MONGO_URI", "")
DUMP_CHANNEL = int(os.environ.get("DUMP_CHANNEL", "0"))
ADMINS = [int(x) for x in os.environ.get("ADMINS", "").split()]
CREDIT_TEXT = os.environ.get("CREDIT_TEXT", "\n\n**✨ Downloaded by @YourBot**")

MEGA_EMAIL = os.environ.get("MEGA_EMAIL", "")
MEGA_PASSWORD = os.environ.get("MEGA_PASSWORD", "")

DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "downloads")
PORT = int(os.environ.get("PORT", "8080"))
MEGARC_PATH = os.path.abspath(".megarc")

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# ==========================================
# SECURE MEGA AUTHENTICATION GENERATOR
# ==========================================
def setup_megarc():
    """Generates the .megarc file and applies strict Linux read/write permissions."""
    try:
        with open(MEGARC_PATH, "w") as f:
            if MEGA_EMAIL and MEGA_PASSWORD:
                f.write(f"[Login]\nUsername = {MEGA_EMAIL}\nPassword = {MEGA_PASSWORD}\n")
            else:
                f.write("[Login]\n# No credentials provided. Folder extraction will fail.\n")
                logger.warning("MEGA_EMAIL or MEGA_PASSWORD missing. Public folders cannot be read.")
        
        # Apply 0600 permissions (Read/Write for owner only) for security
        if os.name == 'posix':
            os.chmod(MEGARC_PATH, 0o600)
    except Exception as e:
        logger.error(f"Failed to secure .megarc file: {e}")

setup_megarc()
