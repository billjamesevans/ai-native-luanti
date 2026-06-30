import importlib.util
import asyncio
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "util" / "ai_native_agents_sdk_bridge_contract.py"
AGENT = ROOT / "tools" / "agents_sdk_model_adapter" / "agent.py"


class AgentsSdkBridgeContractTests(unittest.TestCase):
    def test_contract_validator_passes(self):
        spec = importlib.util.spec_from_file_location("agents_sdk_bridge_contract", CONTRACT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        result = module.validate_contract()

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["violations"], [])
        self.assertEqual(result["bridge_dir"], "tools/agents_sdk_model_adapter")

    def test_offline_smoke_returns_provider_neutral_response(self):
        spec = importlib.util.spec_from_file_location("agents_sdk_agent", AGENT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        response = module.run_model_adapter_request(module.sample_request(), force_offline=True)

        self.assertTrue(response["ok"])
        self.assertEqual(response["response_kind"], "ai_native_model_adapter_response")
        self.assertEqual(response["adapter_name"], "openai-agents-sdk-model-adapter")
        self.assertFalse(response["response"]["agentic_execution"])
        self.assertIn("WebSearchTool", response["response"]["tools_enabled"])
        self.assertIn("recommend_build_option", response["response"]["tools_enabled"])
        self.assertIn("propose_build_option", response["response"]["tools_enabled"])
        self.assertIn("select_build_option", response["response"]["tools_enabled"])
        self.assertIn("plan_build_actions", response["response"]["tools_enabled"])
        self.assertIn("recall_build_prompt_memory", response["response"]["tools_enabled"])
        self.assertEqual(response["response"]["tool_trace"], [])
        self.assertEqual(response["response"]["tool_decision_source"], "offline_adapter_fallback")
        self.assertEqual(response["response"]["world_mutation_authority"], "luanti")
        tool_powers = response["response"]["tool_powers"]
        self.assertIn("WebSearchTool", {power["name"] for power in tool_powers})
        self.assertIn("recommend_build_option", {power["name"] for power in tool_powers})
        self.assertIn("propose_build_option", {power["name"] for power in tool_powers})
        self.assertIn("select_build_option", {power["name"] for power in tool_powers})
        self.assertIn("plan_build_actions", {power["name"] for power in tool_powers})
        self.assertIn("recall_build_prompt_memory", {power["name"] for power in tool_powers})
        self.assertTrue(all(power["direct_world_mutation"] is False for power in tool_powers))

    def test_build_option_recommender_is_read_only_and_bounded(self):
        spec = importlib.util.spec_from_file_location("agents_sdk_agent", AGENT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        result = module.recommend_build_option_payload(
            "platform:platform:default:4|marker:marker:default:1|tnt_wall:wall:tnt:12",
            "build something dramatic with tnt",
        )

        self.assertEqual(result["selected_option_id"], "tnt_wall")
        self.assertEqual(result["candidate_count"], 3)
        self.assertTrue(result["requires_preview"])
        self.assertTrue(result["requires_approval"])
        self.assertTrue(result["requires_rollback"])
        self.assertFalse(result["direct_world_mutation"])
        self.assertEqual(result["policy"], "luanti_executes_only_after_player_approval")

    def test_agent_selected_build_option_validator_is_read_only_and_bounded(self):
        spec = importlib.util.spec_from_file_location("agents_sdk_agent", AGENT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        result = module.select_build_option_payload(
            "platform:platform:default:4|marker:marker:default:1|tnt_wall:wall:tnt:12",
            "tnt_wall",
            "build something dramatic with tnt",
            "The player explicitly asked for TNT in a wall shape.",
        )

        self.assertEqual(result["selected_option_id"], "tnt_wall")
        self.assertEqual(result["selection_status"], "accepted")
        self.assertEqual(result["decision_source"], "agent_selected_build_option")
        self.assertTrue(result["requires_preview"])
        self.assertTrue(result["requires_approval"])
        self.assertTrue(result["requires_rollback"])
        self.assertFalse(result["direct_world_mutation"])

    def test_build_action_plan_tool_is_read_only_and_workflow_bounded(self):
        spec = importlib.util.spec_from_file_location("agents_sdk_agent", AGENT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        result = module.plan_build_actions_payload(
            "platform:platform:default:4|tnt_wall:wall:tnt:12",
            "build a wall of tnt",
            "tnt_wall",
        )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["selected_option_id"], "tnt_wall")
        self.assertEqual(result["build_kind"], "wall")
        self.assertEqual(result["build_material_name"], "tnt")
        self.assertEqual(result["planned_node_writes"], 12)
        self.assertEqual(result["plan_kind"], "luanti_build_action_plan_v1")
        self.assertEqual(result["step_count"], 4)
        self.assertEqual(
            [step["step_id"] for step in result["steps"]],
            [
                "preview_candidate",
                "await_player_approval",
                "queue_rollback_backed_build_task",
                "record_improvement_evidence",
            ],
        )
        self.assertTrue(result["requires_preview"])
        self.assertTrue(result["requires_approval"])
        self.assertTrue(result["requires_rollback"])
        self.assertFalse(result["direct_world_mutation"])
        self.assertTrue(all(step["direct_world_mutation"] is False for step in result["steps"]))
        self.assertEqual(result["world_mutation_authority"], "luanti")

    def test_build_option_validator_rejects_fire_only_mismatch(self):
        spec = importlib.util.spec_from_file_location("agents_sdk_agent", AGENT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        result = module.select_build_option_payload(
            "platform:platform:default:4|fire:fire:fire:1|marker:marker:default:1",
            "platform",
            "build me a fire and only a fire",
            "A platform might be more useful.",
        )
        fallback = module.recommend_build_option_payload(
            "platform:platform:default:4|fire:fire:fire:1|marker:marker:default:1",
            "build me a fire and only a fire",
        )

        self.assertIsNone(result["selected_option_id"])
        self.assertEqual(result["selection_status"], "rejected")
        self.assertEqual(
            result["rejection_reason"],
            "selection_violates_player_request_constraints",
        )
        self.assertEqual(result["required_option_id"], "fire")
        self.assertEqual(fallback["selected_option_id"], "fire")
        self.assertEqual(fallback["selected_build_kind"], "fire")

    def test_generated_build_option_is_read_only_and_bounded(self):
        spec = importlib.util.spec_from_file_location("agents_sdk_agent", AGENT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        candidate_summary = "platform:platform:default:4|wall:wall:default:12|marker:marker:default:1"
        proposal = module.propose_build_option_payload(
            candidate_summary,
            "build me a tall tower",
        )
        recommendation = module.recommend_build_option_payload(
            candidate_summary,
            "build me a tall tower",
        )

        self.assertEqual(proposal["status"], "ready")
        self.assertFalse(proposal["direct_world_mutation"])
        self.assertLessEqual(proposal["generated_option"]["planned_node_writes"], 12)
        self.assertEqual(proposal["generated_option"]["build_kind"], "wall")
        self.assertEqual(recommendation["selected_option_id"], "generated_tower_wall")
        self.assertEqual(recommendation["decision_source"], "generated_build_option_tool")
        self.assertEqual(
            recommendation["generated_option"]["option_id"],
            "generated_tower_wall",
        )
        self.assertTrue(recommendation["requires_approval"])
        self.assertFalse(recommendation["direct_world_mutation"])

    def test_agent_authored_generated_option_flows_through_build_tools(self):
        spec = importlib.util.spec_from_file_location("agents_sdk_agent", AGENT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        candidate_summary = "platform:platform:default:4|wall:wall:default:12"
        proposal = module.propose_build_option(
            candidate_summary=candidate_summary,
            player_request="build a wide lookout wall",
            option_id="generated_agent_lookout_wall",
            build_kind="wall",
            build_material_name="stone",
            build_width=6,
            build_height=2,
            reason="agent composed a wider wall within Luanti's node-write budget",
        )
        selection = module.select_build_option(
            candidate_summary=candidate_summary,
            selected_option_id="generated_agent_lookout_wall",
            player_request="build a wide lookout wall",
            selection_reason="the generated option best matches the requested wider lookout wall",
        )
        action_plan = module.plan_build_actions(
            candidate_summary=candidate_summary,
            player_request="build a wide lookout wall",
            selected_option_id="generated_agent_lookout_wall",
        )

        self.assertEqual(proposal["status"], "ready")
        self.assertFalse(proposal["direct_world_mutation"])
        self.assertEqual(
            proposal["generated_option"]["option_id"],
            "generated_agent_lookout_wall",
        )
        self.assertEqual(proposal["generated_option"]["build_kind"], "wall")
        self.assertEqual(proposal["generated_option"]["build_width"], 6)
        self.assertEqual(proposal["generated_option"]["build_height"], 2)
        self.assertEqual(proposal["generated_option"]["planned_node_writes"], 12)
        self.assertEqual(selection["selected_option_id"], "generated_agent_lookout_wall")
        self.assertEqual(selection["selection_status"], "accepted")
        self.assertEqual(
            selection["decision_source"],
            "agent_selected_generated_build_option",
        )
        self.assertEqual(
            selection["generated_option"]["option_id"],
            "generated_agent_lookout_wall",
        )
        self.assertFalse(selection["direct_world_mutation"])
        self.assertEqual(action_plan["status"], "ready")
        self.assertEqual(action_plan["selected_option_id"], "generated_agent_lookout_wall")
        self.assertEqual(action_plan["build_kind"], "wall")
        self.assertEqual(action_plan["build_material_name"], "stone")
        self.assertEqual(action_plan["planned_node_writes"], 12)
        self.assertEqual(action_plan["world_mutation_authority"], "luanti")
        self.assertFalse(action_plan["direct_world_mutation"])

    def test_explicit_wall_dimensions_require_generated_option(self):
        spec = importlib.util.spec_from_file_location("agents_sdk_agent", AGENT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        candidate_summary = "platform:platform:default:4|wall:wall:default:12"
        proposal = module.propose_build_option_payload(
            candidate_summary,
            "build a 6 wide 2 high lookout wall",
        )
        fixed_selection = module.select_build_option_payload(
            candidate_summary,
            "wall",
            "build a 6 wide 2 high lookout wall",
            "the fixed wall has the same write count",
        )
        recommendation = module.recommend_build_option_payload(
            candidate_summary,
            "build a 6 wide 2 high lookout wall",
        )

        self.assertEqual(proposal["status"], "ready")
        self.assertEqual(
            proposal["generated_option"]["option_id"],
            "generated_dimensioned_wall",
        )
        self.assertEqual(proposal["generated_option"]["build_width"], 6)
        self.assertEqual(proposal["generated_option"]["build_height"], 2)
        self.assertEqual(proposal["generated_option"]["planned_node_writes"], 12)
        self.assertIsNone(fixed_selection["selected_option_id"])
        self.assertEqual(fixed_selection["selection_status"], "rejected")
        self.assertEqual(
            fixed_selection["rejection_reason"],
            "selection_violates_player_request_constraints",
        )
        self.assertEqual(fixed_selection["required_option_id"], "generated_dimensioned_wall")
        self.assertEqual(recommendation["selected_option_id"], "generated_dimensioned_wall")
        self.assertEqual(recommendation["decision_source"], "generated_build_option_tool")

    def test_generated_option_selection_requires_prior_propose_tool_call(self):
        spec = importlib.util.spec_from_file_location("agents_sdk_agent", AGENT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        candidate_summary = "platform:platform:default:4|wall:wall:default:12"
        player_request = "build a 6 wide 2 high lookout wall"
        unproposed_selection = module.select_build_option_payload(
            candidate_summary,
            "generated_dimensioned_wall",
            player_request,
            "reviewed memory matched the generated wall",
        )
        unproposed_plan = module.plan_build_actions_payload(
            candidate_summary,
            player_request,
            "generated_dimensioned_wall",
        )
        proposal = module.propose_build_option_payload(candidate_summary, player_request)
        proposed_options = [proposal["generated_option"]]
        proposed_selection = module.select_build_option_payload(
            candidate_summary,
            "generated_dimensioned_wall",
            player_request,
            "proposed generated option first",
            proposed_options,
        )
        proposed_plan = module.plan_build_actions_payload(
            candidate_summary,
            player_request,
            "generated_dimensioned_wall",
            proposed_options,
        )

        self.assertIsNone(unproposed_selection["selected_option_id"])
        self.assertEqual(unproposed_selection["selection_status"], "rejected")
        self.assertEqual(unproposed_selection["generated_option_status"], "tool_call_required")
        self.assertEqual(unproposed_selection["rejection_reason"], "selected_option_not_executable")
        self.assertEqual(unproposed_plan["status"], "rejected")
        self.assertEqual(proposed_selection["selected_option_id"], "generated_dimensioned_wall")
        self.assertEqual(proposed_selection["selection_status"], "accepted")
        self.assertEqual(
            proposed_selection["decision_source"],
            "agent_selected_generated_build_option",
        )
        self.assertEqual(proposed_plan["status"], "ready")
        self.assertEqual(proposed_plan["selected_option_id"], "generated_dimensioned_wall")

    def test_reviewed_prompt_memory_can_drive_repeated_build_decision(self):
        spec = importlib.util.spec_from_file_location("agents_sdk_agent", AGENT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmpdir:
            case_pack = pathlib.Path(tmpdir) / "case-pack.json"
            case_pack.write_text(json.dumps({
                "schema_version": 1,
                "artifact_kind": "ai_native_agent_prompt_eval_case_pack",
                "cases": [{
                    "case_id": "promoted_fire_only_memory",
                    "case_hint": "fire_only_strict",
                    "prompt": "build something surprising",
                    "expected": {
                        "action": "build",
                        "build_kind": "fire",
                        "build_material_name": "fire",
                        "planned_node_writes": 1,
                    },
                }],
            }), encoding="utf-8")
            old_case_pack = os.environ.get("AI_NATIVE_AGENT_CASE_PACK_PATH")
            os.environ["AI_NATIVE_AGENT_CASE_PACK_PATH"] = str(case_pack)
            try:
                result = module.recommend_build_option_payload(
                    "platform:platform:default:4|fire:fire:fire:1",
                    "build something surprising",
                )
            finally:
                if old_case_pack is None:
                    os.environ.pop("AI_NATIVE_AGENT_CASE_PACK_PATH", None)
                else:
                    os.environ["AI_NATIVE_AGENT_CASE_PACK_PATH"] = old_case_pack

        self.assertEqual(result["selected_option_id"], "fire")
        self.assertEqual(result["decision_source"], "reviewed_prompt_memory")
        self.assertEqual(result["memory_match"]["matched_case_id"], "promoted_fire_only_memory")
        self.assertFalse(result["direct_world_mutation"])

    def test_build_planning_response_exposes_structured_tool_decision(self):
        spec = importlib.util.spec_from_file_location("agents_sdk_agent", AGENT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        request = module.sample_request()
        request["public_prompt"] = "\n".join([
            "Plan a Luanti build request using only the listed executable options.",
            "Player request: build a wall of tnt",
            "Options:",
            "- platform: Small platform kind=platform material=default planned_writes=4",
            "- tnt_wall: Small TNT wall kind=wall material=tnt planned_writes=12",
        ])
        request["context"] = {
            "surface_id": "builder",
            "intent": "build_planning",
            "player_request": "build a wall of tnt",
            "candidate_summary": "platform:platform:default:4|tnt_wall:wall:tnt:12",
        }

        response = module.run_model_adapter_request(request, force_offline=True)

        self.assertTrue(response["ok"])
        nested = response["response"]
        self.assertFalse(nested["agentic_execution"])
        self.assertEqual(nested["selected_option_id"], "tnt_wall")
        self.assertEqual(
            nested["tool_decisions"]["build_option"]["selected_option_id"],
            "tnt_wall",
        )
        self.assertEqual(nested["tool_decision_source"], "offline_adapter_fallback")
        self.assertFalse(nested["tool_decisions"]["build_option"]["direct_world_mutation"])
        self.assertEqual(
            nested["required_tool_calls"],
            ["recall_build_prompt_memory", "select_build_option", "plan_build_actions"],
        )
        self.assertEqual(
            nested["missing_required_tool_calls"],
            ["recall_build_prompt_memory", "select_build_option", "plan_build_actions"],
        )
        self.assertFalse(nested["required_tool_calls_satisfied"])

    def test_build_planning_response_can_expose_generated_tool_option(self):
        spec = importlib.util.spec_from_file_location("agents_sdk_agent", AGENT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        request = module.sample_request()
        request["public_prompt"] = "Player request: build me a tower"
        request["context"] = {
            "surface_id": "builder",
            "intent": "build_planning",
            "player_request": "build me a tower",
            "candidate_summary": "platform:platform:default:4|wall:wall:default:12|marker:marker:default:1",
        }

        response = module.run_model_adapter_request(request, force_offline=True)

        self.assertTrue(response["ok"])
        nested = response["response"]
        self.assertEqual(nested["selected_option_id"], "generated_tower_wall")
        build_option = nested["tool_decisions"]["build_option"]
        self.assertEqual(build_option["decision_source"], "offline_adapter_fallback")
        self.assertEqual(build_option["generated_option_status"], "ready")
        self.assertEqual(
            build_option["generated_option"]["option_id"],
            "generated_tower_wall",
        )
        self.assertFalse(build_option["direct_world_mutation"])
        self.assertEqual(
            nested["required_tool_calls"],
            [
                "recall_build_prompt_memory",
                "select_build_option",
                "plan_build_actions",
                "propose_build_option",
            ],
        )
        self.assertEqual(
            nested["missing_required_tool_calls"],
            [
                "recall_build_prompt_memory",
                "select_build_option",
                "plan_build_actions",
                "propose_build_option",
            ],
        )

    def test_live_agent_response_uses_tool_trace_decision(self):
        spec = importlib.util.spec_from_file_location("agents_sdk_agent", AGENT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        request = module.sample_request()
        request["public_prompt"] = "Player request: build something surprising"
        request["context"] = {
            "surface_id": "builder",
            "intent": "build_planning",
            "player_request": "build something surprising",
            "candidate_summary": "platform:platform:default:4|fire:fire:fire:1",
        }

        old_sdk_ready = module._sdk_ready
        old_run_sdk_agent = module._run_sdk_agent

        async def fake_run_sdk_agent(_request, model=None):
            return {
                "final_output": "Use the fire option.",
                "tool_trace": [
                    {
                        "tool_name": "recall_build_prompt_memory",
                        "result": {
                            "memory_available": False,
                            "selected_option_id": None,
                            "direct_world_mutation": False,
                        },
                    },
                    {
                        "tool_name": "select_build_option",
                        "result": {
                            "selected_option_id": "fire",
                            "selection_status": "accepted",
                            "candidate_count": 2,
                            "direct_world_mutation": False,
                        },
                    },
                    {
                        "tool_name": "plan_build_actions",
                        "result": {
                            "status": "ready",
                            "selected_option_id": "fire",
                            "step_count": 4,
                            "direct_world_mutation": False,
                            "world_mutation_authority": "luanti",
                        },
                    },
                ],
                "tool_decisions": {
                    "build_option": {
                        "selected_option_id": "fire",
                        "candidate_count": 2,
                        "direct_world_mutation": False,
                    },
                    "build_action_plan": {
                        "status": "ready",
                        "selected_option_id": "fire",
                        "step_count": 4,
                        "direct_world_mutation": False,
                        "world_mutation_authority": "luanti",
                    },
                },
            }

        try:
            module._sdk_ready = lambda: True
            module._run_sdk_agent = fake_run_sdk_agent
            response = module.run_model_adapter_request(request)
        finally:
            module._sdk_ready = old_sdk_ready
            module._run_sdk_agent = old_run_sdk_agent

        self.assertTrue(response["ok"])
        nested = response["response"]
        self.assertTrue(nested["agentic_execution"])
        self.assertEqual(nested["selected_option_id"], "fire")
        self.assertEqual(nested["tool_decision_source"], "agents_sdk_function_tool")
        self.assertEqual(nested["tool_trace"][0]["tool_name"], "recall_build_prompt_memory")
        self.assertEqual(nested["tool_trace"][1]["tool_name"], "select_build_option")
        self.assertEqual(nested["tool_trace"][2]["tool_name"], "plan_build_actions")
        self.assertEqual(nested["build_action_plan"]["selected_option_id"], "fire")
        self.assertEqual(nested["build_action_plan"]["step_count"], 4)
        self.assertEqual(
            nested["required_tool_calls"],
            ["recall_build_prompt_memory", "select_build_option", "plan_build_actions"],
        )
        self.assertEqual(nested["missing_required_tool_calls"], [])
        self.assertTrue(nested["required_tool_calls_satisfied"])

    def test_live_agent_model_timeout_returns_bounded_fallback(self):
        spec = importlib.util.spec_from_file_location("agents_sdk_agent", AGENT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        request = module.sample_request()
        request["public_prompt"] = "Player request: build a wall of tnt"
        request["context"] = {
            "surface_id": "builder",
            "intent": "build_planning",
            "player_request": "build a wall of tnt",
            "candidate_summary": "platform:platform:default:4|tnt_wall:wall:tnt:12",
        }

        old_key = os.environ.get("OPENAI_API_KEY")
        old_timeout = os.environ.get("AI_NATIVE_AGENT_MODEL_TIMEOUT_SECONDS")
        old_agent = module.Agent
        old_runner = module.Runner
        os.environ["OPENAI_API_KEY"] = "test-key"
        os.environ["AI_NATIVE_AGENT_MODEL_TIMEOUT_SECONDS"] = "0.05"

        class SlowAgent:
            def __init__(self, *args, **kwargs):
                pass

        class SlowRunner:
            @staticmethod
            async def run(*args, **kwargs):
                await asyncio.sleep(2)
                return "too late"

        module.Agent = SlowAgent
        module.Runner = SlowRunner
        try:
            response = module.run_model_adapter_request(request)
        finally:
            module.Agent = old_agent
            module.Runner = old_runner
            if old_key is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = old_key
            if old_timeout is None:
                os.environ.pop("AI_NATIVE_AGENT_MODEL_TIMEOUT_SECONDS", None)
            else:
                os.environ["AI_NATIVE_AGENT_MODEL_TIMEOUT_SECONDS"] = old_timeout

        self.assertTrue(response["ok"])
        self.assertEqual(response["reason"], "agents_sdk_model_timeout")
        nested = response["response"]
        self.assertFalse(nested["agentic_execution"])
        self.assertTrue(nested["agent_model_timeout"])
        self.assertEqual(
            nested["tool_decision_source"],
            "offline_adapter_fallback_after_agent_timeout",
        )
        self.assertEqual(nested["selected_option_id"], "tnt_wall")
        self.assertEqual(
            nested["missing_required_tool_calls"],
            ["recall_build_prompt_memory", "select_build_option", "plan_build_actions"],
        )

    def test_live_agent_fire_only_mismatch_falls_back_to_constraint(self):
        spec = importlib.util.spec_from_file_location("agents_sdk_agent", AGENT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        request = module.sample_request()
        request["public_prompt"] = "Player request: build me a fire and only a fire"
        request["context"] = {
            "surface_id": "builder",
            "intent": "build_planning",
            "player_request": "build me a fire and only a fire",
            "candidate_summary": "platform:platform:default:4|fire:fire:fire:1",
        }

        old_sdk_ready = module._sdk_ready
        old_run_sdk_agent = module._run_sdk_agent

        async def fake_run_sdk_agent(_request, model=None):
            return {
                "final_output": "Use the platform option.",
                "tool_trace": [
                    {"tool_name": "recall_build_prompt_memory", "result": {}},
                    {
                        "tool_name": "select_build_option",
                        "result": {
                            "selected_option_id": "platform",
                            "selection_status": "accepted",
                            "candidate_count": 2,
                            "direct_world_mutation": False,
                        },
                    },
                    {
                        "tool_name": "plan_build_actions",
                        "result": {
                            "status": "ready",
                            "selected_option_id": "platform",
                            "step_count": 4,
                            "direct_world_mutation": False,
                            "world_mutation_authority": "luanti",
                        },
                    },
                ],
                "tool_decisions": {
                    "build_option": {
                        "selected_option_id": "platform",
                        "selection_status": "accepted",
                        "candidate_count": 2,
                        "direct_world_mutation": False,
                    },
                    "build_action_plan": {
                        "status": "ready",
                        "selected_option_id": "platform",
                        "step_count": 4,
                        "direct_world_mutation": False,
                        "world_mutation_authority": "luanti",
                    },
                },
            }

        try:
            module._sdk_ready = lambda: True
            module._run_sdk_agent = fake_run_sdk_agent
            response = module.run_model_adapter_request(request)
        finally:
            module._sdk_ready = old_sdk_ready
            module._run_sdk_agent = old_run_sdk_agent

        self.assertTrue(response["ok"])
        nested = response["response"]
        self.assertEqual(nested["selected_option_id"], "fire")
        self.assertEqual(nested["model_selected_option_id"], "platform")
        self.assertEqual(nested["rejected_model_selected_option_id"], "platform")
        self.assertEqual(nested["intent_constraint_option_id"], "fire")
        self.assertEqual(
            nested["intent_constraint_reason"],
            "player_request_requires_fire_only",
        )
        self.assertEqual(
            nested["tool_decision_source"],
            "adapter_fallback_after_agent_violated_player_request_constraints",
        )
        self.assertEqual(
            nested["tool_decisions"]["build_option"]["selected_option_id"],
            "fire",
        )

    def test_live_generated_option_requires_propose_tool_trace(self):
        spec = importlib.util.spec_from_file_location("agents_sdk_agent", AGENT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        request = module.sample_request()
        request["public_prompt"] = "Player request: build me a tower"
        request["context"] = {
            "surface_id": "builder",
            "intent": "build_planning",
            "player_request": "build me a tower",
            "candidate_summary": "platform:platform:default:4|wall:wall:default:12",
        }

        old_sdk_ready = module._sdk_ready
        old_run_sdk_agent = module._run_sdk_agent

        async def fake_run_sdk_agent(_request, model=None):
            generated = {
                "option_id": "generated_tower_wall",
                "build_kind": "wall",
                "build_width": 3,
                "build_height": 4,
                "build_material_name": "stone",
                "planned_node_writes": 12,
            }
            return {
                "final_output": "Use the generated tower option.",
                "tool_trace": [
                    {
                        "tool_name": "recall_build_prompt_memory",
                        "result": {
                            "memory_available": False,
                            "selected_option_id": None,
                            "direct_world_mutation": False,
                        },
                    },
                    {
                        "tool_name": "select_build_option",
                        "result": {
                            "selected_option_id": "generated_tower_wall",
                            "selection_status": "accepted",
                            "candidate_count": 2,
                            "decision_source": "generated_build_option_tool",
                            "generated_option_status": "ready",
                            "generated_option": generated,
                            "direct_world_mutation": False,
                        },
                    },
                ],
                "tool_decisions": {
                    "build_option": {
                        "selected_option_id": "generated_tower_wall",
                        "candidate_count": 2,
                        "decision_source": "generated_build_option_tool",
                        "generated_option_status": "ready",
                        "generated_option": generated,
                        "direct_world_mutation": False,
                    },
                },
            }

        try:
            module._sdk_ready = lambda: True
            module._run_sdk_agent = fake_run_sdk_agent
            response = module.run_model_adapter_request(request)
        finally:
            module._sdk_ready = old_sdk_ready
            module._run_sdk_agent = old_run_sdk_agent

        self.assertTrue(response["ok"])
        nested = response["response"]
        self.assertTrue(nested["agentic_execution"])
        self.assertEqual(nested["selected_option_id"], "generated_tower_wall")
        self.assertEqual(
            nested["tool_decision_source"],
            "adapter_fallback_after_agent_missing_required_tool",
        )
        self.assertEqual(
            nested["required_tool_calls"],
            [
                "recall_build_prompt_memory",
                "select_build_option",
                "plan_build_actions",
                "propose_build_option",
            ],
        )
        self.assertEqual(
            nested["missing_required_tool_calls"],
            ["plan_build_actions", "propose_build_option"],
        )
        self.assertFalse(nested["required_tool_calls_satisfied"])
        self.assertEqual(
            nested["tool_decisions"]["build_option"]["decision_source"],
            "offline_adapter_fallback",
        )

    def test_live_generated_option_with_propose_tool_trace_is_healthy(self):
        spec = importlib.util.spec_from_file_location("agents_sdk_agent", AGENT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        request = module.sample_request()
        request["public_prompt"] = "Player request: build me a tower"
        request["context"] = {
            "surface_id": "builder",
            "intent": "build_planning",
            "player_request": "build me a tower",
            "candidate_summary": "platform:platform:default:4|wall:wall:default:12",
        }

        old_sdk_ready = module._sdk_ready
        old_run_sdk_agent = module._run_sdk_agent

        async def fake_run_sdk_agent(_request, model=None):
            generated = {
                "option_id": "generated_tower_wall",
                "build_kind": "wall",
                "build_width": 3,
                "build_height": 4,
                "build_material_name": "stone",
                "planned_node_writes": 12,
            }
            propose_result = {
                "status": "ready",
                "generated_option": generated,
                "direct_world_mutation": False,
            }
            select_result = {
                "selected_option_id": "generated_tower_wall",
                "selection_status": "accepted",
                "candidate_count": 2,
                "decision_source": "agent_selected_generated_build_option",
                "generated_option_status": "ready",
                "generated_option": generated,
                "direct_world_mutation": False,
            }
            return {
                "final_output": "Use the generated tower option.",
                "tool_trace": [
                    {"tool_name": "recall_build_prompt_memory", "result": {}},
                    {"tool_name": "propose_build_option", "result": propose_result},
                    {"tool_name": "select_build_option", "result": select_result},
                    {
                        "tool_name": "plan_build_actions",
                        "result": {
                            "status": "ready",
                            "selected_option_id": "generated_tower_wall",
                            "step_count": 4,
                            "direct_world_mutation": False,
                            "world_mutation_authority": "luanti",
                        },
                    },
                ],
                "tool_decisions": {
                    "build_option": select_result,
                    "build_action_plan": {
                        "status": "ready",
                        "selected_option_id": "generated_tower_wall",
                        "step_count": 4,
                        "direct_world_mutation": False,
                        "world_mutation_authority": "luanti",
                    },
                },
            }

        try:
            module._sdk_ready = lambda: True
            module._run_sdk_agent = fake_run_sdk_agent
            response = module.run_model_adapter_request(request)
        finally:
            module._sdk_ready = old_sdk_ready
            module._run_sdk_agent = old_run_sdk_agent

        self.assertTrue(response["ok"])
        nested = response["response"]
        self.assertTrue(nested["agentic_execution"])
        self.assertEqual(nested["selected_option_id"], "generated_tower_wall")
        self.assertEqual(nested["tool_decision_source"], "agents_sdk_function_tool")
        self.assertEqual(
            nested["required_tool_calls"],
            [
                "recall_build_prompt_memory",
                "select_build_option",
                "plan_build_actions",
                "propose_build_option",
            ],
        )
        self.assertEqual(nested["missing_required_tool_calls"], [])
        self.assertTrue(nested["required_tool_calls_satisfied"])
        self.assertEqual(nested["build_action_plan"]["step_count"], 4)
        self.assertEqual(
            nested["tool_decisions"]["build_option"]["decision_source"],
            "agent_selected_generated_build_option",
        )

    def test_build_planning_missing_required_tool_is_labeled_for_improvement(self):
        spec = importlib.util.spec_from_file_location("agents_sdk_agent", AGENT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        request = module.sample_request()
        request["public_prompt"] = "Player request: build a wall of tnt"
        request["context"] = {
            "surface_id": "builder",
            "intent": "build_planning",
            "player_request": "build a wall of tnt",
            "candidate_summary": "platform:platform:default:4|tnt_wall:wall:tnt:12",
        }

        old_sdk_ready = module._sdk_ready
        old_run_sdk_agent = module._run_sdk_agent

        async def fake_run_sdk_agent(_request, model=None):
            return {
                "final_output": "I can make that dramatic.",
                "tool_trace": [],
                "tool_decisions": {},
            }

        try:
            module._sdk_ready = lambda: True
            module._run_sdk_agent = fake_run_sdk_agent
            response = module.run_model_adapter_request(request)
        finally:
            module._sdk_ready = old_sdk_ready
            module._run_sdk_agent = old_run_sdk_agent

        self.assertTrue(response["ok"])
        nested = response["response"]
        self.assertTrue(nested["agentic_execution"])
        self.assertEqual(nested["selected_option_id"], "tnt_wall")
        self.assertEqual(
            nested["tool_decision_source"],
            "adapter_fallback_after_agent_missing_required_tool",
        )
        self.assertEqual(
            nested["required_tool_calls"],
            ["recall_build_prompt_memory", "select_build_option", "plan_build_actions"],
        )
        self.assertEqual(
            nested["missing_required_tool_calls"],
            ["recall_build_prompt_memory", "select_build_option", "plan_build_actions"],
        )
        self.assertFalse(nested["required_tool_calls_satisfied"])
        self.assertEqual(
            nested["tool_decisions"]["build_option"]["decision_source"],
            "offline_adapter_fallback",
        )

    def test_missing_required_tool_gets_agentic_repair_before_fallback(self):
        spec = importlib.util.spec_from_file_location("agents_sdk_agent", AGENT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        request = module.sample_request()
        request["public_prompt"] = "Player request: build a wall of tnt"
        request["context"] = {
            "surface_id": "builder",
            "intent": "build_planning",
            "player_request": "build a wall of tnt",
            "candidate_summary": "platform:platform:default:4|tnt_wall:wall:tnt:12",
        }

        old_sdk_ready = module._sdk_ready
        old_run_sdk_agent = module._run_sdk_agent
        calls = []

        async def fake_run_sdk_agent(_request, model=None):
            calls.append(_request)
            if len(calls) == 1:
                return {
                    "final_output": "I can make that dramatic.",
                    "tool_trace": [],
                    "tool_decisions": {},
                }
            return {
                "final_output": "Use the TNT wall option through Luanti approval.",
                "tool_trace": [
                    {"tool_name": "recall_build_prompt_memory", "result": {}},
                    {
                        "tool_name": "select_build_option",
                        "result": {
                            "selected_option_id": "tnt_wall",
                            "selection_status": "accepted",
                            "candidate_count": 2,
                            "decision_source": "agent_selected_build_option",
                            "direct_world_mutation": False,
                        },
                    },
                    {
                        "tool_name": "plan_build_actions",
                        "result": {
                            "status": "ready",
                            "selected_option_id": "tnt_wall",
                            "step_count": 4,
                            "direct_world_mutation": False,
                            "world_mutation_authority": "luanti",
                        },
                    },
                ],
                "tool_decisions": {
                    "build_option": {
                        "selected_option_id": "tnt_wall",
                        "selection_status": "accepted",
                        "candidate_count": 2,
                        "decision_source": "agent_selected_build_option",
                        "direct_world_mutation": False,
                    },
                    "build_action_plan": {
                        "status": "ready",
                        "selected_option_id": "tnt_wall",
                        "step_count": 4,
                        "direct_world_mutation": False,
                        "world_mutation_authority": "luanti",
                    },
                },
            }

        try:
            module._sdk_ready = lambda: True
            module._run_sdk_agent = fake_run_sdk_agent
            response = module.run_model_adapter_request(request)
        finally:
            module._sdk_ready = old_sdk_ready
            module._run_sdk_agent = old_run_sdk_agent

        self.assertEqual(len(calls), 2)
        self.assertIn("Agent repair pass:", calls[1]["public_prompt"])
        nested = response["response"]
        self.assertEqual(nested["selected_option_id"], "tnt_wall")
        self.assertEqual(nested["tool_decision_source"], "agents_sdk_repair_function_tool")
        self.assertTrue(nested["agent_repair_attempted"])
        self.assertTrue(nested["agent_repair_succeeded"])
        self.assertEqual(nested["agent_repair_reason"], "agent_missing_required_tool")
        self.assertEqual(
            nested["initial_missing_required_tool_calls"],
            ["recall_build_prompt_memory", "select_build_option", "plan_build_actions"],
        )
        self.assertEqual(nested["missing_required_tool_calls"], [])
        self.assertTrue(nested["required_tool_calls_satisfied"])

    def test_request_response_log_is_public_safe_jsonl(self):
        spec = importlib.util.spec_from_file_location("agents_sdk_agent", AGENT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = pathlib.Path(tmpdir) / "agents-sdk-model-adapter.jsonl"
            old_log_path = os.environ.get("AI_NATIVE_AGENT_LOG_PATH")
            os.environ["AI_NATIVE_AGENT_LOG_PATH"] = str(log_path)
            try:
                request = module.sample_request()
                request["context"]["private_prompt"] = "must-not-log"
                request["context"]["api_key"] = "must-not-log"
                response = module.run_model_adapter_request(request, force_offline=True)
            finally:
                if old_log_path is None:
                    os.environ.pop("AI_NATIVE_AGENT_LOG_PATH", None)
                else:
                    os.environ["AI_NATIVE_AGENT_LOG_PATH"] = old_log_path

            self.assertTrue(response["ok"])
            lines = log_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            entry = json.loads(lines[0])
            raw_entry = json.dumps(entry, sort_keys=True)
            self.assertEqual(entry["event_kind"], "ai_native_agents_sdk_request_response")
            self.assertEqual(entry["adapter_name"], "openai-agents-sdk-model-adapter")
            self.assertEqual(entry["request"]["request_kind"], "ai_native_model_adapter_request")
            self.assertEqual(entry["response"]["response_kind"], "ai_native_model_adapter_response")
            self.assertNotIn("must-not-log", raw_entry)
            self.assertNotIn("OPENAI_API_KEY", raw_entry)
            self.assertNotIn("private_prompt", raw_entry)
            self.assertNotIn("api_key", entry["request"]["context"])

    def test_cli_contract_passes(self):
        completed = subprocess.run(
            [sys.executable, str(CONTRACT)],
            cwd=ROOT,
            check=False,
            text=True,
            capture_output=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn('"status": "pass"', completed.stdout)


if __name__ == "__main__":
    unittest.main()
