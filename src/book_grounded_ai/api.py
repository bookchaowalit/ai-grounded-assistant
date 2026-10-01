"""HTTP boundary for the local grounded assistant."""

from __future__ import annotations

import hmac
import json
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import urlsplit

from .assistant import GroundedAssistant
from .config import API_VERSION, APP_NAME, MAX_BODY_BYTES
from .schema import DataContractError, error_payload
from .store import Corpus, load_corpus


# Route access matrix: path -> (access level, the one allowed method, 405
# message). "public" needs nothing; "reader" needs `Authorization: Bearer
# $BOOK_GROUNDED_AI_TOKEN` when a token is configured. `/v1/ask` is POST
# because the question travels in the body; it changes no state.
# `ApiService.handle` dispatches through this table and
# tests/test_route_access.py pins it.
PUBLIC = "public"
READER = "reader"
ROUTE_ACCESS: dict[str, tuple[str, str, str]] = {
    "/healthz": (PUBLIC, "GET", "health endpoint is read-only"),
    "/v1/metadata": (READER, "GET", "metadata endpoint is read-only"),
    "/v1/ask": (READER, "POST", "ask endpoint requires POST"),
}


@dataclass(frozen=True)
class Response:
    status: int
    payload: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)


class _RateLimiter:
    """Sliding-window limiter whose memory is bounded by active clients.

    Clients with no event inside the window are evicted on a periodic sweep,
    and the number of tracked clients is capped so a flood of distinct client
    ids cannot grow the table without bound.
    """

    def __init__(
        self,
        max_requests: int,
        window_seconds: float = 60.0,
        *,
        max_clients: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_requests < 1:
            raise ValueError("max_requests must be positive")
        if max_clients < 1:
            raise ValueError("max_clients must be positive")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_clients = max_clients
        self._clock = clock
        self._events: dict[str, list[float]] = {}
        self._last_sweep = clock()
        self._lock = threading.Lock()

    def tracked_clients(self) -> int:
        with self._lock:
            return len(self._events)

    def _sweep(self, now: float) -> None:
        idle = [client for client, events in self._events.items() if not events or now - events[-1] >= self.window_seconds]
        for client in idle:
            del self._events[client]
        self._last_sweep = now

    def allow(self, client_id: str) -> tuple[bool, int]:
        now = self._clock()
        with self._lock:
            if now - self._last_sweep >= self.window_seconds or (
                client_id not in self._events and len(self._events) >= self.max_clients
            ):
                self._sweep(now)
            events = [event for event in self._events.get(client_id, []) if now - event < self.window_seconds]
            if len(events) >= self.max_requests:
                retry_after = max(1, int(self.window_seconds - (now - events[0])))
                self._events[client_id] = events
                return False, retry_after
            if client_id not in self._events and len(self._events) >= self.max_clients:
                # Every tracked client is still active: fail closed for new ids.
                return False, max(1, int(self.window_seconds))
            events.append(now)
            self._events[client_id] = events
            return True, 0


class ApiService:
    """Socket-independent application service for HTTP and contract tests."""

    def __init__(self, corpus: Corpus | None = None, *, read_token: str | None = None, rate_limit: int = 60) -> None:
        self.assistant = GroundedAssistant(corpus or load_corpus())
        self.read_token = read_token
        self._rate_limiter = _RateLimiter(rate_limit)

    def _response(self, status: int, payload: dict[str, Any], **headers: str) -> Response:
        return Response(status, payload, headers)

    def _authorized(self, headers: dict[str, str]) -> bool:
        if self.read_token is None:
            return True
        # Compare bytes: hmac.compare_digest raises TypeError for non-ASCII str,
        # and http.server decodes headers as latin-1, so a crafted header
        # would otherwise crash the request instead of returning 401.
        supplied = headers.get("Authorization", "").encode("utf-8", "surrogateescape")
        expected = f"Bearer {self.read_token}".encode("utf-8")
        return hmac.compare_digest(supplied, expected)

    def _body_question(self, headers: dict[str, str], body: bytes | str | None) -> str | Response:
        if body is None:
            return self._response(400, error_payload("INPUT005", "JSON body is required"))
        raw = body.encode("utf-8") if isinstance(body, str) else body
        if len(raw) > MAX_BODY_BYTES:
            return self._response(413, error_payload("INPUT006", "request body exceeds the local limit", {"max_bytes": MAX_BODY_BYTES}))
        content_type = headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            return self._response(415, error_payload("INPUT007", "Content-Type must be application/json"))
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._response(400, error_payload("INPUT008", "request body must be valid UTF-8 JSON"))
        if not isinstance(value, dict) or set(value) != {"question"}:
            return self._response(400, error_payload("INPUT009", "request body must contain only question"))
        return value["question"]

    def handle(
        self,
        method: str,
        target: str,
        headers: dict[str, str] | None = None,
        body: bytes | str | None = None,
        *,
        client_id: str = "local",
    ) -> Response:
        request_headers = headers or {}
        allowed, retry_after = self._rate_limiter.allow(client_id)
        if not allowed:
            return self._response(
                429,
                error_payload("RATE001", "rate limit exceeded", {"window_seconds": 60}),
                **{"Retry-After": str(retry_after)},
            )
        path = urlsplit(target).path or "/"
        method = method.upper()
        route = ROUTE_ACCESS.get(path)
        if route is None:
            return self._response(404, error_payload("API404", "route not found"))
        level, allowed_method, method_message = route
        if method != allowed_method:
            return self._response(405, error_payload("API405", method_message), **{"Allow": allowed_method})
        if level != PUBLIC and not self._authorized(request_headers):
            return self._response(401, error_payload("AUTH001", "Bearer authentication required"), **{"WWW-Authenticate": "Bearer"})
        if path == "/healthz":
            return self._response(
                200,
                {
                    "status": "ok",
                    "assistant": APP_NAME,
                    "api_version": API_VERSION,
                    "data_status": "valid",
                    "adapter": self.assistant.metadata()["adapter"],
                    "external_actions": False,
                },
            )
        if path == "/v1/metadata":
            return self._response(200, self.assistant.metadata())
        question = self._body_question(request_headers, body)
        if isinstance(question, Response):
            return question
        try:
            return self._response(200, self.assistant.answer(question))
        except DataContractError as exc:
            return self._response(400, error_payload(exc.code, exc.message, exc.details))
        except ValueError as exc:
            return self._response(400, error_payload("INPUT010", str(exc)))


class DataApiServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], service: ApiService) -> None:
        super().__init__(address, DataApiRequestHandler)
        self.service = service


class DataApiRequestHandler(BaseHTTPRequestHandler):
    server: DataApiServer
    server_version = "book-grounded-ai-assistant/0.1"
    sys_version = ""

    def _dispatch(self, body: bytes | None = None) -> None:
        headers = {key: value for key, value in self.headers.items()}
        response = self.server.service.handle(
            self.command,
            self.path,
            headers,
            body,
            client_id=self.client_address[0],
        )
        encoded = json.dumps(response.payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        self.send_response(response.status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        for key, value in response.headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        self._dispatch()

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length > MAX_BODY_BYTES:
            self._dispatch(b"x" * (MAX_BODY_BYTES + 1))
            return
        self._dispatch(self.rfile.read(max(0, length)))

    def do_PUT(self) -> None:
        self._dispatch()

    def do_PATCH(self) -> None:
        self._dispatch()

    def do_DELETE(self) -> None:
        self._dispatch()

    def log_message(self, format: str, *args: Any) -> None:
        """Do not emit request paths or payload-shaped values to local logs."""


def create_server(service: ApiService, host: str = "127.0.0.1", port: int = 0) -> DataApiServer:
    return DataApiServer((host, port), service)

