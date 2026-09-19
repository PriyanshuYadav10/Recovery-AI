import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
DB_PATH = ROOT / "data" / "recovery_ai.db"
RECORDINGS_DIR = DATA_DIR / "recordings"
BASELINE_PATH = CONFIG_DIR / "manual_baseline.json"

# Ordered by measured round-trip on this account (see README): on a phone call
# latency is the product, so the fastest usable model leads. The Llama ids that
# used to sit here were decommissioned by Groq and now 404.
#   qwen/qwen3.8-27b     ~145ms
#   openai/gpt-oss-20b   ~590ms
#   openai/gpt-oss-120b  ~807ms
GROQ_DEFAULT_MODEL = "qwen/qwen3.8-27b"
GROQ_FALLBACK_MODELS = [
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
]

SPEECH_CONFIDENCE_THRESHOLD = 0.72
INTENT_CONFIDENCE_THRESHOLD = 0.65
FIELD_CONFIDENCE_THRESHOLD = 0.75
MAX_FIELD_RETRIES = 2
ESCALATION_THRESHOLD = 60


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


# Journey completion sandbox. Points at the built-in mock until CIMET supply theirs;
# swap JOURNEY_SUBMIT_URL in .env to post at the real endpoint with no code change.
JOURNEY_SUBMIT_URL = _env(
    "JOURNEY_SUBMIT_URL", "http://127.0.0.1:8000/api/sandbox/journey/submit"
)
JOURNEY_SUBMIT_TIMEOUT = float(_env("JOURNEY_SUBMIT_TIMEOUT", "8"))
JOURNEY_SUBMIT_RETRIES = int(_env("JOURNEY_SUBMIT_RETRIES", "2"))
JOURNEY_SUBMIT_TOKEN = _env("JOURNEY_SUBMIT_TOKEN", "")

# Node telephony bridge (Twilio media streams). See telephony/bridge.
BRIDGE_BASE_URL = _env("BRIDGE_BASE_URL", "http://127.0.0.1:3100")
HUMAN_QUEUE_NUMBER = _env("HUMAN_QUEUE_NUMBER", "")
