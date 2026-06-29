import importlib.util
import json
import pathlib
import re
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = ROOT / "util" / "ai_native_runtime_verify.py"
DOC = ROOT / "doc" / "ai-native-runtime" / "synthetic-runtime-smoke.md"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"

PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload|/Users/",
    re.I,
)


def load_harness_module():
    assert CLI.is_file(), f"missing {CLI}"
    spec = importlib.util.spec_from_file_location("ai_native_runtime_verify", CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AIRuntimeVerificationHarnessTests(unittest.TestCase):
    def write_operator_status_artifact(self, path, *, payload=None, source="live_command"):
        path.parent.mkdir(parents=True, exist_ok=True)
        package = payload or {
            "schema_version": 1,
            "package_kind": "ai_native_operator_status_package",
            "status": "ready",
            "runtime_context": {
                "game_profile": "ai_runtime",
                "source": source,
                "mutation_performed": False,
            },
            "server_profile_hygiene": {
                "status": "pass",
                "dev_surfaces_disabled_by_default": True,
            },
            "agents": {"total": 0, "summaries": [], "truncated": False},
            "tasks": {"counts": {"total": 0}, "summaries": [], "truncated": False},
            "rollback": {
                "records_total": 0,
                "records_available": 0,
                "status_counts": {},
                "summaries": [],
                "truncated": False,
            },
            "imports": {
                "reviews_total": 0,
                "promotions_total": 0,
                "status_counts": {},
                "promotion_status_counts": {},
                "summaries": [],
                "promotion_summaries": [],
                "truncated": False,
            },
            "benchmarks": {
                "gates": [],
                "status_counts": {},
                "truncated": False,
            },
            "operator_control": {
                "surface_kind": "read_only_task_rollback_control",
                "action_mode": "dry_run_only",
                "mutation_performed": False,
                "recommendations_total": 1,
                "summaries": [
                    {
                        "target_kind": "task",
                        "target_id": "task:one",
                        "status": "queued",
                        "safe_next_action": "inspect_task_before_action",
                        "dry_run_only": True,
                        "will_mutate": False,
                    }
                ],
                "truncated": False,
            },
            "safety": {
                "public_safe_output": True,
                "redactions_applied": 0,
                "truncations_applied": 0,
                "no_raw_assets": True,
                "no_provider_prompts": True,
                "no_family_world_coordinates": True,
            },
            "bounds": {
                "max_bytes": 24000,
                "output_bytes": 1200,
                "truncated": False,
            },
        }
        path.write_text(json.dumps(package, indent=2), encoding="utf-8")

    def write_operator_task_control_live_artifact(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "live_result_kind": "ai_native_operator_task_control_live_result",
            "generated_at": "2026-06-28T12:00:00Z",
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
        payload["bounds"]["output_bytes"] = len(json.dumps(payload, sort_keys=True).encode("utf-8"))
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def write_operator_task_control_command_artifact(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "command_result_kind": "ai_native_operator_task_control_command_result",
            "generated_at": "2026-06-28T12:00:00Z",
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
        payload["bounds"]["output_bytes"] = len(json.dumps(payload, sort_keys=True).encode("utf-8"))
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def write_product_profile_artifact(self, path, *, payload=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        report = payload or {
            "schema_version": 1,
            "status": "pass",
            "profile": {
                "gameid": "ai_runtime",
                "manifest_path": "games/ai_runtime/product_profile_manifest.json",
                "product_mods": ["ai_runtime_base"],
            },
            "startup_inventory": [
                {
                    "name": "ai_runtime_game",
                    "category": "product_runtime",
                    "loaded_by_default_product_profile": True,
                    "requires_explicit_dev_or_test_lane": False,
                },
                {
                    "name": "ai_runtime_base",
                    "category": "first_party_plugin",
                    "loaded_by_default_product_profile": True,
                    "requires_explicit_dev_or_test_lane": False,
                },
                {
                    "name": "ai_operator_status",
                    "category": "product_runtime",
                    "loaded_by_default_product_profile": True,
                    "requires_explicit_dev_or_test_lane": False,
                },
                {
                    "name": "ai_operator_task_control",
                    "category": "product_runtime",
                    "loaded_by_default_product_profile": True,
                    "requires_explicit_dev_or_test_lane": False,
                },
                {
                    "name": "ai_runtime_smoke",
                    "category": "unit_test_helper",
                    "loaded_by_default_product_profile": False,
                    "requires_explicit_dev_or_test_lane": True,
                },
                {
                    "name": "ai_demo_entity_benchmark",
                    "category": "benchmark_fixture",
                    "loaded_by_default_product_profile": False,
                    "requires_explicit_dev_or_test_lane": True,
                },
            ],
            "explicit_dev_surfaces": [
                {
                    "name": "ai_runtime_smoke",
                    "setting": "ai_runtime.enable_smoke_command",
                    "default_enabled": False,
                    "status": "gated",
                },
                {
                    "name": "ai_demo_entity_benchmark",
                    "setting": "ai_runtime.enable_demo_benchmark_command",
                    "default_enabled": False,
                    "status": "gated",
                },
            ],
            "required_runtime_surfaces": [
                {
                    "name": "ai_operator_status",
                    "command": "ai_runtime_operator_status",
                    "status": "present",
                    "loaded_by_default_product_profile": True,
                    "command_registered": True,
                    "server_privilege_required": True,
                    "public_safe_output_required": True,
                },
                {
                    "name": "ai_operator_task_control",
                    "command": "ai_runtime_operator_task_control",
                    "status": "present",
                    "loaded_by_default_product_profile": True,
                    "command_registered": True,
                    "server_privilege_required": True,
                    "public_safe_output_required": True,
                },
            ],
            "test_only_files": ["builtin/game/tests/test_ai_runtime.lua"],
            "test_only_paths": ["util/tests/fixtures/compat", "util/tests"],
            "violations": [],
            "safety": {
                "no_private_content": True,
                "dev_surfaces_disabled_by_default": True,
                "test_fixtures_explicit_only": True,
                "runtime_surfaces_available": True,
            },
        }
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    def command_arg(self, command, flag):
        return command[command.index(flag) + 1]

    def clean_profile_summary_path_for_step(self, step):
        output_root = pathlib.Path(self.command_arg(step.actual_command, "--output-root"))
        return (
            output_root
            / self.command_arg(step.actual_command, "--hardware-class")
            / self.command_arg(step.actual_command, "--date")
            / self.command_arg(step.actual_command, "--luanti-commit")
            / "clean-profile-benchmark-summary.json"
        )

    def write_clean_profile_summary_artifact(self, path, *, payload=None, headless=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        player_probe = {
            "probe_status": "pass",
            "probe_kind": "server_process_liveness",
            "probe_duration_seconds": 3.0,
            "requested_sample_seconds": 3.0,
            "sample_count": 3,
            "synthetic_player_count": 0,
            "headless_player_supported": False,
            "server_stayed_listening": True,
            "server_log_warning_count": 0,
            "expected_server_log_warning_count": 0,
            "actionable_server_log_warning_count": 0,
            "expected_warning_kinds": [],
            "server_log_error_count": 0,
            "latency_probe_kind": "not_measured",
            "latency_proxy_supported": False,
            "join_latency_proxy_ms": {"sample_count": 0},
        }
        if headless:
            player_probe.update(
                {
                    "probe_kind": "headless_client_load",
                    "synthetic_player_count": 2,
                    "headless_player_supported": True,
                    "latency_probe_kind": "headless_join_log_observation",
                    "latency_proxy_supported": True,
                    "join_latency_proxy_ms": {"sample_count": 2},
                    "attempted_synthetic_player_count": 2,
                    "connected_synthetic_player_count": 2,
                    "completed_synthetic_player_count": 2,
                    "client_launch_failure_count": 0,
                }
            )
        summary = payload or {
            "schema_version": 1,
            "runner_version": "ai-native-clean-profile-benchmark:v1",
            "overall_status": "pass",
            "hardware_class": "local-mac",
            "game_profile": {"gameid": "ai_runtime"},
            "run_context": {
                "mode": "clean-profile-local-server",
                "requires_private_world": False,
                "requires_private_assets": False,
                "requires_live_pi": False,
                "requires_model_network": False,
            },
            "failure_notes": [],
            "comparison_summary": {
                "server_step_workload": {
                    "workload_status": "pass",
                    "workload_kind": "server_step_liveness",
                    "attempted_sample_count": 3,
                    "completed_sample_count": 3,
                    "failed_sample_count": 0,
                    "server_stayed_listening": True,
                    "server_log_warning_count": 0,
                    "expected_server_log_warning_count": 0,
                    "actionable_server_log_warning_count": 0,
                    "expected_warning_kinds": [],
                    "server_log_error_count": 0,
                },
                "player_load_tick_probe": player_probe,
                "map_chunk_workload": {
                    "workload_status": "pass",
                    "workload_kind": "synthetic_sqlite_mapblock_churn",
                    "mapblock_rows_created": 4,
                    "warning_count": 0,
                    "error_count": 0,
                },
                "cpu": {
                    "sample_status": "measured",
                    "cpu_sample_count": 3,
                    "avg_process_cpu_percent": 2.0,
                    "max_interval_cpu_percent": 4.0,
                },
                "entity_runtime_operations": {
                    "report_family": "demo_entity",
                    "warnings": 0,
                    "errors": 0,
                },
                "mutation_write_throughput": {
                    "report_family": "mutation",
                    "warnings": 0,
                    "errors": 0,
                    "unsafe_operations": 0,
                },
            },
        }
        path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    def runner_with_operator_artifact(self, runs):
        def run_step(step):
            if step.id == "product_profile_hygiene":
                output_path = pathlib.Path(
                    step.actual_command[step.actual_command.index("--output") + 1]
                )
                self.write_product_profile_artifact(output_path)
            if step.id == "branch_benchmark_gate" and "--game-profile" in step.actual_command:
                if self.command_arg(step.actual_command, "--game-profile") == "ai_runtime":
                    self.write_clean_profile_summary_artifact(
                        self.clean_profile_summary_path_for_step(step)
                    )
            if step.id in {"operator_status_live_command", "operator_status_package"}:
                output_path = pathlib.Path(
                    step.actual_command[step.actual_command.index("--output") + 1]
                )
                source = "live_command" if step.id == "operator_status_live_command" else "command_surrogate"
                self.write_operator_status_artifact(output_path, source=source)
            if step.id == "operator_task_control_live_probe":
                output_path = pathlib.Path(
                    step.actual_command[step.actual_command.index("--output") + 1]
                )
                self.write_operator_task_control_live_artifact(output_path)
            if step.id == "operator_task_control_command_probe":
                output_path = pathlib.Path(
                    step.actual_command[step.actual_command.index("--output") + 1]
                )
                self.write_operator_task_control_command_artifact(output_path)
            return next(runs)

        return run_step

    def test_success_manifest_is_bounded_private_safe_and_records_artifacts(self):
        harness = load_harness_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            args = harness.parse_args(
                [
                    "--output-root",
                    str(output_root),
                    "--hardware-class",
                    "local-mac",
                    "--date",
                    "2026-06-28",
                    "--luanti-commit",
                    "verify-success",
                    "--server-bin",
                    "bin/luantiserver",
                    "--game-profile",
                    "sample-synthetic",
                ]
            )
            runs = iter(
                [
                    harness.CommandRun(0, 0.10, "utility tests ok", ""),
                    harness.CommandRun(0, 0.12, "product profile pass", ""),
                    harness.CommandRun(
                        0,
                        0.20,
                        "local/benchmarks/local-mac/2026-06-28/verify-success/benchmark-gate-manifest.json\n",
                        "",
                    ),
                    harness.CommandRun(0, 0.25, "operator status live command ok", ""),
                    harness.CommandRun(0, 0.25, "operator task control live probe ok", ""),
                    harness.CommandRun(0, 0.25, "operator task control command probe ok", ""),
                    harness.CommandRun(0, 0.30, "TestAIRuntime passed", ""),
                ]
            )

            status, manifest_path, manifest = harness.run_harness(
                args,
                runner=self.runner_with_operator_artifact(runs),
                now_fn=lambda: "2026-06-28T12:00:00Z",
            )

            self.assertEqual(status, 0)
            self.assertTrue(manifest_path.is_file())
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["overall_status"], "pass")
            self.assertEqual(manifest["hardware_class"], "local-mac")
            self.assertEqual(manifest["luanti_commit"], "verify-success")
            self.assertEqual(manifest["game_profile"], "sample-synthetic")
            self.assertEqual(
                manifest["logical_run_dir"],
                "local/benchmarks/local-mac/2026-06-28/verify-success",
            )
            self.assertEqual(
                [step["id"] for step in manifest["steps"]],
                [
                    "utility_contract_tests",
                    "product_profile_hygiene",
                    "branch_benchmark_gate",
                    "operator_status_live_command",
                    "operator_task_control_live_probe",
                    "operator_task_control_command_probe",
                    "ai_runtime_focused_tests",
                ],
            )
            self.assertEqual(manifest["failure_reasons"], [])
            self.assertEqual(
                manifest["artifact_paths"]["product_profile_hygiene"],
                "local/benchmarks/local-mac/2026-06-28/verify-success/ai-runtime-product-profile-hygiene.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["benchmark_gate_manifest"],
                "local/benchmarks/local-mac/2026-06-28/verify-success/benchmark-gate-manifest.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["operator_status_live_command"],
                "local/benchmarks/local-mac/2026-06-28/verify-success/ai-runtime-operator-status-live.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["operator_control_report"],
                "local/benchmarks/local-mac/2026-06-28/verify-success/ai-runtime-operator-control-report.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["operator_action_approval_plan"],
                "local/benchmarks/local-mac/2026-06-28/verify-success/ai-runtime-operator-action-approval-plan.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["operator_action_approval_receipt"],
                "local/benchmarks/local-mac/2026-06-28/verify-success/ai-runtime-operator-action-approval-receipt.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["operator_action_execution_result"],
                "local/benchmarks/local-mac/2026-06-28/verify-success/ai-runtime-operator-action-execution-result.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["operator_task_control_live_result"],
                "local/benchmarks/local-mac/2026-06-28/verify-success/ai-runtime-operator-task-control-live-result.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["operator_task_control_command_result"],
                "local/benchmarks/local-mac/2026-06-28/verify-success/ai-runtime-operator-taREDACTED_KEY_FIXTURE.json",
            )
            self.assertEqual(manifest["product_profile_evidence"]["status"], "pass")
            self.assertEqual(manifest["product_profile_evidence"]["game_profile"], "ai_runtime")
            self.assertEqual(
                manifest["product_profile_evidence"]["product_mods"],
                ["ai_runtime_base"],
            )
            self.assertTrue(
                manifest["product_profile_evidence"]["dev_surfaces_disabled_by_default"]
            )
            self.assertTrue(
                manifest["product_profile_evidence"]["test_fixtures_explicit_only"]
            )
            self.assertTrue(
                manifest["product_profile_evidence"]["runtime_surfaces_available"]
            )
            self.assertEqual(
                manifest["product_profile_evidence"]["runtime_surface_count"],
                2,
            )
            self.assertEqual(
                manifest["product_profile_evidence"]["runtime_surface_commands"],
                [
                    "ai_runtime_operator_status",
                    "ai_runtime_operator_task_control",
                ],
            )
            self.assertEqual(manifest["operator_status_evidence"]["status"], "pass")
            self.assertEqual(manifest["operator_status_evidence"]["package_status"], "ready")
            self.assertEqual(
                manifest["operator_status_evidence"]["operator_control_status"],
                "pass",
            )
            self.assertEqual(
                manifest["operator_status_evidence"]["operator_control_action_mode"],
                "dry_run_only",
            )
            self.assertEqual(
                manifest["operator_status_evidence"]["operator_control_recommendations"],
                1,
            )
            self.assertEqual(
                manifest["operator_status_evidence"]["operator_control_report_status"],
                "pass",
            )
            self.assertEqual(
                manifest["operator_status_evidence"]["operator_control_report_path"],
                "local/benchmarks/local-mac/2026-06-28/verify-success/ai-runtime-operator-control-report.json",
            )
            self.assertEqual(
                manifest["operator_status_evidence"]["operator_action_approval_plan_status"],
                "pass",
            )
            self.assertEqual(
                manifest["operator_status_evidence"]["operator_action_approval_plan_path"],
                "local/benchmarks/local-mac/2026-06-28/verify-success/ai-runtime-operator-action-approval-plan.json",
            )
            self.assertEqual(
                manifest["operator_status_evidence"]["operator_action_approval_plan_items"],
                1,
            )
            self.assertEqual(
                manifest["operator_status_evidence"]["operator_action_approval_receipt_status"],
                "pass",
            )
            self.assertEqual(
                manifest["operator_status_evidence"]["operator_action_approval_receipt_path"],
                "local/benchmarks/local-mac/2026-06-28/verify-success/ai-runtime-operator-action-approval-receipt.json",
            )
            self.assertEqual(
                manifest["operator_status_evidence"]["operator_action_approval_receipt_items"],
                1,
            )
            self.assertEqual(
                manifest["operator_status_evidence"]["operator_action_execution_status"],
                "pass",
            )
            self.assertEqual(
                manifest["operator_status_evidence"]["operator_action_execution_path"],
                "local/benchmarks/local-mac/2026-06-28/verify-success/ai-runtime-operator-action-execution-result.json",
            )
            self.assertEqual(
                manifest["operator_status_evidence"]["operator_action_execution_items"],
                1,
            )
            self.assertEqual(
                manifest["operator_task_control_live_evidence"]["operator_task_control_live_status"],
                "pass",
            )
            self.assertEqual(
                manifest["operator_task_control_live_evidence"]["operator_task_control_live_items"],
                5,
            )
            self.assertEqual(
                manifest["operator_task_control_live_evidence"]["operator_task_control_live_executed"],
                2,
            )
            self.assertEqual(
                manifest["operator_task_control_live_evidence"]["operator_task_control_live_rejected"],
                3,
            )
            self.assertEqual(
                manifest["operator_task_control_command_evidence"]["operator_task_control_command_status"],
                "pass",
            )
            self.assertEqual(
                manifest["operator_task_control_command_evidence"]["operator_task_control_command_items"],
                5,
            )
            self.assertEqual(
                manifest["operator_task_control_command_evidence"]["operator_task_control_command_executed"],
                2,
            )
            self.assertEqual(
                manifest["operator_task_control_command_evidence"]["operator_task_control_command_rejected"],
                3,
            )
            self.assertEqual(
                manifest["operator_task_control_command_evidence"]["live_command"],
                "/ai_runtime_operator_task_control",
            )
            self.assertEqual(manifest["operator_status_evidence"]["output_bytes"], 1200)
            self.assertEqual(manifest["operator_status_evidence"]["max_bytes"], 24000)
            self.assertFalse(manifest["operator_status_evidence"]["truncated"])
            self.assertEqual(
                manifest["operator_status_evidence"]["source_kind"],
                "live_command",
            )
            self.assertEqual(
                manifest["operator_status_evidence"]["execution_path"],
                "disposable_worldmod_registered_chatcommand",
            )
            self.assertTrue(manifest["operator_status_evidence"]["direct_command_execution"])
            self.assertEqual(
                manifest["operator_status_evidence"]["source_path"],
                "local/benchmarks/local-mac/2026-06-28/verify-success/ai-runtime-operator-status-live.json",
            )
            self.assertNotIn("clean_profile_summary", manifest["artifact_paths"])
            self.assertFalse(manifest["run_context"]["requires_private_world"])
            self.assertFalse(manifest["run_context"]["requires_private_assets"])
            self.assertFalse(manifest["run_context"]["requires_live_pi"])
            self.assertFalse(manifest["run_context"]["requires_model_network"])

            serialized = json.dumps(manifest, sort_keys=True)
            self.assertLess(len(serialized), 12000)
            self.assertNotIn(str(output_root), serialized)
            self.assertNotRegex(serialized, PRIVATE_PATTERNS)

    def test_default_profile_records_clean_profile_workload_evidence(self):
        harness = load_harness_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            args = harness.parse_args(
                [
                    "--output-root",
                    str(output_root),
                    "--hardware-class",
                    "local-mac",
                    "--date",
                    "2026-06-28",
                    "--luanti-commit",
                    "verify-default-clean-profile",
                    "--server-bin",
                    "bin/luantiserver",
                ]
            )
            self.assertEqual(args.game_profile, "ai_runtime")
            gate_step = harness.build_steps(args)[2]
            self.assertIn("--game-profile", gate_step.actual_command)
            self.assertIn("ai_runtime", gate_step.actual_command)

            runs = iter(
                [
                    harness.CommandRun(0, 0.10, "utility tests ok", ""),
                    harness.CommandRun(0, 0.12, "product profile pass", ""),
                    harness.CommandRun(
                        0,
                        0.20,
                        "local/benchmarks/local-mac/2026-06-28/verify-default-clean-profile/benchmark-gate-manifest.json\n",
                        "",
                    ),
                    harness.CommandRun(0, 0.25, "operator status live command ok", ""),
                    harness.CommandRun(0, 0.25, "operator task control live probe ok", ""),
                    harness.CommandRun(0, 0.25, "operator task control command probe ok", ""),
                    harness.CommandRun(0, 0.30, "TestAIRuntime passed", ""),
                ]
            )

            status, _, manifest = harness.run_harness(
                args,
                runner=self.runner_with_operator_artifact(runs),
                now_fn=lambda: "2026-06-28T12:08:00Z",
            )

            self.assertEqual(status, 0)
            self.assertEqual(manifest["game_profile"], "ai_runtime")
            self.assertEqual(
                manifest["artifact_paths"]["clean_profile_summary"],
                "local/benchmarks/local-mac/2026-06-28/verify-default-clean-profile/clean-profile-benchmark-summary.json",
            )
            self.assertEqual(manifest["clean_profile_evidence"]["status"], "pass")
            self.assertEqual(
                manifest["clean_profile_evidence"]["server_step_workload_status"],
                "pass",
            )
            self.assertEqual(
                manifest["clean_profile_evidence"]["player_load_probe_status"],
                "pass",
            )
            self.assertEqual(
                manifest["clean_profile_evidence"]["map_chunk_workload_status"],
                "pass",
            )
            self.assertEqual(manifest["clean_profile_evidence"]["cpu_status"], "measured")

    def test_operator_status_accepts_live_lua_empty_operator_control_summaries(self):
        harness = load_harness_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            args = harness.parse_args(
                [
                    "--output-root",
                    str(output_root),
                    "--hardware-class",
                    "local-mac",
                    "--date",
                    "2026-06-28",
                    "--luanti-commit",
                    "verify-empty-operator-control",
                    "--server-bin",
                    "bin/luantiserver",
                ]
            )
            output_path = harness.operator_status_artifact_path(args)
            self.write_operator_status_artifact(output_path)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            payload["operator_control"]["recommendations_total"] = 0
            payload["operator_control"]["summaries"] = None
            output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            evidence, reasons = harness.operator_status_evidence(args)

            self.assertEqual(reasons, [])
            self.assertEqual(evidence["status"], "pass")
            self.assertEqual(evidence["operator_control_status"], "pass")
            self.assertEqual(evidence["operator_control_recommendations"], 0)

    def test_clean_profile_mode_records_profile_artifact_without_losing_gate_manifest(self):
        harness = load_harness_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            args = harness.parse_args(
                [
                    "--output-root",
                    str(output_root),
                    "--hardware-class",
                    "local-mac",
                    "--date",
                    "2026-06-28",
                    "--luanti-commit",
                    "verify-clean-profile",
                    "--server-bin",
                    "bin/luantiserver",
                    "--game-profile",
                    "ai_runtime",
                ]
            )
            steps = harness.build_steps(args)
            self.assertEqual(steps[1].id, "product_profile_hygiene")
            gate_step = steps[2]
            self.assertIn("--game-profile", gate_step.actual_command)
            self.assertIn("ai_runtime", gate_step.actual_command)
            self.assertIn("--server-bin", gate_step.actual_command)
            self.assertIn("bin/luantiserver", gate_step.manifest_command)

            runs = iter(
                [
                    harness.CommandRun(0, 0.10, "utility tests ok", ""),
                    harness.CommandRun(0, 0.12, "product profile pass", ""),
                    harness.CommandRun(
                        0,
                        0.20,
                        "local/benchmarks/local-mac/2026-06-28/verify-clean-profile/benchmark-gate-manifest.json\n",
                        "",
                    ),
                    harness.CommandRun(0, 0.25, "operator status live command ok", ""),
                    harness.CommandRun(0, 0.25, "operator task control live probe ok", ""),
                    harness.CommandRun(0, 0.25, "operator task control command probe ok", ""),
                    harness.CommandRun(0, 0.30, "TestAIRuntime passed", ""),
                ]
            )

            status, _, manifest = harness.run_harness(
                args,
                runner=self.runner_with_operator_artifact(runs),
                now_fn=lambda: "2026-06-28T12:02:00Z",
            )

            self.assertEqual(status, 0)
            self.assertEqual(manifest["game_profile"], "ai_runtime")
            self.assertEqual(
                manifest["artifact_paths"]["product_profile_hygiene"],
                "local/benchmarks/local-mac/2026-06-28/verify-clean-profile/ai-runtime-product-profile-hygiene.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["benchmark_gate_manifest"],
                "local/benchmarks/local-mac/2026-06-28/verify-clean-profile/benchmark-gate-manifest.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["clean_profile_summary"],
                "local/benchmarks/local-mac/2026-06-28/verify-clean-profile/clean-profile-benchmark-summary.json",
            )
            self.assertEqual(manifest["clean_profile_evidence"]["status"], "pass")
            self.assertEqual(
                manifest["clean_profile_evidence"]["source_path"],
                "local/benchmarks/local-mac/2026-06-28/verify-clean-profile/clean-profile-benchmark-summary.json",
            )
            self.assertEqual(
                manifest["clean_profile_evidence"]["server_step_workload_status"],
                "pass",
            )
            self.assertEqual(
                manifest["clean_profile_evidence"]["server_step_attempted_samples"],
                3,
            )
            self.assertEqual(
                manifest["clean_profile_evidence"]["player_load_probe_status"],
                "pass",
            )
            self.assertEqual(
                manifest["clean_profile_evidence"]["player_load_probe_kind"],
                "server_process_liveness",
            )
            self.assertFalse(manifest["clean_profile_evidence"]["headless_player_required"])
            self.assertEqual(
                manifest["clean_profile_evidence"]["map_chunk_workload_status"],
                "pass",
            )
            self.assertEqual(manifest["clean_profile_evidence"]["mapblock_rows_created"], 4)
            self.assertEqual(manifest["clean_profile_evidence"]["cpu_status"], "measured")
            self.assertEqual(manifest["clean_profile_evidence"]["cpu_sample_count"], 3)
            self.assertEqual(manifest["clean_profile_evidence"]["actionable_warning_count"], 0)
            self.assertEqual(manifest["clean_profile_evidence"]["unsafe_operation_count"], 0)
            self.assertEqual(
                manifest["artifact_paths"]["operator_status_live_command"],
                "local/benchmarks/local-mac/2026-06-28/verify-clean-profile/ai-runtime-operator-status-live.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["operator_control_report"],
                "local/benchmarks/local-mac/2026-06-28/verify-clean-profile/ai-runtime-operator-control-report.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["operator_action_approval_plan"],
                "local/benchmarks/local-mac/2026-06-28/verify-clean-profile/ai-runtime-operator-action-approval-plan.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["operator_action_approval_receipt"],
                "local/benchmarks/local-mac/2026-06-28/verify-clean-profile/ai-runtime-operator-action-approval-receipt.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["operator_action_execution_result"],
                "local/benchmarks/local-mac/2026-06-28/verify-clean-profile/ai-runtime-operator-action-execution-result.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["operator_task_control_live_result"],
                "local/benchmarks/local-mac/2026-06-28/verify-clean-profile/ai-runtime-operator-task-control-live-result.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["operator_task_control_command_result"],
                "local/benchmarks/local-mac/2026-06-28/verify-clean-profile/ai-runtime-operator-taREDACTED_KEY_FIXTURE.json",
            )
            self.assertEqual(manifest["product_profile_evidence"]["status"], "pass")
            self.assertEqual(
                manifest["product_profile_evidence"]["manifest_path"],
                "games/ai_runtime/product_profile_manifest.json",
            )
            self.assertEqual(manifest["operator_status_evidence"]["status"], "pass")
            self.assertEqual(manifest["operator_status_evidence"]["source_kind"], "live_command")
            self.assertEqual(
                manifest["operator_status_evidence"]["operator_control_report_status"],
                "pass",
            )
            self.assertEqual(
                manifest["operator_status_evidence"]["operator_action_approval_plan_status"],
                "pass",
            )
            self.assertEqual(
                manifest["operator_status_evidence"]["operator_action_approval_receipt_status"],
                "pass",
            )
            self.assertEqual(
                manifest["operator_status_evidence"]["operator_action_execution_status"],
                "pass",
            )
            self.assertEqual(
                manifest["operator_task_control_live_evidence"]["operator_task_control_live_status"],
                "pass",
            )
            self.assertEqual(
                manifest["operator_task_control_command_evidence"]["operator_task_control_command_status"],
                "pass",
            )
            self.assertIn("clean-profile verification", " ".join(manifest["notes"]))

            serialized = json.dumps(manifest, sort_keys=True)
            self.assertNotIn(str(output_root), serialized)
            self.assertNotRegex(serialized, PRIVATE_PATTERNS)

    def test_surrogate_operator_status_source_is_explicit_and_marked_in_manifest(self):
        harness = load_harness_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            args = harness.parse_args(
                [
                    "--output-root",
                    str(output_root),
                    "--hardware-class",
                    "local-mac",
                    "--date",
                    "2026-06-28",
                    "--luanti-commit",
                    "verify-surrogate",
                    "--server-bin",
                    "bin/luantiserver",
                    "--operator-status-source",
                    "surrogate",
                ]
            )
            runs = iter(
                [
                    harness.CommandRun(0, 0.10, "utility tests ok", ""),
                    harness.CommandRun(0, 0.12, "product profile pass", ""),
                    harness.CommandRun(
                        0,
                        0.20,
                        "local/benchmarks/local-mac/2026-06-28/verify-surrogate/benchmark-gate-manifest.json\n",
                        "",
                    ),
                    harness.CommandRun(0, 0.25, "operator status package ok", ""),
                    harness.CommandRun(0, 0.25, "operator task control live probe ok", ""),
                    harness.CommandRun(0, 0.25, "operator task control command probe ok", ""),
                    harness.CommandRun(0, 0.30, "TestAIRuntime passed", ""),
                ]
            )

            status, _, manifest = harness.run_harness(
                args,
                runner=self.runner_with_operator_artifact(runs),
                now_fn=lambda: "2026-06-28T12:04:00Z",
            )

            self.assertEqual(status, 0)
            self.assertEqual(
                [step["id"] for step in manifest["steps"]],
                [
                    "utility_contract_tests",
                    "product_profile_hygiene",
                    "branch_benchmark_gate",
                    "operator_status_package",
                    "operator_task_control_live_probe",
                    "operator_task_control_command_probe",
                    "ai_runtime_focused_tests",
                ],
            )
            self.assertEqual(
                manifest["artifact_paths"]["product_profile_hygiene"],
                "local/benchmarks/local-mac/2026-06-28/verify-surrogate/ai-runtime-product-profile-hygiene.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["operator_status_package"],
                "local/benchmarks/local-mac/2026-06-28/verify-surrogate/ai-runtime-operator-status.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["operator_control_report"],
                "local/benchmarks/local-mac/2026-06-28/verify-surrogate/ai-runtime-operator-control-report.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["operator_action_approval_plan"],
                "local/benchmarks/local-mac/2026-06-28/verify-surrogate/ai-runtime-operator-action-approval-plan.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["operator_action_approval_receipt"],
                "local/benchmarks/local-mac/2026-06-28/verify-surrogate/ai-runtime-operator-action-approval-receipt.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["operator_action_execution_result"],
                "local/benchmarks/local-mac/2026-06-28/verify-surrogate/ai-runtime-operator-action-execution-result.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["operator_task_control_live_result"],
                "local/benchmarks/local-mac/2026-06-28/verify-surrogate/ai-runtime-operator-task-control-live-result.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["operator_task_control_command_result"],
                "local/benchmarks/local-mac/2026-06-28/verify-surrogate/ai-runtime-operator-taREDACTED_KEY_FIXTURE.json",
            )
            self.assertEqual(manifest["operator_status_evidence"]["source_kind"], "command_surrogate")
            self.assertFalse(manifest["operator_status_evidence"]["direct_command_execution"])
            self.assertEqual(
                manifest["operator_status_evidence"]["execution_path"],
                "python_package_surrogate",
            )
            self.assertEqual(
                manifest["operator_task_control_live_evidence"]["operator_task_control_live_status"],
                "pass",
            )
            self.assertEqual(
                manifest["operator_task_control_command_evidence"]["operator_task_control_command_status"],
                "pass",
            )

    def test_clean_profile_mode_forwards_headless_player_probe_args_to_gate(self):
        harness = load_harness_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            args = harness.parse_args(
                [
                    "--output-root",
                    str(output_root),
                    "--hardware-class",
                    "local-mac",
                    "--date",
                    "2026-06-28",
                    "--luanti-commit",
                    "verify-headless",
                    "--server-bin",
                    "bin/luantiserver",
                    "--game-profile",
                    "ai_runtime",
                    "--headless-player-command",
                    "bin/luanti --config <temp-client-config> --go --address {host} --port {port}",
                    "--headless-player-count",
                    "2",
                ]
            )

            gate_step = harness.build_steps(args)[2]

            self.assertIn("--headless-player-command", gate_step.actual_command)
            self.assertIn("--headless-player-count", gate_step.actual_command)
            self.assertIn("2", gate_step.actual_command)
            self.assertIn("--headless-player-command", gate_step.manifest_command)
            self.assertIn("<headless-player-command>", gate_step.manifest_command)
            self.assertNotIn("{host}", gate_step.manifest_command)

    def test_clean_profile_summary_failure_fails_manifest_even_if_gate_exits_zero(self):
        harness = load_harness_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            args = harness.parse_args(
                [
                    "--output-root",
                    str(output_root),
                    "--hardware-class",
                    "local-mac",
                    "--date",
                    "2026-06-28",
                    "--luanti-commit",
                    "verify-clean-profile-failure",
                    "--server-bin",
                    "bin/luantiserver",
                    "--game-profile",
                    "ai_runtime",
                ]
            )
            runs = iter(
                [
                    harness.CommandRun(0, 0.10, "utility tests ok", ""),
                    harness.CommandRun(0, 0.12, "product profile pass", ""),
                    harness.CommandRun(
                        0,
                        0.20,
                        "local/benchmarks/local-mac/2026-06-28/verify-clean-profile-failure/benchmark-gate-manifest.json\n",
                        "",
                    ),
                    harness.CommandRun(0, 0.25, "operator status live command ok", ""),
                    harness.CommandRun(0, 0.25, "operator task control live probe ok", ""),
                    harness.CommandRun(0, 0.25, "operator task control command probe ok", ""),
                    harness.CommandRun(0, 0.30, "TestAIRuntime passed", ""),
                ]
            )

            def run_step(step):
                if step.id == "product_profile_hygiene":
                    output_path = pathlib.Path(
                        step.actual_command[step.actual_command.index("--output") + 1]
                    )
                    self.write_product_profile_artifact(output_path)
                if step.id == "branch_benchmark_gate":
                    self.write_clean_profile_summary_artifact(
                        self.clean_profile_summary_path_for_step(step),
                        payload={
                            "schema_version": 1,
                            "runner_version": "ai-native-clean-profile-benchmark:v1",
                            "overall_status": "fail",
                            "hardware_class": "local-mac",
                            "game_profile": {"gameid": "ai_runtime"},
                            "run_context": {
                                "mode": "clean-profile-local-server",
                                "requires_private_world": False,
                                "requires_private_assets": False,
                                "requires_live_pi": False,
                                "requires_model_network": False,
                            },
                            "failure_notes": ["server_step_workload_failed"],
                            "comparison_summary": {
                                "player_load_tick_probe": {
                                    "probe_status": "pass",
                                    "probe_kind": "server_process_liveness",
                                    "server_stayed_listening": True,
                                }
                            },
                        },
                    )
                if step.id in {"operator_status_live_command", "operator_status_package"}:
                    output_path = pathlib.Path(
                        step.actual_command[step.actual_command.index("--output") + 1]
                    )
                    self.write_operator_status_artifact(output_path)
                if step.id == "operator_task_control_live_probe":
                    output_path = pathlib.Path(
                        step.actual_command[step.actual_command.index("--output") + 1]
                    )
                    self.write_operator_task_control_live_artifact(output_path)
                if step.id == "operator_task_control_command_probe":
                    output_path = pathlib.Path(
                        step.actual_command[step.actual_command.index("--output") + 1]
                    )
                    self.write_operator_task_control_command_artifact(output_path)
                return next(runs)

            status, _, manifest = harness.run_harness(
                args,
                runner=run_step,
                now_fn=lambda: "2026-06-28T12:06:00Z",
            )

            self.assertEqual(status, 1)
            self.assertEqual(manifest["overall_status"], "fail")
            self.assertEqual(manifest["clean_profile_evidence"]["status"], "fail")
            joined_reasons = " ".join(manifest["failure_reasons"])
            self.assertIn("clean_profile_summary overall_status is not pass", joined_reasons)
            self.assertIn("clean_profile_summary failure_notes present", joined_reasons)
            self.assertIn("clean_profile_summary server_step_workload missing", joined_reasons)

    def test_clean_profile_actionable_warnings_fail_manifest_even_if_gate_exits_zero(self):
        harness = load_harness_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            args = harness.parse_args(
                [
                    "--output-root",
                    str(output_root),
                    "--hardware-class",
                    "local-mac",
                    "--date",
                    "2026-06-28",
                    "--luanti-commit",
                    "verify-clean-profile-warning-failure",
                    "--server-bin",
                    "bin/luantiserver",
                    "--game-profile",
                    "ai_runtime",
                ]
            )
            runs = iter(
                [
                    harness.CommandRun(0, 0.10, "utility tests ok", ""),
                    harness.CommandRun(0, 0.12, "product profile pass", ""),
                    harness.CommandRun(
                        0,
                        0.20,
                        "local/benchmarks/local-mac/2026-06-28/verify-clean-profile-warning-failure/benchmark-gate-manifest.json\n",
                        "",
                    ),
                    harness.CommandRun(0, 0.25, "operator status live command ok", ""),
                    harness.CommandRun(0, 0.25, "operator task control live probe ok", ""),
                    harness.CommandRun(0, 0.25, "operator task control command probe ok", ""),
                    harness.CommandRun(0, 0.30, "TestAIRuntime passed", ""),
                ]
            )

            def run_step(step):
                if step.id == "product_profile_hygiene":
                    output_path = pathlib.Path(
                        step.actual_command[step.actual_command.index("--output") + 1]
                    )
                    self.write_product_profile_artifact(output_path)
                if step.id == "branch_benchmark_gate":
                    summary_path = self.clean_profile_summary_path_for_step(step)
                    self.write_clean_profile_summary_artifact(summary_path)
                    payload = json.loads(summary_path.read_text(encoding="utf-8"))
                    for section_name in (
                        "steady_tick_behavior",
                        "server_step_workload",
                        "player_load_tick_probe",
                    ):
                        section = payload["comparison_summary"].setdefault(section_name, {})
                        section["server_log_warning_count"] = 1
                        section["expected_server_log_warning_count"] = 0
                        section["actionable_server_log_warning_count"] = 1
                        section["expected_warning_kinds"] = []
                    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                if step.id in {"operator_status_live_command", "operator_status_package"}:
                    output_path = pathlib.Path(
                        step.actual_command[step.actual_command.index("--output") + 1]
                    )
                    self.write_operator_status_artifact(output_path)
                if step.id == "operator_task_control_live_probe":
                    output_path = pathlib.Path(
                        step.actual_command[step.actual_command.index("--output") + 1]
                    )
                    self.write_operator_task_control_live_artifact(output_path)
                if step.id == "operator_task_control_command_probe":
                    output_path = pathlib.Path(
                        step.actual_command[step.actual_command.index("--output") + 1]
                    )
                    self.write_operator_task_control_command_artifact(output_path)
                return next(runs)

            status, _, manifest = harness.run_harness(
                args,
                runner=run_step,
                now_fn=lambda: "2026-06-28T12:09:00Z",
            )

            self.assertEqual(status, 1)
            self.assertEqual(manifest["clean_profile_evidence"]["status"], "fail")
            self.assertEqual(manifest["clean_profile_evidence"]["actionable_warning_count"], 3)
            self.assertIn(
                "clean_profile_summary actionable server log warnings present",
                " ".join(manifest["failure_reasons"]),
            )

    def test_clean_profile_unsafe_operation_leakage_fails_manifest_even_if_gate_exits_zero(self):
        harness = load_harness_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            args = harness.parse_args(
                [
                    "--output-root",
                    str(output_root),
                    "--hardware-class",
                    "local-mac",
                    "--date",
                    "2026-06-28",
                    "--luanti-commit",
                    "verify-clean-profile-unsafe-failure",
                    "--server-bin",
                    "bin/luantiserver",
                    "--game-profile",
                    "ai_runtime",
                ]
            )
            runs = iter(
                [
                    harness.CommandRun(0, 0.10, "utility tests ok", ""),
                    harness.CommandRun(0, 0.12, "product profile pass", ""),
                    harness.CommandRun(
                        0,
                        0.20,
                        "local/benchmarks/local-mac/2026-06-28/verify-clean-profile-unsafe-failure/benchmark-gate-manifest.json\n",
                        "",
                    ),
                    harness.CommandRun(0, 0.25, "operator status live command ok", ""),
                    harness.CommandRun(0, 0.25, "operator task control live probe ok", ""),
                    harness.CommandRun(0, 0.25, "operator task control command probe ok", ""),
                    harness.CommandRun(0, 0.30, "TestAIRuntime passed", ""),
                ]
            )

            def run_step(step):
                if step.id == "product_profile_hygiene":
                    output_path = pathlib.Path(
                        step.actual_command[step.actual_command.index("--output") + 1]
                    )
                    self.write_product_profile_artifact(output_path)
                if step.id == "branch_benchmark_gate":
                    summary_path = self.clean_profile_summary_path_for_step(step)
                    self.write_clean_profile_summary_artifact(summary_path)
                    payload = json.loads(summary_path.read_text(encoding="utf-8"))
                    payload["comparison_summary"]["mutation_write_throughput"]["unsafe_operations"] = 2
                    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                if step.id in {"operator_status_live_command", "operator_status_package"}:
                    output_path = pathlib.Path(
                        step.actual_command[step.actual_command.index("--output") + 1]
                    )
                    self.write_operator_status_artifact(output_path)
                if step.id == "operator_task_control_live_probe":
                    output_path = pathlib.Path(
                        step.actual_command[step.actual_command.index("--output") + 1]
                    )
                    self.write_operator_task_control_live_artifact(output_path)
                if step.id == "operator_task_control_command_probe":
                    output_path = pathlib.Path(
                        step.actual_command[step.actual_command.index("--output") + 1]
                    )
                    self.write_operator_task_control_command_artifact(output_path)
                return next(runs)

            status, _, manifest = harness.run_harness(
                args,
                runner=run_step,
                now_fn=lambda: "2026-06-28T12:10:00Z",
            )

            self.assertEqual(status, 1)
            self.assertEqual(manifest["clean_profile_evidence"]["status"], "fail")
            self.assertEqual(manifest["clean_profile_evidence"]["unsafe_operation_count"], 2)
            self.assertIn(
                "clean_profile_summary unsafe operation leakage present",
                " ".join(manifest["failure_reasons"]),
            )

    def test_clean_profile_headless_requirement_rejects_liveness_fallback(self):
        harness = load_harness_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            args = harness.parse_args(
                [
                    "--output-root",
                    str(output_root),
                    "--hardware-class",
                    "local-mac",
                    "--date",
                    "2026-06-28",
                    "--luanti-commit",
                    "verify-headless-required",
                    "--server-bin",
                    "bin/luantiserver",
                    "--game-profile",
                    "ai_runtime",
                    "--require-headless-player-probe",
                ]
            )
            runs = iter(
                [
                    harness.CommandRun(0, 0.10, "utility tests ok", ""),
                    harness.CommandRun(0, 0.12, "product profile pass", ""),
                    harness.CommandRun(
                        0,
                        0.20,
                        "local/benchmarks/local-mac/2026-06-28/verify-headless-required/benchmark-gate-manifest.json\n",
                        "",
                    ),
                    harness.CommandRun(0, 0.25, "operator status live command ok", ""),
                    harness.CommandRun(0, 0.25, "operator task control live probe ok", ""),
                    harness.CommandRun(0, 0.25, "operator task control command probe ok", ""),
                    harness.CommandRun(0, 0.30, "TestAIRuntime passed", ""),
                ]
            )

            status, _, manifest = harness.run_harness(
                args,
                runner=self.runner_with_operator_artifact(runs),
                now_fn=lambda: "2026-06-28T12:07:00Z",
            )

            self.assertEqual(status, 1)
            self.assertEqual(manifest["clean_profile_evidence"]["status"], "fail")
            self.assertTrue(manifest["clean_profile_evidence"]["headless_player_required"])
            self.assertIn(
                "clean_profile_summary headless player probe required but not measured",
                " ".join(manifest["failure_reasons"]),
            )

    def test_failed_command_writes_manifest_with_sanitized_failure_reason(self):
        harness = load_harness_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            args = harness.parse_args(
                [
                    "--output-root",
                    str(output_root),
                    "--hardware-class",
                    "local-mac",
                    "--date",
                    "2026-06-28",
                    "--luanti-commit",
                    "verify-failure",
                    "--server-bin",
                    "bin/luantiserver",
                ]
            )
            runs = iter(
                [
                    harness.CommandRun(0, 0.10, "utility tests ok", ""),
                    harness.CommandRun(0, 0.12, "product profile pass", ""),
                    harness.CommandRun(
                        1,
                        0.20,
                        "",
                        "benchmark failed near /Users/billevans/private and minecraftpi.home",
                    ),
                    harness.CommandRun(0, 0.25, "operator status live command ok", ""),
                    harness.CommandRun(0, 0.25, "operator task control live probe ok", ""),
                    harness.CommandRun(0, 0.25, "operator task control command probe ok", ""),
                    harness.CommandRun(0, 0.30, "TestAIRuntime passed", ""),
                ]
            )

            status, manifest_path, manifest = harness.run_harness(
                args,
                runner=self.runner_with_operator_artifact(runs),
                now_fn=lambda: "2026-06-28T12:01:00Z",
            )

            self.assertEqual(status, 1)
            self.assertTrue(manifest_path.is_file())
            self.assertEqual(manifest["overall_status"], "fail")
            self.assertEqual(manifest["steps"][2]["id"], "branch_benchmark_gate")
            self.assertEqual(manifest["steps"][2]["status"], "fail")
            self.assertEqual(manifest["steps"][2]["returncode"], 1)
            self.assertTrue(
                any(
                    "branch_benchmark_gate exited with status 1" in reason
                    for reason in manifest["failure_reasons"]
                )
            )

            serialized = json.dumps(manifest, sort_keys=True)
            self.assertNotRegex(serialized, PRIVATE_PATTERNS)

    def test_operator_status_artifact_validation_fails_private_or_oversized_output(self):
        harness = load_harness_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            args = harness.parse_args(
                [
                    "--output-root",
                    str(output_root),
                    "--hardware-class",
                    "local-mac",
                    "--date",
                    "2026-06-28",
                    "--luanti-commit",
                    "verify-operator-status-failure",
                    "--server-bin",
                    "bin/luantiserver",
                    "--operator-status-max-bytes",
                    "2000",
                ]
            )
            runs = iter(
                [
                    harness.CommandRun(0, 0.10, "utility tests ok", ""),
                    harness.CommandRun(0, 0.12, "product profile pass", ""),
                    harness.CommandRun(
                        0,
                        0.20,
                        "local/benchmarks/local-mac/2026-06-28/verify-operator-status-failure/benchmark-gate-manifest.json\n",
                        "",
                    ),
                    harness.CommandRun(0, 0.25, "operator status package ok", ""),
                    harness.CommandRun(0, 0.25, "operator task control live probe ok", ""),
                    harness.CommandRun(0, 0.25, "operator task control command probe ok", ""),
                    harness.CommandRun(0, 0.30, "TestAIRuntime passed", ""),
                ]
            )

            def run_step(step):
                if step.id == "product_profile_hygiene":
                    output_path = pathlib.Path(
                        step.actual_command[step.actual_command.index("--output") + 1]
                    )
                    self.write_product_profile_artifact(output_path)
                if step.id == "operator_status_live_command":
                    output_path = pathlib.Path(
                        step.actual_command[step.actual_command.index("--output") + 1]
                    )
                    self.write_operator_status_artifact(
                        output_path,
                        payload={
                            "schema_version": 1,
                            "package_kind": "ai_native_operator_status_package",
                            "status": "ready",
                            "runtime_context": {"game_profile": "ai_runtime"},
                            "server_profile_hygiene": {"status": "pass"},
                            "agents": {},
                            "tasks": {},
                            "rollback": {},
                            "imports": {"source": "minecraftpi.home"},
                            "benchmarks": {},
                            "operator_control": {
                                "surface_kind": "read_only_task_rollback_control",
                                "action_mode": "dry_run_only",
                                "mutation_performed": False,
                                "recommendations_total": 0,
                                "summaries": [],
                                "truncated": False,
                            },
                            "safety": {},
                            "bounds": {
                                "max_bytes": 2000,
                                "output_bytes": 2401,
                                "truncated": True,
                            },
                        },
                    )
                if step.id == "operator_task_control_live_probe":
                    output_path = pathlib.Path(
                        step.actual_command[step.actual_command.index("--output") + 1]
                    )
                    self.write_operator_task_control_live_artifact(output_path)
                if step.id == "operator_task_control_command_probe":
                    output_path = pathlib.Path(
                        step.actual_command[step.actual_command.index("--output") + 1]
                    )
                    self.write_operator_task_control_command_artifact(output_path)
                return next(runs)

            status, _, manifest = harness.run_harness(
                args,
                runner=run_step,
                now_fn=lambda: "2026-06-28T12:03:00Z",
            )

            self.assertEqual(status, 1)
            self.assertEqual(manifest["overall_status"], "fail")
            self.assertEqual(manifest["operator_status_evidence"]["status"], "fail")
            self.assertIn(
                "operator_status_live_command output_bytes exceeds max_bytes",
                " ".join(manifest["failure_reasons"]),
            )
            self.assertIn(
                "operator_status_live_command contains private patterns",
                " ".join(manifest["failure_reasons"]),
            )
            serialized = json.dumps(manifest, sort_keys=True)
            self.assertNotRegex(serialized, PRIVATE_PATTERNS)

    def test_product_profile_hygiene_failure_fails_manifest_even_if_command_exits_zero(self):
        harness = load_harness_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            args = harness.parse_args(
                [
                    "--output-root",
                    str(output_root),
                    "--hardware-class",
                    "local-mac",
                    "--date",
                    "2026-06-28",
                    "--luanti-commit",
                    "verify-profile-failure",
                    "--server-bin",
                    "bin/luantiserver",
                ]
            )
            runs = iter(
                [
                    harness.CommandRun(0, 0.10, "utility tests ok", ""),
                    harness.CommandRun(0, 0.12, "product profile wrote fail report", ""),
                    harness.CommandRun(
                        0,
                        0.20,
                        "local/benchmarks/local-mac/2026-06-28/verify-profile-failure/benchmark-gate-manifest.json\n",
                        "",
                    ),
                    harness.CommandRun(0, 0.25, "operator status live command ok", ""),
                    harness.CommandRun(0, 0.25, "operator task control live probe ok", ""),
                    harness.CommandRun(0, 0.25, "operator task control command probe ok", ""),
                    harness.CommandRun(0, 0.30, "TestAIRuntime passed", ""),
                ]
            )

            def run_step(step):
                if step.id == "product_profile_hygiene":
                    output_path = pathlib.Path(
                        step.actual_command[step.actual_command.index("--output") + 1]
                    )
                    self.write_product_profile_artifact(
                        output_path,
                        payload={
                            "schema_version": 1,
                            "status": "fail",
                            "profile": {
                                "gameid": "ai_runtime",
                                "manifest_path": "games/ai_runtime/product_profile_manifest.json",
                                "product_mods": ["ai_runtime_base", "dev_fixture"],
                            },
                            "startup_inventory": [],
                            "explicit_dev_surfaces": [],
                            "violations": [
                                {
                                    "kind": "fixture_loaded_by_default_product_profile",
                                    "name": "dev_fixture",
                                }
                            ],
                            "safety": {
                                "no_private_content": True,
                                "dev_surfaces_disabled_by_default": False,
                                "test_fixtures_explicit_only": False,
                                "runtime_surfaces_available": False,
                            },
                        },
                    )
                if step.id in {"operator_status_live_command", "operator_status_package"}:
                    output_path = pathlib.Path(
                        step.actual_command[step.actual_command.index("--output") + 1]
                    )
                    self.write_operator_status_artifact(output_path)
                if step.id == "operator_task_control_live_probe":
                    output_path = pathlib.Path(
                        step.actual_command[step.actual_command.index("--output") + 1]
                    )
                    self.write_operator_task_control_live_artifact(output_path)
                if step.id == "operator_task_control_command_probe":
                    output_path = pathlib.Path(
                        step.actual_command[step.actual_command.index("--output") + 1]
                    )
                    self.write_operator_task_control_command_artifact(output_path)
                return next(runs)

            status, _, manifest = harness.run_harness(
                args,
                runner=run_step,
                now_fn=lambda: "2026-06-28T12:05:00Z",
            )

            self.assertEqual(status, 1)
            self.assertEqual(manifest["overall_status"], "fail")
            self.assertEqual(manifest["product_profile_evidence"]["status"], "fail")
            self.assertEqual(
                manifest["product_profile_evidence"]["violation_count"],
                1,
            )
            self.assertIn(
                "product_profile_hygiene status is not pass",
                " ".join(manifest["failure_reasons"]),
            )
            self.assertIn(
                "product_profile_hygiene dev surfaces are not disabled by default",
                " ".join(manifest["failure_reasons"]),
            )
            self.assertIn(
                "product_profile_hygiene test fixtures are not explicit-only",
                " ".join(manifest["failure_reasons"]),
            )
            self.assertIn(
                "product_profile_hygiene runtime surfaces are not available",
                " ".join(manifest["failure_reasons"]),
            )
            serialized = json.dumps(manifest, sort_keys=True)
            self.assertNotRegex(serialized, PRIVATE_PATTERNS)

    def test_docs_place_one_command_harness_after_gate_and_smoke_workflow(self):
        body = DOC.read_text(encoding="utf-8")
        readme = README.read_text(encoding="utf-8")
        for phrase in (
            "util/ai_native_runtime_verify.py",
            "ai-runtime-verification-manifest.json",
            "ai-runtime-product-profile-hygiene.json",
            "ai-runtime-operator-status-live.json",
            "ai-runtime-operator-control-report.json",
            "ai-runtime-operator-action-approval-plan.json",
            "ai-runtime-operator-action-approval-receipt.json",
            "ai-runtime-operator-action-execution-result.json",
            "ai-runtime-operator-task-control-live-result.json",
            "ai-runtime-operator-taREDACTED_KEY_FIXTURE.json",
            "/ai_runtime_operator_status",
            "/ai_runtime_operator_task_control",
            "util/ai_native_operator_control_report.py",
            "util/ai_native_operator_action_approval_plan.py",
            "util/ai_native_operator_action_approval_receipt.py",
            "util/ai_native_operator_task_control_executor.py",
            "util/ai_native_operator_task_control_live_probe.py",
            "util/ai_native_operator_task_control_command_probe.py",
            "product-profile hygiene gate",
            "--operator-status-max-bytes",
            "--operator-action-approval-plan-max-bytes",
            "--operator-action-approval-receipt-max-bytes",
            "--operator-action-execution-result-max-bytes",
            "--operator-taREDACTED_KEY_FIXTURE",
            "--operator-taREDACTED_KEY_FIXTURE",
            "--operator-status-source surrogate",
            "--game-profile sample-synthetic",
            "disposable `ai_runtime` world",
            "default `ai_runtime` profile",
            "disposable live `ai_runtime` queue probe",
            "source_kind = `live_command`",
            "source_kind = `command_surrogate`",
            "operator_control",
            "dry-run-only",
            "safe next actions",
            "approval-plan artifacts",
            "receipt artifacts",
            "receipt-gated task control executor",
            "receipt-gated live task-control probe",
            "receipt-gated task-control command probe",
            "non-mutating",
            "task cancel/retry only",
            "after the branch benchmark gate and `/ai_runtime_smoke`",
            "--game-profile ai_runtime",
            "--require-headless-player-probe",
            "clean-profile-benchmark-summary.json",
            "clean_profile_evidence",
            "server_step_workload",
            "player_load_tick_probe",
            "map_chunk_workload",
            "cpu_sample_count",
            "actionable_warning_count",
            "unsafe_operation_count",
            "local/benchmarks/<hardware-class>/<date>/<commit>/",
            "no family server",
            "no model-network",
            "pre-PR",
        ):
            self.assertIn(phrase, body)
        self.assertIn("util/ai_native_runtime_verify.py", readme)
        self.assertNotRegex(body, PRIVATE_PATTERNS)


if __name__ == "__main__":
    unittest.main()
