import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest


UTIL_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UTIL_DIR))

import ai_native_compat_dry_run as compat

from ai_native_compat_dry_run import (
    build_adapter_apply_smoke,
    build_apply_plan,
    build_apply_task_definitions,
    build_report,
    build_structure_adapter_report,
    main,
    review_adapter_apply_smoke,
    validate_adapter_apply_smoke,
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

    def test_synthetic_structure_adapter_dry_run_emits_reviewable_import_action(self):
        source = self.fixture_root / "structure_adapter" / "synthetic_structure.fixture.json"

        report = build_structure_adapter_report(source)

        self.assertEqual(report["source"]["source_class"], "structure")
        self.assertEqual(report["source"]["path_policy"], "synthetic_fixture")
        self.assertEqual(report["source"]["license_status"], "synthetic")
        self.assertEqual(report["source"]["metadata"]["adapter_kind"], "synthetic_structure_v1")
        self.assertEqual(report["source"]["metadata"]["placement_count"], 5)
        self.assertEqual(report["summary"]["estimated_world_mutations"]["node_writes"], 5)
        self.assertEqual(report["summary"]["estimated_world_mutations"]["mapblock_churn"], 3)
        self.assert_safety_flags(report)
        inventory = self.inventory_by_path(report)
        self.assertEqual(inventory["synthetic_structure.fixture.json"]["source_kind"], "structure")
        self.assertEqual(inventory["synthetic_structure.fixture.json"]["classification"], "blocked")
        self.assertEqual(
            inventory["synthetic_structure.fixture.json"]["reason"],
            "synthetic_structure_adapter_review_required",
        )
        features = {item["feature"]: item for item in report["unsupported_features"]}
        self.assertEqual(features["structure.entities"]["reason"], "requires_manual_review")
        import_action = next(
            action for action in report["planned_actions"]
            if action["action"] == "import_structure"
        )
        adapter = import_action["structure_adapter"]
        self.assertTrue(adapter["synthetic"])
        self.assertEqual(adapter["adapter_kind"], "synthetic_structure_v1")
        self.assertEqual(adapter["placement_count"], 5)
        self.assertEqual(adapter["mapblock_churn"], 3)
        self.assertEqual(adapter["recommended_chunk_size"], 2)
        self.assertEqual(adapter["recommended_chunk_count"], 3)
        self.assertEqual(len(adapter["placements"]), 5)
        self.assertEqual(adapter["placements"][1]["param1"], 3)
        self.assertEqual(adapter["placements"][1]["param2"], 7)
        self.assertEqual(import_action["mutation_cost"]["node_writes"], 5)
        self.assertEqual(import_action["mutation_cost"]["mapblock_churn"], 3)
        self.assertEqual(validate_report(report), [])
        serialized = json.dumps(report)
        self.assertNotIn(str(self.fixture_root), serialized)
        self.assertNotIn("minecraft", serialized.lower())
        self.assertNotIn("asset_payload", serialized.lower())

    def test_public_safe_structure_adapter_dry_run_emits_open_format_handoff(self):
        source = self.fixture_root / "public_structure" / "open_platform.ai-structure.json"

        report = build_report(source)

        self.assertEqual(report["source"]["source_class"], "structure")
        self.assertEqual(report["source"]["path_policy"], "external_reference")
        self.assertEqual(report["source"]["license_status"], "user_supplied")
        metadata = report["source"]["metadata"]
        self.assertEqual(metadata["adapter_kind"], "public_safe_structure_v1")
        self.assertEqual(metadata["structure_format"], "ai_native_structure_v1")
        self.assertEqual(metadata["dimensions"], {"x": 35, "y": 1, "z": 1})
        self.assertEqual(metadata["placement_count"], 5)
        self.assertEqual(metadata["palette_count"], 2)
        self.assertEqual(report["summary"]["estimated_world_mutations"]["node_writes"], 5)
        self.assertEqual(report["summary"]["estimated_world_mutations"]["mapblock_churn"], 3)
        inventory = self.inventory_by_path(report)
        self.assertEqual(inventory["open_platform.ai-structure.json"]["source_kind"], "structure")
        self.assertEqual(inventory["open_platform.ai-structure.json"]["classification"], "blocked")
        self.assertEqual(
            inventory["open_platform.ai-structure.json"]["reason"],
            "public_safe_structure_adapter_review_required",
        )
        features = {item["feature"]: item for item in report["unsupported_features"]}
        self.assertEqual(features["structure.entities"]["reason"], "requires_manual_review")
        import_action = next(
            action for action in report["planned_actions"]
            if action["action"] == "import_structure"
        )
        adapter = import_action["structure_adapter"]
        self.assertFalse(adapter["synthetic"])
        self.assertTrue(adapter["public_safe"])
        self.assertEqual(adapter["adapter_kind"], "public_safe_structure_v1")
        self.assertEqual(adapter["structure_format"], "ai_native_structure_v1")
        self.assertEqual(adapter["dimensions"], {"x": 35, "y": 1, "z": 1})
        self.assertEqual(adapter["placement_count"], 5)
        self.assertEqual(adapter["mapblock_churn"], 3)
        self.assertEqual(adapter["recommended_chunk_count"], 3)
        self.assertEqual(adapter["placements"][1]["param1"], 3)
        self.assertEqual(adapter["placements"][1]["param2"], 7)
        self.assertNotIn(str(self.fixture_root), json.dumps(report))
        self.assertNotIn("asset_payload", json.dumps(report).lower())
        self.assertEqual(validate_report(report), [])

    def test_public_safe_structure_adapter_flows_through_smoke_and_operator_review(self):
        report = build_report(
            self.fixture_root / "public_structure" / "open_platform.ai-structure.json"
        )
        request = self.build_adapter_smoke_request(report)

        smoke = build_adapter_apply_smoke(report, request)
        review = review_adapter_apply_smoke(smoke)

        self.assertEqual(validate_adapter_apply_smoke(smoke), [])
        self.assertEqual(smoke["status"], "ready")
        self.assertEqual(smoke["mutation_cost_expected"]["node_writes"], 5)
        self.assertEqual(smoke["operator_summary"]["expected_apply_chunks"], 3)
        self.assertEqual(review["status"], "ready")
        self.assertTrue(review["machine_gate"]["promotable"])
        self.assertEqual(review["findings"], [])
        self.assertEqual(review["summary"]["placement_count"], 5)
        self.assertIn("rollback.execute", review["summary"]["required_capabilities"])

    def test_public_safe_structure_adapter_reports_private_references_without_importing(self):
        source = self.fixture_root / "public_structure" / "private_reference.ai-structure.json"

        report = build_report(source)

        features = {item["feature"]: item for item in report["unsupported_features"]}
        self.assertIn("structure.private_reference", features)
        self.assertEqual(
            features["structure.private_reference"]["reason"],
            "private_reference_not_imported",
        )
        import_action = next(
            action for action in report["planned_actions"]
            if action["action"] == "import_structure"
        )
        adapter = import_action["structure_adapter"]
        self.assertEqual(adapter["private_reference_count"], 1)
        self.assertNotIn("asset_payload", json.dumps(report).lower())
        self.assertNotIn("local-only-texture.png", json.dumps(report))
        self.assertIn(
            "skip_feature",
            {action["action"] for action in report["planned_actions"]},
        )
        self.assertEqual(validate_report(report), [])

    def test_public_safe_schematic_preflight_emits_structure_handoff(self):
        source = self.fixture_root / "public_schematic" / "open_platform.ai-schematic-preflight.json"

        report = build_report(source)

        self.assertEqual(report["source"]["source_class"], "structure")
        self.assertEqual(report["source"]["path_policy"], "external_reference")
        self.assertEqual(report["source"]["license_status"], "user_supplied")
        metadata = report["source"]["metadata"]
        self.assertEqual(metadata["adapter_kind"], "public_safe_structure_v1")
        self.assertEqual(metadata["source_adapter_kind"], "public_safe_schematic_preflight_v1")
        self.assertEqual(metadata["structure_format"], "ai_native_schematic_preflight_v1")
        self.assertEqual(metadata["source_format"], "schematic")
        self.assertEqual(metadata["placement_count"], 5)
        self.assertEqual(metadata["palette_count"], 3)
        self.assertEqual(report["summary"]["estimated_world_mutations"]["node_writes"], 5)
        self.assertEqual(report["summary"]["estimated_world_mutations"]["mapblock_churn"], 3)
        inventory = self.inventory_by_path(report)
        self.assertEqual(
            inventory["open_platform.ai-schematic-preflight.json"]["reason"],
            "public_safe_schematic_preflight_review_required",
        )
        features = {item["feature"]: item for item in report["unsupported_features"]}
        self.assertEqual(features["structure.block_entities"]["reason"], "requires_manual_review")
        self.assertEqual(features["structure.biomes"]["reason"], "requires_manual_review")
        import_action = next(
            action for action in report["planned_actions"]
            if action["action"] == "import_structure"
        )
        adapter = import_action["structure_adapter"]
        self.assertTrue(adapter["public_safe"])
        self.assertFalse(adapter["synthetic"])
        self.assertEqual(adapter["adapter_kind"], "public_safe_structure_v1")
        self.assertEqual(adapter["source_adapter_kind"], "public_safe_schematic_preflight_v1")
        self.assertEqual(adapter["structure_format"], "ai_native_schematic_preflight_v1")
        self.assertEqual(adapter["source_format"], "schematic")
        self.assertEqual(adapter["payload_policy"], "metadata_only")
        self.assertTrue(adapter["estimated_from_preflight"])
        self.assertEqual(adapter["placement_count"], 5)
        self.assertEqual(adapter["recommended_chunk_count"], 3)
        self.assertEqual(adapter["placements"][1]["param1"], 1)
        self.assertEqual(adapter["placements"][1]["param2"], 2)
        serialized = json.dumps(report)
        self.assertNotIn(str(self.fixture_root), serialized)
        self.assertNotIn("raw_schematic_payload", serialized.lower())
        self.assertNotIn("asset_payload", serialized.lower())
        self.assertEqual(validate_report(report), [])

    def test_public_safe_schematic_preflight_flows_through_promotion_package(self):
        source = self.fixture_root / "public_schematic" / "open_platform.ai-schematic-preflight.json"
        report, request, smoke, review = self.build_public_safe_promotion_chain(source)

        package = compat.build_structure_import_promotion_package(report, request, smoke, review)

        self.assertEqual(smoke["status"], "ready")
        self.assertEqual(review["status"], "ready")
        self.assertEqual(package["status"], "ready_for_operator_promotion")
        self.assertEqual(package["dry_run"]["structure_format"], "ai_native_schematic_preflight_v1")
        self.assertEqual(
            package["dry_run"]["source_adapter_kind"],
            "public_safe_schematic_preflight_v1",
        )
        self.assertEqual(package["apply_task_summary"]["placement_count"], 5)
        self.assertEqual(package["rollback_task_summary"]["task_count"], 1)
        self.assertTrue(package["rollback_task_summary"]["metadata_required"])

    def test_public_safe_schematic_preflight_rejects_unsafe_inputs(self):
        source = self.fixture_root / "public_schematic" / "open_platform.ai-schematic-preflight.json"
        base = json.loads(source.read_text(encoding="utf-8"))

        cases = {
            "license.rights_confirmed": lambda raw: raw["license"].update({
                "rights_confirmed": False,
            }),
            "raw_schematic_payload": lambda raw: raw.update({
                "raw_schematic_payload": "not allowed",
            }),
            "copied_protected_content": lambda raw: raw.update({
                "copied_protected_content": True,
            }),
            "private source paths": lambda raw: raw["preflight"].update({
                "source_path": "/private/operator/build.schem",
            }),
            "family_world_coordinates": lambda raw: raw.update({
                "family_world_coordinates": [{"x": 10, "y": 20, "z": 30}],
            }),
        }

        for expected_message, mutate in cases.items():
            with self.subTest(expected_message=expected_message):
                candidate = json.loads(json.dumps(base))
                mutate(candidate)
                with tempfile.TemporaryDirectory() as tmpdir:
                    path = pathlib.Path(tmpdir) / "bad.ai-schematic-preflight.json"
                    path.write_text(
                        json.dumps(candidate, indent=2, sort_keys=True),
                        encoding="utf-8",
                    )

                    with self.assertRaisesRegex(ValueError, expected_message):
                        build_report(path)

    def test_public_safe_structure_promotion_package_binds_review_chain(self):
        report, request, smoke, review = self.build_public_safe_promotion_chain()
        builder = getattr(compat, "build_structure_import_promotion_package", None)

        self.assertTrue(callable(builder), "promotion package builder is missing")
        package = builder(report, request, smoke, review)

        self.assertEqual(package["mode"], "structure_import_promotion_package")
        self.assertEqual(package["status"], "ready_for_operator_promotion")
        self.assertEqual(package["report_id"], "synthetic-report")
        self.assertEqual(package["dry_run"]["source_class"], "structure")
        self.assertEqual(package["dry_run"]["license_status"], "user_supplied")
        self.assertEqual(package["dry_run"]["rights_status"], "operator_confirmed")
        self.assertEqual(package["dry_run"]["structure_format"], "ai_native_structure_v1")
        self.assertEqual(package["operator_approval"]["approval_state"], "approved")
        self.assertEqual(package["operator_approval"]["operator"], "server")
        self.assertEqual(package["adapter_smoke_summary"]["status"], "ready_for_disposable_staging_smoke")
        self.assertEqual(package["review_gate"]["status"], "ready")
        self.assertTrue(package["review_gate"]["promotable"])
        self.assertEqual(package["apply_task_summary"]["task_count"], 1)
        self.assertEqual(package["apply_task_summary"]["placement_count"], 5)
        self.assertEqual(package["rollback_task_summary"]["task_count"], 1)
        self.assertTrue(package["rollback_task_summary"]["metadata_required"])
        self.assertEqual(package["budget_gates"]["node_writes"]["status"], "within_reviewed_limit")
        self.assertIn("import.assets", package["capability_gates"]["required_capabilities"])
        self.assertIn("rollback.execute", package["capability_gates"]["required_capabilities"])
        unsupported = package["unsupported_feature_summary"]
        self.assertEqual(unsupported["count"], len(report["unsupported_features"]))
        self.assertIn("structure.entities", {item["feature"] for item in unsupported["features"]})
        self.assertTrue(package["safety"]["public_safe_source"])
        self.assertTrue(package["safety"]["no_private_source_paths"])
        self.assertFalse(package["safety"]["world_mutation_executed"])
        serialized = json.dumps(package)
        self.assertNotIn(str(self.fixture_root), serialized)
        self.assertNotIn("asset_payload", serialized.lower())
        self.assertNotIn("server_secret_value", serialized)

    def test_structure_promotion_package_rejects_blocked_or_unsafe_artifacts(self):
        report, request, smoke, review = self.build_public_safe_promotion_chain()
        builder = getattr(compat, "build_structure_import_promotion_package", None)
        self.assertTrue(callable(builder), "promotion package builder is missing")

        cases = {
            "approved_actions must contain": lambda args: args[1].update({
                "approved_actions": [],
            }),
            "target_world.staging": lambda args: args[2]["target_world"].update({
                "staging": False,
            }),
            "live family": lambda args: args[2]["target_world"].update({
                "world_id": "family_voxelibre",
            }),
            "rollback metadata": lambda args: args[2]["rollback_plan"].update({
                "readback_required": False,
            }),
            "review gate": lambda args: args[3].update({
                "status": "blocked",
                "machine_gate": {
                    "promotable": False,
                    "world_mutation_executed": False,
                    "reviewed_for": "disposable_staging_adapter_smoke",
                },
            }),
        }

        for expected_message, mutate in cases.items():
            with self.subTest(expected_message=expected_message):
                args = [
                    json.loads(json.dumps(report)),
                    json.loads(json.dumps(request)),
                    json.loads(json.dumps(smoke)),
                    json.loads(json.dumps(review)),
                ]
                mutate(args)

                with self.assertRaisesRegex(ValueError, expected_message):
                    builder(*args)

    def test_structure_promotion_package_rejects_synthetic_structure_adapter(self):
        report = build_structure_adapter_report(
            self.fixture_root / "structure_adapter" / "synthetic_structure.fixture.json"
        )
        request = self.build_adapter_smoke_request(report)
        smoke = build_adapter_apply_smoke(report, request)
        review = review_adapter_apply_smoke(smoke)
        builder = getattr(compat, "build_structure_import_promotion_package", None)

        self.assertTrue(callable(builder), "promotion package builder is missing")
        with self.assertRaisesRegex(ValueError, "public-safe structure adapter"):
            builder(report, request, smoke, review)

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
                "max_mapblock_churn_total": 0,
                "max_manual_review_items": 10,
                "max_wall_time_ms": 5000,
            },
            "rollback_policy": {
                "policy": "no_world_mutation",
                "metadata_required": True,
            },
        }

    def build_adapter_smoke_request(self, report):
        action_index = next(
            index for index, action in enumerate(report["planned_actions"])
            if action["action"] == "import_structure"
        )
        request = self.build_apply_request(report, action_indexes=(action_index,))
        request["target_world"] = {
            "world_id": "disposable-staging-world",
            "staging": True,
            "disposable": True,
        }
        request["budget"].update({
            "max_node_writes_total": 5,
            "max_node_writes_per_step": 2,
            "max_mapblock_churn_total": 3,
            "max_manual_review_items": 3,
            "max_wall_time_ms": 5000,
        })
        request["rollback_policy"]["policy"] = "chunked"
        return request

    def build_public_safe_promotion_chain(self, source=None):
        source = source or self.fixture_root / "public_structure" / "open_platform.ai-structure.json"
        report = build_report(source)
        request = self.build_adapter_smoke_request(report)
        smoke = build_adapter_apply_smoke(report, request)
        review = review_adapter_apply_smoke(smoke)
        return report, request, smoke, review

    def build_asset_reference_request(self, report, action_names=None):
        action_names = action_names or {"map_texture", "map_sound", "copy_asset_reference"}
        action_indexes = [
            index for index, action in enumerate(report["planned_actions"])
            if action["action"] in action_names
        ]
        request = self.build_apply_request(report, action_indexes=action_indexes)
        request["report_id"] = "asset-reference-report"
        request["target_world"] = {
            "world_id": "operator-asset-manifest",
            "staging": False,
            "disposable": False,
            "world_mutation_allowed": False,
        }
        request["budget"].update({
            "max_node_writes_total": 0,
            "max_node_writes_per_step": 0,
            "max_mapblock_churn_total": 0,
        })
        request["rollback_policy"]["policy"] = "no_world_mutation"
        return request

    def test_asset_reference_promotion_package_binds_java_resource_pack_apply_plan(self):
        report = build_report(self.fixture_root / "java_pack")
        request = self.build_asset_reference_request(report)
        builder = getattr(compat, "build_asset_reference_promotion_package", None)

        self.assertTrue(callable(builder), "asset-reference promotion package builder is missing")
        package = builder(report, request)

        self.assertEqual(package["mode"], "asset_reference_promotion_package")
        self.assertEqual(package["status"], "ready_for_operator_asset_reference_promotion")
        self.assertEqual(package["report_id"], "asset-reference-report")
        self.assertEqual(package["dry_run"]["source_class"], "java_resource_pack")
        self.assertEqual(package["dry_run"]["license_status"], "user_supplied")
        self.assertEqual(package["dry_run"]["rights_status"], "operator_confirmed")
        self.assertEqual(package["dry_run"]["estimated_world_mutations"]["node_writes"], 0)
        inventory_paths = {
            entry["source_path"] for entry in package["dry_run"]["source_inventory"]
        }
        self.assertIn("pack.mcmeta", inventory_paths)
        self.assertIn("assets/synthetic/models_item.json", inventory_paths)
        approved_actions = package["approved_asset_reference_actions"]
        self.assertEqual([action["action"] for action in approved_actions], ["copy_asset_reference"])
        self.assertEqual(package["apply_plan_summary"]["status"], "planned")
        self.assertEqual(package["apply_plan_summary"]["mutation_cost_actual"]["node_writes"], 0)
        self.assertFalse(package["apply_plan_summary"]["safety"]["world_mutation_executed"])
        task_summary = package["no_world_mutation_task_summary"]
        self.assertEqual(task_summary["task_count"], 1)
        self.assertEqual(task_summary["labels"], ["compat.asset.reference"])
        self.assertEqual(task_summary["mutation_classes"], ["metadata_only"])
        self.assertEqual(task_summary["queued_task_count"], 0)
        self.assertEqual(package["budget_gates"]["node_writes"]["status"], "within_reviewed_limit")
        self.assertEqual(package["budget_gates"]["mapblock_churn"]["expected"], 0)
        self.assertIn("import.assets", package["capability_gates"]["required_capabilities"])
        self.assertEqual(package["unsupported_feature_summary"]["count"], 0)
        self.assertTrue(package["safety"]["public_safe_source"])
        self.assertTrue(package["safety"]["assets_remain_operator_supplied"])
        self.assertTrue(package["safety"]["no_asset_bytes_embedded"])
        self.assertTrue(package["safety"]["no_raw_payloads"])
        self.assertTrue(package["safety"]["no_live_family_world_mutation"])
        self.assertFalse(package["safety"]["world_mutation_executed"])
        serialized = json.dumps(package)
        self.assertNotIn(str(self.fixture_root), serialized)
        self.assertNotIn("asset_payload", serialized.lower())

    def test_asset_reference_promotion_package_supports_bedrock_metadata_pack(self):
        report = build_report(self.fixture_root / "bedrock_asset_pack")
        request = self.build_asset_reference_request(report)
        builder = getattr(compat, "build_asset_reference_promotion_package", None)

        self.assertTrue(callable(builder), "asset-reference promotion package builder is missing")
        package = builder(report, request)

        self.assertEqual(package["dry_run"]["source_class"], "bedrock_resource_pack")
        self.assertEqual(package["dry_run"]["license_status"], "user_supplied")
        self.assertEqual(package["approved_asset_reference_actions"][0]["action"], "copy_asset_reference")
        self.assertIn(
            "models/entity/example.geo.json",
            {entry["source_path"] for entry in package["dry_run"]["source_inventory"]},
        )
        self.assertEqual(package["no_world_mutation_task_summary"]["task_count"], 1)
        self.assertEqual(package["unsupported_feature_summary"]["count"], 0)

    def test_asset_reference_promotion_package_rejects_unsafe_or_mutating_inputs(self):
        base_report = build_report(self.fixture_root / "java_pack")
        base_request = self.build_asset_reference_request(base_report)
        builder = getattr(compat, "build_asset_reference_promotion_package", None)
        self.assertTrue(callable(builder), "asset-reference promotion package builder is missing")

        cases = {
            "approved_actions must contain": lambda report, request: request.update({
                "approved_actions": [],
            }),
            "user_supplied": lambda report, request: report["source"].update({
                "license_status": "unknown",
            }),
            "private source paths": lambda report, request: report["source"]["inventory"][0].update({
                "source_path": "/private/assets/example.png",
            }),
            "raw asset payloads": lambda report, request: report["source"]["inventory"][0].update({
                "asset_payload": "base64:not-allowed",
            }),
            "copied protected content": lambda report, request: report.update({
                "copied_protected_content": True,
            }),
            "behavior-script execution": lambda report, request: (
                report["planned_actions"].append({
                    "action": "execute_behavior_script",
                    "status": "blocked",
                    "description": "Do not execute source behavior scripts.",
                    "required_capabilities": ["import.assets"],
                    "mutation_cost": {
                        "node_writes": 0,
                        "mapblock_churn": 0,
                        "media_files": 0,
                        "entity_definitions": 0,
                        "manual_review_items": 1,
                    },
                }),
                request["approved_actions"].append({
                    "action_index": len(report["planned_actions"]) - 1,
                    "action": "execute_behavior_script",
                    "status": "blocked",
                }),
            ),
            "live family world": lambda report, request: request["target_world"].update({
                "world_id": "family_voxelibre",
            }),
            "world-mutating actions": lambda report, request: report["planned_actions"][0]["mutation_cost"].update({
                "node_writes": 1,
            }),
            "asset bytes": lambda report, request: report.update({
                "asset_bytes": "not-allowed",
            }),
        }

        for expected_message, mutate in cases.items():
            with self.subTest(expected_message=expected_message):
                report = json.loads(json.dumps(base_report))
                request = json.loads(json.dumps(base_request))
                mutate(report, request)

                with self.assertRaisesRegex(ValueError, expected_message):
                    builder(report, request)

    def test_asset_reference_promotion_package_cli_writes_machine_readable_artifact(self):
        report = build_report(self.fixture_root / "java_pack")
        request = self.build_asset_reference_request(report)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = pathlib.Path(tmpdir)
            report_path = tmpdir / "dry-run.json"
            request_path = tmpdir / "apply-request.json"
            package_path = tmpdir / "asset-promotion-package.json"
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
            request_path.write_text(json.dumps(request, indent=2, sort_keys=True), encoding="utf-8")
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = main([
                    "--asset-promotion-package", str(report_path),
                    "--approval", str(request_path),
                    "--output", str(package_path),
                    "--summary",
                ])

            self.assertEqual(exit_code, 0)
            package = json.loads(package_path.read_text(encoding="utf-8"))
            self.assertEqual(package["status"], "ready_for_operator_asset_reference_promotion")
            self.assertIn(
                "asset_promotion=ready_for_operator_asset_reference_promotion",
                stdout.getvalue(),
            )
            self.assertIn("asset_tasks=1", stdout.getvalue())

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
                if action == "import_structure":
                    self.assertIn("world.place", definition["required_capabilities"])
                    self.assertIn("world.batch", definition["required_capabilities"])
                self.assertEqual(definition["budget"]["max_steps_per_step"], 1)
                for budget_key, budget_value in request["budget"].items():
                    self.assertEqual(definition["budget"][budget_key], budget_value)
                self.assertEqual(definition["rollback"]["policy"], "no_world_mutation")
                self.assertTrue(definition["rollback"]["required"])
                self.assertTrue(definition["rollback"]["metadata_required"])
                self.assertEqual(definition["rollback"]["world_mutating"], requires_safe_world_ops)
                self.assertTrue(definition["inert"])
                self.assertEqual(definition["queue_state"], "not_queued")
                if action == "import_structure":
                    self.assertEqual(
                        definition["runtime_handoff"]["status"],
                        "staged_executor_available",
                    )
                    self.assertEqual(
                        definition["runtime_handoff"]["runtime_entrypoint"],
                        "core.ai_import_ops.define_structure_apply_task",
                    )
                else:
                    self.assertEqual(definition["runtime_handoff"]["status"], "staging_noop")
                self.assertFalse(definition["runtime_handoff"]["mutation_enabled"])
                self.assertEqual(definition["calibrated_cost"]["node_writes"], 0)
                self.assertIn("estimated_wall_time_ms", definition["calibrated_cost"])
                self.assertEqual(definition["provenance"]["report_id"], "synthetic-report")
                self.assertEqual(definition["provenance"]["dry_run_action"], action)
                self.assertNotIn("steps", definition)

        self.assertNotIn("payload", json.dumps(task_definitions).lower())

    def test_structure_apply_prototype_preserves_cost_and_provenance(self):
        report = build_report(self.fixture_root / "structure" / "example.mcstructure")
        action_index = next(
            index for index, action in enumerate(report["planned_actions"])
            if action["action"] == "import_structure"
        )
        request = self.build_apply_request(report, action_indexes=(action_index,))
        request["budget"].update({
            "max_node_writes_total": 1,
            "max_node_writes_per_step": 1,
            "max_mapblock_churn_total": 1,
            "max_manual_review_items": 2,
            "max_wall_time_ms": 5000,
        })
        request["rollback_policy"]["policy"] = "manifest_only"

        task_definitions = build_apply_task_definitions(report, request)
        summary = build_apply_plan(report, request)

        self.assertEqual(len(task_definitions), 1)
        definition = task_definitions[0]
        self.assertEqual(definition["label"], "compat.structure.place")
        self.assertEqual(definition["mutation_class"], "world_mutating")
        self.assertTrue(definition["requires_safe_world_ops"])
        self.assertTrue(definition["inert"])
        self.assertEqual(definition["queue_state"], "not_queued")
        self.assertEqual(definition["runtime_handoff"]["status"], "staged_executor_available")
        self.assertFalse(definition["runtime_handoff"]["mutation_enabled"])
        self.assertEqual(
            definition["runtime_handoff"]["runtime_entrypoint"],
            "core.ai_import_ops.define_structure_apply_task",
        )
        self.assertIn("import.assets", definition["required_capabilities"])
        self.assertIn("world.place", definition["required_capabilities"])
        self.assertIn("world.batch", definition["required_capabilities"])
        self.assertEqual(definition["rollback"]["policy"], "manifest_only")
        self.assertTrue(definition["rollback"]["metadata_required"])
        self.assertEqual(definition["calibrated_cost"]["node_writes"], 1)
        self.assertEqual(definition["calibrated_cost"]["mapblock_churn"], 1)
        self.assertEqual(definition["calibrated_cost"]["manual_review_items"], 2)
        self.assertGreater(definition["calibrated_cost"]["estimated_wall_time_ms"], 0)
        self.assertEqual(definition["provenance"]["source_class"], "structure")
        self.assertEqual(
            definition["provenance"]["source_reference"]["inventory_hash"],
            report["source"]["content_hashes"][0]["value"],
        )
        self.assertEqual(summary["status"], "planned")
        self.assertEqual(summary["queued_tasks"], [])
        self.assertEqual(summary["running_tasks"], [])
        self.assertFalse(summary["safety"]["world_mutation_executed"])
        self.assertEqual(summary["mutation_cost_actual"]["node_writes"], 0)
        self.assertEqual(validate_apply_summary(summary), [])

    def test_structure_adapter_apply_handoff_uses_chunked_runtime_and_rollback_entrypoints(self):
        report = build_structure_adapter_report(
            self.fixture_root / "structure_adapter" / "synthetic_structure.fixture.json"
        )
        action_index = next(
            index for index, action in enumerate(report["planned_actions"])
            if action["action"] == "import_structure"
        )
        request = self.build_apply_request(report, action_indexes=(action_index,))
        request["budget"].update({
            "max_node_writes_total": 5,
            "max_node_writes_per_step": 2,
            "max_mapblock_churn_total": 3,
            "max_manual_review_items": 3,
            "max_wall_time_ms": 5000,
        })
        request["rollback_policy"]["policy"] = "chunked"

        task_definitions = build_apply_task_definitions(report, request)
        summary = build_apply_plan(report, request)

        self.assertEqual(len(task_definitions), 1)
        definition = task_definitions[0]
        self.assertEqual(definition["label"], "compat.structure.place")
        self.assertTrue(definition["inert"])
        self.assertEqual(definition["queue_state"], "not_queued")
        self.assertEqual(definition["rollback"]["policy"], "chunked")
        self.assertEqual(definition["calibrated_cost"]["node_writes"], 5)
        self.assertEqual(definition["calibrated_cost"]["mapblock_churn"], 3)
        self.assertEqual(
            definition["runtime_handoff"]["runtime_entrypoint"],
            "core.ai_import_ops.define_chunked_structure_apply_task",
        )
        self.assertEqual(
            definition["runtime_handoff"]["rollback_plan_entrypoint"],
            "core.ai_import_ops.plan_structure_rollback",
        )
        self.assertEqual(
            definition["runtime_handoff"]["rollback_execute_entrypoint"],
            "core.ai_import_ops.queue_chunked_structure_rollback_task",
        )
        staged_apply = definition["staged_apply"]
        self.assertEqual(staged_apply["task_constructor"],
            "core.ai_import_ops.define_chunked_structure_apply_task")
        self.assertEqual(staged_apply["rollback_plan_entrypoint"],
            "core.ai_import_ops.plan_structure_rollback")
        self.assertEqual(staged_apply["rollback_execute_entrypoint"],
            "core.ai_import_ops.queue_chunked_structure_rollback_task")
        self.assertEqual(staged_apply["placement_count"], 5)
        self.assertEqual(staged_apply["chunk_size"], 2)
        self.assertEqual(staged_apply["chunk_count"], 3)
        self.assertEqual(len(staged_apply["placements"]), 5)
        self.assertEqual(staged_apply["target_world"]["world_id"], "staging-world")
        self.assertTrue(staged_apply["target_world"]["staging"])
        self.assertTrue(staged_apply["requires_explicit_approval"])
        self.assertFalse(staged_apply["allow_mutation"])
        self.assertEqual(summary["status"], "planned")
        self.assertEqual(summary["queued_tasks"], [])
        self.assertFalse(summary["safety"]["world_mutation_executed"])
        serialized = json.dumps(task_definitions)
        self.assertNotIn("payload", serialized.lower())
        self.assertNotIn(str(self.fixture_root), serialized)

    def test_adapter_apply_smoke_consumes_structure_adapter_handoff(self):
        report = build_structure_adapter_report(
            self.fixture_root / "structure_adapter" / "synthetic_structure.fixture.json"
        )
        request = self.build_adapter_smoke_request(report)

        smoke = build_adapter_apply_smoke(report, request)

        self.assertEqual(validate_adapter_apply_smoke(smoke), [])
        self.assertEqual(smoke["mode"], "adapter_apply_smoke")
        self.assertEqual(smoke["status"], "ready")
        self.assertEqual(smoke["target_world"]["world_id"], "disposable-staging-world")
        self.assertTrue(smoke["target_world"]["staging"])
        self.assertTrue(smoke["target_world"]["disposable"])
        self.assertEqual(smoke["mutation_cost_expected"]["node_writes"], 5)
        self.assertEqual(smoke["mutation_cost_expected"]["mapblock_churn"], 3)
        self.assertEqual(len(smoke["apply_tasks"]), 1)
        self.assertEqual(len(smoke["rollback_tasks"]), 1)
        apply_task = smoke["apply_tasks"][0]
        self.assertEqual(
            apply_task["entrypoint"],
            "core.ai_import_ops.define_chunked_structure_apply_task",
        )
        self.assertEqual(apply_task["placement_count"], 5)
        self.assertEqual(apply_task["chunk_size"], 2)
        self.assertEqual(apply_task["chunk_count"], 3)
        self.assertEqual(len(apply_task["placements"]), 5)
        self.assertTrue(apply_task["explicit_approval"])
        self.assertTrue(apply_task["allow_mutation"])
        self.assertEqual(apply_task["rollback_policy"], "chunked")
        self.assertIn("get_node", apply_task["operator_supplied_runtime_hooks"])
        self.assertIn("persist_record", apply_task["operator_supplied_runtime_hooks"])
        self.assertNotIn("asset_payload", json.dumps(smoke).lower())
        self.assertNotIn("private_payload", json.dumps(smoke).lower())
        self.assertNotIn(str(self.fixture_root), json.dumps(smoke))

        self.assertEqual(
            smoke["rollback_plan"]["entrypoint"],
            "core.ai_import_ops.plan_structure_rollback",
        )
        self.assertEqual(smoke["rollback_plan"]["source_task_ids"], [apply_task["task_id"]])
        self.assertFalse(smoke["rollback_plan"]["will_mutate"])
        rollback_task = smoke["rollback_tasks"][0]
        self.assertEqual(
            rollback_task["entrypoint"],
            "core.ai_import_ops.queue_chunked_structure_rollback_task",
        )
        self.assertEqual(rollback_task["source_task_id"], apply_task["task_id"])
        self.assertTrue(rollback_task["explicit_approval"])
        self.assertTrue(rollback_task["allow_mutation"])
        self.assertEqual(rollback_task["rollback_policy"], "chunked")
        self.assertIn("inspect_record", rollback_task["operator_supplied_runtime_hooks"])
        self.assertEqual(
            smoke["operator_summary"]["expected_apply_chunks"],
            3,
        )
        self.assertFalse(smoke["safety"]["world_mutation_executed"])
        self.assertTrue(smoke["safety"]["no_live_family_world_mutation"])

    def test_adapter_apply_smoke_rejects_missing_approval_and_non_staging_target(self):
        report = build_structure_adapter_report(
            self.fixture_root / "structure_adapter" / "synthetic_structure.fixture.json"
        )
        request = self.build_adapter_smoke_request(report)
        missing_approval = json.loads(json.dumps(request))
        missing_approval["approved_actions"] = []
        with self.assertRaisesRegex(ValueError, "approved_actions must contain"):
            build_adapter_apply_smoke(report, missing_approval)

        non_staging = json.loads(json.dumps(request))
        non_staging["target_world"]["staging"] = False
        with self.assertRaisesRegex(ValueError, "target_world.staging"):
            build_adapter_apply_smoke(report, non_staging)

        not_disposable = json.loads(json.dumps(request))
        not_disposable["target_world"]["disposable"] = False
        with self.assertRaisesRegex(ValueError, "target_world.disposable"):
            build_adapter_apply_smoke(report, not_disposable)

        live_family = json.loads(json.dumps(request))
        live_family["target_world"]["world_id"] = "family_voxelibre"
        with self.assertRaisesRegex(ValueError, "live family world"):
            build_adapter_apply_smoke(report, live_family)

    def test_adapter_apply_smoke_cli_writes_machine_readable_review_manifest(self):
        report = build_structure_adapter_report(
            self.fixture_root / "structure_adapter" / "synthetic_structure.fixture.json"
        )
        request = self.build_adapter_smoke_request(report)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = pathlib.Path(tmpdir)
            report_path = tmpdir / "dry-run.json"
            request_path = tmpdir / "apply-request.json"
            smoke_path = tmpdir / "adapter-smoke.json"
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
            request_path.write_text(json.dumps(request, indent=2, sort_keys=True), encoding="utf-8")
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = main([
                    "--adapter-apply-smoke", str(report_path),
                    "--approval", str(request_path),
                    "--output", str(smoke_path),
                    "--summary",
                ])

            self.assertEqual(exit_code, 0)
            smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
            self.assertEqual(validate_adapter_apply_smoke(smoke), [])
            self.assertIn("smoke=ready_for_disposable_staging_smoke", stdout.getvalue())
            self.assertIn("expected_writes=5", stdout.getvalue())

    def test_adapter_smoke_operator_review_marks_valid_manifest_ready(self):
        report = build_structure_adapter_report(
            self.fixture_root / "structure_adapter" / "synthetic_structure.fixture.json"
        )
        smoke = build_adapter_apply_smoke(report, self.build_adapter_smoke_request(report))

        review = review_adapter_apply_smoke(smoke)

        self.assertEqual(review["mode"], "adapter_apply_smoke_review")
        self.assertEqual(review["status"], "ready")
        self.assertEqual(review["report_id"], "synthetic-report")
        self.assertEqual(review["target_world"]["world_id"], "disposable-staging-world")
        self.assertEqual(review["findings"], [])
        self.assertTrue(review["machine_gate"]["promotable"])
        self.assertFalse(review["machine_gate"]["world_mutation_executed"])
        self.assertEqual(review["summary"]["apply_task_count"], 1)
        self.assertEqual(review["summary"]["rollback_task_count"], 1)
        self.assertEqual(review["summary"]["placement_count"], 5)
        self.assertEqual(review["summary"]["chunk_count"], 3)
        self.assertEqual(review["summary"]["expected_node_writes"], 5)
        self.assertEqual(review["summary"]["expected_mapblock_churn"], 3)
        self.assertIn(
            "core.ai_import_ops.define_chunked_structure_apply_task",
            review["summary"]["runtime_entrypoints"],
        )
        self.assertIn(
            "core.ai_import_ops.queue_chunked_structure_rollback_task",
            review["summary"]["runtime_entrypoints"],
        )
        self.assertIn("import.assets", review["summary"]["required_capabilities"])
        self.assertIn("rollback.execute", review["summary"]["required_capabilities"])

    def test_adapter_smoke_operator_review_blocks_unsafe_manifests(self):
        report = build_structure_adapter_report(
            self.fixture_root / "structure_adapter" / "synthetic_structure.fixture.json"
        )
        smoke = build_adapter_apply_smoke(report, self.build_adapter_smoke_request(report))

        cases = {
            "missing_explicit_approval": lambda payload: payload["apply_tasks"][0].update({
                "explicit_approval": False,
            }),
            "target_world_not_staging": lambda payload: payload["target_world"].update({
                "staging": False,
            }),
            "target_world_not_disposable": lambda payload: payload["target_world"].update({
                "disposable": False,
            }),
            "forbidden_target_world": lambda payload: payload["target_world"].update({
                "world_id": "family_voxelibre",
            }),
            "rollback_task_missing": lambda payload: payload.update({
                "rollback_tasks": [],
            }),
            "missing_runtime_hook": lambda payload: payload["apply_tasks"][0].update({
                "operator_supplied_runtime_hooks": ["get_node", "set_node"],
            }),
            "excessive_node_write_budget": lambda payload: payload["apply_tasks"][0].update({
                "max_node_writes_total": 5000,
            }),
        }

        for expected_code, mutate in cases.items():
            with self.subTest(expected_code=expected_code):
                candidate = json.loads(json.dumps(smoke))
                mutate(candidate)

                review = review_adapter_apply_smoke(candidate)

                self.assertEqual(review["status"], "blocked")
                self.assertFalse(review["machine_gate"]["promotable"])
                self.assertIn(
                    expected_code,
                    {finding["code"] for finding in review["findings"]},
                )

    def test_adapter_smoke_operator_review_cli_writes_machine_readable_gate(self):
        report = build_structure_adapter_report(
            self.fixture_root / "structure_adapter" / "synthetic_structure.fixture.json"
        )
        smoke = build_adapter_apply_smoke(report, self.build_adapter_smoke_request(report))
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = pathlib.Path(tmpdir)
            smoke_path = tmpdir / "adapter-smoke.json"
            review_path = tmpdir / "adapter-review.json"
            smoke_path.write_text(json.dumps(smoke, indent=2, sort_keys=True), encoding="utf-8")
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = main([
                    "--review-adapter-smoke", str(smoke_path),
                    "--output", str(review_path),
                    "--summary",
                ])

            self.assertEqual(exit_code, 0)
            review = json.loads(review_path.read_text(encoding="utf-8"))
            self.assertEqual(review["status"], "ready")
            self.assertTrue(review["machine_gate"]["promotable"])
            self.assertIn("review=ready", stdout.getvalue())
            self.assertIn("placements=5", stdout.getvalue())

    def test_structure_promotion_package_cli_writes_machine_readable_artifact(self):
        report, request, smoke, review = self.build_public_safe_promotion_chain()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = pathlib.Path(tmpdir)
            report_path = tmpdir / "dry-run.json"
            request_path = tmpdir / "apply-request.json"
            smoke_path = tmpdir / "adapter-smoke.json"
            review_path = tmpdir / "adapter-review.json"
            package_path = tmpdir / "promotion-package.json"
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
            request_path.write_text(json.dumps(request, indent=2, sort_keys=True), encoding="utf-8")
            smoke_path.write_text(json.dumps(smoke, indent=2, sort_keys=True), encoding="utf-8")
            review_path.write_text(json.dumps(review, indent=2, sort_keys=True), encoding="utf-8")
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                try:
                    exit_code = main([
                        "--promotion-package", str(report_path),
                        "--approval", str(request_path),
                        "--adapter-smoke", str(smoke_path),
                        "--adapter-review", str(review_path),
                        "--output", str(package_path),
                        "--summary",
                    ])
                except SystemExit as exc:
                    exit_code = exc.code

            self.assertEqual(exit_code, 0)
            package = json.loads(package_path.read_text(encoding="utf-8"))
            self.assertEqual(package["status"], "ready_for_operator_promotion")
            self.assertIn("promotion=ready_for_operator_promotion", stdout.getvalue())
            self.assertIn("rollback_tasks=1", stdout.getvalue())

    def test_structure_apply_rejects_over_budget_request(self):
        report = build_report(self.fixture_root / "structure" / "example.mcstructure")
        action_index = next(
            index for index, action in enumerate(report["planned_actions"])
            if action["action"] == "import_structure"
        )
        request = self.build_apply_request(report, action_indexes=(action_index,))
        request["rollback_policy"]["policy"] = "manifest_only"

        with self.assertRaisesRegex(ValueError, "budget.max_node_writes_total"):
            build_apply_task_definitions(report, request)

    def test_structure_apply_rejects_no_mutation_rollback_policy(self):
        report = build_report(self.fixture_root / "structure" / "example.mcstructure")
        action_index = next(
            index for index, action in enumerate(report["planned_actions"])
            if action["action"] == "import_structure"
        )
        request = self.build_apply_request(report, action_indexes=(action_index,))
        request["budget"].update({
            "max_node_writes_total": 1,
            "max_node_writes_per_step": 1,
            "max_mapblock_churn_total": 1,
            "max_manual_review_items": 2,
        })

        with self.assertRaisesRegex(ValueError, "manifest_only, snapshot, or chunked"):
            build_apply_task_definitions(report, request)

    def test_apply_plan_builds_no_mutation_summary(self):
        report = build_report(self.fixture_root / "bedrock_pack")
        request = self.build_apply_request(report, action_indexes=(0, 1))

        summary = build_apply_plan(report, request)

        self.assertEqual(summary["status"], "planned")
        self.assertEqual(summary["report_id"], "synthetic-report")
        self.assertEqual(validate_apply_summary(summary), [])
        self.assertEqual(summary["queued_tasks"], [])
        self.assertEqual(summary["running_tasks"], [])
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
