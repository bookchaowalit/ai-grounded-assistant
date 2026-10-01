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

from book_grounded_ai.api import ApiService, _RateLimiter, create_server
from book_grounded_ai.assistant import GroundedAssistant
from book_grounded_ai.evaluation import evaluate_gates, outcome_metrics, run_evaluation
from book_grounded_ai.schema import DataContractError
from book_grounded_ai.store import load_corpus
from book_grounded_ai.telemetry import SafeTelemetrySink


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class CorpusContractTests(unittest.TestCase):
    def test_corpus_is_versioned_and_lineage_verified(self) -> None:
        corpus = load_corpus(REPOSITORY_ROOT)
        self.assertEqual(corpus.schema_version, "knowledge.v1")
        self.assertEqual(corpus.dataset, "approved_knowledge")
        self.assertEqual(len(corpus.records), 5)
        self.assertEqual(corpus.lineage.privacy_class, "public-demo")
        self.assertEqual(corpus.lineage.record_count, 5)

    def test_tampered_manifest_fails_closed(self) -> None:
        manifest_path = REPOSITORY_ROOT / "data" / "manifests" / "knowledge_chunks.v1.manifest.json"
        original = manifest_path.read_text(encoding="utf-8")
        try:
            manifest_path.write_text(original.replace('"record_count": 5', '"record_count": 6'), encoding="utf-8")
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
        self.assertEqual(result["passed"], 17)
        self.assertEqual(result["failed"], 0)
        for outcome in ("grounded", "fallback", "refused"):
            with self.subTest(outcome=outcome):
                self.assertGreaterEqual(result["per_outcome"][outcome]["expected"], 2)
                self.assertEqual(result["per_outcome"][outcome]["precision"], 1.0)
                self.assertEqual(result["per_outcome"][outcome]["recall"], 1.0)

    def test_safety_gates_hold_even_when_pass_rate_is_relaxed(self) -> None:
        full = run_evaluation(self.assistant, REPOSITORY_ROOT)
        self.assertEqual([g["passed"] for g in full["gates"]], [True, True])

        class NeverRefuses:
            """Answers injections instead of refusing (a regressed guardrail)."""

            def __init__(self, inner: GroundedAssistant) -> None:
                self.inner = inner

            def metadata(self) -> dict:
                return self.inner.metadata()

            def answer(self, question: str) -> dict:
                response = self.inner.answer(question)
                if response["data_status"] == "refused":
                    return {**response, "data_status": "ok", "fallback": True,
                            "grounding": {**response["grounding"], "source_ids": []}}
                return response

        relaxed = run_evaluation(NeverRefuses(self.assistant), REPOSITORY_ROOT, required_pass_rate=0.5)
        self.assertGreaterEqual(relaxed["pass_rate"], 0.5)
        self.assertEqual(relaxed["status"], "fail")
        failed = [g for g in relaxed["gates"] if not g["passed"]]
        self.assertEqual([(g["outcome"], g["metric"], g["actual"]) for g in failed], [("refused", "recall", 0.0)])
        with self.assertRaises(ValueError):
            run_evaluation(self.assistant, REPOSITORY_ROOT, required_pass_rate=1.5)

    def test_gates_fail_when_vacuous_or_below_floor(self) -> None:
        empty = outcome_metrics([{"expected_outcome": "fallback", "actual_outcome": "fallback"}])
        self.assertEqual([g["passed"] for g in evaluate_gates(empty)], [False, False])
        overclaims = outcome_metrics(
            [
                {"expected_outcome": "refused", "actual_outcome": "refused"},
                {"expected_outcome": "grounded", "actual_outcome": "grounded"},
                {"expected_outcome": "fallback", "actual_outcome": "grounded"},
            ]
        )
        checks = evaluate_gates(overclaims)
        self.assertEqual(checks[0]["passed"], True)
        self.assertEqual((checks[1]["metric"], checks[1]["actual"], checks[1]["passed"]), ("precision", 0.5, False))

    def test_outcome_metrics_report_precision_and_recall(self) -> None:
        results = [
            {"expected_outcome": "grounded", "actual_outcome": "grounded"},
            {"expected_outcome": "grounded", "actual_outcome": "fallback"},
            {"expected_outcome": "fallback", "actual_outcome": "fallback"},
        ]
        metrics = outcome_metrics(results)
        self.assertEqual(metrics["grounded"]["precision"], 1.0)
        self.assertEqual(metrics["grounded"]["recall"], 0.5)
        self.assertEqual(metrics["fallback"]["precision"], 0.5)
        self.assertEqual(metrics["fallback"]["recall"], 1.0)
        self.assertIsNone(metrics["refused"]["precision"])
        self.assertIsNone(metrics["refused"]["recall"])


class RateLimiterTests(unittest.TestCase):
    def test_idle_clients_are_evicted(self) -> None:
        now = [0.0]
        limiter = _RateLimiter(2, window_seconds=10.0, clock=lambda: now[0])
        for index in range(50):
            self.assertEqual(limiter.allow(f"client-{index}"), (True, 0))
        self.assertEqual(limiter.tracked_clients(), 50)
        now[0] = 11.0
        self.assertEqual(limiter.allow("fresh"), (True, 0))
        self.assertEqual(limiter.tracked_clients(), 1)

    def test_limit_still_applies_within_window(self) -> None:
        now = [0.0]
        limiter = _RateLimiter(2, window_seconds=10.0, clock=lambda: now[0])
        self.assertTrue(limiter.allow("a")[0])
        self.assertTrue(limiter.allow("a")[0])
        allowed, retry_after = limiter.allow("a")
        self.assertFalse(allowed)
        self.assertGreaterEqual(retry_after, 1)
        now[0] = 10.5
        self.assertTrue(limiter.allow("a")[0])

    def test_client_table_is_capped(self) -> None:
        now = [0.0]
        limiter = _RateLimiter(5, window_seconds=10.0, max_clients=3, clock=lambda: now[0])
        for name in ("a", "b", "c"):
            self.assertTrue(limiter.allow(name)[0])
        self.assertFalse(limiter.allow("d")[0])
        self.assertTrue(limiter.allow("a")[0])
        self.assertLessEqual(limiter.tracked_clients(), 3)
        now[0] = 10.5
        self.assertTrue(limiter.allow("d")[0])
        self.assertLessEqual(limiter.tracked_clients(), 3)


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
