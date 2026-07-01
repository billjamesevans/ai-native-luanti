from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openrealm_creator_kernel.cli import build_artifacts
from openrealm_creator_kernel.planner import plan_from_prompt
from openrealm_creator_kernel.safety import validate_plan


class CreatorKernelTests(unittest.TestCase):
    def test_moonstone_prompt_generates_safe_ore_pack(self):
        plan = plan_from_prompt("Add a new ore called moonstone that spawns below level -200 and crafts a glowing sword")
        self.assertEqual(plan.plan_kind, "ore_mod")
        self.assertIn("openrealm_moonstone", plan.mod_name)
        self.assertTrue(any(node.name == "moonstone_ore" for node in plan.nodes))
        self.assertTrue(any(tool.name == "moonstone_glowing_sword" for tool in plan.tools))
        self.assertTrue(validate_plan(plan).ok)

    def test_village_prompt_has_bounded_structure(self):
        plan = plan_from_prompt("Build a cozy lakeside village with floating lanterns")
        self.assertEqual(plan.plan_kind, "structure")
        self.assertEqual(len(plan.structures), 1)
        self.assertLessEqual(len(plan.structures[0].placements), plan.safety_budget.max_structure_nodes)
        self.assertTrue(validate_plan(plan).ok)

    def test_dangerous_prompt_is_blocked(self):
        plan = plan_from_prompt("Build a cabin and run os.execute rm -rf everything")
        report = validate_plan(plan)
        self.assertFalse(report.ok)
        self.assertTrue(any(issue.code == "dangerous_prompt_token" for issue in report.issues))

    def test_artifact_generation_writes_luanti_mod(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "generated"
            result = build_artifacts("Build a cozy lakeside village with floating lanterns", out)
            self.assertTrue(result["plan"].exists())
            self.assertTrue(result["preview"].exists())
            self.assertTrue((result["mod_dir"] / "init.lua").exists())
            self.assertTrue((result["mod_dir"] / "mod.conf").exists())
            self.assertTrue(result["package"].exists())


if __name__ == "__main__":
    unittest.main()
