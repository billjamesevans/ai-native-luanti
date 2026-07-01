import importlib.util
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
QUEUE = ROOT / "util" / "ai_native_agent_eval_queue.py"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"
OPERATING_LOOP = ROOT / "doc" / "ai-native-runtime" / "project-operating-loop.md"
ADAPTER_DOC = ROOT / "doc" / "ai-native-runtime" / "agents-sdk-model-adapter.md"

PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload|/Users/",
    re.I,
)
DOC_PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|/Users/",
    re.I,
)


def load_queue_module():
    assert QUEUE.is_file(), f"missing {QUEUE}"
    spec = importlib.util.spec_from_file_location("ai_native_agent_eval_queue", QUEUE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def agents_sdk_log_entry(prompt="build me a fire and only a fire"):
    return {
        "schema_version": 1,
        "event_kind": "ai_native_agents_sdk_request_response",
        "created_at": "2026-06-30T12:00:00Z",
        "adapter_name": "openai-agents-sdk-model-adapter",
        "request": {
            "request_kind": "ai_native_model_adapter_request",
            "adapter_contract": "provider_neutral_v1",
            "agent_id": "nova_agent:Eval:guide",
            "owner": "Eval",
            "task_id": "ai-agent-eval:model",
            "public_prompt": prompt,
            "context": {
                "surface_id": "guide",
                "capabilities": "world.read,http.llm",
            },
            "safety": {"public_safe_request": True},
            "bounds": {"max_response_bytes": 4000},
        },
        "response": {
            "response_kind": "ai_native_model_adapter_response",
            "adapter_contract": "provider_neutral_v1",
            "ok": True,
            "message": "Use the fire primitive only after Luanti preview approval.",
            "adapter_name": "openai-agents-sdk-model-adapter",
            "elapsed_us": 42,
            "response": {
                "agentic_execution": True,
                "tools_enabled": ["select_build_option", "recommend_build_option", "classify_world_action"],
                "world_mutation_authority": "luanti",
            },
        },
    }


def agents_sdk_missing_required_tool_entry():
    entry = agents_sdk_log_entry("AI-native Luanti model adapter request.")
    entry["request"]["context"].update({
        "intent": "build_planning",
        "player_request": "build me a tower",
        "candidate_summary": "platform:platform:default:4|wall:wall:default:12",
    })
    entry["response"]["message"] = "Fell back to bounded tower planning after missing SDK tool evidence."
    entry["response"]["response"].update({
        "agentic_execution": True,
        "selected_option_id": "generated_tower_wall",
        "tool_decision_source": "adapter_fallback_after_agent_missing_required_tool",
        "required_tool_calls": [
            "recall_build_prompt_memory",
            "select_build_option",
            "propose_build_option",
        ],
        "missing_required_tool_calls": ["propose_build_option"],
        "required_tool_calls_satisfied": False,
        "tool_trace": [
            {"tool_name": "recall_build_prompt_memory"},
            {"tool_name": "select_build_option"},
        ],
        "tool_decisions": {
            "build_option": {
                "selected_option_id": "generated_tower_wall",
                "decision_source": "agent_selected_generated_build_option",
                "generated_option_status": "ready",
                "direct_world_mutation": False,
            },
        },
    })
    return entry


def agents_sdk_generated_option_entry():
    entry = agents_sdk_log_entry("AI-native Luanti model adapter request.")
    entry["request"]["context"].update({
        "intent": "build_planning",
        "player_request": "build a 6 wide 2 high lookout wall",
        "candidate_summary": "platform:platform:default:4|wall:wall:default:12",
    })
    generated = {
        "option_id": "generated_dimensioned_wall",
        "build_kind": "wall",
        "build_width": 6,
        "build_height": 2,
        "build_material_name": "stone",
        "planned_node_writes": 12,
        "reason": "player_requested_specific_dimensions",
    }
    select_result = {
        "selected_option_id": "generated_dimensioned_wall",
        "selection_status": "accepted",
        "candidate_count": 3,
        "decision_source": "agent_selected_generated_build_option",
        "generated_option_status": "ready",
        "generated_option": generated,
        "direct_world_mutation": False,
    }
    plan_result = {
        "status": "ready",
        "selected_option_id": "generated_dimensioned_wall",
        "step_count": 4,
        "direct_world_mutation": False,
        "world_mutation_authority": "luanti",
    }
    entry["response"]["message"] = "Use the generated 6 wide 2 high wall option."
    entry["response"]["response"].update({
        "agentic_execution": True,
        "tools_enabled": [
            "recall_build_prompt_memory",
            "propose_build_option",
            "select_build_option",
            "plan_build_actions",
        ],
        "selected_option_id": "generated_dimensioned_wall",
        "tool_decision_source": "agents_sdk_function_tool",
        "required_tool_calls": [
            "recall_build_prompt_memory",
            "select_build_option",
            "plan_build_actions",
            "propose_build_option",
        ],
        "missing_required_tool_calls": [],
        "required_tool_calls_satisfied": True,
        "world_mutation_authority": "luanti",
        "tool_trace": [
            {"tool_name": "recall_build_prompt_memory", "result": {}},
            {
                "tool_name": "propose_build_option",
                "result": {
                    "status": "ready",
                    "generated_option": generated,
                    "direct_world_mutation": False,
                },
            },
            {"tool_name": "select_build_option", "result": select_result},
            {"tool_name": "plan_build_actions", "result": plan_result},
        ],
        "build_action_plan": plan_result,
        "tool_decisions": {
            "build_option": select_result,
            "build_action_plan": plan_result,
        },
    })
    return entry


def resolved_generated_wall_contract_entries():
    failed = agents_sdk_missing_required_tool_entry()
    failed["created_at"] = "2026-06-30T15:04:13Z"
    failed["request"]["context"]["player_request"] = "build a 6 wide 2 high lookout wall"
    failed["request"]["context"]["candidate_summary"] = "platform:platform:default:4|wall:wall:default:12"
    failed["response"]["response"].update({
        "selected_option_id": "generated_dimensioned_wall",
        "model_selected_option_id": "generated_dimensioned_wall",
        "tool_decisions": {
            "build_option": {
                "selected_option_id": "generated_dimensioned_wall",
                "decision_source": "offline_adapter_fallback",
                "generated_option_status": "ready",
                "generated_option": {
                    "option_id": "generated_dimensioned_wall",
                    "build_kind": "wall",
                    "build_width": 6,
                    "build_height": 2,
                    "build_material_name": "stone",
                    "planned_node_writes": 12,
                },
                "direct_world_mutation": False,
            },
        },
    })
    passed = agents_sdk_generated_option_entry()
    passed["created_at"] = "2026-06-30T15:12:29Z"
    return failed, passed


def request_response_log_gate_payload():
    def case(
        *,
        case_id,
        prompt,
        selected_option_id,
        candidate_summary,
        build_kind,
        material,
        planned_writes,
        tool_source="agents_sdk_function_tool",
        generated=None,
    ):
        required = [
            "recall_build_prompt_memory",
            "select_build_option",
            "plan_build_actions",
        ]
        trace = list(required)
        generated_status = "not_needed"
        generated_fields = {}
        if generated:
            required.append("propose_build_option")
            trace = [
                "recall_build_prompt_memory",
                "propose_build_option",
                "select_build_option",
                "plan_build_actions",
            ]
            generated_status = "ready"
            generated_fields = {
                "generated_option_id": generated["option_id"],
                "generated_option_build_kind": generated["build_kind"],
                "generated_option_build_material_name": generated["build_material_name"],
                "generated_option_build_width": generated.get("build_width"),
                "generated_option_build_depth": generated.get("build_depth"),
                "generated_option_build_height": generated.get("build_height"),
                "generated_option_build_count": generated.get("build_count"),
                "generated_option_planned_node_writes": generated["planned_node_writes"],
            }
        return {
            "case_id": case_id,
            "prompt": prompt,
            "status": "pass",
            "matches": 1,
            "failures": [],
            "observed": {
                "created_at": "2026-06-30T21:11:17Z",
                "event_kind": "ai_native_agents_sdk_request_response",
                "adapter_name": "openai-agents-sdk-model-adapter",
                "request": {
                    "agent_id": "nova_agent:PromptEvalLive",
                    "owner": "PromptEvalLive",
                    "task_id": f"ai-agent-build-planner:{case_id}",
                    "public_prompt": f"Player request: {prompt}",
                    "context": {
                        "intent": "build_planning",
                        "player_request": prompt,
                        "candidate_summary": candidate_summary,
                        "surface_id": "builder",
                    },
                },
                "response": {
                    "ok": True,
                    "message": f"Selected {selected_option_id}.",
                    "reason": "",
                    "selected_option_id": selected_option_id,
                    "tool_decision_source": tool_source,
                    "required_tool_calls": required,
                    "missing_required_tool_calls": [],
                    "required_tool_calls_satisfied": True,
                    "tool_trace_names": trace,
                    "build_action_plan_status": "ready",
                    "build_action_plan_step_count": 4,
                    "build_action_plan_build_kind": build_kind,
                    "build_action_plan_build_material_name": material,
                    "build_action_plan_planned_node_writes": planned_writes,
                    "world_mutation_authority": "luanti",
                    "generated_option_status": generated_status,
                    **generated_fields,
                },
            },
        }

    return {
        "schema_version": 1,
        "artifact_kind": "ai_native_agent_request_response_log_gate",
        "generated_at": "2026-06-30T21:12:00Z",
        "status": "pass",
        "source_summary": {
            "files_read": 1,
            "lines_read": 4,
            "entries_read": 4,
            "case_count": 4,
            "cases_passed": 4,
            "cases_failed": 0,
        },
        "cases": [
            case(
                case_id="build_fire",
                prompt="build a fire",
                selected_option_id="fire",
                candidate_summary="platform:platform:default:4|fire:fire:fire:1",
                build_kind="fire",
                material="fire",
                planned_writes=1,
            ),
            case(
                case_id="fire_only_strict",
                prompt="build me a fire and only a fire",
                selected_option_id="fire",
                candidate_summary="platform:platform:default:4|fire:fire:fire:1",
                build_kind="fire",
                material="fire",
                planned_writes=1,
            ),
            case(
                case_id="tnt_wall",
                prompt="build a wall of tnt",
                selected_option_id="tnt_wall",
                candidate_summary="platform:platform:default:4|tnt_wall:wall:tnt:12",
                build_kind="wall",
                material="tnt",
                planned_writes=12,
            ),
            case(
                case_id="generated_build_option",
                prompt="build a small shelter",
                selected_option_id="generated_shelter_floor",
                candidate_summary="platform:platform:default:4|wall:wall:default:12",
                build_kind="platform",
                material="stone",
                planned_writes=12,
                tool_source="local_agent_tool_contract_fast_path",
                generated={
                    "option_id": "generated_shelter_floor",
                    "build_kind": "platform",
                    "build_material_name": "stone",
                    "build_width": 4,
                    "build_depth": 3,
                    "planned_node_writes": 12,
                },
            ),
        ],
        "failures": [],
        "violations": [],
        "safety": {"public_safe_output": True, "no_world_mutation": True},
    }


def nova_trace_line(prompt="build a wall of tnt"):
    payload = {
        "schema_version": 1,
        "event_kind": "nova_request_trace",
        "event": "completed",
        "trace": {
            "trace_id": "nova_trace:99",
            "owner": "Eval",
            "agent_id": "nova_agent:Eval:builder",
            "action": "build",
            "route": "deterministic_build_parser",
            "public_prompt": prompt,
            "completed_us": 123456,
            "response": {
                "ok": True,
                "status": "pending_approval",
                "action": "build",
                "build_kind": "wall",
                "build_material_name": "tnt",
                "planned_node_writes": 12,
                "approval_id": "approval:tnt",
                "selected_candidate_id": "tnt_wall",
                "adapter_selected_candidate_id": "tnt_wall",
                "model_selected_candidate_id": "tnt_wall",
                "selection_source": "model_tool_decision",
                "adapter_tool_decision_source": "agents_sdk_function_tool",
                "adapter_required_tool_calls": [
                    "recall_build_prompt_memory",
                    "select_build_option",
                ],
                "adapter_missing_required_tool_calls": [],
                "adapter_required_tool_calls_satisfied": True,
                "build_option_decision_source": "agent_selected_build_option",
                "adapter_memory_available": True,
                "adapter_memory_matched_case_id": "promoted_tnt_wall_123",
                "adapter_memory_case_hint": "tnt_wall",
                "adapter_tool_trace_names": [
                    "recall_build_prompt_memory",
                    "select_build_option",
                    "plan_build_actions",
                ],
                "adapter_build_action_plan_status": "ready",
                "adapter_build_action_plan_step_count": 4,
                "adapter_build_action_plan_selected_candidate_id": "tnt_wall",
            },
        },
    }
    return "[ai_agent_plugin] request_trace=" + json.dumps(payload, sort_keys=True)


def nova_agent_log_entry(prompt="build a wall of tnt"):
    return {
        "ts": "2026-06-30T12:10:00Z",
        "player": "Eval",
        "prompt": prompt,
        "model": "gpt-5-nano",
        "source": "agents_sdk",
        "ok": True,
        "label": "tnt wall",
        "message": "Building a tnt wall.",
        "correction_source": "prompt_contract",
        "contract_satisfied": True,
        "prompt_contract": {
            "intent": "build",
            "material": "tnt",
            "contract_kind": "tnt_wall",
            "contract_required": True,
        },
        "actions": [
            {
                "type": "fill_box",
                "material": "tnt",
                "offset": {"x": 0, "y": 1, "z": 0},
                "size": {"x": 15, "y": 5, "z": 1},
            }
        ],
        "tool_trace": [
            {"tool_name": "analyze_build_intent", "result": {"contract_kind": "tnt_wall"}},
            {"tool_name": "validate_plan_contract", "result": {"contract_satisfied": False}},
        ],
    }


def nova_agent_fire_only_option_log_entry():
    return {
        "ts": "2026-06-30T12:14:00Z",
        "player": "Eval",
        "prompt": "build me a fire and only a fire",
        "model": "gpt-5-nano",
        "source": "agents_sdk_tool_plan",
        "tool_decision_source": "agents_sdk_submit_nova_plan_tool",
        "required_tool_calls": [
            "recall_build_prompt_memory",
            "analyze_build_intent",
            "draft_build_options",
            "validate_plan_contract",
            "submit_nova_plan",
        ],
        "missing_required_tool_calls": [],
        "required_tool_calls_satisfied": True,
        "ok": True,
        "label": "single fire",
        "message": "Placing one fire from reviewed prompt memory.",
        "selected_option_id": "reviewed_prompt_memory",
        "decision_reason": "The strict prompt asks for one fire and no extra structure.",
        "contract_satisfied": True,
        "prompt_contract": {
            "intent": "build",
            "material": "fire",
            "contract_kind": "single_fire",
            "contract_required": True,
        },
        "reviewed_prompt_memory": {
            "matched_case_id": "promoted_fire_only_strict_abc123",
            "case_hint": "fire_only_strict",
            "match_quality": "exact",
        },
        "build_options": [
            {
                "option_id": "reviewed_prompt_memory",
                "source": "reviewed_prompt_memory",
                "label": "single fire",
                "build_kind": "fire",
                "build_material_name": "fire",
                "planned_node_writes": 1,
                "contract_satisfied": True,
                "action_count": 1,
            },
            {
                "option_id": "generic_structure",
                "source": "fallback",
                "label": "generic structure",
                "build_kind": "house",
                "build_material_name": "stone",
                "planned_node_writes": 100,
                "contract_satisfied": False,
                "action_count": 2,
            },
        ],
        "actions": [
            {
                "type": "place_node",
                "material": "fire",
                "offset": {"x": 0, "y": 1, "z": 0},
                "count": 1,
            }
        ],
        "tool_trace": [
            {"tool_name": "recall_build_prompt_memory"},
            {"tool_name": "analyze_build_intent"},
            {"tool_name": "draft_build_options"},
            {"tool_name": "validate_plan_contract"},
            {"tool_name": "submit_nova_plan"},
        ],
    }


def nova_agent_gold_house_option_log_entry():
    return {
        "ts": "2026-06-30T12:16:00Z",
        "player": "Eval",
        "prompt": "build a house out of gold",
        "model": "gpt-5-nano",
        "source": "agents_sdk_tool_plan",
        "tool_decision_source": "agents_sdk_submit_nova_plan_tool",
        "required_tool_calls": ["resolve_build_plan", "submit_nova_plan"],
        "missing_required_tool_calls": [],
        "required_tool_calls_satisfied": True,
        "ok": True,
        "label": "gold house",
        "message": "Building a compact gold house.",
        "selected_option_id": "prompt_shaped_build",
        "build_kind": "house",
        "build_material_name": "gold",
        "planned_node_writes": 220,
        "decision_reason": "Selected the prompt-shaped house option.",
        "contract_satisfied": True,
        "build_options": [
            {
                "option_id": "prompt_shaped_build",
                "source": "local_prompt_shape",
                "label": "gold house",
                "build_kind": "house",
                "build_material_name": "gold",
                "planned_node_writes": 220,
                "contract_satisfied": True,
                "action_count": 4,
            }
        ],
        "actions": [
            {
                "type": "hollow_box",
                "material": "gold",
                "offset": {"x": 0, "y": 1, "z": 0},
                "size": {"x": 9, "y": 5, "z": 7},
            },
            {
                "type": "fill_box",
                "material": "gold",
                "offset": {"x": 0, "y": 6, "z": 0},
                "size": {"x": 11, "y": 1, "z": 9},
            },
        ],
        "tool_trace": [
            {"tool_name": "resolve_build_plan"},
            {"tool_name": "submit_nova_plan"},
        ],
    }


def nova_agent_resolved_plan_timeout_log_entry():
    return {
        "ts": "2026-06-30T12:18:00Z",
        "player": "Eval",
        "prompt": "build a small cabin here",
        "model": "gpt-5-nano",
        "agent_runtime": "openai-agents-sdk",
        "agent_model_called": True,
        "agent_model_status": "timeout_after_resolve",
        "fallback_reason": "runner_timeout_after_resolve",
        "source": "agents_sdk_resolved_plan_after_timeout",
        "tool_decision_source": "resolve_build_plan_recommended_plan",
        "required_tool_calls": ["resolve_build_plan"],
        "missing_required_tool_calls": [],
        "required_tool_calls_satisfied": True,
        "ok": True,
        "label": "agent custom build",
        "message": "Nova accepted: agent custom build.",
        "selected_option_id": "best_guess",
        "decision_reason": "Used the resolve_build_plan recommended plan after the runner timed out before submit.",
        "contract_satisfied": True,
        "reviewed_prompt_memory": {"memory_available": True},
        "build_options": [
            {
                "option_id": "best_guess",
                "source": "local_best_guess",
                "label": "agent custom build",
                "contract_satisfied": True,
                "action_count": 2,
            }
        ],
        "actions": [
            {
                "type": "hollow_box",
                "material": "stone",
                "offset": {"x": 0, "y": 1, "z": 0},
                "size": {"x": 11, "y": 7, "z": 11},
            },
            {
                "type": "sphere",
                "material": "glass",
                "offset": {"x": 0, "y": 12, "z": 0},
                "radius": 4,
            },
        ],
        "tool_trace": [
            {"tool_name": "resolve_build_plan", "result": {"recommended_option_id": "best_guess"}},
        ],
    }


def operator_labels_payload(prompt="build a bridge"):
    return {
        "schema_version": 1,
        "artifact_kind": "ai_native_agent_eval_operator_labels",
        "labels": [
            {
                "label_id": "reviewed_stone_bridge_platform",
                "prompt": prompt,
                "case_hint": "stone_bridge_platform",
                "expected": {
                    "action": "build",
                    "build_kind": "platform",
                    "build_material_name": "stone",
                    "planned_node_writes": 12,
                    "route": "agentic_build_planner",
                },
            }
        ],
    }


def verified_live_probe_payload(cases=None):
    def probe_case(
        case_id,
        prompt,
        selected,
        build_kind,
        material,
        writes,
        *,
        width=None,
        height=None,
        generated=False,
    ):
        tool_trace = ["recall_build_prompt_memory", "select_build_option", "plan_build_actions"]
        if generated:
            tool_trace = [
                "recall_build_prompt_memory",
                "select_build_option",
                "propose_build_option",
                "select_build_option",
                "plan_build_actions",
            ]
        return {
            "case_id": case_id,
            "prompt": prompt,
            "status": "pass",
            "ok": True,
            "expected_candidate": selected,
            "expected_node": f"ai_runtime_base:{material}",
            "expected_writes": writes,
            "node_count": writes,
            "non_air_count": writes,
            "checks": {
                "agentic_route": True,
                "reply_queued": True,
                "auto_applied": True,
                "approved_build": True,
                "selected_candidate": True,
                "kind": True,
                "material": True,
                "node": True,
                "planned_writes": True,
                "width": True,
                "height": True,
                "required_tools": True,
                "tool_trace_names": True,
                "action_plan_ready": True,
                "world_mutation_authority": True,
                "generated_option": True,
                "task_completed": True,
                "rollback_record": True,
                "node_count": True,
                "no_extra_nodes": True,
            },
            "trace": {
                "route": "agentic_build_planner",
                "action": "build",
                "public_prompt": prompt,
            },
            "reply": {
                "ok": True,
                "action": "build",
                "status": "queued",
                "approved_action": "build",
                "auto_applied_approval": True,
                "auto_apply_policy": "ai_runtime.auto_apply_build_approvals",
                "planner_mode": "agentic_model_adapter",
                "selected_candidate_id": selected,
                "adapter_tool_decision_source": "agents_sdk_function_tool",
                "adapter_required_tool_calls_satisfied": True,
                "adapter_missing_required_tool_calls": None,
                "adapter_tool_trace_names": tool_trace,
                "adapter_build_action_plan_status": "ready",
                "adapter_build_action_plan_step_count": 4,
                "adapter_build_action_plan_world_mutation_authority": "luanti",
                "planned_node_writes": writes,
                "build_kind": build_kind,
                "build_material_name": material,
                "build_material_node": f"ai_runtime_base:{material}",
                "build_width": width,
                "build_height": height,
                "generated_build_option_status": "validated" if generated else None,
                "generated_candidate_id": selected if generated else None,
                "agentic_tool_success_required": generated,
            },
        }

    if cases is None:
        cases = [
            probe_case("fire_only_strict", "build me a fire and only a fire", "fire", "fire", "fire", 1),
            probe_case("tnt_wall", "build a wall of tnt", "tnt_wall", "wall", "tnt", 12, width=4, height=3),
            probe_case(
                "generated_dimensioned_wall",
                "build a 6 wide 2 high lookout wall",
                "generated_dimensioned_wall",
                "wall",
                "stone",
                12,
                width=6,
                height=2,
                generated=True,
            ),
        ]
    return {
        "schema_version": 1,
        "live_result_kind": "ai_native_nova_auto_apply_live_result",
        "generated_at": "2026-06-30T14:41:15Z",
        "status": "pass",
        "ok": True,
        "reason": None,
        "runtime_context": {
            "mode": "disposable_live_ai_runtime_nova_auto_apply_probe",
            "requires_private_world": False,
            "requires_private_assets": False,
            "world_mutation_scope": "disposable_synthetic_ai_runtime_world",
        },
        "summary": {
            "cases_total": len(cases),
            "cases_passed": len(cases),
            "cases_failed": 0,
            "agentic_build_planner_checked": True,
            "auto_apply_checked": True,
        },
        "cases": cases,
        "safety": {
            "public_safe_output": True,
            "requires_private_world": False,
            "requires_private_assets": False,
        },
    }


class AgentEvalQueueTests(unittest.TestCase):
    def test_builds_public_safe_eval_candidates_from_sidecar_and_nova_logs(self):
        module = load_queue_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            nova_agent_log = root / "nova-agent-requests.jsonl"
            action_log = root / "debug.log"
            sidecar_log.write_text(json.dumps(agents_sdk_log_entry()) + "\n", encoding="utf-8")
            nova_agent_log.write_text(json.dumps(nova_agent_log_entry()) + "\n", encoding="utf-8")
            action_log.write_text(nova_trace_line() + "\n", encoding="utf-8")

            payload = module.build_eval_candidate_queue(
                agents_sdk_logs=[sidecar_log],
                nova_agent_logs=[nova_agent_log],
                action_logs=[action_log],
                generated_at="2026-06-30T12:30:00Z",
            )

        self.assertEqual(payload["artifact_kind"], "ai_native_agent_eval_candidate_queue")
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["source_summary"]["agents_sdk_log_entries_read"], 1)
        self.assertEqual(payload["source_summary"]["nova_agent_log_entries_read"], 1)
        self.assertEqual(payload["source_summary"]["nova_request_traces_read"], 1)
        self.assertEqual(payload["source_summary"]["candidates_total"], 3)
        self.assertEqual(payload["source_summary"]["ready_for_prompt_eval"], 3)
        self.assertTrue(payload["safety"]["public_safe_output"])
        self.assertFalse(PRIVATE_PATTERNS.search(json.dumps(payload, sort_keys=True)))

        fire = next(candidate for candidate in payload["candidates"] if candidate["case_hint"] == "fire_only_strict")
        self.assertTrue(fire["ready_for_prompt_eval"])
        self.assertEqual(fire["expected"]["build_kind"], "fire")
        self.assertEqual(fire["expected"]["build_material_name"], "fire")
        self.assertEqual(fire["expected"]["planned_node_writes"], 1)
        self.assertTrue(fire["expected"]["forbidden_extra_structure"])

        tnt_sources = {
            candidate["source_kind"]: candidate
            for candidate in payload["candidates"]
            if candidate["case_hint"] == "tnt_wall"
        }
        self.assertIn("nova_request_trace", tnt_sources)
        self.assertIn("nova_agent_sidecar_request_response", tnt_sources)
        trace_tnt = tnt_sources["nova_request_trace"]
        self.assertEqual(trace_tnt["expected"]["build_kind"], "wall")
        self.assertEqual(trace_tnt["expected"]["build_material_name"], "tnt")
        self.assertEqual(trace_tnt["expected"]["planned_node_writes"], 12)
        self.assertFalse(trace_tnt["expected"]["danger_refusal_allowed"])
        self.assertEqual(
            trace_tnt["observed"]["adapter_tool_decision_source"],
            "agents_sdk_function_tool",
        )
        self.assertEqual(
            trace_tnt["observed"]["adapter_required_tool_calls"],
            ["recall_build_prompt_memory", "select_build_option"],
        )
        self.assertEqual(trace_tnt["observed"]["adapter_missing_required_tool_calls"], [])
        self.assertTrue(trace_tnt["observed"]["adapter_required_tool_calls_satisfied"])
        self.assertEqual(
            trace_tnt["observed"]["build_option_decision_source"],
            "agent_selected_build_option",
        )
        self.assertTrue(trace_tnt["observed"]["adapter_memory_available"])
        self.assertEqual(
            trace_tnt["observed"]["adapter_memory_matched_case_id"],
            "promoted_tnt_wall_123",
        )
        self.assertEqual(
            trace_tnt["observed"]["adapter_tool_trace_names"],
            ["recall_build_prompt_memory", "select_build_option", "plan_build_actions"],
        )
        self.assertEqual(trace_tnt["observed"]["adapter_build_action_plan_status"], "ready")
        self.assertEqual(trace_tnt["observed"]["adapter_build_action_plan_step_count"], 4)
        self.assertEqual(
            trace_tnt["observed"]["adapter_build_action_plan_selected_candidate_id"],
            "tnt_wall",
        )
        self.assertEqual(trace_tnt["observed"]["selected_candidate_id"], "tnt_wall")
        self.assertEqual(trace_tnt["observed"]["model_selected_candidate_id"], "tnt_wall")
        self.assertEqual(trace_tnt["observed"]["selection_source"], "model_tool_decision")
        sidecar_tnt = tnt_sources["nova_agent_sidecar_request_response"]
        self.assertEqual(sidecar_tnt["observed"]["contract_kind"], "tnt_wall")
        self.assertTrue(sidecar_tnt["observed"]["contract_satisfied"])
        self.assertEqual(sidecar_tnt["observed"]["correction_source"], "prompt_contract")
        self.assertEqual(sidecar_tnt["observed"]["build_kind"], "wall")
        self.assertEqual(sidecar_tnt["observed"]["build_material_name"], "tnt")
        self.assertEqual(sidecar_tnt["observed"]["planned_node_writes"], 75)
        self.assertEqual(
            sidecar_tnt["observed"]["tool_trace_names"],
            ["analyze_build_intent", "validate_plan_contract"],
        )

    def test_private_entries_are_skipped_and_not_retained(self):
        module = load_queue_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            private_entry = agents_sdk_log_entry("explain this private path")
            private_entry["request"]["context"]["private_prompt"] = "must not be retained"
            sidecar_log.write_text(json.dumps(private_entry) + "\n", encoding="utf-8")

            payload = module.build_eval_candidate_queue(
                agents_sdk_logs=[sidecar_log],
                generated_at="2026-06-30T12:30:00Z",
            )

        raw = json.dumps(payload, sort_keys=True)
        self.assertEqual(payload["status"], "empty")
        self.assertEqual(payload["source_summary"]["entries_skipped_private"], 1)
        self.assertEqual(payload["source_summary"]["candidates_total"], 0)
        self.assertNotIn("must not be retained", raw)
        self.assertNotIn("private_prompt", raw)
        self.assertTrue(payload["violations"])
        self.assertTrue(payload["safety"]["public_safe_output"])

    def test_agents_sdk_candidate_uses_player_request_and_tool_trace(self):
        module = load_queue_module()
        entry = agents_sdk_log_entry(
            "AI-native Luanti model adapter request.\nplayer_request: build me a fire and only a fire"
        )
        entry["request"]["context"].update({
            "intent": "build_planning",
            "player_request": "build me a fire and only a fire",
            "candidate_summary": "fire:fire:fire:1|platform:platform:stone:9",
        })
        entry["response"]["response"].update({
            "selected_option_id": "fire",
            "tool_decision_source": "agents_sdk_function_tool",
            "tool_trace": [
                {"tool_name": "recall_build_prompt_memory"},
                {"tool_name": "select_build_option"},
                {"tool_name": "plan_build_actions"},
            ],
            "build_action_plan": {
                "status": "ready",
                "selected_option_id": "fire",
                "plan_kind": "luanti_build_action_plan_v1",
                "step_count": 4,
                "direct_world_mutation": False,
                "world_mutation_authority": "luanti",
            },
            "tool_decisions": {
                "build_option": {
                    "selected_option_id": "fire",
                    "decision_source": "agent_selected_build_option",
                    "memory_match": {
                        "memory_available": True,
                        "matched_case_id": "promoted_fire_only_strict_123",
                    },
                },
                "build_action_plan": {
                    "status": "ready",
                    "selected_option_id": "fire",
                    "plan_kind": "luanti_build_action_plan_v1",
                    "step_count": 4,
                    "direct_world_mutation": False,
                    "world_mutation_authority": "luanti",
                },
            },
        })

        candidate = module.candidate_from_agents_sdk_entry(entry)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["prompt"], "build me a fire and only a fire")
        self.assertEqual(candidate["prompt_source"], "context.player_request")
        self.assertEqual(candidate["case_hint"], "fire_only_strict")
        self.assertEqual(candidate["observed"]["selected_option_id"], "fire")
        self.assertEqual(candidate["observed"]["tool_decision_source"], "agents_sdk_function_tool")
        self.assertEqual(candidate["observed"]["build_option_decision_source"], "agent_selected_build_option")
        self.assertEqual(candidate["observed"]["build_option_selected_option_id"], "fire")
        self.assertTrue(candidate["observed"]["memory_available"])
        self.assertEqual(
            candidate["observed"]["tool_trace_names"],
            ["recall_build_prompt_memory", "select_build_option", "plan_build_actions"],
        )
        self.assertEqual(candidate["observed"]["build_action_plan_status"], "ready")
        self.assertEqual(candidate["observed"]["build_action_plan_step_count"], 4)
        self.assertEqual(
            candidate["observed"]["build_action_plan_selected_option_id"],
            "fire",
        )
        self.assertEqual(
            candidate["observed"]["build_action_plan_world_mutation_authority"],
            "luanti",
        )
        self.assertFalse(candidate["ready_for_adapter_contract_eval"])

    def test_agents_sdk_candidate_retains_rejected_model_choice(self):
        module = load_queue_module()
        entry = agents_sdk_log_entry(
            "AI-native Luanti model adapter request.\nplayer_request: build me a fire and only a fire"
        )
        entry["request"]["context"].update({
            "intent": "build_planning",
            "player_request": "build me a fire and only a fire",
            "candidate_summary": "platform:platform:default:4|fire:fire:fire:1",
        })
        entry["response"]["response"].update({
            "selected_option_id": "fire",
            "model_selected_option_id": "platform",
            "rejected_model_selected_option_id": "platform",
            "intent_constraint_option_id": "fire",
            "intent_constraint_reason": "player_request_requires_fire_only",
            "tool_decision_source":
                "adapter_fallback_after_agent_violated_player_request_constraints",
            "tool_trace": [
                {"tool_name": "recall_build_prompt_memory"},
                {
                    "tool_name": "select_build_option",
                    "args": {"selected_option_id": "platform"},
                    "result": {"selected_option_id": None, "selection_status": "rejected"},
                },
            ],
            "tool_decisions": {
                "build_option": {
                    "selected_option_id": "fire",
                    "decision_source": "offline_adapter_fallback",
                    "memory_match": {"memory_available": True},
                },
            },
        })

        candidate = module.candidate_from_agents_sdk_entry(entry)

        self.assertIsNotNone(candidate)
        observed = candidate["observed"]
        self.assertEqual(observed["selected_option_id"], "fire")
        self.assertEqual(observed["model_selected_option_id"], "platform")
        self.assertEqual(observed["rejected_model_selected_option_id"], "platform")
        self.assertEqual(observed["intent_constraint_option_id"], "fire")
        self.assertEqual(
            observed["intent_constraint_reason"],
            "player_request_requires_fire_only",
        )
        self.assertEqual(
            observed["tool_decision_source"],
            "adapter_fallback_after_agent_violated_player_request_constraints",
        )

    def test_nova_trace_candidate_retains_rejected_model_choice(self):
        module = load_queue_module()
        payload = json.loads(
            nova_trace_line("build me a fire and only a fire").split("request_trace=", 1)[1]
        )
        response = payload["trace"]["response"]
        response.update({
            "build_kind": "fire",
            "build_material_name": "fire",
            "planned_node_writes": 1,
            "selected_candidate_id": "fire",
            "adapter_selected_candidate_id": "fire",
            "model_selected_candidate_id": "platform",
            "selection_source": "model_tool_decision_rejected_intent_constraint",
            "intent_constraint_option_id": "fire",
            "intent_constraint_reason": "player_request_requires_fire_only",
            "adapter_tool_decision_source":
                "adapter_fallback_after_agent_violated_player_request_constraints",
            "adapter_model_selected_candidate_id": "platform",
            "adapter_rejected_model_selected_candidate_id": "platform",
        })

        candidate = module.candidate_from_nova_trace(payload)

        self.assertIsNotNone(candidate)
        observed = candidate["observed"]
        self.assertEqual(observed["selected_candidate_id"], "fire")
        self.assertEqual(observed["adapter_selected_candidate_id"], "fire")
        self.assertEqual(observed["model_selected_candidate_id"], "platform")
        self.assertEqual(
            observed["selection_source"],
            "model_tool_decision_rejected_intent_constraint",
        )
        self.assertEqual(observed["intent_constraint_option_id"], "fire")
        self.assertEqual(
            observed["adapter_rejected_model_selected_candidate_id"],
            "platform",
        )

    def test_agents_sdk_missing_required_tool_becomes_contract_eval_candidate(self):
        module = load_queue_module()
        entry = agents_sdk_missing_required_tool_entry()

        candidate = module.candidate_from_agents_sdk_entry(entry)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["prompt"], "build me a tower")
        self.assertEqual(candidate["case_hint"], "model_adapter_review")
        self.assertEqual(candidate["priority"], "high")
        self.assertFalse(candidate["ready_for_prompt_eval"])
        self.assertTrue(candidate["ready_for_adapter_contract_eval"])
        self.assertEqual(candidate["adapter_contract_review_status"], "adapter_contract_candidate_ready")
        contract = candidate["adapter_tool_contract"]
        self.assertEqual(contract["status"], "fail")
        self.assertEqual(
            contract["required_tool_calls"],
            ["recall_build_prompt_memory", "select_build_option", "propose_build_option"],
        )
        self.assertEqual(contract["missing_required_tool_calls"], ["propose_build_option"])
        self.assertFalse(contract["required_tool_calls_satisfied"])
        self.assertEqual(
            contract["expected"]["missing_required_tool_calls"],
            [],
        )
        self.assertEqual(
            contract["expected"]["tool_decision_source"],
            "agents_sdk_function_tool",
        )
        replay_request = candidate["adapter_replay_request"]
        self.assertEqual(replay_request["request_kind"], "ai_native_model_adapter_request")
        self.assertEqual(replay_request["adapter_contract"], "provider_neutral_v1")
        self.assertEqual(replay_request["context"]["intent"], "build_planning")
        self.assertEqual(replay_request["context"]["player_request"], "build me a tower")
        self.assertIn("candidate_summary", replay_request["context"])
        self.assertTrue(replay_request["safety"]["public_safe_request"])
        self.assertFalse(PRIVATE_PATTERNS.search(json.dumps(replay_request, sort_keys=True)))

    def test_queue_counts_adapter_contract_failures(self):
        module = load_queue_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            sidecar_log.write_text(
                json.dumps(agents_sdk_missing_required_tool_entry()) + "\n",
                encoding="utf-8",
            )

            payload = module.build_eval_candidate_queue(
                agents_sdk_logs=[sidecar_log],
                generated_at="2026-06-30T12:30:00Z",
            )

        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["source_summary"]["candidates_total"], 1)
        self.assertEqual(payload["source_summary"]["ready_for_prompt_eval"], 0)
        self.assertEqual(payload["source_summary"]["manual_review_required"], 0)
        self.assertEqual(payload["source_summary"]["ready_for_adapter_contract_eval"], 1)
        self.assertEqual(payload["source_summary"]["adapter_contract_failures"], 1)
        self.assertEqual(payload["source_summary"]["adapter_contract_failures_active"], 1)
        self.assertEqual(payload["source_summary"]["adapter_contract_failures_total"], 1)
        self.assertEqual(payload["source_summary"]["adapter_contract_failures_resolved"], 0)
        self.assertTrue(payload["candidates"][0]["ready_for_adapter_contract_eval"])

    def test_later_contract_pass_marks_prior_failure_resolved(self):
        module = load_queue_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            failed, passed = resolved_generated_wall_contract_entries()
            sidecar_log.write_text(
                json.dumps(failed) + "\n" + json.dumps(passed) + "\n",
                encoding="utf-8",
            )

            payload = module.build_eval_candidate_queue(
                agents_sdk_logs=[sidecar_log],
                generated_at="2026-06-30T15:30:00Z",
                max_bytes=100000,
            )

        self.assertEqual(payload["source_summary"]["adapter_contract_failures"], 0)
        self.assertEqual(payload["source_summary"]["adapter_contract_failures_active"], 0)
        self.assertEqual(payload["source_summary"]["adapter_contract_failures_total"], 1)
        self.assertEqual(payload["source_summary"]["adapter_contract_failures_resolved"], 1)
        self.assertEqual(payload["source_summary"]["ready_for_adapter_contract_eval"], 0)
        self.assertEqual(payload["source_summary"]["manual_review_required"], 0)
        resolved = next(
            candidate
            for candidate in payload["candidates"]
            if candidate["case_hint"] == "model_adapter_review"
        )
        self.assertFalse(resolved["ready_for_adapter_contract_eval"])
        self.assertEqual(resolved["adapter_contract_review_status"], "adapter_contract_resolved")
        self.assertEqual(
            resolved["adapter_contract_resolution"]["status"],
            "resolved_by_later_pass",
        )
        self.assertEqual(
            resolved["adapter_tool_contract"]["resolution_status"],
            "resolved_by_later_pass",
        )
        self.assertEqual(resolved["priority"], "high")

    def test_resolved_contract_failure_survives_small_candidate_queue(self):
        module = load_queue_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            probe = root / "nova-auto-apply.json"
            failed, passed = resolved_generated_wall_contract_entries()
            sidecar_log.write_text(
                json.dumps(failed) + "\n" + json.dumps(passed) + "\n",
                encoding="utf-8",
            )
            probe.write_text(json.dumps(verified_live_probe_payload()), encoding="utf-8")

            payload = module.build_eval_candidate_queue(
                agents_sdk_logs=[sidecar_log],
                verified_live_probe_paths=[probe],
                generated_at="2026-06-30T15:30:00Z",
                max_candidates=2,
                max_bytes=100000,
            )

        self.assertEqual(payload["source_summary"]["candidates_total"], 2)
        self.assertEqual(payload["source_summary"]["adapter_contract_failures"], 0)
        self.assertEqual(payload["source_summary"]["adapter_contract_failures_total"], 1)
        self.assertEqual(payload["source_summary"]["adapter_contract_failures_resolved"], 1)
        self.assertIn(
            "adapter_contract_resolved",
            {candidate.get("adapter_contract_review_status") for candidate in payload["candidates"]},
        )

    def test_verified_generated_option_becomes_prompt_eval_candidate(self):
        module = load_queue_module()

        candidate = module.candidate_from_agents_sdk_entry(agents_sdk_generated_option_entry())

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["prompt"], "build a 6 wide 2 high lookout wall")
        self.assertEqual(candidate["case_hint"], "generated_dimensioned_wall")
        self.assertTrue(candidate["ready_for_prompt_eval"])
        self.assertFalse(candidate["ready_for_adapter_contract_eval"])
        self.assertEqual(candidate["review_status"], "candidate_ready")
        self.assertEqual(candidate["expected"]["route"], "agentic_build_planner")
        self.assertEqual(candidate["expected"]["selected_candidate_id"], "generated_dimensioned_wall")
        self.assertEqual(candidate["expected"]["build_kind"], "wall")
        self.assertEqual(candidate["expected"]["build_material_name"], "stone")
        self.assertEqual(candidate["expected"]["planned_node_writes"], 12)
        self.assertEqual(candidate["expected"]["build_width"], 6)
        self.assertEqual(candidate["expected"]["build_height"], 2)
        self.assertTrue(candidate["expected"]["forbidden_extra_structure"])
        observed = candidate["observed"]
        self.assertEqual(observed["generated_option_id"], "generated_dimensioned_wall")
        self.assertEqual(observed["generated_option_status"], "ready")
        self.assertEqual(observed["generated_option_build_width"], 6)
        self.assertEqual(observed["generated_option_build_height"], 2)
        self.assertEqual(
            observed["tool_trace_names"],
            [
                "recall_build_prompt_memory",
                "propose_build_option",
                "select_build_option",
                "plan_build_actions",
            ],
        )

    def test_local_tool_contract_fast_path_can_be_prompt_eval_candidate(self):
        module = load_queue_module()
        entry = agents_sdk_generated_option_entry()
        entry["response"]["response"]["tool_decision_source"] = "local_agent_tool_contract_fast_path"
        entry["response"]["response"]["local_tool_contract_reason"] = "agents_sdk_model_timeout"

        candidate = module.candidate_from_agents_sdk_entry(entry)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["case_hint"], "generated_dimensioned_wall")
        self.assertTrue(candidate["ready_for_prompt_eval"])
        self.assertFalse(candidate["ready_for_adapter_contract_eval"])
        self.assertEqual(
            candidate["observed"]["tool_decision_source"],
            "local_agent_tool_contract_fast_path",
        )
        self.assertEqual(candidate["adapter_tool_contract"]["status"], "pass")
        self.assertIn(
            "local_agent_tool_contract_fast_path",
            candidate["adapter_tool_contract"]["expected"]["tool_decision_sources"],
        )

    def test_request_response_log_gate_cases_become_prompt_eval_candidates(self):
        module = load_queue_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            gate = root / "ai-agent-request-response-log-gate.json"
            gate.write_text(json.dumps(request_response_log_gate_payload()), encoding="utf-8")

            payload = module.build_eval_candidate_queue(
                request_response_log_gate_paths=[gate],
                generated_at="2026-06-30T21:15:00Z",
                max_bytes=100000,
            )

        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["source_summary"]["request_response_log_gate_files_read"], 1)
        self.assertEqual(payload["source_summary"]["request_response_log_gate_cases_read"], 4)
        self.assertEqual(payload["source_summary"]["request_response_log_gate_candidates_added"], 4)
        self.assertEqual(payload["source_summary"]["ready_for_prompt_eval"], 4)
        self.assertFalse(PRIVATE_PATTERNS.search(json.dumps(payload, sort_keys=True)))
        by_hint = {candidate["case_hint"]: candidate for candidate in payload["candidates"]}
        self.assertEqual(
            by_hint["build_fire"]["source_kind"],
            module.REQUEST_RESPONSE_LOG_GATE_SOURCE_KIND,
        )
        self.assertEqual(by_hint["fire_only_strict"]["expected"]["build_kind"], "fire")
        self.assertEqual(by_hint["fire_only_strict"]["expected"]["route"], "agentic_build_planner")
        self.assertTrue(by_hint["fire_only_strict"]["expected"]["forbidden_extra_structure"])
        self.assertEqual(by_hint["tnt_wall"]["expected"]["build_material_name"], "tnt")
        self.assertFalse(by_hint["tnt_wall"]["expected"]["danger_refusal_allowed"])
        generated = by_hint["generated_shelter_floor"]
        self.assertEqual(generated["expected"]["selected_candidate_id"], "generated_shelter_floor")
        self.assertEqual(generated["expected"]["build_kind"], "platform")
        self.assertEqual(generated["expected"]["build_material_name"], "stone")
        self.assertEqual(generated["expected"]["build_width"], 4)
        self.assertEqual(generated["expected"]["build_depth"], 3)
        self.assertEqual(generated["observed"]["tool_decision_source"], "local_agent_tool_contract_fast_path")
        self.assertEqual(generated["adapter_tool_contract"]["status"], "pass")

    def test_verified_live_probe_cases_become_prompt_eval_candidates(self):
        module = load_queue_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            probe_dir = root / "live-probes"
            probe_dir.mkdir()
            (probe_dir / "nova-auto-apply.json").write_text(
                json.dumps(verified_live_probe_payload()),
                encoding="utf-8",
            )

            payload = module.build_eval_candidate_queue(
                verified_live_probe_paths=[probe_dir],
                generated_at="2026-06-30T15:00:00Z",
            )

        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["source_summary"]["verified_live_probe_files_read"], 1)
        self.assertEqual(payload["source_summary"]["verified_live_probe_cases_read"], 3)
        self.assertEqual(payload["source_summary"]["verified_live_probe_candidates_added"], 3)
        self.assertEqual(payload["source_summary"]["ready_for_prompt_eval"], 3)
        self.assertFalse(PRIVATE_PATTERNS.search(json.dumps(payload, sort_keys=True)))
        by_hint = {candidate["case_hint"]: candidate for candidate in payload["candidates"]}
        self.assertEqual(by_hint["fire_only_strict"]["source_kind"], module.VERIFIED_LIVE_PROBE_KIND)
        self.assertEqual(by_hint["fire_only_strict"]["expected"]["route"], "agentic_build_planner")
        self.assertEqual(by_hint["tnt_wall"]["expected"]["build_material_name"], "tnt")
        generated = by_hint["generated_dimensioned_wall"]
        self.assertEqual(generated["expected"]["selected_candidate_id"], "generated_dimensioned_wall")
        self.assertEqual(generated["expected"]["build_width"], 6)
        self.assertEqual(generated["expected"]["build_height"], 2)
        self.assertEqual(generated["observed"]["generated_option_status"], "ready")
        self.assertEqual(
            generated["observed"]["tool_trace_names"],
            [
                "recall_build_prompt_memory",
                "select_build_option",
                "propose_build_option",
                "select_build_option",
                "plan_build_actions",
            ],
        )

    def test_verified_live_probe_accepts_local_tool_contract_fast_path(self):
        module = load_queue_module()
        case = verified_live_probe_payload()["cases"][0]
        case["reply"]["adapter_tool_decision_source"] = "local_agent_tool_contract_fast_path"

        candidate = module.candidate_from_verified_live_probe_case(
            verified_live_probe_payload([case]),
            case,
        )

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["case_hint"], "fire_only_strict")
        self.assertEqual(
            candidate["observed"]["tool_decision_source"],
            "local_agent_tool_contract_fast_path",
        )
        self.assertEqual(candidate["adapter_tool_contract"]["status"], "pass")

    def test_verified_live_probe_reader_ignores_prompt_eval_live_artifact(self):
        module = load_queue_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            probe_dir = root / "live-probes"
            probe_dir.mkdir()
            (probe_dir / "nova-auto-apply.json").write_text(
                json.dumps(verified_live_probe_payload()),
                encoding="utf-8",
            )
            (probe_dir / "ai-agent-prompt-eval-live-latest.json").write_text(
                json.dumps({
                    "live_result_kind": "ai_native_agent_prompt_eval_live_result",
                    "status": "pass",
                    "summary": {"cases_total": 5, "cases_passed": 5},
                }),
                encoding="utf-8",
            )

            payload = module.build_eval_candidate_queue(
                verified_live_probe_paths=[probe_dir],
                generated_at="2026-06-30T15:00:00Z",
            )

        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["source_summary"]["verified_live_probe_files_read"], 1)
        self.assertEqual(payload["source_summary"]["verified_live_probe_cases_read"], 3)
        self.assertFalse(any(
            item["kind"] == "invalid_verified_live_probe_kind"
            for item in payload["violations"]
        ))

    def test_prompt_label_does_not_relabel_verified_live_probe_case_family(self):
        module = load_queue_module()
        simple_fire = verified_live_probe_payload()["cases"][0]
        simple_fire["case_id"] = "fire_simple"
        simple_fire["prompt"] = "build a fire"
        stale_label = {
            "schema_version": 1,
            "artifact_kind": "ai_native_agent_eval_operator_labels",
            "labels": [
                {
                    "label_id": "reviewed_fire_only_strict_stale",
                    "prompt": "build a fire",
                    "case_hint": "fire_only_strict",
                    "expected": {
                        "action": "build",
                        "build_kind": "fire",
                        "build_material_name": "fire",
                        "planned_node_writes": 1,
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            probe = root / "simple-fire-live-probe.json"
            probe.write_text(
                json.dumps(verified_live_probe_payload([simple_fire])),
                encoding="utf-8",
            )

            payload = module.build_eval_candidate_queue(
                verified_live_probe_paths=[probe],
                operator_label_payloads=[stale_label],
                generated_at="2026-06-30T16:10:00Z",
            )

        self.assertEqual(payload["source_summary"]["operator_labels_applied"], 0)
        candidate = payload["candidates"][0]
        self.assertEqual(candidate["prompt"], "build a fire")
        self.assertEqual(candidate["case_hint"], "build_fire")
        self.assertEqual(candidate["expected"]["planned_node_writes"], 1)
        self.assertTrue(candidate["expected"]["forbidden_extra_structure"])
        self.assertNotIn("operator_label", candidate)

    def test_verified_live_probe_duplicates_are_compacted_before_byte_cap(self):
        module = load_queue_module()
        older = verified_live_probe_payload()
        older["generated_at"] = "2026-06-30T14:33:40Z"
        newer = verified_live_probe_payload()
        newer["generated_at"] = "2026-06-30T14:41:15Z"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            probe_dir = root / "live-probes"
            probe_dir.mkdir()
            (probe_dir / "nova-auto-apply-old.json").write_text(json.dumps(older), encoding="utf-8")
            (probe_dir / "nova-auto-apply-new.json").write_text(json.dumps(newer), encoding="utf-8")

            payload = module.build_eval_candidate_queue(
                verified_live_probe_paths=[probe_dir],
                generated_at="2026-06-30T15:00:00Z",
            )

        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["source_summary"]["verified_live_probe_cases_read"], 6)
        self.assertEqual(payload["source_summary"]["verified_live_probe_candidates_added"], 6)
        self.assertEqual(payload["source_summary"]["candidates_total"], 3)
        self.assertEqual(payload["source_summary"]["ready_for_prompt_eval"], 3)
        self.assertEqual(
            {candidate["case_hint"] for candidate in payload["candidates"]},
            {"fire_only_strict", "tnt_wall", "generated_dimensioned_wall"},
        )
        self.assertTrue(all(candidate["observed_at"] == newer["generated_at"] for candidate in payload["candidates"]))
        self.assertLess(payload["bounds"]["output_bytes"], payload["bounds"]["max_bytes"])

    def test_verified_live_probe_failed_case_does_not_promote(self):
        module = load_queue_module()
        bad_case = verified_live_probe_payload()["cases"][0]
        bad_case["checks"]["selected_candidate"] = False
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            probe = root / "bad-live-probe.json"
            probe.write_text(json.dumps(verified_live_probe_payload([bad_case])), encoding="utf-8")

            payload = module.build_eval_candidate_queue(
                verified_live_probe_paths=[probe],
                generated_at="2026-06-30T15:00:00Z",
            )

        self.assertEqual(payload["status"], "empty")
        self.assertEqual(payload["source_summary"]["verified_live_probe_cases_read"], 1)
        self.assertEqual(payload["source_summary"]["verified_live_probe_candidates_added"], 0)
        self.assertTrue(
            any(item["kind"] == "verified_live_probe_case_not_promotable" for item in payload["violations"])
        )

    def test_generated_option_survives_small_candidate_queue(self):
        module = load_queue_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            entries = []
            for index in range(8):
                entry = agents_sdk_log_entry("build me a fire and only a fire")
                entry["created_at"] = f"2026-06-30T12:00:{index:02d}Z"
                entries.append(json.dumps(entry))
            generated = agents_sdk_generated_option_entry()
            generated["created_at"] = "2026-06-30T12:01:00Z"
            entries.append(json.dumps(generated))
            sidecar_log.write_text("\n".join(entries) + "\n", encoding="utf-8")

            payload = module.build_eval_candidate_queue(
                agents_sdk_logs=[sidecar_log],
                generated_at="2026-06-30T12:30:00Z",
                max_candidates=3,
                max_bytes=100000,
            )

        self.assertEqual(payload["source_summary"]["candidates_total"], 2)
        self.assertEqual(
            {candidate["case_hint"] for candidate in payload["candidates"]},
            {"fire_only_strict", "generated_dimensioned_wall"},
        )

    def test_agents_sdk_candidate_extracts_embedded_player_request_from_wrapper_prompt(self):
        module = load_queue_module()
        entry = agents_sdk_log_entry(
            "\n".join(
                [
                    "Plan a Luanti build request using only the listed executable options.",
                    "Luanti will enforce capabilities, approval, rollback, and world mutation.",
                    "Player request: build a small shelter",
                    "Options:",
                    "- fire: Single fire kind=fire material=fire planned_writes=1",
                ]
            )
        )

        candidate = module.candidate_from_agents_sdk_entry(entry)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["prompt"], "build a small shelter")
        self.assertEqual(candidate["prompt_source"], "request.public_prompt.player_request")
        self.assertNotEqual(candidate["case_hint"], "fire_only_strict")
        self.assertFalse(candidate["ready_for_prompt_eval"])

    def test_nova_trace_accepts_null_tool_trace_names_from_live_log(self):
        module = load_queue_module()
        payload = json.loads(nova_trace_line().split("request_trace=", 1)[1])
        payload["trace"]["response"]["adapter_tool_trace_names"] = None

        candidate = module.candidate_from_nova_trace(payload)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["source_kind"], "nova_request_trace")
        self.assertEqual(candidate["observed"]["adapter_tool_trace_names"], [])

    def test_action_log_queue_handles_null_and_non_object_response_without_crashing(self):
        module = load_queue_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            action_log = root / "debug.log"
            null_tool_payload = json.loads(nova_trace_line().split("request_trace=", 1)[1])
            null_tool_payload["trace"]["response"]["adapter_tool_trace_names"] = None
            invalid_payload = json.loads(nova_trace_line().split("request_trace=", 1)[1])
            invalid_payload["trace"]["response"] = "not a response object"
            action_log.write_text(
                "[ai_agent_plugin] request_trace="
                + json.dumps(null_tool_payload, sort_keys=True)
                + "\n"
                + "[ai_agent_plugin] request_trace="
                + json.dumps(invalid_payload, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )

            payload = module.build_eval_candidate_queue(
                action_logs=[action_log],
                generated_at="2026-06-30T13:45:00Z",
            )

        self.assertEqual(payload["source_summary"]["nova_request_traces_read"], 2)
        self.assertEqual(payload["source_summary"]["candidates_total"], 2)
        self.assertEqual(payload["candidates"][0]["observed"]["adapter_tool_trace_names"], [])

    def test_operator_labels_promote_unknown_prompt_to_reviewed_candidate(self):
        module = load_queue_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            sidecar_log.write_text(
                json.dumps(agents_sdk_log_entry("build a bridge")) + "\n",
                encoding="utf-8",
            )

            unlabelled = module.build_eval_candidate_queue(
                agents_sdk_logs=[sidecar_log],
                generated_at="2026-06-30T12:30:00Z",
            )
            labelled = module.build_eval_candidate_queue(
                agents_sdk_logs=[sidecar_log],
                operator_label_payloads=[operator_labels_payload()],
                generated_at="2026-06-30T12:30:00Z",
            )

        self.assertEqual(unlabelled["source_summary"]["ready_for_prompt_eval"], 0)
        self.assertEqual(unlabelled["candidates"][0]["review_status"], "needs_operator_label")
        self.assertEqual(labelled["source_summary"]["operator_labels_read"], 1)
        self.assertEqual(labelled["source_summary"]["operator_labels_applied"], 1)
        self.assertEqual(labelled["source_summary"]["ready_for_prompt_eval"], 1)
        candidate = labelled["candidates"][0]
        self.assertEqual(candidate["case_hint"], "stone_bridge_platform")
        self.assertEqual(candidate["review_status"], "operator_labeled_candidate_ready")
        self.assertEqual(candidate["operator_label"]["mode"], "operator_label_overlay")
        self.assertEqual(candidate["expected"]["build_kind"], "platform")
        self.assertEqual(candidate["expected"]["build_material_name"], "stone")
        self.assertEqual(candidate["expected"]["planned_node_writes"], 12)
        self.assertFalse(PRIVATE_PATTERNS.search(json.dumps(labelled, sort_keys=True)))

    def test_private_operator_labels_are_rejected_without_promoting_candidate(self):
        module = load_queue_module()
        private_labels = operator_labels_payload()
        private_labels["labels"][0]["expected"]["private_prompt"] = "must not be retained"

        payload = module.build_eval_candidate_queue(
            operator_label_payloads=[private_labels],
            generated_at="2026-06-30T12:30:00Z",
        )

        self.assertEqual(payload["status"], "empty")
        self.assertEqual(payload["source_summary"]["operator_labels_read"], 0)
        self.assertEqual(payload["source_summary"]["operator_labels_applied"], 0)
        self.assertTrue(any(item["kind"] == "operator_labels_not_public_safe" for item in payload["violations"]))
        self.assertNotIn("must not be retained", json.dumps(payload, sort_keys=True))

    def test_nova_agent_log_candidate_records_contract_and_correction(self):
        module = load_queue_module()

        candidate = module.candidate_from_nova_agent_log_entry(nova_agent_log_entry())

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["source_kind"], "nova_agent_sidecar_request_response")
        self.assertEqual(candidate["case_hint"], "tnt_wall")
        self.assertEqual(candidate["priority"], "high")
        self.assertEqual(candidate["route"], "agents_sdk")
        self.assertEqual(candidate["action"], "build")
        self.assertEqual(candidate["observed_status"], "corrected")
        self.assertEqual(candidate["observed_reason"], "prompt_contract")
        self.assertEqual(candidate["observed"]["contract_kind"], "tnt_wall")
        self.assertTrue(candidate["observed"]["contract_satisfied"])
        self.assertEqual(candidate["observed"]["planned_node_writes"], 75)
        self.assertEqual(candidate["expected"]["planned_node_writes"], 12)

    def test_nova_agent_log_candidate_records_agentic_option_selection(self):
        module = load_queue_module()

        candidate = module.candidate_from_nova_agent_log_entry(nova_agent_fire_only_option_log_entry())

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["source_kind"], "nova_agent_sidecar_request_response")
        self.assertEqual(candidate["case_hint"], "fire_only_strict")
        self.assertEqual(candidate["route"], "agents_sdk_tool_plan")
        self.assertEqual(candidate["observed_status"], "success")
        self.assertEqual(candidate["observed"]["selected_option_id"], "reviewed_prompt_memory")
        self.assertEqual(candidate["observed"]["selected_candidate_id"], "reviewed_prompt_memory")
        self.assertEqual(
            candidate["observed"]["decision_reason"],
            "The strict prompt asks for one fire and no extra structure.",
        )
        self.assertEqual(
            candidate["observed"]["required_tool_calls"],
            [
                "recall_build_prompt_memory",
                "analyze_build_intent",
                "draft_build_options",
                "validate_plan_contract",
                "submit_nova_plan",
            ],
        )
        self.assertEqual(candidate["observed"]["missing_required_tool_calls"], [])
        self.assertTrue(candidate["observed"]["required_tool_calls_satisfied"])
        self.assertEqual(
            candidate["observed"]["tool_trace_names"],
            [
                "recall_build_prompt_memory",
                "analyze_build_intent",
                "draft_build_options",
                "validate_plan_contract",
                "submit_nova_plan",
            ],
        )
        self.assertEqual(candidate["observed"]["build_option_count"], 2)
        self.assertEqual(candidate["observed"]["build_options"][0]["option_id"], "reviewed_prompt_memory")
        self.assertTrue(candidate["observed"]["build_options"][0]["contract_satisfied"])
        self.assertEqual(
            candidate["observed"]["reviewed_prompt_memory_matched_case_id"],
            "promoted_fire_only_strict_abc123",
        )
        self.assertEqual(candidate["expected"]["route"], "agentic_build_planner")
        self.assertEqual(candidate["expected"]["planned_node_writes"], 1)
        self.assertEqual(candidate["adapter_tool_contract"]["status"], "pass")
        self.assertEqual(
            candidate["adapter_tool_contract"]["expected"]["tool_decision_source"],
            "agents_sdk_submit_nova_plan_tool",
        )
        self.assertFalse(candidate["ready_for_adapter_contract_eval"])

    def test_nova_agent_log_candidate_promotes_prompt_shaped_house_eval(self):
        module = load_queue_module()

        candidate = module.candidate_from_nova_agent_log_entry(nova_agent_gold_house_option_log_entry())

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["source_kind"], "nova_agent_sidecar_request_response")
        self.assertEqual(candidate["case_hint"], "prompt_shaped_house")
        self.assertTrue(candidate["ready_for_prompt_eval"])
        self.assertEqual(candidate["expected"]["route"], "agentic_build_planner")
        self.assertEqual(candidate["expected"]["build_kind"], "house")
        self.assertEqual(candidate["expected"]["build_material_name"], "gold")
        self.assertEqual(candidate["expected"]["planned_node_writes"], 220)
        self.assertEqual(candidate["observed"]["build_kind"], "house")
        self.assertEqual(candidate["observed"]["build_material_name"], "gold")
        self.assertEqual(candidate["observed"]["planned_node_writes"], 220)
        self.assertEqual(candidate["observed"]["build_options"][0]["build_kind"], "house")
        self.assertEqual(candidate["adapter_tool_contract"]["status"], "pass")

    def test_legacy_generic_house_trace_still_becomes_named_prompt_eval_backlog(self):
        module = load_queue_module()
        entry = nova_agent_resolved_plan_timeout_log_entry()
        entry["prompt"] = "build a house out of gold"
        entry["source"] = "agents_sdk_tool_plan"
        entry["tool_decision_source"] = "agents_sdk_submit_nova_plan_tool"
        entry["required_tool_calls"] = ["resolve_build_plan", "submit_nova_plan"]
        entry["missing_required_tool_calls"] = []
        entry["required_tool_calls_satisfied"] = True

        candidate = module.candidate_from_nova_agent_log_entry(entry)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["case_hint"], "prompt_shaped_house")
        self.assertTrue(candidate["ready_for_prompt_eval"])
        self.assertEqual(candidate["expected"]["build_kind"], "house")
        self.assertEqual(candidate["expected"]["build_material_name"], "gold")
        self.assertEqual(candidate["adapter_tool_contract"]["status"], "pass")

    def test_legacy_generic_creative_trace_becomes_landmark_prompt_eval_backlog(self):
        module = load_queue_module()
        entry = nova_agent_resolved_plan_timeout_log_entry()
        entry["prompt"] = "build something amazing"
        entry["source"] = "agents_sdk_tool_plan"
        entry["tool_decision_source"] = "agents_sdk_submit_nova_plan_tool"
        entry["required_tool_calls"] = ["resolve_build_plan", "submit_nova_plan"]
        entry["missing_required_tool_calls"] = []
        entry["required_tool_calls_satisfied"] = True

        candidate = module.candidate_from_nova_agent_log_entry(entry)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["case_hint"], "creative_landmark")
        self.assertTrue(candidate["ready_for_prompt_eval"])
        self.assertEqual(candidate["expected"]["route"], "agentic_build_planner")
        self.assertEqual(candidate["expected"]["build_kind"], "landmark")
        self.assertEqual(candidate["expected"]["build_material_name"], "quartz")
        self.assertEqual(candidate["adapter_tool_contract"]["status"], "pass")

    def test_non_replayable_nova_timeout_trace_requires_review_not_replay(self):
        module = load_queue_module()

        candidate = module.candidate_from_nova_agent_log_entry(
            nova_agent_resolved_plan_timeout_log_entry()
        )

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["source_kind"], "nova_agent_sidecar_request_response")
        self.assertEqual(candidate["route"], "agents_sdk_resolved_plan_after_timeout")
        self.assertEqual(candidate["case_hint"], "prompt_shaped_cabin")
        self.assertTrue(candidate["ready_for_prompt_eval"])
        self.assertEqual(candidate["expected"]["build_kind"], "cabin")
        self.assertEqual(candidate["adapter_tool_contract"]["status"], "review")
        self.assertEqual(
            candidate["adapter_tool_contract"]["review_reason"],
            "non_replayable_family_sidecar_contract_observation",
        )
        self.assertFalse(candidate["ready_for_adapter_contract_eval"])
        self.assertNotIn("adapter_replay_request", candidate)

    def test_non_replayable_nova_timeout_trace_does_not_block_adapter_contract_gate(self):
        module = load_queue_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            nova_agent_log = root / "nova-agent-requests.jsonl"
            nova_agent_log.write_text(
                json.dumps(nova_agent_resolved_plan_timeout_log_entry()) + "\n",
                encoding="utf-8",
            )

            payload = module.build_eval_candidate_queue(
                nova_agent_logs=[nova_agent_log],
                generated_at="2026-06-30T12:30:00Z",
            )

        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["source_summary"]["candidates_total"], 1)
        self.assertEqual(payload["source_summary"]["ready_for_adapter_contract_eval"], 0)
        self.assertEqual(payload["source_summary"]["adapter_contract_failures_active"], 0)
        self.assertEqual(payload["source_summary"]["manual_review_required"], 0)
        self.assertEqual(payload["source_summary"]["ready_for_prompt_eval"], 1)

    def test_nova_agent_sidecar_candidates_rank_ahead_of_live_probe_evidence(self):
        module = load_queue_module()
        probe_payload = verified_live_probe_payload()
        live_candidate = module.candidate_from_verified_live_probe_case(
            probe_payload,
            probe_payload["cases"][0],
        )
        sidecar_candidate = module.candidate_from_nova_agent_log_entry(
            nova_agent_fire_only_option_log_entry()
        )

        self.assertIsNotNone(live_candidate)
        self.assertIsNotNone(sidecar_candidate)
        ordered = sorted([live_candidate, sidecar_candidate], key=module._candidate_sort_key)

        self.assertEqual(ordered[0]["source_kind"], "nova_agent_sidecar_request_response")
        self.assertEqual(ordered[0]["observed"]["selected_option_id"], "reviewed_prompt_memory")
        self.assertEqual(ordered[0]["observed"]["build_options"][0]["option_id"], "reviewed_prompt_memory")

    def test_cli_writes_candidate_queue(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            nova_agent_log = root / "nova-agent-requests.jsonl"
            operator_labels = root / "operator-labels.json"
            output = root / "candidate-queue.json"
            sidecar_log.write_text(json.dumps(agents_sdk_log_entry("build a fire")) + "\n", encoding="utf-8")
            nova_agent_log.write_text(json.dumps(nova_agent_log_entry()) + "\n", encoding="utf-8")
            operator_labels.write_text(json.dumps(operator_labels_payload()), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(QUEUE),
                    "--root",
                    str(root),
                    "--agents-sdk-log",
                    str(sidecar_log),
                    "--nova-agent-log",
                    str(nova_agent_log),
                    "--operator-labels",
                    str(operator_labels),
                    "--output",
                    str(output),
                    "--generated-at",
                    "2026-06-30T12:30:00Z",
                ],
                cwd=ROOT,
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "ready")
            self.assertEqual(payload["source_summary"]["nova_agent_log_entries_read"], 1)
            self.assertEqual(payload["source_summary"]["operator_labels_read"], 1)
            self.assertEqual(payload["source_summary"]["operator_labels_applied"], 0)
            self.assertEqual(
                {candidate["case_hint"] for candidate in payload["candidates"]},
                {"build_fire", "tnt_wall"},
            )

    def test_docs_include_agent_improvement_loop(self):
        bodies = [path.read_text(encoding="utf-8") for path in (README, OPERATING_LOOP, ADAPTER_DOC)]
        combined = "\n".join(bodies)
        self.assertIn("ai_native_agent_eval_queue.py", combined)
        self.assertIn("ai_native_agent_feedback_packet.py", combined)
        self.assertIn("Agent Improvement Loop", combined)
        self.assertIn("agents-sdk-model-adapter.jsonl", combined)
        self.assertIn("--operator-labels", combined)
        self.assertIn("--from-operator-feedback", combined)
        self.assertIn("/ai_agent_feedback", combined)
        self.assertIn("ai_native_agent_eval_operator_labels", combined)
        loop_sections = []
        for body in bodies:
            if "## Agent Improvement Loop" not in body:
                continue
            section = body.split("## Agent Improvement Loop", 1)[1]
            section = section.split("\n## ", 1)[0]
            loop_sections.append(section)
        self.assertGreaterEqual(len(loop_sections), 2)
        self.assertNotRegex("\n".join(loop_sections), DOC_PRIVATE_PATTERNS)


if __name__ == "__main__":
    unittest.main()
