from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
import json
import tempfile

from .cli import build_artifacts
from .planner import plan_from_prompt
from .safety import validate_plan


class OpenRealmKernelHandler(BaseHTTPRequestHandler):
    """Tiny local HTTP API for the OpenRealm Creator Kernel.

    This intentionally uses only the Python standard library so a creator can
    run it immediately. It is designed for local development and launcher
    prototyping, not as a public internet service.
    """

    server_version = "OpenRealmCreatorKernel/0.1"

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json({"ok": True, "service": "openrealm_creator_kernel", "version": "0.1.0"})
            return
        self._json({"ok": False, "error": "not_found"}, status=404)

    def do_POST(self) -> None:
        try:
            payload = self._payload()
            if self.path == "/v1/plan":
                prompt = str(payload.get("prompt", "")).strip()
                if not prompt:
                    raise ValueError("prompt is required")
                plan = plan_from_prompt(prompt)
                report = validate_plan(plan)
                self._json({
                    "ok": report.ok,
                    "plan": plan.to_dict(),
                    "safety": {
                        "ok": report.ok,
                        "issues": [issue.__dict__ for issue in report.issues],
                    },
                })
                return
            if self.path == "/v1/demo-package":
                prompt = str(payload.get("prompt", "")).strip()
                if not prompt:
                    raise ValueError("prompt is required")
                with tempfile.TemporaryDirectory(prefix="openrealm_kernel_") as tmp:
                    result = build_artifacts(prompt, Path(tmp), package=True)
                    plan = json.loads(Path(result["plan"]).read_text(encoding="utf-8"))
                    audit = json.loads(Path(result["audit"]).read_text(encoding="utf-8"))
                    self._json({
                        "ok": True,
                        "plan": plan,
                        "audit": audit,
                        "package_name": Path(result["package"]).name,
                        "note": "This endpoint validates packaging but does not persist files. Use the CLI for durable output.",
                    })
                return
            self._json({"ok": False, "error": "not_found"}, status=404)
        except Exception as exc:  # local dev endpoint: return useful diagnostics
            self._json({"ok": False, "error": type(exc).__name__, "message": str(exc)}, status=400)

    def _payload(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        return json.loads(raw or "{}")

    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[openrealm-kernel] {self.address_string()} - {fmt % args}")


def serve(host: str = "127.0.0.1", port: int = 8787) -> None:
    httpd = ThreadingHTTPServer((host, port), OpenRealmKernelHandler)
    print(f"OpenRealm Creator Kernel listening at http://{host}:{port}")
    print("POST /v1/plan with JSON {'prompt':'build a cabin'}")
    httpd.serve_forever()
