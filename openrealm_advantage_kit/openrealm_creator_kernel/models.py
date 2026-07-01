from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
import hashlib
import json

PlanKind = Literal["structure", "ore_mod", "biome_recipe", "world_recipe"]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_id(prefix: str, payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:12]}"


@dataclass(frozen=True)
class Placement:
    x: int
    y: int
    z: int
    node: str


@dataclass(frozen=True)
class Structure:
    name: str
    description: str
    placements: list[Placement]
    max_radius: int = 32


@dataclass(frozen=True)
class NodeDef:
    name: str
    description: str
    texture_hint: str
    groups: dict[str, int] = field(default_factory=dict)
    light_source: int = 0
    drawtype: str = "normal"
    paramtype: str | None = None
    walkable: bool = True


@dataclass(frozen=True)
class CraftItemDef:
    name: str
    description: str
    inventory_image_hint: str


@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    inventory_image_hint: str
    damage_groups: dict[str, int] = field(default_factory=lambda: {"fleshy": 7})
    full_punch_interval: float = 0.7


@dataclass(frozen=True)
class Recipe:
    output: str
    recipe: list[list[str]]


@dataclass(frozen=True)
class OreDef:
    ore: str
    wherein: str = "default:stone"
    clust_scarcity: int = 9 * 9 * 9
    clust_num_ores: int = 5
    clust_size: int = 3
    y_min: int = -31000
    y_max: int = -200


@dataclass(frozen=True)
class SafetyBudget:
    max_node_definitions: int = 32
    max_craft_items: int = 32
    max_tools: int = 16
    max_recipes: int = 32
    max_ores: int = 16
    max_structures: int = 8
    max_structure_nodes: int = 256
    requires_preview: bool = True
    requires_approval: bool = True
    rollback_required: bool = True
    ai_direct_world_mutation_allowed: bool = False


@dataclass(frozen=True)
class OpenRealmPlan:
    schema_version: str
    product: str
    assistant: str
    plan_id: str
    plan_kind: PlanKind
    title: str
    source_prompt: str
    created_at: str
    mod_name: str
    summary: str
    tags: list[str]
    safety_budget: SafetyBudget
    nodes: list[NodeDef] = field(default_factory=list)
    craft_items: list[CraftItemDef] = field(default_factory=list)
    tools: list[ToolDef] = field(default_factory=list)
    recipes: list[Recipe] = field(default_factory=list)
    ores: list[OreDef] = field(default_factory=list)
    structures: list[Structure] = field(default_factory=list)
    world_recipe: dict[str, Any] = field(default_factory=dict)
    approval_steps: list[str] = field(default_factory=list)
    ai_disclosure: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False)

    @classmethod
    def create(
        cls,
        *,
        plan_kind: PlanKind,
        title: str,
        source_prompt: str,
        mod_name: str,
        summary: str,
        tags: list[str],
        nodes: list[NodeDef] | None = None,
        craft_items: list[CraftItemDef] | None = None,
        tools: list[ToolDef] | None = None,
        recipes: list[Recipe] | None = None,
        ores: list[OreDef] | None = None,
        structures: list[Structure] | None = None,
        world_recipe: dict[str, Any] | None = None,
    ) -> "OpenRealmPlan":
        payload = {
            "kind": plan_kind,
            "title": title,
            "prompt": source_prompt,
            "mod": mod_name,
            "tags": tags,
        }
        return cls(
            schema_version="openrealm.plan.v1",
            product="OpenRealm",
            assistant="Nova",
            plan_id=stable_id("orplan", payload),
            plan_kind=plan_kind,
            title=title,
            source_prompt=source_prompt,
            created_at=utc_now(),
            mod_name=mod_name,
            summary=summary,
            tags=tags,
            safety_budget=SafetyBudget(),
            nodes=nodes or [],
            craft_items=craft_items or [],
            tools=tools or [],
            recipes=recipes or [],
            ores=ores or [],
            structures=structures or [],
            world_recipe=world_recipe or {},
            approval_steps=[
                "Review generated OpenRealm plan.",
                "Inspect preview and node/write budget.",
                "Install only in a disposable test world first.",
                "Approve in-world command before mutation.",
                "Use rollback command if result is not wanted.",
            ],
            ai_disclosure={
                "ai_assisted": True,
                "assistant_name": "Nova",
                "human_approval_required": True,
                "direct_world_mutation_by_ai": False,
                "generated_code_is_template_based": True,
            },
            provenance={
                "generator": "openrealm_creator_kernel",
                "generator_version": "0.1.0",
                "created_by": "local_operator",
                "source": "prompt",
            },
        )
