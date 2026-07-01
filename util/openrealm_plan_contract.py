#!/usr/bin/env python3
"""Verify the OpenRealm Plan v1 public runtime contract."""

from __future__ import annotations

import argparse
import copy
import json
import pathlib
import re
import sys
from typing import Any


DOC = pathlib.Path("doc/ai-native-runtime/openrealm-plan-contract.md")
README = pathlib.Path("doc/ai-native-runtime/README.md")
SCHEMA = pathlib.Path("doc/ai-native-runtime/schemas/openrealm-plan-v1.schema.json")
EXAMPLE = pathlib.Path("doc/ai-native-runtime/examples/openrealm-plan-v1.example.json")
KIT_SCHEMA = pathlib.Path("openrealm_advantage_kit/schemas/openrealm_plan.schema.json")
KIT_PLAN_GLOB_ROOTS = [
    pathlib.Path("openrealm_advantage_kit/examples/generated"),
    pathlib.Path("openrealm_advantage_kit/out"),
]

PLAN_KINDS = {"structure", "ore_mod", "biome_recipe", "world_recipe"}
IDENT_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
MOD_RE = re.compile(r"^[a-z][a-z0-9_]{1,62}$")
NODE_RE = re.compile(r"^[a-z][a-z0-9_]{1,62}:[a-z][a-z0-9_]{0,62}$")
PLAN_ID_RE = re.compile(r"^orplan_[a-f0-9]{12}$")
PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|ANTHROPIC_API_KEY|"
    r"GITHUB_TOKEN|AWS_SECRET_ACCESS_KEY|/Users/",
    re.I,
)
RAW_CODE_PATTERN = re.compile(
    r"\b(?:os\.execute|io\.popen|loadstring|dofile|debug\.|package\.loaded|"
    r"minetest\.request_http_api|core\.request_http_api|require\s*\(|"
    r"function\s*\(|local\s+function|while\s+true|rm\s+-rf|"
    r"api[_-]?key|secret|token)\b",
    re.I,
)
RAW_PAYLOAD_KEYS = {
    "raw_lua",
    "lua",
    "lua_code",
    "script",
    "script_body",
    "shell",
    "command",
    "provider_credentials",
    "api_key",
    "headers",
    "raw_asset_payload",
}
ALLOWED_EXTERNAL_PREFIXES = (
    "default:",
    "doors:",
    "stairs:",
    "wool:",
    "fire:",
    "tnt:",
    "farming:",
    "ai_runtime_base:",
)
RESERVED_LUA_WORDS = {
    "and",
    "break",
    "do",
    "else",
    "elseif",
    "end",
    "false",
    "for",
    "function",
    "if",
    "in",
    "local",
    "nil",
    "not",
    "or",
    "repeat",
    "return",
    "then",
    "true",
    "until",
    "while",
}


def read_json(root: pathlib.Path, relpath: pathlib.Path) -> dict[str, Any]:
    return json.loads((root / relpath).read_text(encoding="utf-8"))


def issue(kind: str, path: str, message: str) -> dict[str, str]:
    return {"kind": kind, "path": path, "message": message}


def is_identifier(value: Any) -> bool:
    return isinstance(value, str) and bool(IDENT_RE.match(value)) and value not in RESERVED_LUA_WORDS


def is_mod_name(value: Any) -> bool:
    return isinstance(value, str) and bool(MOD_RE.match(value)) and value not in RESERVED_LUA_WORDS


def is_node_name(value: Any) -> bool:
    return isinstance(value, str) and bool(NODE_RE.match(value))


def add_required(payload: dict[str, Any], field: str, path: str, issues: list[dict]) -> bool:
    if field not in payload:
        issues.append(issue("missing_required_field", f"{path}.{field}", "Required field is missing."))
        return False
    return True


