"""Command-line entry points for the local grounded assistant."""

from __future__ import annotations

import argparse
import json
import os
import sys

from .api import ApiService, create_server
from .config import DEFAULT_HOST, DEFAULT_PORT, TOKEN_ENV
from .evaluation import load_evaluation_cases, run_evaluation
from .schema import DataContractError
from .store import load_corpus


def _print(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))


def _corpus(args: argparse.Namespace):
    return load_corpus(args.root)


def _root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=None, help="repository root containing data/ (defaults to this app)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="book-grounded-ai-assistant", description="Local grounded answer assistant")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="verify corpus, manifest, and evaluation set")
    _root_argument(validate)

    metadata = subparsers.add_parser("metadata", help="print assistant metadata")
    _root_argument(metadata)
    metadata.add_argument("--json", action="store_true")

    ask = subparsers.add_parser("ask", help="answer one question from approved local context")
    _root_argument(ask)
    ask.add_argument("--question", required=True)
    ask.add_argument("--json", action="store_true")

    evaluate = subparsers.add_parser("evaluate", help="run the offline golden-question set")
    _root_argument(evaluate)
    evaluate.add_argument("--json", action="store_true")

    serve = subparsers.add_parser("serve", help="serve the local HTTP API")
    _root_argument(serve)
    serve.add_argument("--host", default=DEFAULT_HOST)
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument(
        "--allow-unauthenticated-local",
        action="store_true",
        help="allow local-only development without BOOK_GROUNDED_AI_TOKEN",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            corpus = _corpus(args)
            cases = load_evaluation_cases(args.root)
            _print(
                {
                    "status": "ok",
                    "assistant": "book-grounded-ai-assistant",
                    "corpus_schema_version": corpus.schema_version,
                    "dataset": corpus.dataset,
                    "records_count": len(corpus.records),
                    "evaluation_cases": len(cases),
                    "lineage": corpus.lineage.as_dict(),
                }
            )
            return 0
        if args.command == "metadata":
            response = ApiService(_corpus(args)).handle("GET", "/v1/metadata")
            _print(response.payload)
            return 0 if response.status == 200 else 1
        if args.command == "ask":
            response = ApiService(_corpus(args)).assistant.answer(args.question)
            _print(response)
            return 0
        if args.command == "evaluate":
            service = ApiService(_corpus(args))
            result = run_evaluation(service.assistant, args.root)
            _print(result)
            return 0 if result["status"] == "pass" else 1
        if args.command == "serve":
            token = os.environ.get(TOKEN_ENV) or None
            if token is None and not args.allow_unauthenticated_local:
                _print(
                    {
                        "error": {
                            "code": "CONFIG001",
                            "message": f"set {TOKEN_ENV} or pass --allow-unauthenticated-local for local development",
                        }
                    }
                )
                return 2
            server = create_server(ApiService(_corpus(args), read_token=token), args.host, args.port)
            print(f"{server.server_address[0]}:{server.server_address[1]}", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                return 0
            finally:
                server.server_close()
            return 0
    except DataContractError as exc:
        _print({"error": {"code": exc.code, "message": exc.message, "details": exc.details}})
        return 1
    except ValueError as exc:
        _print({"error": {"code": "INPUT010", "message": str(exc), "details": {}}})
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())

