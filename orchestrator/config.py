"""
Central place every other module reads settings from. Nothing to build
here — just fill in .env (copied from .env.example) and this loads it.
"""
import os
from dotenv import load_dotenv

load_dotenv()

NEBIUS_API_KEY = os.environ.get("NEBIUS_API_KEY", "")
NEBIUS_BASE_URL = os.environ.get(
    "NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1"
)

MODEL_NANO = os.environ.get("MODEL_NANO", "")
MODEL_SUPER = os.environ.get("MODEL_SUPER", "")
MODEL_ULTRA = os.environ.get("MODEL_ULTRA", "")

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")

CONTREE_API_TOKEN = os.environ.get("CONTREE_API_TOKEN", "")
CONTREE_PROJECT_ID = os.environ.get("CONTREE_PROJECT_ID", "")

LOCAL_RPC_URL = os.environ.get("LOCAL_RPC_URL", "http://127.0.0.1:8545")
SANDBOX_MODE = os.environ.get("SANDBOX_MODE", "local")

MAX_RETRY_ATTEMPTS = int(os.environ.get("MAX_RETRY_ATTEMPTS", "3"))
MAX_COMPILE_RETRIES = int(os.environ.get("MAX_COMPILE_RETRIES", "3"))
LLM_TIMEOUT_SECONDS = int(os.environ.get("LLM_TIMEOUT_SECONDS", "60"))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")