def walk_values(value: Any, path: str = "$"):
    if isinstance(value, dict):
        for key, child in value.items():
            yield f"{path}.{key}", key, child
            yield from walk_values(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield f"{path}[{index}]", None, child
            yield from walk_values(child, f"{path}[{index}]")


def check_no_private_or_raw_payloads(payload: dict[str, Any], issues: list[dict]) -> None:
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    if PRIVATE_PATTERNS.search(serialized):
        issues.append(issue("private_or_secret_marker", "$", "Plan contains a private path, host, showcase marker, or secret marker."))
    for path, key, value in walk_values(payload):
        if key in RAW_PAYLOAD_KEYS:
            issues.append(issue("raw_payload_field", path, f"Raw payload field {key!r} is not allowed in OpenRealm plans."))
        if isinstance(value, str) and RAW_CODE_PATTERN.search(value):
            issues.append(issue("raw_code_payload", path, "Plan text contains code execution, credential, or destructive command markers."))


def check_node_ref(value: Any, path: str, own_prefix: str, issues: list[dict]) -> None:
    if not is_node_name(value):
        issues.append(issue("unsafe_node_name", path, f"Node name is unsafe: {value!r}"))
        return
    if not (value.startswith(own_prefix) or value.startswith(ALLOWED_EXTERNAL_PREFIXES)):
        issues.append(issue("external_node_prefix", path, f"Node prefix is not allowlisted: {value!r}"))


def check_identifier_collection(collection: Any, label: str, path: str, issues: list[dict]) -> None:
    if not isinstance(collection, list):
        issues.append(issue("invalid_collection", path, f"{label} must be an array."))
        return
    for index, item in enumerate(collection):
        if not isinstance(item, dict):
            issues.append(issue("invalid_collection_item", f"{path}[{index}]", f"{label} item must be an object."))
            continue
        if not is_identifier(item.get("name")):
            issues.append(issue("unsafe_identifier", f"{path}[{index}].name", f"{label} name is unsafe: {item.get('name')!r}"))


def validate_openrealm_plan(payload: dict[str, Any]) -> list[dict]:
    issues: list[dict] = []
    if not isinstance(payload, dict):
        return [issue("invalid_plan", "$", "Plan must be a JSON object.")]

    required = [
        "schema_version",
        "product",
        "assistant",
        "plan_id",
        "plan_kind",
        "title",
        "source_prompt",
        "created_at",
        "mod_name",
        "summary",
        "tags",
        "safety_budget",
        "nodes",
        "craft_items",
        "tools",
        "recipes",
        "ores",
        "structures",
        "world_recipe",
        "approval_steps",
        "ai_disclosure",
        "provenance",
    ]
    for field in required:
        add_required(payload, field, "$", issues)

    if payload.get("schema_version") != "openrealm.plan.v1":
        issues.append(issue("schema_version_mismatch", "$.schema_version", "Expected openrealm.plan.v1."))
    if payload.get("product") != "OpenRealm":
        issues.append(issue("product_mismatch", "$.product", "Expected OpenRealm."))
    if payload.get("assistant") != "Nova":
        issues.append(issue("assistant_mismatch", "$.assistant", "Expected Nova."))
    if not isinstance(payload.get("plan_id"), str) or not PLAN_ID_RE.match(payload["plan_id"]):
        issues.append(issue("unsafe_plan_id", "$.plan_id", "Plan id must match orplan_<12 lowercase hex>."))
    if payload.get("plan_kind") not in PLAN_KINDS:
        issues.append(issue("invalid_plan_kind", "$.plan_kind", "Plan kind is not supported."))
    if not is_mod_name(payload.get("mod_name")):
        issues.append(issue("unsafe_mod_name", "$.mod_name", f"Mod name is unsafe: {payload.get('mod_name')!r}"))

    check_no_private_or_raw_payloads(payload, issues)

    budget = payload.get("safety_budget")
    if not isinstance(budget, dict):
        issues.append(issue("invalid_safety_budget", "$.safety_budget", "Safety budget must be an object."))
        budget = {}

    budget_requirements = {
        "requires_preview": True,
        "requires_approval": True,
        "rollback_required": True,
        "ai_direct_world_mutation_allowed": False,
    }
    for field, expected in budget_requirements.items():
        if field not in budget:
            kind = "missing_rollback_policy" if field == "rollback_required" else "missing_safety_policy"
            issues.append(issue(kind, f"$.safety_budget.{field}", "Required safety policy is missing."))
        elif budget.get(field) is not expected:
            kind = "missing_rollback_policy" if field == "rollback_required" else "unsafe_safety_policy"
            issues.append(issue(kind, f"$.safety_budget.{field}", f"Expected {expected!r}."))

    numeric_budgets = [
        "max_node_definitions",
        "max_craft_items",
        "max_tools",
        "max_recipes",
        "max_ores",
        "max_structures",
        "max_structure_nodes",
    ]
    for field in numeric_budgets:
        if not isinstance(budget.get(field), int) or budget.get(field, -1) < 0:
            issues.append(issue("invalid_budget", f"$.safety_budget.{field}", "Budget must be a non-negative integer."))

    nodes = payload.get("nodes", [])
    craft_items = payload.get("craft_items", [])
    tools = payload.get("tools", [])
    recipes = payload.get("recipes", [])
    ores = payload.get("ores", [])
    structures = payload.get("structures", [])

    check_identifier_collection(nodes, "node", "$.nodes", issues)
    check_identifier_collection(craft_items, "craft_item", "$.craft_items", issues)
    check_identifier_collection(tools, "tool", "$.tools", issues)
    if isinstance(nodes, list) and len(nodes) > budget.get("max_node_definitions", 0):
        issues.append(issue("too_many_nodes", "$.nodes", "Node definition count exceeds safety budget."))
    if isinstance(craft_items, list) and len(craft_items) > budget.get("max_craft_items", 0):
        issues.append(issue("too_many_craft_items", "$.craft_items", "Craft item count exceeds safety budget."))
    if isinstance(tools, list) and len(tools) > budget.get("max_tools", 0):
        issues.append(issue("too_many_tools", "$.tools", "Tool count exceeds safety budget."))
    if isinstance(recipes, list) and len(recipes) > budget.get("max_recipes", 0):
        issues.append(issue("too_many_recipes", "$.recipes", "Recipe count exceeds safety budget."))
    if isinstance(ores, list) and len(ores) > budget.get("max_ores", 0):
        issues.append(issue("too_many_ores", "$.ores", "Ore count exceeds safety budget."))
    if isinstance(structures, list) and len(structures) > budget.get("max_structures", 0):
        issues.append(issue("too_many_structures", "$.structures", "Structure count exceeds safety budget."))

    own_prefix = str(payload.get("mod_name", "")) + ":"
    known_defs = set()
    for collection in [nodes, craft_items, tools]:
        if isinstance(collection, list):
            known_defs.update(own_prefix + item.get("name", "") for item in collection if isinstance(item, dict))

    if isinstance(recipes, list):
        for index, recipe in enumerate(recipes):
            if not isinstance(recipe, dict):
                issues.append(issue("invalid_recipe", f"$.recipes[{index}]", "Recipe must be an object."))
                continue
            check_node_ref(recipe.get("output"), f"$.recipes[{index}].output", own_prefix, issues)
            rows = recipe.get("recipe")
            if not isinstance(rows, list):
                issues.append(issue("invalid_recipe", f"$.recipes[{index}].recipe", "Recipe grid must be an array."))
                continue
            for row_index, row in enumerate(rows):
                if not isinstance(row, list):
                    issues.append(issue("invalid_recipe", f"$.recipes[{index}].recipe[{row_index}]", "Recipe row must be an array."))
                    continue
                for cell_index, cell in enumerate(row):
                    if cell == "":
                        continue
                    path = f"$.recipes[{index}].recipe[{row_index}][{cell_index}]"
                    check_node_ref(cell, path, own_prefix, issues)
                    if (
                        isinstance(cell, str)
                        and not cell.startswith(ALLOWED_EXTERNAL_PREFIXES)
                        and cell not in known_defs
                    ):
                        issues.append(issue("unknown_recipe_input", path, f"Recipe input is not defined by this plan: {cell!r}"))

    if isinstance(ores, list):
        for index, ore in enumerate(ores):
            if not isinstance(ore, dict):
                issues.append(issue("invalid_ore", f"$.ores[{index}]", "Ore must be an object."))
                continue
            check_node_ref(ore.get("ore"), f"$.ores[{index}].ore", own_prefix, issues)
            check_node_ref(ore.get("wherein"), f"$.ores[{index}].wherein", own_prefix, issues)
            if isinstance(ore.get("y_min"), int) and isinstance(ore.get("y_max"), int) and ore["y_min"] > ore["y_max"]:
                issues.append(issue("bad_ore_depth", f"$.ores[{index}]", "Ore y_min cannot exceed y_max."))

    if payload.get("plan_kind") == "structure" and not structures:
        issues.append(issue("missing_structure", "$.structures", "Structure plans must include at least one structure."))
    if isinstance(structures, list):
        for index, structure in enumerate(structures):
            path = f"$.structures[{index}]"
            if not isinstance(structure, dict):
                issues.append(issue("invalid_structure", path, "Structure must be an object."))
                continue
            if not is_identifier(structure.get("name")):
                issues.append(issue("unsafe_identifier", f"{path}.name", f"Structure name is unsafe: {structure.get('name')!r}"))
            placements = structure.get("placements")
            if not isinstance(placements, list):
                issues.append(issue("invalid_structure", f"{path}.placements", "Placements must be an array."))
                continue
            if len(placements) > budget.get("max_structure_nodes", 0):
                issues.append(issue("structure_too_large", f"{path}.placements", "Structure placement count exceeds safety budget."))
            max_radius = structure.get("max_radius", 0)
            if not isinstance(max_radius, int) or max_radius < 1:
                issues.append(issue("invalid_structure_radius", f"{path}.max_radius", "Structure max_radius must be positive."))
                max_radius = 0
            for placement_index, placement in enumerate(placements):
                placement_path = f"{path}.placements[{placement_index}]"
                if not isinstance(placement, dict):
                    issues.append(issue("invalid_placement", placement_path, "Placement must be an object."))
                    continue
                check_node_ref(placement.get("node"), f"{placement_path}.node", own_prefix, issues)
                for axis in ["x", "y", "z"]:
                    value = placement.get(axis)
                    if not isinstance(value, int):
                        issues.append(issue("invalid_placement_axis", f"{placement_path}.{axis}", "Placement coordinate must be an integer."))
                    elif max_radius and abs(value) > max_radius:
                        issues.append(issue("placement_out_of_bounds", f"{placement_path}.{axis}", "Placement exceeds structure max_radius."))

    approval_steps = payload.get("approval_steps")
    if not isinstance(approval_steps, list) or not approval_steps:
        issues.append(issue("missing_approval_steps", "$.approval_steps", "Plan must include approval steps."))
    ai_disclosure = payload.get("ai_disclosure")
    if not isinstance(ai_disclosure, dict):
        issues.append(issue("invalid_ai_disclosure", "$.ai_disclosure", "AI disclosure must be an object."))
    else:
        expected = {
            "ai_assisted": True,
            "human_approval_required": True,
            "direct_world_mutation_by_ai": False,
            "generated_code_is_template_based": True,
        }
        for field, expected_value in expected.items():
            if ai_disclosure.get(field) is not expected_value:
                issues.append(issue("invalid_ai_disclosure", f"$.ai_disclosure.{field}", f"Expected {expected_value!r}."))

    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        issues.append(issue("invalid_provenance", "$.provenance", "Provenance must be an object."))
    else:
        for field in ["generator", "generator_version", "source"]:
            if not provenance.get(field):
                issues.append(issue("invalid_provenance", f"$.provenance.{field}", "Provenance field is required."))

    return issues


def find_generated_plan_paths(root: pathlib.Path) -> list[pathlib.Path]:
    paths: list[pathlib.Path] = []
    for relroot in KIT_PLAN_GLOB_ROOTS:
        base = root / relroot
        if not base.exists():
            continue
        paths.extend(path.relative_to(root) for path in base.rglob("openrealm_plan.json") if path.is_file())
    return sorted(paths)


def mutation_rejection_checks(example: dict[str, Any]) -> dict[str, bool]:
    checks: dict[str, bool] = {}

    unsafe_identifier = copy.deepcopy(example)
    unsafe_identifier["nodes"][0]["name"] = "../bad"
    checks["rejects_unsafe_identifier"] = any(
        item["kind"] == "unsafe_identifier" for item in validate_openrealm_plan(unsafe_identifier)
    )

    over_budget = copy.deepcopy(example)
    structure = over_budget["structures"][0]
    structure["placements"] = structure["placements"] * 2
    over_budget["safety_budget"]["max_structure_nodes"] = len(example["structures"][0]["placements"])
    checks["rejects_over_budget_structure"] = any(
        item["kind"] == "structure_too_large" for item in validate_openrealm_plan(over_budget)
    )

    raw_payload = copy.deepcopy(example)
    raw_payload["world_recipe"]["raw_lua"] = "os.execute('rm -rf /')"
    checks["rejects_raw_code_payload"] = any(
        item["kind"] in {"raw_payload_field", "raw_code_payload"} for item in validate_openrealm_plan(raw_payload)
    )

    missing_rollback = copy.deepcopy(example)
    del missing_rollback["safety_budget"]["rollback_required"]
    checks["rejects_missing_rollback_policy"] = any(
        item["kind"] == "missing_rollback_policy" for item in validate_openrealm_plan(missing_rollback)
    )

    direct_mutation = copy.deepcopy(example)
    direct_mutation["safety_budget"]["ai_direct_world_mutation_allowed"] = True
    checks["rejects_direct_ai_mutation"] = any(
        item["kind"] == "unsafe_safety_policy" for item in validate_openrealm_plan(direct_mutation)
    )

    return checks


def schema_mentions_required_sections(schema: dict[str, Any]) -> dict[str, bool]:
    required = set(schema.get("required", []))
    properties = schema.get("properties", {})
    return {
        "nodes": "nodes" in required and "nodes" in properties,
        "craft_items": "craft_items" in required and "craft_items" in properties,
        "tools": "tools" in required and "tools" in properties,
        "recipes": "recipes" in required and "recipes" in properties,
        "ores": "ores" in required and "ores" in properties,
        "structures": "structures" in required and "structures" in properties,
        "approval_steps": "approval_steps" in required and "approval_steps" in properties,
        "ai_disclosure": "ai_disclosure" in required and "ai_disclosure" in properties,
        "provenance": "provenance" in required and "provenance" in properties,
        "safety_budget": "safety_budget" in required and "safety_budget" in properties,
    }


def require_file(root: pathlib.Path, relpath: pathlib.Path, violations: list[dict]) -> bool:
    if not (root / relpath).is_file():
        violations.append(issue("missing_file", relpath.as_posix(), "Required contract file is missing."))
        return False
    return True


def build_report(root: pathlib.Path | str) -> dict[str, Any]:
    root = pathlib.Path(root)
    violations: list[dict] = []
    for relpath in [DOC, README, SCHEMA, EXAMPLE, KIT_SCHEMA]:
        require_file(root, relpath, violations)

    schema: dict[str, Any] = {}
    kit_schema: dict[str, Any] = {}
    example: dict[str, Any] = {}
    generated_results: list[dict[str, Any]] = []
    rejection_checks: dict[str, bool] = {}
    schema_checks: dict[str, bool] = {}
    kit_schema_checks: dict[str, bool] = {}

    if (root / SCHEMA).is_file():
        schema = read_json(root, SCHEMA)
        schema_checks = schema_mentions_required_sections(schema)
        for check, passed in schema_checks.items():
            if not passed:
                violations.append(issue("schema_missing_contract_section", f"{SCHEMA.as_posix()}:{check}", "Schema is missing a required OpenRealm Plan section."))
        if schema.get("properties", {}).get("schema_version", {}).get("const") != "openrealm.plan.v1":
            violations.append(issue("schema_version_not_canonical", SCHEMA.as_posix(), "Schema must define openrealm.plan.v1."))

    if (root / KIT_SCHEMA).is_file():
        kit_schema = read_json(root, KIT_SCHEMA)
        kit_schema_checks = schema_mentions_required_sections(kit_schema)
        for check, passed in kit_schema_checks.items():
            if not passed:
                violations.append(issue("kit_schema_missing_contract_section", f"{KIT_SCHEMA.as_posix()}:{check}", "Kit schema is missing a required OpenRealm Plan section."))
        if kit_schema.get("properties", {}).get("schema_version", {}).get("const") != "openrealm.plan.v1":
            violations.append(issue("kit_schema_version_not_canonical", KIT_SCHEMA.as_posix(), "Kit schema must define openrealm.plan.v1."))

    if (root / EXAMPLE).is_file():
        example = read_json(root, EXAMPLE)
        example_issues = validate_openrealm_plan(example)
        if example_issues:
            violations.append(issue("example_plan_invalid", EXAMPLE.as_posix(), "Public example does not satisfy OpenRealm Plan v1."))
            violations.extend(example_issues)
        else:
            rejection_checks = mutation_rejection_checks(example)
            for check, passed in rejection_checks.items():
                if not passed:
                    violations.append(issue("validator_rejection_missing", check, "Validator accepted an unsafe mutated example."))

    generated_plan_paths = find_generated_plan_paths(root)
    if not generated_plan_paths:
        violations.append(issue("missing_generated_plan_fixtures", "openrealm_advantage_kit", "No generated OpenRealm plan fixtures were found."))
    for relpath in generated_plan_paths:
        payload = read_json(root, relpath)
        plan_issues = validate_openrealm_plan(payload)
        generated_results.append({
            "path": relpath.as_posix(),
            "status": "pass" if not plan_issues else "fail",
            "issue_count": len(plan_issues),
        })
        for plan_issue in plan_issues:
            violations.append(issue("generated_plan_invalid", relpath.as_posix(), f"{plan_issue['kind']}: {plan_issue['message']}"))

    if (root / DOC).is_file():
        doc = (root / DOC).read_text(encoding="utf-8")
        for phrase in [
            "openrealm.plan.v1",
            "Luanti remains the world authority",
            "preview, human approval, queued execution, audit recording, and rollback metadata",
            "python3 util/openrealm_plan_contract.py",
        ]:
            if phrase not in doc:
                violations.append(issue("doc_missing_required_phrase", DOC.as_posix(), phrase))

    if (root / README).is_file():
        readme = (root / README).read_text(encoding="utf-8")
        for phrase in [
            "openrealm-plan-contract.md",
            "python3 util/openrealm_plan_contract.py",
        ]:
            if phrase not in readme:
                violations.append(issue("readme_missing_openrealm_plan_contract", README.as_posix(), phrase))

    return {
        "schema_version": 1,
        "status": "pass" if not violations else "fail",
        "contract": {
            "name": "OpenRealm Plan v1",
            "schema": SCHEMA.as_posix(),
            "example": EXAMPLE.as_posix(),
            "doc": DOC.as_posix(),
            "verifier": "util/openrealm_plan_contract.py",
            "kit_schema": KIT_SCHEMA.as_posix(),
            "generated_plan_fixtures": len(generated_plan_paths),
        },
        "schema_checks": schema_checks,
        "kit_schema_checks": kit_schema_checks,
        "kit_schema_status": "pass" if kit_schema_checks and all(kit_schema_checks.values()) else "fail",
        "example_status": "pass" if example and not validate_openrealm_plan(example) else "fail",
        "generated_plans": generated_results,
        "rejection_checks": rejection_checks,
        "safety": {
            "requires_preview_approval_rollback": bool(
                example
                and example.get("safety_budget", {}).get("requires_preview") is True
                and example.get("safety_budget", {}).get("requires_approval") is True
                and example.get("safety_budget", {}).get("rollback_required") is True
            ),
            "blocks_direct_ai_mutation": bool(
                example
                and example.get("safety_budget", {}).get("ai_direct_world_mutation_allowed") is False
                and example.get("ai_disclosure", {}).get("direct_world_mutation_by_ai") is False
            ),
            "generated_plans_valid": bool(generated_results) and all(item["status"] == "pass" for item in generated_results),
        },
        "violations": violations,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root to verify.")
    parser.add_argument("--output", help="Write JSON report to this path.")
    args = parser.parse_args(argv)

    try:
        report = build_report(args.root)
        payload = json.dumps(report, indent=2, sort_keys=False) + "\n"
        if args.output:
            output_path = pathlib.Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        return 0 if report["status"] == "pass" else 2
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
