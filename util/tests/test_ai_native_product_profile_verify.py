import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = ROOT / "util" / "ai_native_product_profile_verify.py"
MANIFEST = ROOT / "games" / "ai_runtime" / "product_profile_manifest.json"
BUILTIN_INIT = ROOT / "builtin" / "game" / "init.lua"


def load_verifier_module():
    assert CLI.is_file(), f"missing {CLI}"
    spec = importlib.util.spec_from_file_location("ai_native_product_profile_verify", CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AIProductProfileVerifierTests(unittest.TestCase):
    def test_manifest_declares_product_mods_and_explicit_dev_surfaces(self):
        self.assertTrue(MANIFEST.is_file(), f"missing {MANIFEST}")
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["gameid"], "ai_runtime")
        self.assertEqual(manifest["product_mods"], ["ai_runtime_base"])
        self.assertEqual(
            {
                surface["name"]: surface["setting"]
                for surface in manifest["explicit_dev_surfaces"]
            },
            {
                "ai_runtime_smoke": "ai_runtime.enable_smoke_command",
                "ai_demo_entity_benchmark": "ai_runtime.enable_demo_benchmark_command",
            },
        )
        self.assertIn("builtin/game/tests/test_ai_runtime.lua", manifest["test_only_files"])
        self.assertIn("util/tests/fixtures/compat", manifest["test_only_paths"])

    def test_manifest_inventory_classifies_product_and_fixture_surfaces(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

        inventory = manifest["startup_inventory"]
        categories = {entry["category"] for entry in inventory}

        self.assertEqual(
            categories,
            {
                "product_runtime",
                "first_party_plugin",
                "benchmark_fixture",
                "compatibility_fixture",
                "unit_test_helper",
            },
        )
        default_loaded = {
            entry["name"]
            for entry in inventory
            if entry["loaded_by_default_product_profile"] is True
        }
        self.assertEqual(
            default_loaded,
            {
                "ai_runtime_game",
                "ai_runtime_base",
                "ai_operator_status",
                "ai_operator_task_control",
            },
        )
        for entry in inventory:
            if entry["category"] != "product_runtime" and entry["name"] != "ai_runtime_base":
                self.assertFalse(entry["loaded_by_default_product_profile"], entry)
                self.assertTrue(entry["requires_explicit_dev_or_test_lane"], entry)

    def test_manifest_declares_required_clean_runtime_command_surfaces(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

        surfaces = {surface["name"]: surface for surface in manifest["required_runtime_surfaces"]}

        self.assertEqual(
            set(surfaces),
            {"ai_operator_status", "ai_operator_task_control"},
        )
        self.assertEqual(
            surfaces["ai_operator_status"],
            {
                "name": "ai_operator_status",
                "source_file": "builtin/game/ai_operator_status.lua",
                "command": "ai_runtime_operator_status",
                "privilege": "server",
                "mutation_scope": "read_only_status",
                "loaded_by_default_product_profile": True,
                "public_safe_output_required": True,
            },
        )
        self.assertEqual(
            surfaces["ai_operator_task_control"],
            {
                "name": "ai_operator_task_control",
                "source_file": "builtin/game/ai_operator_task_control.lua",
                "command": "ai_runtime_operator_task_control",
                "privilege": "server",
                "mutation_scope": "receipt_gated_task_queue_only",
                "loaded_by_default_product_profile": True,
                "public_safe_output_required": True,
            },
        )

    def test_builtin_fixture_modules_require_explicit_dev_settings_before_load(self):
        init_lua = BUILTIN_INIT.read_text(encoding="utf-8")

        self.assertIn('core.settings:get_bool("ai_runtime.enable_smoke_command", false)', init_lua)
        self.assertIn('core.settings:get_bool("ai_runtime.enable_demo_benchmark_command", false)', init_lua)
        self.assertLess(
            init_lua.find('core.settings:get_bool("ai_runtime.enable_smoke_command", false)'),
            init_lua.find('dofile(gamepath .. "ai_runtime_smoke.lua")'),
        )
        self.assertLess(
            init_lua.find('core.settings:get_bool("ai_runtime.enable_demo_benchmark_command", false)'),
            init_lua.find('dofile(gamepath .. "demo_entity_benchmark.lua")'),
        )

    def test_verifier_reports_clean_product_profile_and_gated_dev_surfaces(self):
        verifier = load_verifier_module()

        report = verifier.build_report(ROOT)

        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["profile"]["gameid"], "ai_runtime")
        self.assertEqual(report["profile"]["product_mods"], ["ai_runtime_base"])
        self.assertEqual(report["violations"], [])
        self.assertTrue(report["safety"]["no_private_content"])
        self.assertTrue(report["safety"]["dev_surfaces_disabled_by_default"])
        self.assertTrue(report["safety"]["test_fixtures_explicit_only"])
        self.assertEqual(
            {entry["category"] for entry in report["startup_inventory"]},
            {
                "product_runtime",
                "first_party_plugin",
                "benchmark_fixture",
                "compatibility_fixture",
                "unit_test_helper",
            },
        )
        surfaces = {surface["name"]: surface for surface in report["explicit_dev_surfaces"]}
        self.assertEqual(surfaces["ai_runtime_smoke"]["default_enabled"], False)
        self.assertEqual(surfaces["ai_demo_entity_benchmark"]["default_enabled"], False)
        self.assertEqual(surfaces["ai_runtime_smoke"]["status"], "gated")
        self.assertEqual(surfaces["ai_demo_entity_benchmark"]["status"], "gated")
        runtime_surfaces = {surface["name"]: surface for surface in report["required_runtime_surfaces"]}
        self.assertEqual(
            {
                name: surface["status"]
                for name, surface in runtime_surfaces.items()
            },
            {
                "ai_operator_status": "present",
                "ai_operator_task_control": "present",
            },
        )
        for surface in runtime_surfaces.values():
            self.assertTrue(surface["loaded_by_default_product_profile"])
            self.assertTrue(surface["command_registered"])
            self.assertTrue(surface["server_privilege_required"])
            self.assertTrue(surface["public_safe_output_required"])
        self.assertTrue(report["safety"]["runtime_surfaces_available"])

    def test_cli_writes_machine_readable_report(self):
        verifier = load_verifier_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output = pathlib.Path(tmpdir) / "product-profile-report.json"

            exit_code = verifier.main(["--root", str(ROOT), "--output", str(output)])

            self.assertEqual(exit_code, 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["profile"]["gameid"], "ai_runtime")

    def test_cli_creates_nested_output_parent_directories(self):
        verifier = load_verifier_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output = pathlib.Path(tmpdir) / "nested" / "run" / "product-profile-report.json"

            exit_code = verifier.main(["--root", str(ROOT), "--output", str(output)])

            self.assertEqual(exit_code, 0)
            self.assertTrue(output.is_file())
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "pass")


if __name__ == "__main__":
    unittest.main()
