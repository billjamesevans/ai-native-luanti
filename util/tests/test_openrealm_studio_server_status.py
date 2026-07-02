import importlib.util
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "openrealm_advantage_kit" / "studio" / "server.py"


def load_module():
    spec = importlib.util.spec_from_file_location("openrealm_studio_server_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def gate_payload(**overrides):
    payload = {
        "schema_version": 1,
        "artifact_kind": "openrealm_live_review_gate_result",
        "status": "pass",
        "source_trace_id": "nova_trace:11",
        "selected_option_id": "fire",
        "case_hint": "fire_only_strict",
        "artifacts": {
            "review_packet": "local/review-packets/live-review/trace11-studio-review-packet.json",
            "candidate_queue": "local/review-packets/live-review/trace11-candidate-queue.json",
        },
        "checks": {
            "review_packet_public_safe": True,
            "operator_label_matched": True,
            "case_pack_has_cases": True,
        },
        "violations": [],
        "summary": {
            "operator_label_matched": True,
            "operator_labels_applied": 1,
            "candidate_queue_status": "ready",
            "case_pack_status": "ready",
            "cases_total": 1,
        },
        "safety": {
            "public_safe_output": True,
            "no_world_mutation": True,
            "no_raw_assets": True,
            "no_provider_prompts": True,
            "no_family_world_coordinates": True,
        },
    }
    payload.update(overrides)
    return payload


class OpenRealmStudioStatusTests(unittest.TestCase):
    def env_for(self, root, gate_path):
        missing = str(root / "missing.json")
        return {
            "OPENREALM_LIVE_REVIEW_GATE": str(gate_path),
            "OPENREALM_QUALITY_GATE": missing,
            "OPENREALM_PROMPT_EVAL": missing,
            "OPENREALM_REQUEST_LOG_GATE": missing,
        }

    def test_live_review_gate_summary_is_public_safe(self):
        server = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            gate_path = root / "gate-result.json"
            gate_path.write_text(json.dumps(gate_payload()) + "\n", encoding="utf-8")

            with mock.patch.dict(os.environ, self.env_for(root, gate_path)):
                summary = server.live_review_gate_status()
                quality = server.quality_gate_status(summary)

            self.assertTrue(summary["present"])
            self.assertEqual(summary["current_health"], "pass")
            self.assertEqual(summary["source_trace_id"], "nova_trace:11")
            self.assertEqual(summary["selected_option_id"], "fire")
            self.assertEqual(summary["checks_passed"], 3)
            self.assertEqual(summary["checks_total"], 3)
            self.assertEqual(summary["artifact_keys"], ["candidate_queue", "review_packet"])
            self.assertNotIn("trace11-studio-review-packet", json.dumps(summary))
            self.assertEqual(quality["status"], "pass")
            self.assertEqual(quality["live_review_gate_health"], "pass")

    def test_live_review_gate_rejects_unsafe_payload_without_leaking_details(self):
        server = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            gate_path = root / "gate-result.json"
            unsafe = gate_payload(violations=[{"kind": "diagnostic", "details": "/Users/example/private"}])
            gate_path.write_text(json.dumps(unsafe) + "\n", encoding="utf-8")

            with mock.patch.dict(os.environ, self.env_for(root, gate_path)):
                summary = server.live_review_gate_status()
                quality = server.quality_gate_status(summary)

            encoded = json.dumps(summary)
            self.assertEqual(summary["current_health"], "fail")
            self.assertTrue(summary["unsafe_payload_rejected"])
            self.assertFalse(summary["public_safe_output"])
            self.assertNotIn("/Users/example/private", encoded)
            self.assertEqual(quality["status"], "fail")
            self.assertEqual(quality["live_review_gate_violations"], 1)


if __name__ == "__main__":
    unittest.main()
