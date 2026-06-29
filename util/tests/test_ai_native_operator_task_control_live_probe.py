import importlib.util
import json
import pathlib
import re
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = ROOT / "util" / "ai_native_operator_task_control_live_probe.py"
DOC = ROOT / "doc" / "ai-native-runtime" / "operator-status-package.md"
SMOKE_DOC = ROOT / "doc" / "ai-native-runtime" / "synthetic-runtime-smoke.md"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"
PRIVATE_PATTERNS = re.compile(
    r"/Users/|minecraftpi|192\.168|spacebase|themepark|showcase100|"
    r"disneyland100|(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|"
    r"private_prompt|asset_payload",
    re.I,
)


def load_live_probe_module():
    assert CLI.is_file(), f"missing {CLI}"
    spec = importlib.util.spec_from_file_location("ai_native_operator_task_control_live_probe", CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_live_result():
    return {
        "schema_version": 1,
        "live_result_kind": "ai_native_operator_task_control_live_result",
        "generated_at": "2026-06-29T06:00:00Z",
        "runtime_context": {
            "mode": "disposable_live_ai_runtime_task_control_probe",
            "gameid": "ai_runtime",
            "requires_live_pi": False,
            "requires_private_world": False,
            "world_mutation_performed": False,
        },
        "source_receipt": {
            "receipt_kind": "ai_native_operator_action_approval_receipt",
            "status": "attention",
        },
        "operator_actions": {
            "mode": "receipt_gated_live_task_control",
            "mutation_performed": True,
            "task_queue_mutation_performed": True,
            "world_mutation_performed": False,
            "allowed_approval_kinds": ["task_cancel_retry_review", "task_retry_review"],
            "executor_capabilities": ["task.cancel", "task.inspect", "task.retry"],
        },
        "summary": {
            "decisions_total": 5,
            "executed_total": 2,
            "rejected_total": 3,
            "skipped_total": 0,
            "by_result_status": {"executed": 2, "rejected": 3},
            "by_operation": {"none": 3, "task.cancel": 1, "task.retry": 1},
            "by_rejection_reason": {
                "decision_not_approved": 1,
                "unsupported_approval_kind": 2,
            },
            "attention_required": True,
        },
        "results": [
            {
                "decision_id": "decision:cancel-live-running",
                "status": "executed",
                "operation": "task.cancel",
                "before_status": "running",
                "after_status": "cancelled",
                "reason": "approved_receipt",
            },
            {
                "decision_id": "decision:retry-live-blocked",
                "status": "executed",
                "operation": "task.retry",
                "before_status": "blocked",
                "after_status": "queued",
                "reason": "approved_receipt",
            },
            {
                "decision_id": "decision:denied-live",
                "status": "rejected",
                "operation": "none",
                "reason": "decision_not_approved",
            },
            {
                "decision_id": "decision:rollback-live-rejected",
                "status": "rejected",
                "operation": "none",
                "reason": "unsupported_approval_kind",
            },
            {
                "decision_id": "decision:import-live-rejected",
                "status": "rejected",
                "operation": "none",
                "reason": "unsupported_approval_kind",
            },
        ],
        "live_task_state_after": {
            "tasks": [
                {"task_id": "task:live-cancel", "status": "cancelled", "retry_count": 0},
                {"task_id": "task:live-retry", "status": "queued", "retry_count": 1},
                {"task_id": "task:live-denied", "status": "blocked", "retry_count": 0},
            ]
        },
        "safety": {
            "public_safe_output": True,
            "receipt_required": True,
            "receipt_gated": True,
            "disposable_live_world_only": True,
            "live_queue_probe_only": True,
            "task_control_only": True,
            "task_queue_mutation_only": True,
            "world_mutation_performed": False,
            "no_world_mutation": True,
            "no_rollback_execution": True,
            "no_import_promotion_execution": True,
            "no_structure_apply": True,
            "no_raw_assets": True,
            "no_provider_prompts": True,
            "no_family_world_coordinates": True,
        },
        "bounds": {
            "max_bytes": 22000,
            "output_bytes": 0,
            "truncated": False,
        },
    }


class AIOperatorTaskControlLiveProbeTests(unittest.TestCase):
    def assert_public_safe(self, payload):
        encoded = json.dumps(payload, sort_keys=True)
        self.assertLessEqual(len(encoded.encode("utf-8")), payload["bounds"]["max_bytes"])
        self.assertNotRegex(encoded, PRIVATE_PATTERNS)

    def test_probe_worldmod_embeds_receipt_gated_live_task_control(self):
        probe = load_live_probe_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            world_dir = pathlib.Path(tmpdir) / "world"
            probe.write_probe_world(
                world_dir,
                generated_at="2026-06-29T06:00:00Z",
                max_bytes=22000,
            )

            source = (world_dir / "worldmods" / probe.PROBE_MOD_NAME / "init.lua").read_text(
                encoding="utf-8"
            )
            self.assertIn("ai-runtime-operator-task-control-live-result.json", source)
            self.assertIn("receipt_gated_live_task_control", source)
            self.assertIn("core.cancel_ai_task", source)
            self.assertIn("core.retry_ai_task", source)
            self.assertIn("task_cancel_retry_review", source)
            self.assertIn("task_retry_review", source)
            self.assertIn("no_rollback_execution", source)
            self.assertIn("no_import_promotion_execution", source)
            self.assertIn("no_world_mutation", source)
            self.assertNotRegex(source, PRIVATE_PATTERNS)

    def test_validate_live_result_accepts_bounded_cancel_retry_artifact(self):
        probe = load_live_probe_module()
        result = sample_live_result()
        result["bounds"]["output_bytes"] = len(json.dumps(result, sort_keys=True).encode("utf-8"))

        evidence = probe.validate_live_result(result, max_bytes=22000)

        self.assertEqual(evidence["operator_task_control_live_status"], "pass")
        self.assertEqual(evidence["operator_task_control_live_items"], 5)
        self.assertEqual(evidence["operator_task_control_live_executed"], 2)
        self.assertEqual(evidence["operator_task_control_live_rejected"], 3)
        self.assertEqual(evidence["operator_task_control_live_world_mutation"], False)
        self.assert_public_safe(result)

    def test_validate_live_result_rejects_private_or_mutating_artifact(self):
        probe = load_live_probe_module()
        result = sample_live_result()
        result["runtime_context"]["world_mutation_performed"] = True

        with self.assertRaisesRegex(ValueError, "world mutation"):
            probe.validate_live_result(result, max_bytes=22000)

        result = sample_live_result()
        result["results"][0]["operator_note"] = "/Users/billevans/private/spacebase"
        result["bounds"]["output_bytes"] = len(json.dumps(result, sort_keys=True).encode("utf-8"))
        with self.assertRaisesRegex(ValueError, "private"):
            probe.validate_live_result(result, max_bytes=22000)

    def test_run_probe_copies_live_artifact_after_successful_disposable_server(self):
        probe = load_live_probe_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            server_bin = root / "bin" / "luantiserver"
            server_bin.parent.mkdir(parents=True)
            server_bin.write_text("#!/bin/sh\n", encoding="utf-8")
            output = root / "out" / probe.LIVE_ARTIFACT_NAME

            def fake_run(command, cwd, text, capture_output, check, timeout):
                world_dir = pathlib.Path(command[command.index("--world") + 1])
                result = sample_live_result()
                result["bounds"]["output_bytes"] = len(
                    json.dumps(result, sort_keys=True).encode("utf-8")
                )
                (world_dir / probe.LIVE_ARTIFACT_NAME).write_text(
                    json.dumps(result),
                    encoding="utf-8",
                )
                (world_dir / probe.LIVE_RESULT_NAME).write_text(
                    json.dumps({"status": "pass", "reason": "captured"}),
                    encoding="utf-8",
                )
                return mock.Mock(returncode=0, stdout="", stderr="")

            with mock.patch.object(probe.subprocess, "run", side_effect=fake_run):
                exit_code = probe.main([
                    "--root",
                    str(root),
                    "--server-bin",
                    "bin/luantiserver",
                    "--output",
                    str(output),
                    "--generated-at",
                    "2026-06-29T06:00:00Z",
                    "--max-bytes",
                    "22000",
                    "--timeout",
                    "1",
                ])

            self.assertEqual(exit_code, 0)
            copied = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(copied["live_result_kind"], "ai_native_operator_task_control_live_result")
            self.assertEqual(copied["summary"]["executed_total"], 2)
            self.assert_public_safe(copied)

    def test_docs_describe_disposable_live_task_control_probe(self):
        readme = README.read_text(encoding="utf-8")
        doc = DOC.read_text(encoding="utf-8")
        smoke = SMOKE_DOC.read_text(encoding="utf-8")

        for body in (readme, doc, smoke):
            self.assertIn("ai_native_operator_task_control_live_probe.py", body)
            self.assertIn("ai-runtime-operator-task-control-live-result.json", body)
            self.assertIn("disposable live `ai_runtime` queue probe", body)
            self.assertIn("task cancel/retry only", body)
            self.assertIn("no rollback execution", body)
            self.assertIn("no import promotion execution", body)
            self.assertIn("no world mutation", body)
            self.assertNotRegex(body, PRIVATE_PATTERNS)


if __name__ == "__main__":
    unittest.main()
