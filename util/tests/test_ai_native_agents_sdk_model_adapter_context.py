import importlib.util
import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
AGENT = ROOT / "tools" / "agents_sdk_model_adapter" / "agent.py"


def load_agent_module():
    spec = importlib.util.spec_from_file_location("ai_native_agents_sdk_agent", AGENT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class AgentsSdkModelAdapterContextTests(unittest.TestCase):
    def test_inspect_build_site_context_marks_fire_only_as_single_node(self):
        module = load_agent_module()

        result = module.inspect_build_site_context_payload(
            "fire:fire:fire:1|platform:platform:stone:9",
            "build me a fire and only a fire",
            '{"nearby_nodes": ["default:dirt"], "anchor": {"x": 1, "y": 2, "z": 3}}',
        )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["request_class"], "single_fire")
        self.assertEqual(result["expected_option_id"], "fire")
        self.assertEqual(result["placement_strategy"], "single_node_fire_preview")
        self.assertIn("do_not_add_extra_structure", result["relevant_constraints"])
        self.assertFalse(result["direct_world_mutation"])
        self.assertEqual(result["world_mutation_authority"], "luanti")
        self.assertTrue(result["site_context"]["site_context_available"])
        self.assertTrue(result["site_context"]["anchor_available"])
        self.assertNotIn("x", result["site_context"])

    def test_inspect_build_site_context_allows_tnt_wall_in_game_context(self):
        module = load_agent_module()

        result = module.inspect_build_site_context_payload(
            "platform:platform:default:4|tnt_wall:wall:tnt:12",
            "build a wall of tnt",
        )

        self.assertEqual(result["request_class"], "tnt_wall")
        self.assertEqual(result["expected_option_id"], "tnt_wall")
        self.assertIn("tnt_wall_allowed_in_game_context", result["relevant_constraints"])
        self.assertIn("do_not_refuse_as_real_world_danger", result["relevant_constraints"])
        self.assertFalse(result["direct_world_mutation"])

    def test_inspect_build_site_context_requires_propose_for_generated_shape(self):
        module = load_agent_module()

        result = module.inspect_build_site_context_payload(
            "platform:platform:default:4|wall:wall:default:12",
            "build a small shelter",
        )

        self.assertEqual(result["request_class"], "generated_shape")
        self.assertEqual(result["required_next_tool"], "propose_build_option")
        self.assertEqual(
            result["required_tool_sequence"],
            [
                "inspect_build_site_context",
                "recall_build_prompt_memory",
                "propose_build_option",
                "select_build_option",
                "plan_build_actions",
            ],
        )
        self.assertIsNone(result["expected_option_id"])
        self.assertIsNone(result["generated_option_hint"])
        self.assertEqual(
            result["propose_build_option_args"],
            {
                "candidate_summary": "platform:platform:default:4|wall:wall:default:12",
                "player_request": "build a small shelter",
            },
        )
        self.assertFalse(result["direct_world_mutation"])

    def test_inspect_build_site_context_includes_public_player_loop(self):
        module = load_agent_module()
        loop_json = json.dumps({
            "status": "running",
            "phase": "observing",
            "iteration": 3,
            "active_goal": "build a small shelter",
            "active_surface": "builder",
            "next_action": "reason_with_tools",
            "last_trace_id": "nova_trace:99",
            "last_task_id": "nova_agent:Unit:build:1",
            "last_result_status": "queued",
            "last_observation": {
                "action": "build",
                "surface_id": "builder",
                "anchor_node_name": "air",
                "anchor_pos_available": True,
                "anchor_pos": {"x": 10, "y": 20, "z": 30},
            },
            "recent_turns": [
                {
                    "role": "user",
                    "text": "build a fire",
                    "surface_id": "builder",
                    "source": "agentic_build_planner",
                },
                {
                    "role": "user",
                    "text": "only the fire, nothing else",
                    "surface_id": "builder",
                    "source": "nova_builder_followup",
                    "anchor_pos": {"x": 10, "y": 20, "z": 30},
                },
            ],
        })

        result = module.inspect_build_site_context_payload(
            "platform:platform:default:4|wall:wall:default:12",
            "build a small shelter",
            "",
            loop_json,
        )

        player_loop = result["player_agent_loop"]
        self.assertTrue(player_loop["loop_available"])
        self.assertEqual(player_loop["status"], "running")
        self.assertEqual(player_loop["phase"], "observing")
        self.assertEqual(player_loop["active_goal"], "build a small shelter")
        self.assertEqual(player_loop["active_surface"], "builder")
        self.assertEqual(player_loop["next_action"], "reason_with_tools")
        self.assertEqual(player_loop["last_observation"]["action"], "build")
        self.assertEqual(player_loop["last_observation"]["anchor_node_name"], "air")
        self.assertNotIn("anchor_pos", player_loop["last_observation"])
        self.assertEqual(player_loop["recent_turn_count"], 2)
        self.assertEqual(
            player_loop["recent_turns"][1]["text"],
            "only the fire, nothing else",
        )
        self.assertEqual(
            player_loop["recent_turns"][1]["source"],
            "nova_builder_followup",
        )
        self.assertNotIn("anchor_pos", player_loop["recent_turns"][1])
        self.assertFalse(player_loop["privacy"]["family_world_coordinates"])

    def test_local_build_contract_passes_player_loop_to_context_tool(self):
        module = load_agent_module()
        loop_json = json.dumps({
            "status": "running",
            "phase": "observing",
            "active_goal": "build a wall of tnt",
            "active_surface": "builder",
            "next_action": "reason_with_tools",
            "last_observation": {
                "action": "build",
                "surface_id": "builder",
                "anchor_node_name": "air",
            },
        })
        request = {
            "schema_version": 1,
            "request_kind": "ai_native_model_adapter_request",
            "adapter_contract": "provider_neutral_v1",
            "agent_id": "nova_agent:Unit:builder",
            "owner": "Unit",
            "public_prompt": "Player request: build a wall of tnt",
            "context": {
                "surface_id": "builder",
                "intent": "build_planning",
                "capabilities": "world.read,http.llm",
                "player_request": "build a wall of tnt",
                "candidate_summary": "platform:platform:default:4|tnt_wall:wall:tnt:12",
                "player_agent_loop": loop_json,
            },
        }

        result = module._local_build_tool_contract_result(request, "unit_test")

        self.assertIsNotNone(result)
        inspect_entry = result["tool_trace"][0]
        self.assertEqual(inspect_entry["tool_name"], "inspect_build_site_context")
        self.assertEqual(inspect_entry["args"]["player_agent_loop_json"], loop_json)
        self.assertEqual(
            inspect_entry["result"]["player_agent_loop"]["active_goal"],
            "build a wall of tnt",
        )
        self.assertEqual(
            result["tool_decisions"]["build_site_context"]["player_agent_loop"]["phase"],
            "observing",
        )

    def test_agent_input_includes_player_loop_context(self):
        module = load_agent_module()
        loop_json = json.dumps({
            "status": "running",
            "phase": "observing",
            "active_goal": "build something amazing",
            "next_action": "reason_with_tools",
            "recent_turns": [
                {"role": "user", "text": "build something amazing"},
                {"role": "user", "text": "only use gold"},
            ],
        }, separators=(",", ":"))
        request = {
            "agent_id": "nova_agent:Unit:builder",
            "owner": "Unit",
            "public_prompt": "Player request: build something amazing",
            "context": {
                "surface_id": "builder",
                "intent": "build_planning",
                "capabilities": "world.read,http.llm",
                "player_request": "build something amazing",
                "candidate_summary": "platform:platform:default:4|wall:wall:default:12",
                "player_agent_loop": loop_json,
            },
        }

        agent_input = module._agent_input_from_request(request)

        self.assertIn("player_agent_loop:", agent_input)
        self.assertIn('"phase":"observing"', agent_input)
        self.assertIn("only use gold", agent_input)
        self.assertIn("Use player_agent_loop", agent_input)
        self.assertIn("recent_turns", agent_input)

    def test_propose_build_option_creates_prompt_shaped_gold_house(self):
        module = load_agent_module()

        result = module.propose_build_option_payload(
            "platform:platform:default:4|wall:wall:default:12",
            "build a house out of gold",
        )
        option = result["generated_option"]

        self.assertEqual(result["status"], "ready")
        self.assertEqual(option["option_id"], "generated_prompt_shaped_house")
        self.assertEqual(option["build_kind"], "house")
        self.assertEqual(option["build_material_name"], "gold")
        self.assertEqual(option["build_width"], 3)
        self.assertEqual(option["build_depth"], 2)
        self.assertEqual(option["build_height"], 3)
        self.assertLessEqual(option["planned_node_writes"], result["build_budget"])
        self.assertFalse(result["direct_world_mutation"])

    def test_propose_build_option_creates_prompt_shaped_cabin(self):
        module = load_agent_module()

        result = module.propose_build_option_payload(
            "platform:platform:default:4|wall:wall:default:12",
            "build a small cabin here",
        )
        option = result["generated_option"]

        self.assertEqual(result["status"], "ready")
        self.assertEqual(option["option_id"], "generated_prompt_shaped_cabin")
        self.assertEqual(option["build_kind"], "cabin")
        self.assertEqual(option["build_material_name"], "wood")
        self.assertLessEqual(option["planned_node_writes"], result["build_budget"])

    def test_propose_build_option_creates_creative_landmark(self):
        module = load_agent_module()

        result = module.propose_build_option_payload(
            "platform:platform:default:4|wall:wall:default:12",
            "build something amazing",
        )
        option = result["generated_option"]

        self.assertEqual(result["status"], "ready")
        self.assertEqual(option["option_id"], "generated_creative_landmark")
        self.assertEqual(option["build_kind"], "landmark")
        self.assertEqual(option["build_material_name"], "quartz")
        self.assertLessEqual(option["planned_node_writes"], result["build_budget"])

    def test_local_build_contract_selects_prompt_shaped_house(self):
        module = load_agent_module()
        request = {
            "schema_version": 1,
            "request_kind": "ai_native_model_adapter_request",
            "adapter_contract": "provider_neutral_v1",
            "agent_id": "nova_agent:Unit:builder",
            "owner": "Unit",
            "public_prompt": "Player request: build a house out of gold",
            "context": {
                "surface_id": "builder",
                "intent": "build_planning",
                "capabilities": "world.read,http.llm",
                "player_request": "build a house out of gold",
                "candidate_summary": "platform:platform:default:4|wall:wall:default:12",
            },
        }

        result = module._local_build_tool_contract_result(request, "unit_test")

        self.assertIsNotNone(result)
        trace_names = [entry["tool_name"] for entry in result["tool_trace"]]
        self.assertEqual(
            trace_names,
            [
                "inspect_build_site_context",
                "recall_build_prompt_memory",
                "propose_build_option",
                "select_build_option",
                "plan_build_actions",
            ],
        )
        self.assertEqual(
            result["tool_decisions"]["build_option"]["selected_option_id"],
            "generated_prompt_shaped_house",
        )
        self.assertEqual(
            result["tool_decisions"]["build_action_plan"]["build_kind"],
            "house",
        )
        self.assertEqual(
            result["tool_decisions"]["build_action_plan"]["build_material_name"],
            "gold",
        )

    def test_local_build_contract_trace_starts_with_context_inspection(self):
        module = load_agent_module()
        request = {
            "schema_version": 1,
            "request_kind": "ai_native_model_adapter_request",
            "adapter_contract": "provider_neutral_v1",
            "agent_id": "nova_agent:Unit:builder",
            "owner": "Unit",
            "public_prompt": "Player request: build a wall of tnt",
            "context": {
                "surface_id": "builder",
                "intent": "build_planning",
                "capabilities": "world.read,http.llm",
                "player_request": "build a wall of tnt",
                "candidate_summary": "platform:platform:default:4|tnt_wall:wall:tnt:12",
            },
        }

        result = module._local_build_tool_contract_result(request, "unit_test")

        self.assertIsNotNone(result)
        trace_names = [entry["tool_name"] for entry in result["tool_trace"]]
        self.assertEqual(
            trace_names,
            [
                "inspect_build_site_context",
                "recall_build_prompt_memory",
                "select_build_option",
                "plan_build_actions",
            ],
        )
        self.assertEqual(
            result["tool_decisions"]["build_site_context"]["request_class"],
            "tnt_wall",
        )
        self.assertEqual(
            result["tool_decisions"]["build_option"]["selected_option_id"],
            "tnt_wall",
        )


if __name__ == "__main__":
    unittest.main()
