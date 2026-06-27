import json
import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
LUA_MODULE = ROOT / "builtin" / "game" / "demo_entity_benchmark.lua"
DOC = ROOT / "doc" / "ai-native-runtime" / "generic-demo-entity-benchmark.md"
EXAMPLE = ROOT / "doc" / "ai-native-runtime" / "examples" / "generic-demo-entity-benchmark-report.example.json"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"

EXPECTED_SCENARIOS = {
    "entity_count_small",
    "movement_patrol",
    "collision_wall_contact",
    "cleanup_despawn",
}

PRIVATE_PATTERNS = re.compile(
    r"bill|wills|minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|asset_payload|prompt",
    re.I,
)

MEDIA_PATTERNS = re.compile(r"\.(png|jpg|jpeg|webp|obj|glb|gltf|ogg|mp3|wav)\b", re.I)


class DemoEntityBenchmarkFixtureTests(unittest.TestCase):
    def load_json(self, path):
        with self.subTest(path=path.name):
            self.assertTrue(path.is_file(), f"missing {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def assert_public_safe_text(self, body):
        self.assertNotRegex(body, PRIVATE_PATTERNS)
        self.assertNotRegex(body, MEDIA_PATTERNS)

    def test_lua_module_is_code_only_public_safe_fixture(self):
        self.assertTrue(LUA_MODULE.is_file(), f"missing {LUA_MODULE}")
        body = LUA_MODULE.read_text(encoding="utf-8")
        self.assertIn("core.demo_entity_benchmark", body)
        self.assertIn("ai_demo_benchmark:helper", body)
        self.assertIn("node_mutation_enabled = false", body)
        self.assertNotIn("core.set_node", body)
        self.assertNotIn("core.add_node", body)
        self.assertNotIn("core.remove_node", body)
        self.assert_public_safe_text(body)

    def test_example_report_covers_required_scenarios_and_metrics(self):
        report = self.load_json(EXAMPLE)
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["fixture_id"], "generic_demo_entity:benchmark:v1")
        self.assertEqual(report["entity_name"], "ai_demo_benchmark:helper")
        self.assertIn(report["hardware_class"], {"local-mac", "low-power-server"})
        self.assertIn("runtime_counters", report)
        self.assertEqual(
            report["runtime_counters"]["entities_by_type"]["ai_demo_benchmark:helper"],
            0,
        )
        self.assertFalse(report["run_context"]["requires_private_world"])
        self.assertFalse(report["run_context"]["requires_private_assets"])
        self.assertFalse(report["run_context"]["requires_live_pi"])
        self.assertEqual(report["provenance"]["source_category"], "code-only")
        self.assertFalse(report["provenance"]["assets_included"])
        self.assertFalse(report["mutation"]["node_mutation_enabled"])

        scenario_ids = {scenario["scenario_id"] for scenario in report["scenarios"]}
        self.assertEqual(EXPECTED_SCENARIOS, scenario_ids)

        for scenario in report["scenarios"]:
            with self.subTest(scenario=scenario["scenario_id"]):
                metrics = scenario["metrics"]
                for field in (
                    "entity_count",
                    "movement_steps",
                    "collision_checks",
                    "collision_events",
                    "cleaned_up",
                    "remaining_entities",
                    "avg_step_ms",
                    "p95_step_ms",
                    "max_lag_ms",
                    "node_writes",
                    "warnings",
                    "errors",
                ):
                    self.assertIn(field, metrics)
                self.assertEqual(metrics["node_writes"], 0)
                self.assertEqual(metrics["remaining_entities"], 0)
                self.assertGreaterEqual(metrics["p95_step_ms"], metrics["avg_step_ms"])
                self.assertGreaterEqual(metrics["max_lag_ms"], metrics["p95_step_ms"])

        self.assert_public_safe_text(json.dumps(report, sort_keys=True))

    def test_public_documentation_explains_fixture_and_non_goals(self):
        self.assertTrue(DOC.is_file(), f"missing {DOC}")
        body = DOC.read_text(encoding="utf-8")
        body_lower = body.lower()

        for phrase in (
            "code-only",
            "no assets",
            "ai_demo_entity_benchmark",
            "machine-readable",
            "hardware_class",
            "runtime_counters",
            "local-mac",
            "low-power-server",
            "entity count",
            "movement",
            "collision",
            "cleanup",
            "server-step impact",
            "node mutation disabled",
            "not a gameplay creature",
            "entity_count_small",
            "movement_patrol",
            "collision_wall_contact",
            "cleanup_despawn",
        ):
            self.assertIn(phrase, body_lower)

        self.assertIn("generic-demo-entity-benchmark.md", README.read_text(encoding="utf-8"))
        self.assert_public_safe_text(body)


if __name__ == "__main__":
    unittest.main()
