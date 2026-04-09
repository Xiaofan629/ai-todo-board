import os
from dotenv import load_dotenv

load_dotenv()

# Bot 类型 (wecom / feishu)
BOT_TYPE = os.getenv("BOT_TYPE", "wecom")

# 企业微信 Bot
WECOM_BOT_ID = os.getenv("WECOM_BOT_ID", "")
WECOM_BOT_SECRET = os.getenv("WECOM_BOT_SECRET", "")

# 飞书 Bot
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")

# 服务配置
SERVER_PORT = int(os.getenv("SERVER_PORT", "9526"))
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")

# 数据库
DB_PATH = os.getenv("DB_PATH", "./data/todos.db")

# 个性化配置
OWNER_NAME = os.getenv("OWNER_NAME", "孙小凡")
SPECIAL_USERID = os.getenv("SPECIAL_USERID", "sunxiaofan")
PROJECT_BASE_DIR = os.getenv("PROJECT_BASE_DIR", "/home/sunxiaofan/zhihu")
ROOT_PATH = os.getenv("ROOT_PATH", "")

# LangChain / LLM
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://open.bigmodel.cn/api/anthropic")
LLM_MODEL = os.getenv("LLM_MODEL", "glm-5.1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")

# MCP 配置
MCP_CONFIG_PATH = os.getenv("MCP_CONFIG_PATH", "./mcp_config.json")
