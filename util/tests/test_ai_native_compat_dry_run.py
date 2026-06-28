import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest


UTIL_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UTIL_DIR))

from ai_native_compat_dry_run import (
    build_apply_plan,
    build_apply_task_definitions,
    build_report,
    main,
    validate_apply_summary,
    validate_report,
)


class CompatibilityDryRunTests(unittest.TestCase):
    def setUp(self):
        self.fixture_root = pathlib.Path(__file__).resolve().parent / "fixtures" / "compat"

    def assert_safety_flags(self, report):
        self.assertTrue(report["safety"]["no_assets_copied"])
        self.assertTrue(report["safety"]["no_world_mutation"])
        self.assertTrue(report["safety"]["source_paths_redacted"])
        self.assertTrue(report["safety"]["user_rights_required"])

    def inventory_by_path(self, report):
        return {
            entry["source_path"]: entry
            for entry in report["source"]["inventory"]
        }

    def test_bedrock_manifest_report_has_safety_and_unsupported_rows(self):
        source = self.fixture_root / "bedrock_pack"

        report = build_report(source)

        self.assertIn("report_version", report)
        self.assertIn("source", report)
        self.assertEqual(report["report_version"], 1)
        self.assertEqual(report["mode"], "dry_run")
        self.assertEqual(report["source"]["source_class"], "bedrock_resource_pack")
        self.assertEqual(report["source"]["path_policy"], "external_reference")
        self.assertEqual(report["source"]["license_status"], "user_supplied")
        self.assert_safety_flags(report)

        features = {item["feature"]: item for item in report["unsupported_features"]}
        self.assertEqual(
            features["entity.behavior_script"]["reason"],
            "behavior_script_not_supported",
        )
        self.assertEqual(features["entity.ai_goal"]["reason"], "entity_ai_not_supported")
        inventory = self.inventory_by_path(report)
        self.assertEqual(inventory["manifest.json"]["classification"], "mapped")
        self.assertEqual(inventory["entities/example.entity.json"]["classification"], "blocked")
        self.assertEqual(inventory["scripts/main.js"]["classification"], "unsupported")
        self.assertTrue(
            all("import.assets" in entry["required_capabilities"]
                for entry in inventory.values())
        )
        self.assertNotIn(str(source), json.dumps(report))
        self.assertTrue(
            all("import.assets" in action["required_capabilities"]
                for action in report["planned_actions"])
        )

    def test_java_pack_report_classifies_metadata_and_language_assets(self):
        source = self.fixture_root / "java_pack"

        report = build_report(source)

        self.assertIn("source", report)
        self.assertIn("summary", report)
        self.assertEqual(report["source"]["source_class"], "java_resource_pack")
        self.assertEqual(report["summary"]["risk_level"], "low")
        self.assert_safety_flags(report)
        sections = {section["name"]: section for section in report["sections"]}
        self.assertEqual(sections["metadata"]["status"], "supported")
        self.assertEqual(sections["models"]["status"], "partial")
        self.assertEqual(report["summary"]["estimated_world_mutations"]["node_writes"], 0)
        inventory = self.inventory_by_path(report)
        self.assertEqual(inventory["pack.mcmeta"]["classification"], "mapped")
        self.assertEqual(inventory["assets/synthetic/models_item.json"]["classification"], "blocked")

    def test_source_inventory_classifies_structure_world_and_mod_metadata(self):
        structure = build_report(self.fixture_root / "structure" / "example.mcstructure")
        structure_inventory = self.inventory_by_path(structure)

        self.assertEqual(structure["source"]["source_class"], "structure")
        self.assertEqual(structure["summary"]["risk_level"], "high")
        self.assertEqual(structure_inventory["example.mcstructure"]["source_kind"], "structure")
        self.assertEqual(structure_inventory["example.mcstructure"]["classification"], "blocked")
        self.assertEqual(structure["summary"]["estimated_world_mutations"]["node_writes"], 1)
        self.assertEqual(structure["summary"]["estimated_world_mutations"]["mapblock_churn"], 1)
        self.assertEqual(structure["summary"]["estimated_world_mutations"]["manual_review_items"], 2)
        sections = {section["name"]: section for section in structure["sections"]}
        self.assertEqual(sections["structures"]["counts"]["estimated_node_writes"], 1)
        self.assertEqual(sections["structures"]["counts"]["estimated_mapblock_churn"], 1)
        import_action = next(
            action for action in structure["planned_actions"]
            if action["action"] == "import_structure"
        )
        self.assertEqual(import_action["mutation_cost"]["node_writes"], 1)
        self.assertEqual(import_action["mutation_cost"]["mapblock_churn"], 1)
        self.assertEqual(import_action["mutation_cost"]["manual_review_items"], 2)
        self.assertIn(
            "import_structure",
            {action["action"] for action in structure["planned_actions"]},
        )
        self.assertEqual(validate_report(structure), [])

        world = build_report(self.fixture_root / "world_export")
        world_inventory = self.inventory_by_path(world)
        self.assertEqual(world["source"]["source_class"], "world")
        self.assertEqual(world_inventory["level.dat"]["source_kind"], "world")
        self.assertEqual(world_inventory["level.dat"]["classification"], "blocked")
        self.assertIn(
            "world.format",
            {feature["feature"] for feature in world["unsupported_features"]},
        )
        self.assertEqual(validate_report(world), [])

        luanti_mod = build_report(self.fixture_root / "luanti_mod")
        mod_inventory = self.inventory_by_path(luanti_mod)
        self.assertEqual(luanti_mod["source"]["source_class"], "luanti_mod")
        self.assertEqual(luanti_mod["source"]["metadata"]["mod_name"], "synthetic_compat_mod")
        self.assertEqual(mod_inventory["mod.conf"]["source_kind"], "mod_metadata")
        self.assertEqual(mod_inventory["mod.conf"]["classification"], "mapped")
        self.assertEqual(mod_inventory["depends.txt"]["classification"], "mapped")
        self.assertNotIn(str(self.fixture_root), json.dumps(luanti_mod))
        self.assertEqual(validate_report(luanti_mod), [])

    def test_cli_writes_json_report_and_summary(self):
        source = self.fixture_root / "bedrock_pack"
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = pathlib.Path(tmpdir) / "report.json"
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = main([str(source), "--output", str(output_path), "--summary"])

            self.assertEqual(exit_code, 0)
            report = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(report["mode"], "dry_run")
            self.assertIn("risk=", stdout.getvalue())
            self.assertIn("unsupported=", stdout.getvalue())

    def test_generated_reports_validate_required_contract(self):
        for fixture_name in ("bedrock_pack", "java_pack"):
            with self.subTest(fixture=fixture_name):
                report = build_report(self.fixture_root / fixture_name)

                self.assertEqual(validate_report(report), [])

    def test_validator_rejects_missing_required_fields(self):
        report = build_report(self.fixture_root / "java_pack")
        del report["summary"]["risk_level"]

        errors = validate_report(report)

        self.assertIn("summary.risk_level is required", errors)

    def test_validator_rejects_false_or_missing_safety_flags(self):
        report = build_report(self.fixture_root / "bedrock_pack")
        report["safety"]["no_world_mutation"] = False
        del report["safety"]["source_paths_redacted"]

        errors = validate_report(report)

        self.assertIn("safety.no_world_mutation must be true", errors)
        self.assertIn("safety.source_paths_redacted is required", errors)

    def test_validator_rejects_silently_dropped_unsupported_rows(self):
        report = build_report(self.fixture_root / "bedrock_pack")
        report["unsupported_features"] = [
            item for item in report["unsupported_features"]
            if item["feature"] != "entity.ai_goal"
        ]

        errors = validate_report(
            report,
            expected_unsupported_features={"entity.behavior_script", "entity.ai_goal"},
        )

        self.assertIn("unsupported_features missing expected feature entity.ai_goal", errors)

    def test_fixture_policy_is_documented_and_payloads_are_metadata_only(self):
        readme = self.fixture_root / "README.md"

        self.assertTrue(readme.is_file())
        self.assertIn("Synthetic", readme.read_text(encoding="utf-8"))
        for path in self.fixture_root.rglob("*"):
            if not path.is_file():
                continue
            self.assertLess(path.stat().st_size, 4096, path)
            self.assertIn(
                path.suffix,
                {".json", ".js", ".mcmeta", ".md", ".mcstructure", ".dat", ".conf", ".txt"},
            )

    def build_apply_request(self, report, action_indexes=(0,)):
        inventory_hash = report["source"]["content_hashes"][0]["value"]
        approved_actions = []
        for action_index in action_indexes:
            action = report["planned_actions"][action_index]
            approved_actions.append({
                "action_index": action_index,
                "action": action["action"],
                "status": action["status"],
            })
        return {
            "request_version": 1,
            "mode": "apply_plan",
            "report_id": "synthetic-report",
            "report_version": report["report_version"],
            "source_reference": {
                "reference_type": "mounted_fixture",
                "redacted_id": report["source"]["source_id"],
                "inventory_hash": inventory_hash,
            },
            "approved_actions": approved_actions,
            "target_world": {
                "world_id": "staging-world",
                "staging": True,
            },
            "operator": "server",
            "agent_id": "compat_import:server",
            "budget": {
                "max_media_files": 10,
                "max_entity_definitions": 5,
                "max_node_writes_total": 0,
                "max_node_writes_per_step": 0,
                "max_manual_review_items": 10,
                "max_wall_time_ms": 5000,
            },
            "rollback_policy": {
                "policy": "no_world_mutation",
                "metadata_required": True,
            },
        }

    def synthetic_planned_action(self, action, status="partial"):
        return {
            "action": action,
            "status": status,
            "description": f"Synthetic {action} action.",
            "required_capabilities": ["import.assets"],
            "mutation_cost": {
                "node_writes": 0,
                "mapblock_churn": 0,
                "media_files": 1 if action in {"map_texture", "map_sound"} else 0,
                "entity_definitions": 1 if action == "register_entity_stub" else 0,
                "manual_review_items": 1 if action == "skip_feature" else 0,
            },
        }

    def test_task_definition_mapping_covers_approved_compatibility_actions(self):
        report = build_report(self.fixture_root / "bedrock_pack")
        report["planned_actions"] = [
            self.synthetic_planned_action("map_texture"),
            self.synthetic_planned_action("map_sound"),
            self.synthetic_planned_action("register_entity_stub"),
            self.synthetic_planned_action("register_node_alias"),
            self.synthetic_planned_action("import_structure"),
            self.synthetic_planned_action("skip_feature", status="skipped"),
        ]
        request = self.build_apply_request(
            report,
            action_indexes=range(len(report["planned_actions"])),
        )

        task_definitions = build_apply_task_definitions(report, request)

        expected = {
            "map_texture": ("compat.media.texture", "metadata_only", False),
            "map_sound": ("compat.media.sound", "metadata_only", False),
            "register_entity_stub": ("compat.entity.stub", "metadata_only", False),
            "register_node_alias": ("compat.node.alias", "metadata_only", False),
            "import_structure": ("compat.structure.place", "world_mutating", True),
            "skip_feature": ("compat.feature.skip", "none", False),
        }
        self.assertEqual(len(task_definitions), len(expected))
        for index, definition in enumerate(task_definitions):
            action = report["planned_actions"][index]["action"]
            label, mutation_class, requires_safe_world_ops = expected[action]
            with self.subTest(action=action):
                self.assertEqual(definition["task_id"], f"compat:synthetic-report:{index}")
                self.assertEqual(definition["agent_id"], "compat_import:server")
                self.assertEqual(definition["owner"], "server")
                self.assertEqual(definition["label"], label)
                self.assertEqual(definition["mutation_class"], mutation_class)
                self.assertEqual(definition["requires_safe_world_ops"], requires_safe_world_ops)
                self.assertEqual(definition["source_action"]["action_index"], index)
                self.assertEqual(definition["source_action"]["action"], action)
                self.assertEqual(definition["source_action"]["status"], report["planned_actions"][index]["status"])
                self.assertIn("import.assets", definition["required_capabilities"])
                self.assertEqual(definition["budget"]["max_steps_per_step"], 1)
                for budget_key, budget_value in request["budget"].items():
                    self.assertEqual(definition["budget"][budget_key], budget_value)
                self.assertEqual(definition["rollback"]["policy"], "no_world_mutation")
                self.assertTrue(definition["rollback"]["required"])
                self.assertTrue(definition["rollback"]["metadata_required"])
                self.assertEqual(definition["rollback"]["world_mutating"], requires_safe_world_ops)
                self.assertTrue(definition["inert"])
                self.assertEqual(definition["queue_state"], "not_queued")
                self.assertNotIn("steps", definition)

        self.assertNotIn("payload", json.dumps(task_definitions).lower())

    def test_apply_plan_builds_no_mutation_summary(self):
        report = build_report(self.fixture_root / "bedrock_pack")
        request = self.build_apply_request(report, action_indexes=(0, 1))

        summary = build_apply_plan(report, request)

        self.assertEqual(summary["status"], "planned")
        self.assertEqual(summary["report_id"], "synthetic-report")
        self.assertEqual(validate_apply_summary(summary), [])
        self.assertEqual(summary["queued_tasks"], [])
        self.assertEqual(summary["completed_tasks"], [])
        self.assertEqual(summary["blocked_tasks"], [])
        self.assertEqual(summary["mutation_cost_actual"]["node_writes"], 0)
        self.assertEqual(summary["mutation_cost_actual"]["mapblock_churn"], 0)
        self.assertEqual(summary["mutation_cost_actual"]["media_files"], 0)
        self.assertEqual(summary["mutation_cost_actual"]["entity_definitions"], 0)
        self.assertEqual(summary["safety"]["world_mutation_executed"], False)
        self.assertEqual(summary["safety"]["assets_remain_operator_supplied"], True)
        self.assertEqual(summary["safety"]["dry_run_report_unchanged"], True)
        self.assertNotIn("payload", json.dumps(summary).lower())

    def test_apply_plan_rejects_missing_approval_budget_and_rollback(self):
        report = build_report(self.fixture_root / "bedrock_pack")
        request = self.build_apply_request(report)
        del request["approved_actions"]
        del request["budget"]
        del request["rollback_policy"]

        with self.assertRaisesRegex(ValueError, "approved_actions is required"):
            build_apply_plan(report, request)

    def test_apply_plan_rejects_unknown_planned_action_reference(self):
        report = build_report(self.fixture_root / "bedrock_pack")
        request = self.build_apply_request(report)
        request["approved_actions"][0]["action_index"] = len(report["planned_actions"]) + 10

        with self.assertRaisesRegex(ValueError, "approved action index"):
            build_apply_plan(report, request)

    def test_apply_plan_cli_writes_summary_and_preserves_report(self):
        report = build_report(self.fixture_root / "bedrock_pack")
        request = self.build_apply_request(report, action_indexes=(0, 1))
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = pathlib.Path(tmpdir)
            report_path = tmpdir / "dry-run.json"
            request_path = tmpdir / "apply-request.json"
            summary_path = tmpdir / "apply-summary.json"
            report_payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
            report_path.write_text(report_payload, encoding="utf-8")
            request_path.write_text(json.dumps(request, indent=2, sort_keys=True), encoding="utf-8")

            exit_code = main([
                "--apply-plan", str(report_path),
                "--approval", str(request_path),
                "--output", str(summary_path),
            ])

            self.assertEqual(exit_code, 0)
            self.assertEqual(report_path.read_text(encoding="utf-8"), report_payload)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(validate_apply_summary(summary), [])
            self.assertEqual(summary["status"], "planned")
            self.assertEqual(summary["safety"]["world_mutation_executed"], False)
            self.assertEqual(
                sorted(path.name for path in tmpdir.iterdir()),
                ["apply-request.json", "apply-summary.json", "dry-run.json"],
            )

    def test_apply_plan_cli_rejects_missing_approval_file(self):
        report = build_report(self.fixture_root / "bedrock_pack")
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = pathlib.Path(tmpdir) / "dry-run.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                exit_code = main(["--apply-plan", str(report_path)])

            self.assertNotEqual(exit_code, 0)
            self.assertIn("--approval is required", stderr.getvalue())

    def test_apply_plan_cli_rejects_missing_budget_and_rollback(self):
        report = build_report(self.fixture_root / "bedrock_pack")
        request = self.build_apply_request(report)
        for removed_field in ("budget", "rollback_policy"):
            with self.subTest(removed_field=removed_field):
                broken_request = json.loads(json.dumps(request))
                del broken_request[removed_field]
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmpdir = pathlib.Path(tmpdir)
                    report_path = tmpdir / "dry-run.json"
                    request_path = tmpdir / "apply-request.json"
                    report_path.write_text(json.dumps(report), encoding="utf-8")
                    request_path.write_text(json.dumps(broken_request), encoding="utf-8")
                    stderr = io.StringIO()

                    with contextlib.redirect_stderr(stderr):
                        exit_code = main([
                            "--apply-plan", str(report_path),
                            "--approval", str(request_path),
                        ])

                    self.assertNotEqual(exit_code, 0)
                    self.assertIn(f"{removed_field} is required", stderr.getvalue())

    def test_apply_plan_cli_rejects_missing_planned_action_reference(self):
        report = build_report(self.fixture_root / "bedrock_pack")
        request = self.build_apply_request(report)
        request["approved_actions"][0]["action_index"] = len(report["planned_actions"]) + 1
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = pathlib.Path(tmpdir)
            report_path = tmpdir / "dry-run.json"
            request_path = tmpdir / "apply-request.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            request_path.write_text(json.dumps(request), encoding="utf-8")
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                exit_code = main([
                    "--apply-plan", str(report_path),
                    "--approval", str(request_path),
                ])

            self.assertNotEqual(exit_code, 0)
            self.assertIn("approved action index", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
