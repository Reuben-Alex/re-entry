"""
Central place every other module reads settings from. Nothing to build
here — just fill in .env (copied from .env.example) and this loads it.
"""
import os
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

NEBIUS_API_KEY = os.environ.get("NEBIUS_API_KEY", "")
NEBIUS_BASE_URL = os.environ.get(
    "NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1"
)

MODEL_NANO = os.environ.get(
    "MODEL_NANO", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
)
MODEL_SUPER = os.environ.get(
    "MODEL_SUPER", "nvidia/nemotron-3-super-120b-a12b"
)
MODEL_ULTRA = os.environ.get(
    "MODEL_ULTRA", "nvidia/Nemotron-3-Ultra-550b-a55b"
)

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
DEMO_SKIP_TAVILY = os.environ.get("DEMO_SKIP_TAVILY", "").lower() == "true"

CONTREE_API_TOKEN = os.environ.get(
    "CONTREE_API_TOKEN", os.environ.get("CONTREE_TOKEN", "")
)
CONTREE_PROJECT_ID = os.environ.get(
    "CONTREE_PROJECT_ID",
    os.environ.get("NEBIUS_PROJECT_ID", os.environ.get("NEBIUS_AI_PROJECT", "")),
)

LOCAL_RPC_URL = os.environ.get("LOCAL_RPC_URL", "http://127.0.0.1:8545")
SANDBOX_MODE = os.environ.get("SANDBOX_MODE", "local")

MAX_RETRY_ATTEMPTS = int(os.environ.get("MAX_RETRY_ATTEMPTS", "3"))
MAX_COMPILE_RETRIES = int(os.environ.get("MAX_COMPILE_RETRIES", "3"))
LLM_TIMEOUT_SECONDS = int(os.environ.get("LLM_TIMEOUT_SECONDS", "180"))
ENABLE_PATCH_VERIFY = os.environ.get("ENABLE_PATCH_VERIFY", "true").lower() == "true"
INCLUDE_BLIND = os.environ.get("INCLUDE_BLIND", "").lower() == "true"

RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")
