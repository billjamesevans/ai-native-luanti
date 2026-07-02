import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = ROOT / "util" / "openrealm_advantage_kit_verify.py"


def load_verifier_module():
    assert CLI.is_file(), f"missing {CLI}"
    spec = importlib.util.spec_from_file_location("openrealm_advantage_kit_verify", CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OpenRealmAdvantageKitVerifierTests(unittest.TestCase):
    def test_report_verifies_assets_manifest_schema_and_docs(self):
        verifier = load_verifier_module()

        report = verifier.build_report(ROOT)

        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["kit"]["product_name"], "OpenRealm")
        self.assertEqual(report["kit"]["assistant_name"], "Nova")
        self.assertEqual(report["violations"], [])
        self.assertTrue(report["safety"]["canonical_assets_present"])
        self.assertTrue(report["safety"]["manifest_blocks_direct_ai_world_mutation"])
        self.assertTrue(report["safety"]["manifest_requires_preview_approval_audit_rollback"])
        self.assertTrue(report["safety"]["private_boundary_clean"])
        self.assertTrue(report["safety"]["required_docs_complete"])
        self.assertTrue(report["safety"]["schema_present"])
        self.assertTrue(report["safety"]["generated_mods_use_runtime_queue"])
        self.assertEqual(len(report["generated_runtime"]), 5)
        self.assertTrue(all(item["status"] == "pass" for item in report["generated_runtime"]))

        assets = {asset["role"]: asset for asset in report["assets"]}
        self.assertEqual(
            set(assets),
            {
                "brand_style_guide",
                "brand_assets_sheet",
                "creator_studio_mockup",
                "future_key_art",
                "creator_flow",
                "nova_architecture",
                "roadmap_ecosystem",
            },
        )
        self.assertEqual(
            assets["brand_style_guide"]["sha256"],
            "fa3487807ec4339e43d8d7fbeb0c5499e3a516e321d0c40a7db82bb2225f5e23",
        )
        self.assertEqual(
            (assets["brand_assets_sheet"]["width"], assets["brand_assets_sheet"]["height"]),
            (1448, 1086),
        )

    def test_optional_tests_and_js_check_are_recorded(self):
        verifier = load_verifier_module()

        report = verifier.build_report(ROOT, run_tests=True, run_js_check=True)

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["test_result"]["status"], "pass")
        self.assertEqual(report["js_check_result"]["status"], "pass")

    def test_private_boundary_scan_allows_guard_patterns_only(self):
        verifier = load_verifier_module()

        self.assertEqual(verifier.private_boundary_matches(ROOT), [])

        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            docs = root / "openrealm_advantage_kit" / "docs"
            docs.mkdir(parents=True)
            (docs / "leak.md").write_text("Do not publish themepark notes.\n", encoding="utf-8")

            matches = verifier.private_boundary_matches(root)

        self.assertEqual(matches, [
            {
                "path": "openrealm_advantage_kit/docs/leak.md",
                "line": 1,
                "pattern": "themepark",
            }
        ])

    def test_cli_writes_machine_readable_report(self):
        verifier = load_verifier_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output = pathlib.Path(tmpdir) / "openrealm-advantage-kit.json"

            exit_code = verifier.main(["--root", str(ROOT), "--output", str(output)])

            self.assertEqual(exit_code, 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "pass")
            self.assertEqual(len(report["assets"]), 7)
            self.assertEqual(report["kit"]["schema_path"], "openrealm_advantage_kit/schemas/openrealm_plan.schema.json")


if __name__ == "__main__":
    unittest.main()
