from __future__ import annotations

from dataclasses import dataclass
import re

from .identifiers import is_identifier, is_mod_name, is_node_name
from .models import OpenRealmPlan

DANGEROUS_PROMPT_TOKENS = re.compile(
    r"\b(?:os\.execute|io\.popen|require\s*\(|loadstring|dofile|debug\.|package\.loaded|"
    r"minetest\.request_http_api|delete\s+world|rm\s+-rf|api[_-]?key|secret|token)\b",
    re.I,
)

ALLOWED_EXTERNAL_PREFIXES = (
    "default:", "doors:", "stairs:", "wool:", "fire:", "tnt:", "farming:",
)


@dataclass(frozen=True)
class SafetyIssue:
    code: str
    message: str
    severity: str = "error"


@dataclass(frozen=True)
class SafetyReport:
    ok: bool
    issues: list[SafetyIssue]

    def raise_for_errors(self) -> None:
        if not self.ok:
            details = "; ".join(f"{i.code}: {i.message}" for i in self.issues)
            raise ValueError(f"OpenRealm safety validation failed: {details}")


def validate_plan(plan: OpenRealmPlan) -> SafetyReport:
    issues: list[SafetyIssue] = []
    budget = plan.safety_budget

    if DANGEROUS_PROMPT_TOKENS.search(plan.source_prompt or ""):
        issues.append(SafetyIssue("dangerous_prompt_token", "Prompt contains text that looks like code execution, secrets, or destructive commands."))

    if not is_mod_name(plan.mod_name):
        issues.append(SafetyIssue("unsafe_mod_name", f"Mod name is not safe: {plan.mod_name!r}"))

    if len(plan.nodes) > budget.max_node_definitions:
        issues.append(SafetyIssue("too_many_nodes", "Plan defines too many nodes."))
    if len(plan.craft_items) > budget.max_craft_items:
        issues.append(SafetyIssue("too_many_craft_items", "Plan defines too many craft items."))
    if len(plan.tools) > budget.max_tools:
        issues.append(SafetyIssue("too_many_tools", "Plan defines too many tools."))
    if len(plan.recipes) > budget.max_recipes:
        issues.append(SafetyIssue("too_many_recipes", "Plan defines too many recipes."))
    if len(plan.ores) > budget.max_ores:
        issues.append(SafetyIssue("too_many_ores", "Plan defines too many ores."))
    if len(plan.structures) > budget.max_structures:
        issues.append(SafetyIssue("too_many_structures", "Plan defines too many structures."))

    for collection_name, collection in [
        ("nodes", plan.nodes),
        ("craft_items", plan.craft_items),
        ("tools", plan.tools),
    ]:
        for item in collection:
            if not is_identifier(item.name):
                issues.append(SafetyIssue("unsafe_identifier", f"{collection_name} has unsafe name: {item.name!r}"))

    own_prefix = plan.mod_name + ":"
    known_nodes = {own_prefix + node.name for node in plan.nodes}
    known_items = {own_prefix + item.name for item in plan.craft_items}
    known_tools = {own_prefix + tool.name for tool in plan.tools}
    known_any = known_nodes | known_items | known_tools

    def check_node_name(value: str, context: str) -> None:
        if not is_node_name(value):
            issues.append(SafetyIssue("unsafe_node_name", f"{context} node name is unsafe: {value!r}"))
            return
        if not (value.startswith(own_prefix) or value.startswith(ALLOWED_EXTERNAL_PREFIXES)):
            issues.append(SafetyIssue("external_node_prefix", f"{context} uses non-allowlisted prefix: {value!r}"))

    for ore in plan.ores:
        check_node_name(ore.ore, "ore")
        check_node_name(ore.wherein, "wherein")
        if ore.y_min > ore.y_max:
            issues.append(SafetyIssue("bad_ore_depth", "Ore y_min cannot be greater than y_max."))
        if ore.clust_scarcity < 1 or ore.clust_size < 1 or ore.clust_num_ores < 1:
            issues.append(SafetyIssue("bad_ore_cluster", "Ore cluster settings must be positive."))

    for recipe in plan.recipes:
        if not is_node_name(recipe.output):
            issues.append(SafetyIssue("unsafe_recipe_output", f"Recipe output is unsafe: {recipe.output!r}"))
        for row in recipe.recipe:
            for cell in row:
                if cell and not is_node_name(cell):
                    issues.append(SafetyIssue("unsafe_recipe_input", f"Recipe input is unsafe: {cell!r}"))
                elif cell and not (cell in known_any or cell.startswith(ALLOWED_EXTERNAL_PREFIXES)):
                    issues.append(SafetyIssue("unknown_recipe_input", f"Recipe input is not known or allowlisted: {cell!r}", "warning"))

    for structure in plan.structures:
        if not is_identifier(structure.name):
            issues.append(SafetyIssue("unsafe_structure_name", f"Structure name is unsafe: {structure.name!r}"))
        if len(structure.placements) > budget.max_structure_nodes:
            issues.append(SafetyIssue("structure_too_large", f"Structure {structure.name!r} exceeds node budget."))
        for placement in structure.placements:
            check_node_name(placement.node, f"structure {structure.name}")
            if abs(placement.x) > structure.max_radius or abs(placement.y) > structure.max_radius or abs(placement.z) > structure.max_radius:
                issues.append(SafetyIssue("placement_out_of_bounds", f"Placement outside allowed radius in {structure.name!r}."))

    if budget.ai_direct_world_mutation_allowed:
        issues.append(SafetyIssue("ai_direct_mutation", "AI direct mutation must remain disabled."))
    if not budget.requires_preview or not budget.requires_approval:
        issues.append(SafetyIssue("missing_preview_approval", "Preview and approval are required."))
    if not budget.rollback_required:
        issues.append(SafetyIssue("rollback_not_required", "Rollback must remain required."))

    hard_errors = [issue for issue in issues if issue.severity == "error"]
    return SafetyReport(ok=not hard_errors, issues=issues)
