import importlib.util
import json
import pathlib
import re
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = ROOT / "util" / "ai_native_operator_status_package.py"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"
DOC = ROOT / "doc" / "ai-native-runtime" / "operator-status-package.md"
PRIVATE_PATTERNS = re.compile(
    r"/Users/|minecraftpi|192\.168|spacebase|themepark|showcase100|"
    r"disneyland100|sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|"
    r"private_prompt|asset_payload",
    re.I,
)


def load_status_module():
    assert CLI.is_file(), f"missing {CLI}"
    spec = importlib.util.spec_from_file_location("ai_native_operator_status_package", CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AIOperatorStatusPackageTests(unittest.TestCase):
    def assert_public_safe(self, payload):
        encoded = json.dumps(payload, sort_keys=True)
        self.assertLessEqual(len(encoded.encode("utf-8")), payload["bounds"]["max_bytes"])
        self.assertNotRegex(encoded, PRIVATE_PATTERNS)

    def test_default_package_is_bounded_and_non_mutating(self):
        status_package = load_status_module()

        package = status_package.build_package(
            ROOT,
            generated_at="2026-06-29T00:00:00Z",
        )

        self.assertEqual(package["schema_version"], 1)
        self.assertEqual(package["package_kind"], "ai_native_operator_status_package")
        self.assertEqual(package["status"], "ready")
        self.assertEqual(package["runtime_context"]["game_profile"], "ai_runtime")
        self.assertFalse(package["runtime_context"]["mutation_performed"])
        self.assertEqual(package["agents"]["total"], 0)
        self.assertEqual(package["tasks"]["counts"], {"total": 0})
        self.assertEqual(package["rollback"]["records_available"], 0)
        self.assertEqual(package["imports"]["reviews_total"], 0)
        self.assertEqual(package["benchmarks"]["gates"], [])
        self.assertEqual(package["server_profile_hygiene"]["status"], "pass")
        self.assertTrue(package["server_profile_hygiene"]["dev_surfaces_disabled_by_default"])
        self.assert_public_safe(package)

    def test_populated_synthetic_package_summarizes_sections_and_redacts_private_content(self):
        status_package = load_status_module()
        source_state = {
            "agents": [
                {
                    "agent_id": "nova:emma",
                    "owner": "emma",
                    "capability_profile": "clean",
                    "capabilities": ["world.read", "world.place"],
                },
                {
                    "agent_id": "operator:bill",
                    "owner": "bill",
                    "capability_profile": "operator",
                    "capabilities": ["rollback.execute", "import.assets"],
                },
            ],
            "tasks": [
                {
                    "task_id": "task:build:1",
                    "agent_id": "nova:emma",
                    "status": "running",
                    "label": "Build from /Users/billevans/private/spacebase.plan",
                },
                {
                    "task_id": "task:import:2",
                    "agent_id": "operator:bill",
                    "status": "blocked",
                    "reason": "private_prompt and asset_payload were supplied",
                },
            ],
            "rollback_records": [
                {
                    "record_id": "rollback:1",
                    "task_id": "task:build:1",
                    "status": "available",
                    "storage_ref": "rollback://minecraftpi.home/192.168.230.60/record",
                }
            ],
            "import_reviews": [
                {
                    "review_id": "review:asset:1",
                    "status": "blocked",
                    "source": "themepark resource pack",
                    "rights_confirmed": False,
                },
                {
                    "review_id": "review:structure:2",
                    "status": "approved",
                    "source": "public-safe fixture",
                    "rights_confirmed": True,
                },
            ],
            "promotion_packages": [
                {
                    "package_id": "promotion:structure:1",
                    "status": "ready",
                    "source": "public-safe promotion",
                    "approval_confirmed": True,
                }
            ],
            "benchmark_gates": [
                {
                    "gate_id": "local:latest",
                    "status": "pass",
                    "source": "/Users/billevans/benchmarks/REDACTED_KEY_FIXTURE",
                }
            ],
            "notes": {
                "server": "minecraftpi.home",
                "world": "disneyland100",
                "env": "OPENAI_API_KEY",
            },
        }

        package = status_package.build_package(
            ROOT,
            generated_at="2026-06-29T00:00:00Z",
            source_state=source_state,
            max_bytes=24000,
        )

        self.assertEqual(package["status"], "attention")
        self.assertEqual(package["agents"]["total"], 2)
        self.assertEqual(package["agents"]["capability_profiles"], ["clean", "operator"])
        self.assertEqual(package["tasks"]["counts"]["running"], 1)
        self.assertEqual(package["tasks"]["counts"]["blocked"], 1)
        self.assertEqual(package["rollback"]["records_available"], 1)
        self.assertEqual(package["imports"]["promotions_total"], 1)
        self.assertEqual(package["imports"]["status_counts"], {"approved": 1, "blocked": 1})
        self.assertEqual(package["imports"]["promotion_status_counts"], {"ready": 1})
        self.assertEqual(package["benchmarks"]["status_counts"], {"pass": 1})
        self.assertGreater(package["safety"]["redactions_applied"], 0)
        self.assert_public_safe(package)

    def test_cli_writes_machine_readable_report(self):
        status_package = load_status_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = pathlib.Path(tmpdir) / "operator-state.json"
            output_path = pathlib.Path(tmpdir) / "operator-status.json"
            input_path.write_text(
                json.dumps({
                    "tasks": [
                        {"task_id": "task:1", "status": "completed", "agent_id": "agent:one"}
                    ]
                }),
                encoding="utf-8",
            )

            exit_code = status_package.main([
                "--root",
                str(ROOT),
                "--input",
                str(input_path),
                "--output",
                str(output_path),
                "--generated-at",
                "2026-06-29T00:00:00Z",
            ])

            self.assertEqual(exit_code, 0)
            package = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(package["package_kind"], "ai_native_operator_status_package")
            self.assertEqual(package["tasks"]["counts"]["completed"], 1)
            self.assert_public_safe(package)

    def test_docs_describe_operator_status_package_boundary(self):
        self.assertTrue(DOC.is_file(), f"missing {DOC}")
        readme = README.read_text(encoding="utf-8")
        doc = DOC.read_text(encoding="utf-8")

        self.assertIn("operator-status-package.md", readme)
        self.assertIn("future CLI/dashboard", doc)
        self.assertIn("bounded JSON", doc)
        self.assertIn("does not mutate a world", doc)
        self.assertIn("family-server content", doc)


if __name__ == "__main__":
    unittest.main()
