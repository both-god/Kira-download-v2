import os
from dotenv import load_dotenv

load_dotenv()


def _int(v, d=0):
    try:
        return int(str(v).strip())
    except Exception:
        return d


BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = _int(os.getenv("OWNER_ID"), 8744596998)
API_ID = _int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH", "")
SESSION_STRING = os.getenv("SESSION_STRING", "")
BIG_GROUP_ID = _int(os.getenv("BIG_GROUP_ID"))
NUB_API_BASE = os.getenv("NUB_API_BASE", "https://api.nubcoders.com")
NUB_API_TOKEN = os.getenv("NUB_API_TOKEN", "")
NUB_INFO_PATH = os.getenv("NUB_INFO_PATH", "/info")
NUB_STREAM_PATH = os.getenv("NUB_STREAM_PATH", "/stream")
NUB_SEARCH_PATH = os.getenv("NUB_SEARCH_PATH", "/search")
NUB_API_URL_PARAM = os.getenv("NUB_API_URL_PARAM", "q")
COOKIES_FILE = os.getenv("COOKIES_FILE", "")
MAX_PARALLEL = _int(os.getenv("MAX_PARALLEL"), 3)

DB_PATH = os.getenv("DB_PATH", "data.db")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "downloads")
BOT_UPLOAD_LIMIT = 48 * 1024 * 1024        # Bot API ផ្ញើបានត្រឹម ~50MB
MAX_FILE = 2000 * 1024 * 1024              # 2GB
KEY_PREFIX = "KIRA"
