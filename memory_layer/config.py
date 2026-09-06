import logging
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# ─── Config & Directory Resolution ─────────────────────────────
AGENT_DIR = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(AGENT_DIR / ".env")
except ImportError:
    pass

# ─── Model & Compute Routing Configuration ─────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
OLLAMA_API_BASE = os.getenv("OLLAMA_API_BASE", "http://127.0.0.1:11434").strip()
if OLLAMA_API_BASE:
    os.environ["OLLAMA_API_BASE"] = OLLAMA_API_BASE

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "hybrid").lower()
LOCAL_DEFAULT = "litellm:ollama/qwen2.5:7b"
CLOUD_DEFAULT = "gemini-2.5-flash-lite"

LOCAL_MODEL = os.getenv("LOCAL_MODEL") or os.getenv("OLLAMA_MODEL") or LOCAL_DEFAULT
CLOUD_MODEL = os.getenv("CLOUD_MODEL") or os.getenv("GEMINI_MODEL") or CLOUD_DEFAULT

if LLM_PROVIDER == "hybrid":
    INGEST_MODEL = os.getenv("INGEST_MODEL", LOCAL_MODEL)
    CONSOLIDATE_MODEL = os.getenv("CONSOLIDATE_MODEL", LOCAL_MODEL)
    if GEMINI_API_KEY:
        QUERY_MODEL = os.getenv("QUERY_MODEL", CLOUD_MODEL)
    else:
        QUERY_MODEL = LOCAL_MODEL
elif LLM_PROVIDER == "gemini":
    INGEST_MODEL = os.getenv("INGEST_MODEL", CLOUD_MODEL)
    CONSOLIDATE_MODEL = os.getenv("CONSOLIDATE_MODEL", CLOUD_MODEL)
    QUERY_MODEL = os.getenv("QUERY_MODEL", CLOUD_MODEL)
else:  # ollama
    INGEST_MODEL = os.getenv("INGEST_MODEL", LOCAL_MODEL)
    CONSOLIDATE_MODEL = os.getenv("CONSOLIDATE_MODEL", LOCAL_MODEL)
    QUERY_MODEL = os.getenv("QUERY_MODEL", LOCAL_MODEL)

MODEL = QUERY_MODEL
DB_PATH = os.getenv("MEMORY_DB", str(AGENT_DIR / "memory.db"))
if not os.path.isabs(DB_PATH):
    DB_PATH = str(AGENT_DIR / DB_PATH)

# Supported file types for multimodal ingestion
TEXT_EXTENSIONS = {".txt", ".md", ".json", ".csv", ".log", ".xml", ".yaml", ".yml"}
MEDIA_EXTENSIONS = {
    # Images
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
    # Audio
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    # Video
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
    # Documents
    ".pdf": "application/pdf",
}
ALL_SUPPORTED = TEXT_EXTENSIONS | set(MEDIA_EXTENSIONS.keys())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="[%H:%M]",
    stream=sys.stdout,
)
log = logging.getLogger("memory-agent")
