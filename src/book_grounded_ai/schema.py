"""Versioned corpus, answer, and error contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .config import CORPUS_NAME, CORPUS_SCHEMA_VERSION, MAX_QUESTION_CHARS


class DataContractError(ValueError):
    """Raised when input or a governed local artifact violates its contract."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def error_payload(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def _object(value: Any, *, code: str, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DataContractError(code, message)
    return value


def _non_empty_string(value: Any, *, field: str, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DataContractError(code, f"{field} must be a non-empty string", {"field": field})
    return value


def _timestamp(value: Any, *, field: str, code: str) -> str:
    result = _non_empty_string(value, field=field, code=code)
    try:
        parsed = datetime.fromisoformat(result.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DataContractError(code, f"{field} must be ISO-8601", {"field": field}) from exc
    if parsed.tzinfo is None:
        raise DataContractError(code, f"{field} must include a timezone", {"field": field})
    return result


def validate_knowledge_record(value: Any, *, index: int) -> dict[str, str]:
    record = _object(value, code="SCHEMA001", message=f"knowledge record {index} must be an object")
    required = {"id", "title", "text", "source_url", "classification", "updated_at"}
    if set(record) != required:
        raise DataContractError(
            "SCHEMA002",
            f"knowledge record {index} fields do not match knowledge.v1",
            {"index": index, "expected_fields": sorted(required), "actual_fields": sorted(record)},
        )
    text = _non_empty_string(record["text"], field="text", code="SCHEMA003")
    if len(text) > 4_000:
        raise DataContractError("SCHEMA004", "knowledge text exceeds the local context bound", {"index": index})
    source_url = _non_empty_string(record["source_url"], field="source_url", code="SCHEMA003")
    if not source_url.startswith("https://example.invalid/"):
        raise DataContractError("SCHEMA005", "fixture source_url must use the sanitized example domain", {"index": index})
    classification = _non_empty_string(record["classification"], field="classification", code="SCHEMA003")
    if classification != "public-demo":
        raise DataContractError("SCHEMA006", "local corpus classification must be public-demo", {"index": index})
    return {
        "id": _non_empty_string(record["id"], field="id", code="SCHEMA003"),
        "title": _non_empty_string(record["title"], field="title", code="SCHEMA003"),
        "text": text,
        "source_url": source_url,
        "classification": classification,
        "updated_at": _timestamp(record["updated_at"], field="updated_at", code="SCHEMA007"),
    }


def validate_knowledge_records(value: Any, *, field: str = "records") -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise DataContractError("SCHEMA008", f"{field} must be an array", {"field": field})
    records = [validate_knowledge_record(item, index=index) for index, item in enumerate(value)]
    ids = [record["id"] for record in records]
    if len(ids) != len(set(ids)):
        raise DataContractError("SCHEMA009", f"{field} contains duplicate ids", {"field": field})
    return records


def validate_bronze_document(value: Any) -> tuple[str, str, list[dict[str, str]]]:
    document = _object(value, code="SCHEMA010", message="Bronze knowledge document must be an object")
    if document.get("schema_version") != CORPUS_SCHEMA_VERSION:
        raise DataContractError(
            "SCHEMA011",
            "Bronze schema_version is unsupported",
            {"expected": CORPUS_SCHEMA_VERSION, "actual": document.get("schema_version")},
        )
    if document.get("dataset") != CORPUS_NAME:
        raise DataContractError(
            "SCHEMA012",
            "Bronze dataset is unsupported",
            {"expected": CORPUS_NAME, "actual": document.get("dataset")},
        )
    return CORPUS_SCHEMA_VERSION, CORPUS_NAME, validate_knowledge_records(document.get("records"))


def validate_manifest(value: Any) -> dict[str, Any]:
    manifest = _object(value, code="LINEAGE010", message="knowledge manifest must be an object")
    required = {
        "manifest_version",
        "source",
        "dataset",
        "schema_version",
        "privacy_class",
        "retention_class",
        "source_object",
        "bronze_object",
        "source_sha256",
        "bronze_sha256",
        "record_count",
    }
    if set(manifest) != required:
        raise DataContractError(
            "LINEAGE011",
            "manifest fields do not match the lineage contract",
            {"expected_fields": sorted(required), "actual_fields": sorted(manifest)},
        )
    for field in (
        "manifest_version",
        "source",
        "dataset",
        "schema_version",
        "privacy_class",
        "retention_class",
        "source_object",
        "bronze_object",
    ):
        _non_empty_string(manifest[field], field=field, code="LINEAGE012")
    if manifest["dataset"] != CORPUS_NAME or manifest["schema_version"] != CORPUS_SCHEMA_VERSION:
        raise DataContractError("LINEAGE013", "manifest dataset/schema is unsupported")
    if manifest["privacy_class"] != "public-demo":
        raise DataContractError("LINEAGE014", "manifest privacy_class is unsupported")
    for field in ("source_sha256", "bronze_sha256"):
        digest = _non_empty_string(manifest[field], field=field, code="LINEAGE015")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise DataContractError("LINEAGE016", f"{field} must be a lowercase SHA-256 digest", {"field": field})
    if not isinstance(manifest["record_count"], int) or isinstance(manifest["record_count"], bool) or manifest["record_count"] < 0:
        raise DataContractError("LINEAGE017", "record_count must be a non-negative integer")
    return manifest


def validate_question(value: Any) -> str:
    if not isinstance(value, str):
        raise DataContractError("INPUT001", "question must be a string")
    question = value.strip()
    if not question:
        raise DataContractError("INPUT002", "question must not be empty")
    if len(question) > MAX_QUESTION_CHARS:
        raise DataContractError(
            "INPUT003",
            "question exceeds the context budget",
            {"max_chars": MAX_QUESTION_CHARS},
        )
    if "\x00" in question:
        raise DataContractError("INPUT004", "question contains an unsupported control character")
    return question

