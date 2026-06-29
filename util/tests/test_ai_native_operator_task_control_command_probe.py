import importlib.util
import json
import pathlib
import re
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = ROOT / "util" / "ai_native_operator_task_control_command_probe.py"
DOC = ROOT / "doc" / "ai-native-runtime" / "operator-status-package.md"
SMOKE_DOC = ROOT / "doc" / "ai-native-runtime" / "synthetic-runtime-smoke.md"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"
PRIVATE_PATTERNS = re.compile(
    r"/Users/|minecraftpi|192\.168|spacebase|themepark|showcase100|"
    r"disneyland100|(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|"
    r"private_prompt|asset_payload",
    re.I,
)


def load_command_probe_module():
    assert CLI.is_file(), f"missing {CLI}"
    spec = importlib.util.spec_from_file_location("ai_native_operator_task_control_command_probe", CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_command_result():
    return {
        "schema_version": 1,
        "command_result_kind": "ai_native_operator_task_control_command_result",
        "generated_at": "2026-06-29T06:00:00Z",
        "runtime_context": {
            "game_profile": "ai_runtime",
            "command": "/ai_runtime_operator_task_control",
            "source": "live_runtime_state",
            "actor": "admin",
            "world_mutation_performed": False,
        },
        "source_receipt": {
            "receipt_kind": "ai_native_operator_action_approval_receipt",
            "status": "attention",
        },
        "operator_actions": {
            "mode": "receipt_gated_task_cancel_retry",
            "mutation_scope": "live_task_queue",
            "mutation_performed": True,
            "task_queue_mutation_performed": True,
            "world_mutation_performed": False,
            "allowed_operations": ["cancel", "retry"],
            "allowed_approval_kinds": ["task_cancel_retry_review", "task_retry_review"],
        },
        "summary": {
            "decisions_total": 5,
            "executed_total": 2,
            "rejected_total": 3,
            "skipped_total": 0,
            "by_result_status": {"executed": 2, "rejected": 3},
            "by_operation": {"cancel": 1, "retry": 1, "none": 3},
            "by_rejection_reason": {
                "decision_not_approved": 1,
                "unsupported_target_kind": 2,
            },
            "attention_required": True,
        },
        "results": [
            {
                "decision_id": "decision:cancel-command-running",
                "status": "executed",
                "operation": "cancel",
                "before_status": "running",
                "after_status": "cancelled",
                "reason": "approved_receipt",
            },
            {
                "decision_id": "decision:retry-command-blocked",
                "status": "executed",
                "operation": "retry",
                "before_status": "blocked",
                "after_status": "queued",
                "reason": "approved_receipt",
            },
            {
                "decision_id": "decision:denied-command",
                "status": "rejected",
                "operation": "none",
                "reason": "decision_not_approved",
            },
            {
                "decision_id": "decision:rollback-command-rejected",
                "status": "rejected",
                "operation": "none",
                "reason": "unsupported_target_kind",
            },
            {
                "decision_id": "decision:import-command-rejected",
                "status": "rejected",
                "operation": "none",
                "reason": "unsupported_target_kind",
            },
        ],
        "safety": {
            "public_safe_output": True,
            "receipt_required": True,
            "receipt_gated": True,
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


class AIOperatorTaskControlCommandProbeTests(unittest.TestCase):
    def assert_public_safe(self, payload):
        encoded = json.dumps(payload, sort_keys=True)
        self.assertLessEqual(len(encoded.encode("utf-8")), payload["bounds"]["max_bytes"])
        self.assertNotRegex(encoded, PRIVATE_PATTERNS)

    def test_probe_worldmod_invokes_receipt_gated_operator_command(self):
        probe = load_command_probe_module()
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
            self.assertIn("ai-runtime-operator-taREDACTED_KEY_FIXTURE.json", source)
            self.assertIn("core.registered_chatcommands.ai_runtime_operator_task_control", source)
            self.assertIn("/ai_runtime_operator_task_control", source)
            self.assertIn("receipt_json=", source)
            self.assertIn("task_cancel_retry_review", source)
            self.assertIn("task_retry_review", source)
            self.assertIn("no_rollback_execution", source)
            self.assertIn("no_import_promotion_execution", source)
            self.assertIn("no_world_mutation", source)
            self.assertNotRegex(source, PRIVATE_PATTERNS)

    def test_validate_command_result_accepts_bounded_cancel_retry_artifact(self):
        probe = load_command_probe_module()
        result = sample_command_result()
        result["bounds"]["output_bytes"] = len(json.dumps(result, sort_keys=True).encode("utf-8"))

        evidence = probe.validate_command_result(result, max_bytes=22000)

        self.assertEqual(evidence["operator_task_control_command_status"], "pass")
        self.assertEqual(evidence["operator_task_control_command_items"], 5)
        self.assertEqual(evidence["operator_task_control_command_executed"], 2)
        self.assertEqual(evidence["operator_task_control_command_rejected"], 3)
        self.assertEqual(evidence["operator_task_control_command_world_mutation"], False)
        self.assert_public_safe(result)

    def test_validate_command_result_rejects_private_or_world_mutating_artifact(self):
        probe = load_command_probe_module()
        result = sample_command_result()
        result["runtime_context"]["world_mutation_performed"] = True

        with self.assertRaisesRegex(ValueError, "world mutation"):
            probe.validate_command_result(result, max_bytes=22000)

        result = sample_command_result()
        result["results"][0]["operator_note"] = "/Users/billevans/private/spacebase"
        result["bounds"]["output_bytes"] = len(json.dumps(result, sort_keys=True).encode("utf-8"))
        with self.assertRaisesRegex(ValueError, "private"):
            probe.validate_command_result(result, max_bytes=22000)

    def test_run_probe_copies_command_artifact_after_successful_disposable_server(self):
        probe = load_command_probe_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            server_bin = root / "bin" / "luantiserver"
            server_bin.parent.mkdir(parents=True)
            server_bin.write_text("#!/bin/sh\n", encoding="utf-8")
            output = root / "out" / probe.COMMAND_ARTIFACT_NAME

            def fake_run(command, cwd, text, capture_output, check, timeout):
                world_dir = pathlib.Path(command[command.index("--world") + 1])
                result = sample_command_result()
                result["bounds"]["output_bytes"] = len(
                    json.dumps(result, sort_keys=True).encode("utf-8")
                )
                (world_dir / probe.COMMAND_ARTIFACT_NAME).write_text(
                    json.dumps(result),
                    encoding="utf-8",
                )
                (world_dir / probe.COMMAND_PROBE_STATUS_NAME).write_text(
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
            self.assertEqual(
                copied["command_result_kind"],
                "ai_native_operator_task_control_command_result",
            )
            self.assertEqual(copied["summary"]["executed_total"], 2)
            self.assert_public_safe(copied)

    def test_docs_describe_receipt_gated_task_control_command_probe(self):
        readme = README.read_text(encoding="utf-8")
        doc = DOC.read_text(encoding="utf-8")
        smoke = SMOKE_DOC.read_text(encoding="utf-8")

        for body in (readme, doc, smoke):
            self.assertIn("ai_native_operator_task_control_command_probe.py", body)
            self.assertIn("ai-runtime-operator-taREDACTED_KEY_FIXTURE.json", body)
            self.assertIn("/ai_runtime_operator_task_control", body)
            self.assertIn("receipt-gated task-control command probe", body)
            self.assertIn("task cancel/retry only", body)
            self.assertIn("no rollback execution", body)
            self.assertIn("no import promotion execution", body)
            self.assertIn("no world mutation", body)
            self.assertNotRegex(body, PRIVATE_PATTERNS)


if __name__ == "__main__":
    unittest.main()
