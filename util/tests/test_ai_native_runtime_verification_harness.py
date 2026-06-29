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
    r"sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload|/Users/",
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

    def runner_with_operator_artifact(self, runs):
        def run_step(step):
            if step.id in {"operator_status_live_command", "operator_status_package"}:
                output_path = pathlib.Path(
                    step.actual_command[step.actual_command.index("--output") + 1]
                )
                source = "live_command" if step.id == "operator_status_live_command" else "command_surrogate"
                self.write_operator_status_artifact(output_path, source=source)
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
                ]
            )
            runs = iter(
                [
                    harness.CommandRun(0, 0.10, "utility tests ok", ""),
                    harness.CommandRun(
                        0,
                        0.20,
                        "local/benchmarks/local-mac/2026-06-28/verify-success/benchmark-gate-manifest.json\n",
                        "",
                    ),
                    harness.CommandRun(0, 0.25, "operator status live command ok", ""),
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
                    "branch_benchmark_gate",
                    "operator_status_live_command",
                    "ai_runtime_focused_tests",
                ],
            )
            self.assertEqual(manifest["failure_reasons"], [])
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
            gate_step = steps[1]
            self.assertIn("--game-profile", gate_step.actual_command)
            self.assertIn("ai_runtime", gate_step.actual_command)
            self.assertIn("--server-bin", gate_step.actual_command)
            self.assertIn("bin/luantiserver", gate_step.manifest_command)

            runs = iter(
                [
                    harness.CommandRun(0, 0.10, "utility tests ok", ""),
                    harness.CommandRun(
                        0,
                        0.20,
                        "local/benchmarks/local-mac/2026-06-28/verify-clean-profile/benchmark-gate-manifest.json\n",
                        "",
                    ),
                    harness.CommandRun(0, 0.25, "operator status live command ok", ""),
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
                manifest["artifact_paths"]["benchmark_gate_manifest"],
                "local/benchmarks/local-mac/2026-06-28/verify-clean-profile/benchmark-gate-manifest.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["clean_profile_summary"],
                "local/benchmarks/local-mac/2026-06-28/verify-clean-profile/clean-profile-benchmark-summary.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["operator_status_live_command"],
                "local/benchmarks/local-mac/2026-06-28/verify-clean-profile/ai-runtime-operator-status-live.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["operator_control_report"],
                "local/benchmarks/local-mac/2026-06-28/verify-clean-profile/ai-runtime-operator-control-report.json",
            )
            self.assertEqual(manifest["operator_status_evidence"]["status"], "pass")
            self.assertEqual(manifest["operator_status_evidence"]["source_kind"], "live_command")
            self.assertEqual(
                manifest["operator_status_evidence"]["operator_control_report_status"],
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
                    harness.CommandRun(
                        0,
                        0.20,
                        "local/benchmarks/local-mac/2026-06-28/verify-surrogate/benchmark-gate-manifest.json\n",
                        "",
                    ),
                    harness.CommandRun(0, 0.25, "operator status package ok", ""),
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
                    "branch_benchmark_gate",
                    "operator_status_package",
                    "ai_runtime_focused_tests",
                ],
            )
            self.assertEqual(
                manifest["artifact_paths"]["operator_status_package"],
                "local/benchmarks/local-mac/2026-06-28/verify-surrogate/ai-runtime-operator-status.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["operator_control_report"],
                "local/benchmarks/local-mac/2026-06-28/verify-surrogate/ai-runtime-operator-control-report.json",
            )
            self.assertEqual(manifest["operator_status_evidence"]["source_kind"], "command_surrogate")
            self.assertFalse(manifest["operator_status_evidence"]["direct_command_execution"])
            self.assertEqual(
                manifest["operator_status_evidence"]["execution_path"],
                "python_package_surrogate",
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

            gate_step = harness.build_steps(args)[1]

            self.assertIn("--headless-player-command", gate_step.actual_command)
            self.assertIn("--headless-player-count", gate_step.actual_command)
            self.assertIn("2", gate_step.actual_command)
            self.assertIn("--headless-player-command", gate_step.manifest_command)
            self.assertIn("<headless-player-command>", gate_step.manifest_command)
            self.assertNotIn("{host}", gate_step.manifest_command)

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
                    harness.CommandRun(
                        1,
                        0.20,
                        "",
                        "benchmark failed near /Users/billevans/private and minecraftpi.home",
                    ),
                    harness.CommandRun(0, 0.25, "operator status live command ok", ""),
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
            self.assertEqual(manifest["steps"][1]["id"], "branch_benchmark_gate")
            self.assertEqual(manifest["steps"][1]["status"], "fail")
            self.assertEqual(manifest["steps"][1]["returncode"], 1)
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
                    harness.CommandRun(
                        0,
                        0.20,
                        "local/benchmarks/local-mac/2026-06-28/verify-operator-status-failure/benchmark-gate-manifest.json\n",
                        "",
                    ),
                    harness.CommandRun(0, 0.25, "operator status package ok", ""),
                    harness.CommandRun(0, 0.30, "TestAIRuntime passed", ""),
                ]
            )

            def run_step(step):
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

    def test_docs_place_one_command_harness_after_gate_and_smoke_workflow(self):
        body = DOC.read_text(encoding="utf-8")
        readme = README.read_text(encoding="utf-8")
        for phrase in (
            "util/ai_native_runtime_verify.py",
            "ai-runtime-verification-manifest.json",
            "ai-runtime-operator-status-live.json",
            "ai-runtime-operator-control-report.json",
            "/ai_runtime_operator_status",
            "util/ai_native_operator_control_report.py",
            "--operator-status-max-bytes",
            "--operator-status-source surrogate",
            "disposable `ai_runtime` world",
            "source_kind = `live_command`",
            "source_kind = `command_surrogate`",
            "operator_control",
            "dry-run-only",
            "safe next actions",
            "after the branch benchmark gate and `/ai_runtime_smoke`",
            "--game-profile ai_runtime",
            "clean-profile-benchmark-summary.json",
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
