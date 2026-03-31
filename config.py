import os
from dotenv import load_dotenv

load_dotenv()

WECOM_BOT_ID = os.getenv("WECOM_BOT_ID", "")
WECOM_BOT_SECRET = os.getenv("WECOM_BOT_SECRET", "")
AGENT_API_URL = os.getenv("AGENT_API_URL", "http://localhost:9527")
SERVER_PORT = int(os.getenv("SERVER_PORT", "9526"))
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
DB_PATH = os.getenv("DB_PATH", "./data/todos.db")
CLAUDE_BIN = os.getenv("CLAUDE_BIN", "claude")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "")
PROJECT_BASE_DIR = os.getenv("PROJECT_BASE_DIR", "/home/sunxiaofan/zhihu")
OWNER_NAME = os.getenv("OWNER_NAME", "孙小凡")
SPECIAL_USERID = os.getenv("SPECIAL_USERID", "sunxiaofan")
ROOT_PATH = os.getenv("ROOT_PATH", "")
