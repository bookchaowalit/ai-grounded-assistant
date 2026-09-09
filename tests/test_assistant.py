from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from book_grounded_ai.api import ApiService, create_server
from book_grounded_ai.assistant import GroundedAssistant
from book_grounded_ai.evaluation import run_evaluation
from book_grounded_ai.schema import DataContractError
from book_grounded_ai.store import load_corpus
from book_grounded_ai.telemetry import SafeTelemetrySink


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class CorpusContractTests(unittest.TestCase):
    def test_corpus_is_versioned_and_lineage_verified(self) -> None:
        corpus = load_corpus(REPOSITORY_ROOT)
        self.assertEqual(corpus.schema_version, "knowledge.v1")
        self.assertEqual(corpus.dataset, "approved_knowledge")
        self.assertEqual(len(corpus.records), 3)
        self.assertEqual(corpus.lineage.privacy_class, "public-demo")
        self.assertEqual(corpus.lineage.record_count, 3)

    def test_tampered_manifest_fails_closed(self) -> None:
        manifest_path = REPOSITORY_ROOT / "data" / "manifests" / "knowledge_chunks.v1.manifest.json"
        original = manifest_path.read_text(encoding="utf-8")
        try:
            manifest_path.write_text(original.replace('"record_count": 3', '"record_count": 4'), encoding="utf-8")
            with self.assertRaisesRegex(DataContractError, "record_count"):
                load_corpus(REPOSITORY_ROOT)
        finally:
            manifest_path.write_text(original, encoding="utf-8")


class AssistantContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.telemetry = SafeTelemetrySink()
        self.assistant = GroundedAssistant(load_corpus(REPOSITORY_ROOT), telemetry=self.telemetry)

    def test_known_question_is_grounded_and_cited(self) -> None:
        response = self.assistant.answer("Where should approved source evidence live?")
        self.assertFalse(response["fallback"])
        self.assertEqual(response["data_status"], "grounded")
        self.assertEqual(response["grounding"]["source_ids"], ["knowledge-001"])
        self.assertEqual(response["grounding"]["citations"][0]["id"], "knowledge-001")
        self.assertIn("durable landing and Bronze objects", response["answer"])

    def test_unknown_question_returns_safe_fallback(self) -> None:
        response = self.assistant.answer("What is the current weather in Bangkok?")
        self.assertTrue(response["fallback"])
        self.assertEqual(response["data_status"], "insufficient-context")
        self.assertEqual(response["grounding"]["source_ids"], [])
        self.assertIn("not have enough approved context", response["answer"])

    def test_redaction_is_applied_and_telemetry_contains_no_raw_text(self) -> None:
        question = "Where should source evidence live? email alice@example.com token=secret-value"
        response = self.assistant.answer(question)
        self.assertFalse(response["fallback"])
        self.assertTrue(response["redaction"]["applied"])
        self.assertEqual(response["redaction"]["categories"], ["api-key", "email"])
        event = self.telemetry.events[-1].as_dict()
        serialized = json.dumps(event, sort_keys=True)
        self.assertNotIn(question, serialized)
        self.assertNotIn("alice@example.com", serialized)
        self.assertNotIn("secret-value", serialized)
        self.assertNotIn("answer", event)
        self.assertNotIn("question", event)

    def test_input_budget_is_enforced(self) -> None:
        with self.assertRaisesRegex(DataContractError, "context budget"):
            self.assistant.answer("x" * 501)

    def test_offline_evaluation_reaches_full_threshold(self) -> None:
        result = run_evaluation(self.assistant, REPOSITORY_ROOT)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["passed"], 3)
        self.assertEqual(result["failed"], 0)


class HttpBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.token = "generated-in-memory-http-token"
        self.service = ApiService(load_corpus(REPOSITORY_ROOT), read_token=self.token, rate_limit=20)

    def test_auth_and_safe_ask_contract(self) -> None:
        unauthenticated = self.service.handle(
            "POST",
            "/v1/ask",
            {"Content-Type": "application/json"},
            json.dumps({"question": "Where should source evidence live?"}),
        )
        authenticated = self.service.handle(
            "POST",
            "/v1/ask",
            {"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"},
            json.dumps({"question": "Where should source evidence live?"}),
        )
        self.assertEqual(unauthenticated.status, 401)
        self.assertEqual(authenticated.status, 200)
        self.assertNotIn("question", authenticated.payload)
        self.assertFalse(authenticated.payload["telemetry"]["raw_payload_persisted"])

    def test_invalid_body_and_mutation_are_bounded(self) -> None:
        invalid = self.service.handle(
            "POST",
            "/v1/ask",
            {"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"},
            json.dumps({"prompt": "not the contract"}),
        )
        mutation = self.service.handle(
            "PUT",
            "/v1/ask",
            {"Authorization": f"Bearer {self.token}"},
        )
        self.assertEqual(invalid.status, 400)
        self.assertEqual(invalid.payload["error"]["code"], "INPUT009")
        self.assertEqual(mutation.status, 405)
        self.assertEqual(mutation.headers["Allow"], "POST")

    def test_rate_limit_returns_retry_hint(self) -> None:
        service = ApiService(load_corpus(REPOSITORY_ROOT), rate_limit=1)
        self.assertEqual(service.handle("GET", "/healthz", client_id="rate-test").status, 200)
        response = service.handle("GET", "/healthz", client_id="rate-test")
        self.assertEqual(response.status, 429)
        self.assertIn("Retry-After", response.headers)

    def test_http_server_exposes_grounded_answer(self) -> None:
        server = create_server(self.service, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/v1/ask"
            request = Request(
                url,
                data=json.dumps({"question": "How should a reference app handle provider changes?"}).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urlopen(request, timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, 200)
            self.assertEqual(payload["grounding"]["source_ids"], ["knowledge-002"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_http_unauthorized_response_is_structured(self) -> None:
        server = create_server(self.service, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = Request(
                f"http://127.0.0.1:{server.server_address[1]}/v1/metadata",
                method="GET",
            )
            with self.assertRaises(HTTPError) as context:
                try:
                    urlopen(request, timeout=3)
                except HTTPError as error:
                    error.close()
                    raise
            self.assertEqual(context.exception.code, 401)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


class CliTests(unittest.TestCase):
    def test_validate_and_evaluate_commands(self) -> None:
        env = dict(os.environ, PYTHONPATH=str(REPOSITORY_ROOT / "src"))
        for command in (("validate",), ("evaluate",)):
            result = subprocess.run(
                [sys.executable, "-m", "book_grounded_ai.cli", *command],
                cwd=REPOSITORY_ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(result.stdout)
            self.assertIn(payload["status"], {"ok", "pass"})


if __name__ == "__main__":
    unittest.main()
