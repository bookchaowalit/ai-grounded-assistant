"""Route access matrix for the grounded assistant API.

ROUTE_ACCESS is the table `ApiService.handle` dispatches on. These tests pin
it, keep non-GET routes off the public level, and call every route with every
method as an anonymous caller, with a wrong token and with the read token.
"""

from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from book_grounded_ai import cli
from book_grounded_ai.api import PUBLIC, READER, ROUTE_ACCESS, ApiService
from book_grounded_ai.store import load_corpus

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TOKEN = "matrix-read-token"
EXPECTED = {
    "/healthz": (PUBLIC, "GET"),
    "/v1/metadata": (READER, "GET"),
    "/v1/ask": (READER, "POST"),
}
ALL_METHODS = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
ASK_BODY = json.dumps({"question": "Where should approved source evidence live?"})


class RouteAccessMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ApiService(load_corpus(REPOSITORY_ROOT), read_token=TOKEN, rate_limit=10_000)

    def test_table_is_pinned(self) -> None:
        self.assertEqual(
            {path: (level, method) for path, (level, method, _msg) in ROUTE_ACCESS.items()},
            EXPECTED,
        )

    def test_only_get_routes_may_be_public(self) -> None:
        for path, (level, method, _msg) in ROUTE_ACCESS.items():
            if method != "GET":
                self.assertNotEqual(level, PUBLIC, f"{method} {path} must require the token")

    def test_every_route_method_and_caller(self) -> None:
        callers = {
            "anonymous": {},
            "wrong-token": {"Authorization": "Bearer wrong"},
            "reader": {"Authorization": f"Bearer {TOKEN}"},
        }
        for path, (level, allowed, _msg) in ROUTE_ACCESS.items():
            for method in ALL_METHODS:
                for caller, auth in callers.items():
                    with self.subTest(path=path, method=method, caller=caller):
                        headers = {"Content-Type": "application/json", **auth}
                        body = ASK_BODY if method == "POST" else None
                        response = self.service.handle(method, path, headers, body)
                        if method != allowed:
                            self.assertEqual(response.status, 405)
                            self.assertEqual(response.headers.get("Allow"), allowed)
                        elif level == PUBLIC or caller == "reader":
                            self.assertEqual(response.status, 200)
                        else:
                            self.assertEqual(response.status, 401)

    def test_non_string_question_is_a_400_input_error(self) -> None:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"}
        for question in (123, None, ["a"], {"q": "x"}):
            with self.subTest(question=question):
                response = self.service.handle("POST", "/v1/ask", headers, json.dumps({"question": question}))
                self.assertEqual(response.status, 400)
                self.assertEqual(response.payload["error"]["code"], "INPUT001")

    def test_unlisted_paths_are_404(self) -> None:
        for path in ("/", "/v1", "/v1/ask/extra", "/admin", "/healthz/x"):
            with self.subTest(path=path):
                self.assertEqual(
                    self.service.handle("GET", path, {"Authorization": f"Bearer {TOKEN}"}).status,
                    404,
                )


class UnauthenticatedBindTests(unittest.TestCase):
    def test_unauthenticated_mode_refuses_non_loopback_hosts(self) -> None:
        for host in ("0.0.0.0", "::", "10.0.0.5"):
            with self.subTest(host=host):
                with (
                    patch.dict(os.environ, {"BOOK_GROUNDED_AI_TOKEN": ""}),
                    redirect_stdout(io.StringIO()) as out,
                ):
                    code = cli.main(
                        [
                            "serve",
                            "--port",
                            "0",
                            "--host",
                            host,
                            "--allow-unauthenticated-local",
                        ]
                    )
                self.assertEqual(code, 2)
                self.assertEqual(json.loads(out.getvalue())["error"]["code"], "CONFIG002")


if __name__ == "__main__":
    unittest.main()
