"""Configuration constants for the local grounded assistant."""

from pathlib import Path

APP_NAME = "book-grounded-ai-assistant"
API_VERSION = "v1"
ANSWER_SCHEMA_VERSION = "answer.v1"
CORPUS_SCHEMA_VERSION = "knowledge.v1"
CORPUS_NAME = "approved_knowledge"
MODEL_ADAPTER = "deterministic-extractive-v1"
TOKEN_ENV = "BOOK_GROUNDED_AI_TOKEN"
DEFAULT_HOST = "127.0.0.1"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
DEFAULT_PORT = 8090
MAX_QUESTION_CHARS = 500
MAX_BODY_BYTES = 8 * 1024
MAX_ANSWER_CHARS = 2_000
RETRIEVAL_TOP_K = 1
RETRIEVAL_MIN_SCORE = 2
LATENCY_TARGET_MS = 100
EVALUATION_VERSION = "golden_questions.v1"

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PACKAGE_ROOT.parent
MANIFEST_PATH = REPOSITORY_ROOT / "data" / "manifests" / "knowledge_chunks.v1.manifest.json"
EVALUATION_PATH = REPOSITORY_ROOT / "data" / "evaluation" / "golden_questions.v1.json"
