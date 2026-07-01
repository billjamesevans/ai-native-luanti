import copy
import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = ROOT / "util" / "openrealm_plan_contract.py"
DOC = ROOT / "doc" / "ai-native-runtime" / "openrealm-plan-contract.md"
SCHEMA = ROOT / "doc" / "ai-native-runtime" / "schemas" / "openrealm-plan-v1.schema.json"
EXAMPLE = ROOT / "doc" / "ai-native-runtime" / "examples" / "openrealm-plan-v1.example.json"


def load_contract_module():
    assert CLI.is_file(), f"missing {CLI}"
    spec = importlib.util.spec_from_file_location("openrealm_plan_contract", CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OpenRealmPlanContractTests(unittest.TestCase):
    def test_contract_artifacts_exist(self):
        for path in [CLI, DOC, SCHEMA, EXAMPLE]:
            self.assertTrue(path.is_file(), f"missing {path}")

    def test_example_and_generated_plans_validate(self):
        contract = load_contract_module()

        report = contract.build_report(ROOT)

        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["violations"], [])
        self.assertEqual(report["contract"]["schema"], "doc/ai-native-runtime/schemas/openrealm-plan-v1.schema.json")
        self.assertGreaterEqual(report["contract"]["generated_plan_fixtures"], 6)
        self.assertTrue(report["safety"]["requires_preview_approval_rollback"])
        self.assertTrue(report["safety"]["blocks_direct_ai_mutation"])
        self.assertTrue(report["safety"]["generated_plans_valid"])
        self.assertTrue(all(report["schema_checks"].values()))
        self.assertEqual(report["kit_schema_status"], "pass")
        self.assertTrue(all(report["kit_schema_checks"].values()))
        self.assertTrue(all(report["rejection_checks"].values()))

    def test_validator_rejects_unsafe_plan_variants(self):
        contract = load_contract_module()
        example = json.loads(EXAMPLE.read_text(encoding="utf-8"))

        unsafe_identifier = copy.deepcopy(example)
        unsafe_identifier["structures"][0]["name"] = "bad-name"
        self.assertTrue(any(
            issue["kind"] == "unsafe_identifier"
            for issue in contract.validate_openrealm_plan(unsafe_identifier)
        ))

        over_budget = copy.deepcopy(example)
        over_budget["safety_budget"]["max_structure_nodes"] = 1
        self.assertTrue(any(
            issue["kind"] == "structure_too_large"
            for issue in contract.validate_openrealm_plan(over_budget)
        ))

        raw_payload = copy.deepcopy(example)
        raw_payload["world_recipe"]["lua_code"] = "local function bad() os.execute('rm -rf /') end"
        issues = contract.validate_openrealm_plan(raw_payload)
        self.assertTrue(any(issue["kind"] == "raw_payload_field" for issue in issues))
        self.assertTrue(any(issue["kind"] == "raw_code_payload" for issue in issues))

        missing_rollback = copy.deepcopy(example)
        missing_rollback["safety_budget"].pop("rollback_required")
        self.assertTrue(any(
            issue["kind"] == "missing_rollback_policy"
            for issue in contract.validate_openrealm_plan(missing_rollback)
        ))

    def test_cli_writes_machine_readable_report(self):
        contract = load_contract_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output = pathlib.Path(tmpdir) / "openrealm-plan-contract.json"

            exit_code = contract.main(["--root", str(ROOT), "--output", str(output)])

            self.assertEqual(exit_code, 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["example_status"], "pass")


if __name__ == "__main__":
    unittest.main()
