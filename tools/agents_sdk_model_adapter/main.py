#!/usr/bin/env python3
"""HTTP entrypoint for the OpenAI Agents SDK model adapter sidecar."""

from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from agent import adapter_health, run_model_adapter_request, sample_request


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "AiNativeLuantiAgentsSdkAdapter/0.1"

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API.
        if self.path != "/health":
            self._write_json(404, {"ok": False, "reason": "not_found"})
            return
        self._write_json(200, adapter_health())

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API.
        if self.path != "/v1/model-adapter":
            self._write_json(404, {"ok": False, "reason": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 64_000:
                self._write_json(413, {"ok": False, "reason": "request_too_large"})
                return
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self._write_json(400, {"ok": False, "reason": "invalid_json"})
            return
        response = run_model_adapter_request(payload)
        self._write_json(200 if response.get("ok") else 502, response)

    def log_message(self, fmt: str, *args: Any) -> None:
        if os.getenv("AI_NATIVE_AGENT_HTTP_LOGS") == "1":
            super().log_message(fmt, *args)


def serve(host: str, port: int) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"serving ai-native Agents SDK model adapter on http://{host}:{port}")
    httpd.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8766")))
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    if args.smoke:
        response = run_model_adapter_request(sample_request(), force_offline=True)
        print(json.dumps(response, indent=2, sort_keys=True))
        return 0 if response.get("ok") else 1

    serve(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
