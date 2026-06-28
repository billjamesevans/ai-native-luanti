import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = ROOT / "util" / "ai_native_mvp_audit.py"
CHECKLIST = ROOT / "doc" / "ai-native-runtime" / "mvp-gap-checklist.md"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"

PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload|"
    r"/Users/|/opt/|bill@",
    re.I,
)


class MvpAuditTests(unittest.TestCase):
    def write_scorecard(self, path, *, ranked_gaps=None, overall_status="gap-scorecard-ready"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "runner_version": "ai-native-runtime-gap-scorecard:v1",
                    "overall_status": overall_status,
                    "ranked_gaps": ranked_gaps or [],
                    "hardware_classes": ["local-mac", "low-power-server"],
                    "lanes": [
                        {
                            "hardware_class": "local-mac",
                            "measurement_status": "ready",
                        },
                        {
                            "hardware_class": "low-power-server",
                            "measurement_status": "ready",
                        },
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def run_audit(self, scorecard_path, output_path, *, check=True):
        completed = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "--scorecard",
                str(scorecard_path),
                "--output",
                str(output_path),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if check and completed.returncode != 0:
            self.fail(
                "MVP audit failed unexpectedly\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )
        return completed

    def test_mvp_audit_writes_public_safe_requirement_matrix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scorecard_path = pathlib.Path(tmpdir) / "runtime-gap-scorecard.json"
            output_path = pathlib.Path(tmpdir) / "mvp-audit.json"
            self.write_scorecard(scorecard_path)

            completed = self.run_audit(scorecard_path, output_path)

            self.assertIn("mvp-audit.json", completed.stdout)
            report_text = output_path.read_text(encoding="utf-8")
            self.assertIsNone(PRIVATE_PATTERNS.search(report_text))
            report = json.loads(report_text)
            self.assertEqual(report["runner_version"], "ai-native-mvp-audit:v1")
            self.assertEqual(report["overall_status"], "mvp-gaps-open")
            self.assertEqual(
                report["scorecard_prerequisite"]["status"],
                "pass",
            )
            self.assertEqual(
                report["scorecard_prerequisite"]["logical_path"],
                "local/benchmarks/runtime-gap-scorecard.json",
            )

            categories = {item["category"] for item in report["acceptance_audit"]}
            self.assertIn("already_proven", categories)
            self.assertIn("implemented_but_weakly_verified", categories)
            self.assertNotIn("missing_runtime_behavior", categories)
            self.assertIn("compatibility_import_deferral", categories)

            acceptance_ids = {item["id"] for item in report["acceptance_audit"]}
            self.assertEqual(
                acceptance_ids,
                {
                    "fork-builds-locally",
                    "agent-identity-capabilities",
                    "queued-inspect-place-remove",
                    "structured-action-results",
                    "task-cancellation",
                    "protected-unsafe-skips",
                    "runtime-metrics",
                    "first-party-deterministic-plugin",
                    "first-party-follow-come-product-behavior",
                    "lag-pausing-budget-enforcement",
                    "player-teleport-and-combat-capabilities",
                    "model-and-import-capability-boundaries",
                    "compatibility-import-deferred",
                },
            )

            audit_by_id = {item["id"]: item for item in report["acceptance_audit"]}
            self.assertEqual(
                audit_by_id["fork-builds-locally"]["category"],
                "already_proven",
            )
            self.assertEqual(
                audit_by_id["agent-identity-capabilities"]["category"],
                "implemented_but_weakly_verified",
            )
            self.assertEqual(
                audit_by_id["lag-pausing-budget-enforcement"]["category"],
                "already_proven",
            )
            self.assertEqual(
                audit_by_id["runtime-metrics"]["category"],
                "already_proven",
            )
            self.assertEqual(
                audit_by_id["first-party-deterministic-plugin"]["category"],
                "already_proven",
            )
            self.assertEqual(
                audit_by_id["first-party-follow-come-product-behavior"]["category"],
                "already_proven",
            )
            self.assertEqual(
                audit_by_id["player-teleport-and-combat-capabilities"]["category"],
                "already_proven",
            )
            self.assertEqual(
                audit_by_id["model-and-import-capability-boundaries"]["category"],
                "already_proven",
            )
            self.assertEqual(
                audit_by_id["compatibility-import-deferred"]["category"],
                "compatibility_import_deferral",
            )

            for item in report["acceptance_audit"]:
                self.assertTrue(item["mvp_spec_refs"], item["id"])
                self.assertTrue(item["evidence"], item["id"])
                self.assertIn(
                    item["verification_strength"],
                    {"proven", "weak", "missing", "deferred"},
                )

            follow_on_ids = [issue["id"] for issue in report["follow_on_issues"]]
            self.assertGreaterEqual(len(follow_on_ids), 1)
            self.assertEqual(
                follow_on_ids[:1],
                [
                    "mvp-agent-policy-profile",
                ],
            )

    def test_mvp_audit_refuses_dirty_runtime_gap_scorecard(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scorecard_path = pathlib.Path(tmpdir) / "runtime-gap-scorecard.json"
            output_path = pathlib.Path(tmpdir) / "mvp-audit.json"
            self.write_scorecard(
                scorecard_path,
                ranked_gaps=[
                    {
                        "id": "low-power-warning-gap",
                        "severity": "high",
                        "message": "unreviewed warning",
                    }
                ],
            )

            completed = self.run_audit(scorecard_path, output_path, check=False)

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("clean runtime gap scorecard", completed.stderr)
            self.assertFalse(output_path.exists())

    def test_committed_checklist_links_audit_command_and_gap_categories(self):
        checklist_text = CHECKLIST.read_text(encoding="utf-8")
        self.assertIsNone(PRIVATE_PATTERNS.search(checklist_text))
        for needle in (
            "Issue #94",
            "doc/ai-native-runtime/mvp-spec.md",
            "util/ai_native_mvp_audit.py",
            "already_proven",
            "implemented_but_weakly_verified",
            "missing_runtime_behavior",
            "missing_first_party_plugin_behavior",
            "compatibility_import_deferral",
            "clean scorecard is a prerequisite gate",
        ):
            self.assertIn(needle, checklist_text)

        readme_text = README.read_text(encoding="utf-8")
        self.assertIn("MVP gap checklist", readme_text)
        self.assertIn("mvp-gap-checklist.md", readme_text)
        self.assertIn("ai_native_mvp_audit.py", readme_text)


if __name__ == "__main__":
    unittest.main()
