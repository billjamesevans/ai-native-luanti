#!/usr/bin/env python3
"""Dry-run compatibility reporter and no-mutation apply planner."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import pathlib
import sys
import zipfile


REPORT_VERSION = 1
APPLY_REQUEST_VERSION = 1
APPLY_SUMMARY_VERSION = 1
TOP_LEVEL_REQUIRED = (
    "report_version",
    "mode",
    "generated_at",
    "source",
    "summary",
    "sections",
    "unsupported_features",
    "planned_actions",
    "safety",
)
SOURCE_REQUIRED = ("source_id", "source_class", "path_policy", "license_status", "inventory")
SUMMARY_REQUIRED = (
    "risk_level",
    "items_total",
    "supported",
    "partial",
    "unsupported",
    "skipped",
    "unknown",
    "estimated_world_mutations",
)
MUTATION_COST_REQUIRED = (
    "node_writes",
    "mapblock_churn",
    "media_files",
    "entity_definitions",
    "manual_review_items",
)
STRUCTURE_BYTES_PER_NODE_ESTIMATE = 64
MAPBLOCK_NODE_VOLUME = 16 * 16 * 16
SYNTHETIC_STRUCTURE_FIXTURE_KIND = "ai_native_synthetic_structure"
SYNTHETIC_STRUCTURE_ADAPTER_KIND = "synthetic_structure_v1"
SECTION_REQUIRED = ("name", "items_total", "status", "message")
UNSUPPORTED_FEATURE_REQUIRED = (
    "feature",
    "status",
    "reason",
    "severity",
    "message",
    "recommendation",
)
PLANNED_ACTION_REQUIRED = ("action", "status", "description", "mutation_cost")
INVENTORY_ENTRY_REQUIRED = (
    "entry_id",
    "source_path",
    "source_kind",
    "size_bytes",
    "classification",
    "reason",
    "required_capabilities",
)
SAFETY_REQUIRED_TRUE = (
    "no_assets_copied",
    "no_world_mutation",
    "source_paths_redacted",
    "user_rights_required",
)
APPLY_REQUEST_REQUIRED = (
    "request_version",
    "mode",
    "report_id",
    "report_version",
    "source_reference",
    "approved_actions",
    "target_world",
    "operator",
    "agent_id",
    "budget",
    "rollback_policy",
)
SOURCE_REFERENCE_REQUIRED = ("reference_type", "redacted_id", "inventory_hash")
APPROVED_ACTION_REQUIRED = ("action_index", "action", "status")
APPLY_BUDGET_REQUIRED = (
    "max_media_files",
    "max_entity_definitions",
    "max_node_writes_total",
    "max_node_writes_per_step",
    "max_mapblock_churn_total",
    "max_manual_review_items",
    "max_wall_time_ms",
)
ROLLBACK_POLICY_REQUIRED = ("policy", "metadata_required")
ROLLBACK_POLICIES = ("snapshot", "manifest_only", "chunked", "no_world_mutation")
WORLD_MUTATING_ROLLBACK_POLICIES = ("snapshot", "manifest_only", "chunked")
APPLY_SUMMARY_REQUIRED = (
    "summary_version",
    "apply_id",
    "report_id",
    "status",
    "approved_actions",
    "queued_tasks",
    "running_tasks",
    "completed_tasks",
    "blocked_tasks",
    "mutation_cost_actual",
    "rollback_records",
    "audit_record_count",
    "operator_next_actions",
    "safety",
)
APPLY_SUMMARY_SAFETY_REQUIRED = (
    "assets_remain_operator_supplied",
    "dry_run_report_unchanged",
    "world_mutation_executed",
)
PLANNED_ACTION_TASK_MAPPINGS = {
    "copy_asset_reference": {
        "label": "compat.asset.reference",
        "mutation_class": "metadata_only",
        "requires_safe_world_ops": False,
    },
    "map_texture": {
        "label": "compat.media.texture",
        "mutation_class": "metadata_only",
        "requires_safe_world_ops": False,
    },
    "map_sound": {
        "label": "compat.media.sound",
        "mutation_class": "metadata_only",
        "requires_safe_world_ops": False,
    },
    "register_node_alias": {
        "label": "compat.node.alias",
        "mutation_class": "metadata_only",
        "requires_safe_world_ops": False,
    },
    "register_entity_stub": {
        "label": "compat.entity.stub",
        "mutation_class": "metadata_only",
        "requires_safe_world_ops": False,
    },
    "import_structure": {
        "label": "compat.structure.place",
        "mutation_class": "world_mutating",
        "requires_safe_world_ops": True,
        "extra_capabilities": ("world.place", "world.batch"),
    },
    "skip_feature": {
        "label": "compat.feature.skip",
        "mutation_class": "none",
        "requires_safe_world_ops": False,
    },
}


def _utc_now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _normalized_relpath(path):
    return pathlib.PurePosixPath(path).as_posix()


def _directory_entries(source):
    entries = []
    for path in sorted(p for p in source.rglob("*") if p.is_file()):
        relpath = _normalized_relpath(path.relative_to(source))
        entries.append({
            "path": relpath,
            "size": path.stat().st_size,
        })
    return entries


def _zip_entries(source):
    entries = []
    with zipfile.ZipFile(source) as archive:
        for info in sorted(archive.infolist(), key=lambda item: item.filename):
            if info.is_dir():
                continue
            entries.append({
                "path": _normalized_relpath(info.filename),
                "size": info.file_size,
            })
    return entries


def _entries_for(source):
    if source.is_dir():
        return _directory_entries(source)
    if source.suffix.lower() in {".mcpack", ".mcworld", ".zip"} and zipfile.is_zipfile(source):
        return _zip_entries(source)
    return [{
        "path": source.name,
        "size": source.stat().st_size,
    }]


def _read_zip_json(source, filename):
    with zipfile.ZipFile(source) as archive:
        with archive.open(filename) as handle:
            return json.loads(handle.read().decode("utf-8"))


def _read_entry_text(source, filename):
    if source.is_dir():
        return (source / filename).read_text(encoding="utf-8")
    with zipfile.ZipFile(source) as archive:
        with archive.open(filename) as handle:
            return handle.read().decode("utf-8")


def _mapblock_key(pos):
    return (
        math.floor(pos["x"] / 16),
        math.floor(pos["y"] / 16),
        math.floor(pos["z"] / 16),
    )


def _mapblock_churn_from_positions(placements):
    return len({_mapblock_key(placement["pos"]) for placement in placements})


def _check_int(value, field):
    if not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _normalize_structure_pos(value, field):
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return {
        "x": _check_int(value.get("x"), f"{field}.x"),
        "y": _check_int(value.get("y"), f"{field}.y"),
        "z": _check_int(value.get("z"), f"{field}.z"),
    }


def _normalize_synthetic_structure_fixture(raw, source):
    if raw.get("fixture_kind") != SYNTHETIC_STRUCTURE_FIXTURE_KIND:
        return None
    if raw.get("fixture_version") != 1:
        raise ValueError("fixture_version must be 1")
    placements = raw.get("placements")
    if not isinstance(placements, list) or not placements:
        raise ValueError("placements must be a non-empty array")

    palette = raw.get("palette", {})
    if not isinstance(palette, dict):
        raise ValueError("palette must be an object")
    normalized_palette = {
        str(alias): str(node_name)
        for alias, node_name in palette.items()
    }

    normalized_placements = []
    for index, placement in enumerate(placements):
        if not isinstance(placement, dict):
            raise ValueError(f"placements[{index}] must be an object")
        node_ref = placement.get("node") or placement.get("node_name")
        if not isinstance(node_ref, str) or not node_ref:
            raise ValueError(f"placements[{index}].node must be a non-empty string")
        node_name = normalized_palette.get(node_ref, node_ref)
        if ":" not in node_name and node_name != "air":
            raise ValueError(
                f"placements[{index}].node must resolve to a namespaced node or air"
            )
        normalized = {
            "pos": _normalize_structure_pos(placement.get("pos"), f"placements[{index}].pos"),
            "node_name": node_name,
        }
        if "param1" in placement:
            normalized["param1"] = _check_int(placement["param1"], f"placements[{index}].param1")
        if "param2" in placement:
            normalized["param2"] = _check_int(placement["param2"], f"placements[{index}].param2")
        normalized_placements.append(normalized)

    unsupported_fields = raw.get("unsupported_fields", [])
    if not isinstance(unsupported_fields, list):
        raise ValueError("unsupported_fields must be an array")
    normalized_unsupported = []
    for index, item in enumerate(unsupported_fields):
        if not isinstance(item, dict):
            raise ValueError(f"unsupported_fields[{index}] must be an object")
        field = item.get("field")
        if not isinstance(field, str) or not field:
            raise ValueError(f"unsupported_fields[{index}].field must be a non-empty string")
        normalized_unsupported.append({
            "field": field,
            "reason": str(item.get("reason") or "requires_manual_review"),
            "message": str(item.get("message") or f"{field} requires manual review."),
            "recommendation": str(item.get("recommendation")
                or "Keep the field out of staged apply until an adapter supports it."),
        })

    chunk_size = raw.get("recommended_chunk_size", 2)
    chunk_size = _check_int(chunk_size, "recommended_chunk_size")
    if chunk_size <= 0:
        raise ValueError("recommended_chunk_size must be positive")

    return {
        "adapter_kind": SYNTHETIC_STRUCTURE_ADAPTER_KIND,
        "fixture_name": str(raw.get("name") or source.stem),
        "fixture_version": 1,
        "synthetic": True,
        "palette": normalized_palette,
        "placements": normalized_placements,
        "recommended_chunk_size": chunk_size,
        "unsupported_fields": normalized_unsupported,
    }


def _load_synthetic_structure_fixture(source):
    if not source.is_file() or source.suffix.lower() != ".json":
        return None
    try:
        raw = _read_json(source)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    return _normalize_synthetic_structure_fixture(raw, source)


def _parse_luanti_mod_conf(text):
    metadata = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        metadata[key.strip()] = value.strip()
    return metadata


def _metadata_for(source, entries, synthetic_structure=None):
    if synthetic_structure:
        return "structure", {
            "adapter_kind": synthetic_structure["adapter_kind"],
            "fixture_name": synthetic_structure["fixture_name"],
            "fixture_version": synthetic_structure["fixture_version"],
            "placement_count": len(synthetic_structure["placements"]),
            "palette_count": len(synthetic_structure["palette"]),
            "unsupported_field_count": len(synthetic_structure["unsupported_fields"]),
        }

    names = {entry["path"] for entry in entries}
    if source.is_dir() and (source / "pack.mcmeta").is_file():
        metadata = _read_json(source / "pack.mcmeta").get("pack", {})
        return "java_resource_pack", {
            "pack_format": str(metadata.get("pack_format", "")),
            "description": str(metadata.get("description", "")),
        }

    manifest_name = next((name for name in names if name.endswith("manifest.json")), None)
    if manifest_name:
        if source.is_dir():
            manifest = _read_json(source / manifest_name)
        else:
            manifest = _read_zip_json(source, manifest_name)
        module_types = [module.get("type", "") for module in manifest.get("modules", [])]
        if "resources" in module_types:
            source_class = "bedrock_resource_pack"
        elif "data" in module_types:
            source_class = "bedrock_behavior_pack"
        else:
            source_class = "unknown"
        return source_class, {
            "manifest_format_version": str(manifest.get("format_version", "")),
            "pack_name": str(manifest.get("header", {}).get("name", "")),
            "module_types": ",".join(sorted(t for t in module_types if t)),
        }

    mod_conf_name = next((name for name in names if name == "mod.conf" or name.endswith("/mod.conf")), None)
    if mod_conf_name:
        mod_conf = _parse_luanti_mod_conf(_read_entry_text(source, mod_conf_name))
        depends_name = next((name for name in names if name == "depends.txt" or name.endswith("/depends.txt")), None)
        parent = pathlib.PurePosixPath(mod_conf_name).parent
        fallback_name = source.name if str(parent) == "." else parent.name
        metadata = {
            "mod_name": mod_conf.get("name", fallback_name),
            "description": mod_conf.get("description", ""),
        }
        if depends_name:
            metadata["depends_declared"] = "true"
        return "luanti_mod", metadata

    if any(name.endswith("level.dat") for name in names):
        return "world", {}

    suffix = source.suffix.lower()
    if suffix in {".schem", ".schematic", ".mcstructure"}:
        return "structure", {}
    if suffix == ".mcworld":
        return "world", {}
    return "unknown", {}


def _inventory_hash(entries):
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(entry["path"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(entry["size"]).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _category_counts(entries, synthetic_structure=None):
    counts = {
        "metadata": 0,
        "textures": 0,
        "sounds": 0,
        "models": 0,
        "entities": 0,
        "behaviors": 0,
        "structures": 0,
        "world": 0,
    }
    for entry in entries:
        path = entry["path"].lower()
        suffix = pathlib.PurePosixPath(path).suffix
        if (path.endswith("pack.mcmeta") or path.endswith("manifest.json")
                or path.endswith("mod.conf") or path.endswith("depends.txt")):
            counts["metadata"] += 1
        if "/textures/" in f"/{path}" or suffix in {".png", ".jpg", ".jpeg"}:
            counts["textures"] += 1
        if "/sounds/" in f"/{path}" or suffix in {".ogg", ".wav"}:
            counts["sounds"] += 1
        if "/models/" in f"/{path}" or "models" in path:
            counts["models"] += 1
        if "/entities/" in f"/{path}" or ".entity.json" in path:
            counts["entities"] += 1
        if "/scripts/" in f"/{path}" or suffix == ".js" or "behavior" in path:
            counts["behaviors"] += 1
        if suffix in {".schem", ".schematic", ".mcstructure"}:
            counts["structures"] += 1
        if path.endswith("level.dat") or suffix == ".mcworld":
            counts["world"] += 1
    if synthetic_structure:
        counts["metadata"] = 0
        counts["structures"] = max(1, counts["structures"])
    return counts


def _source_kind(entry, synthetic_structure=None):
    if synthetic_structure:
        return "structure"
    path = entry["path"].lower()
    suffix = pathlib.PurePosixPath(path).suffix
    wrapped = f"/{path}"
    if path.endswith("mod.conf") or path.endswith("depends.txt"):
        return "mod_metadata"
    if path.endswith("pack.mcmeta") or path.endswith("manifest.json"):
        return "metadata"
    if "/textures/" in wrapped or suffix in {".png", ".jpg", ".jpeg"}:
        return "texture"
    if "/sounds/" in wrapped or suffix in {".ogg", ".wav"}:
        return "sound"
    if "/models/" in wrapped or "models" in path:
        return "model"
    if "/scripts/" in wrapped or suffix == ".js" or "behavior" in path:
        return "behavior"
    if "/entities/" in wrapped or ".entity.json" in path:
        return "entity"
    if suffix in {".schem", ".schematic", ".mcstructure"}:
        return "structure"
    if path.endswith("level.dat") or suffix == ".mcworld":
        return "world"
    return "unknown"


def _inventory_classification(source_kind, source_class):
    if source_kind in {"metadata", "mod_metadata", "texture", "sound"}:
        return "mapped", "metadata_or_asset_reference"
    if source_kind in {"model", "entity"}:
        return "blocked", "requires_manual_review"
    if source_kind == "behavior":
        return "unsupported", "behavior_script_not_supported"
    if source_kind == "structure":
        return "blocked", "requires_apply_approval"
    if source_kind == "world":
        return "blocked", "world_format_not_supported"
    if source_class == "unknown":
        return "unsupported", "unsupported_format"
    return "unknown", "unclassified_entry"


def _source_inventory(entries, source_class, synthetic_structure=None):
    inventory = []
    for index, entry in enumerate(entries):
        source_kind = _source_kind(entry, synthetic_structure)
        classification, reason = _inventory_classification(source_kind, source_class)
        if synthetic_structure and source_kind == "structure":
            classification = "blocked"
            reason = "synthetic_structure_adapter_review_required"
        inventory.append({
            "entry_id": f"entry:{index + 1}",
            "source_path": entry["path"],
            "source_kind": source_kind,
            "size_bytes": entry["size"],
            "classification": classification,
            "reason": reason,
            "required_capabilities": ["import.assets"],
        })
    return inventory


def _section_status(name, count, unsupported_count):
    if count == 0:
        return "skipped"
    if name in {"metadata"}:
        return "supported"
    if name in {"behaviors"} and unsupported_count:
        return "unsupported"
    return "partial"


def _sections(counts, unsupported_features, structure_cost=None):
    structure_cost = structure_cost or {
        "node_writes": 0,
        "mapblock_churn": 0,
        "manual_review_items": 0,
    }
    sections = []
    unsupported_by_name = {
        "entities": sum(1 for item in unsupported_features if item["feature"] == "entity.ai_goal"),
        "behaviors": sum(1 for item in unsupported_features if item["feature"] == "entity.behavior_script"),
    }
    for name in ("metadata", "textures", "sounds", "models", "entities", "behaviors", "structures", "world"):
        count = counts[name]
        if count == 0:
            continue
        status = _section_status(name, count, unsupported_by_name.get(name, 0))
        section_counts = {
            "items": count,
        }
        if name == "structures":
            section_counts.update({
                "estimated_node_writes": structure_cost["node_writes"],
                "estimated_mapblock_churn": structure_cost["mapblock_churn"],
                "manual_review_items": structure_cost["manual_review_items"],
            })
        sections.append({
            "name": name,
            "items_total": count,
            "status": status,
            "message": _section_message(name, status),
            "counts": section_counts,
        })
    if not sections:
        sections.append({
            "name": "metadata",
            "items_total": 0,
            "status": "unknown",
            "message": "No recognized metadata was found.",
            "counts": {
                "items": 0,
            },
        })
    return sections


def _section_message(name, status):
    if name == "metadata" and status == "supported":
        return "Pack metadata can be parsed without copying source assets."
    if name == "behaviors":
        return "Behavior scripts are reported but not executed or translated."
    if name == "entities":
        return "Entity descriptors can create placeholder stubs; behavior AI needs manual mapping."
    if name == "models":
        return "Model references are inventoried for manual mapping."
    if name == "textures":
        return "Texture files can be referenced by later import steps after rights are confirmed."
    if name == "sounds":
        return "Sound files can be referenced by later import steps after rights are confirmed."
    if name == "structures":
        return "Structure files require an apply-phase placement review."
    if name == "world":
        return "World metadata requires an apply-phase conversion review."
    return "Items were detected but need importer support."


def _unsupported_features(entries, source_class, synthetic_structure=None):
    features = []
    for entry in entries:
        path = entry["path"]
        lower = path.lower()
        suffix = pathlib.PurePosixPath(lower).suffix
        if "/scripts/" in f"/{lower}" or suffix == ".js" or "behavior" in lower:
            features.append({
                "feature": "entity.behavior_script",
                "source_path": path,
                "status": "unsupported",
                "reason": "behavior_script_not_supported",
                "severity": "warning",
                "message": "Behavior scripts are not translated or executed by dry-run compatibility reports.",
                "recommendation": "Create a manual Luanti behavior or keep the entity as a static stub.",
            })
        if "/entities/" in f"/{lower}" or ".entity.json" in lower:
            features.append({
                "feature": "entity.ai_goal",
                "source_path": path,
                "status": "unsupported",
                "reason": "entity_ai_not_supported",
                "severity": "warning",
                "message": "Source entity AI goals do not have a Luanti mapping yet.",
                "recommendation": "Map the entity to a first-party agent or manually authored mob definition.",
            })
        if path.endswith("level.dat") or suffix == ".mcworld":
            features.append({
                "feature": "world.format",
                "source_path": path,
                "status": "unsupported",
                "reason": "world_format_not_supported",
                "severity": "warning",
                "message": "Whole-world conversion is not supported by the dry-run importer yet.",
                "recommendation": "Start with public-safe metadata inventory or structures before world conversion.",
            })
    if source_class == "unknown":
        features.append({
            "feature": "source.format",
            "source_path": "",
            "status": "unknown",
            "reason": "unsupported_format",
            "severity": "error",
            "message": "The source format could not be classified safely.",
            "recommendation": "Provide a Java pack.mcmeta, Bedrock manifest.json, or known structure file.",
        })
    if synthetic_structure:
        for item in synthetic_structure["unsupported_fields"]:
            features.append({
                "feature": f"structure.{item['field']}",
                "source_path": f"{synthetic_structure['fixture_name']}#{item['field']}",
                "status": "unsupported",
                "reason": "requires_manual_review",
                "severity": "warning",
                "message": item["message"],
                "recommendation": item["recommendation"],
            })
    return features


def _mutation_cost(counts, unsupported_count):
    structure_cost = _structure_cost_from_counts(counts)
    return {
        "node_writes": structure_cost["node_writes"],
        "mapblock_churn": structure_cost["mapblock_churn"],
        "media_files": counts["textures"] + counts["sounds"] + counts["models"],
        "entity_definitions": counts["entities"],
        "manual_review_items": (
            unsupported_count + counts["models"] + counts["world"]
            + structure_cost["manual_review_items"]
        ),
    }


def _structure_cost(entries, synthetic_structure=None):
    if synthetic_structure:
        placements = synthetic_structure["placements"]
        node_writes = len(placements)
        mapblock_churn = _mapblock_churn_from_positions(placements)
        return {
            "structure_files": 1,
            "node_writes": node_writes,
            "mapblock_churn": mapblock_churn,
            "manual_review_items": 2,
            "calibration": {
                "strategy": "synthetic_structure_adapter",
                "adapter_kind": synthetic_structure["adapter_kind"],
                "recommended_chunk_size": synthetic_structure["recommended_chunk_size"],
                "notes": [
                    "Synthetic fixture placements are parsed as metadata for review.",
                    "Dry-run does not queue tasks or mutate a world.",
                ],
            },
        }

    structure_entries = [
        entry for entry in entries
        if pathlib.PurePosixPath(entry["path"].lower()).suffix
        in {".schem", ".schematic", ".mcstructure"}
    ]
    node_writes = sum(
        max(1, math.ceil(entry["size"] / STRUCTURE_BYTES_PER_NODE_ESTIMATE))
        for entry in structure_entries
    )
    return {
        "structure_files": len(structure_entries),
        "node_writes": node_writes,
        "mapblock_churn": len(structure_entries)
        if node_writes else 0,
        "manual_review_items": len(structure_entries) * 2,
        "calibration": {
            "strategy": "synthetic_size_estimate",
            "bytes_per_node": STRUCTURE_BYTES_PER_NODE_ESTIMATE,
            "mapblock_node_volume": MAPBLOCK_NODE_VOLUME,
            "notes": [
                "Dry-run does not parse or copy source structure payloads.",
                "Each structure file requires placement and palette review before apply.",
            ],
        },
    }


def _structure_cost_from_counts(counts):
    structures = counts["structures"]
    return {
        "structure_files": structures,
        "node_writes": structures,
        "mapblock_churn": structures,
        "manual_review_items": structures * 2,
    }


def _structure_adapter_payload(synthetic_structure, structure_cost):
    if not synthetic_structure:
        return None
    placement_count = len(synthetic_structure["placements"])
    chunk_size = min(synthetic_structure["recommended_chunk_size"], placement_count)
    return {
        "adapter_kind": synthetic_structure["adapter_kind"],
        "fixture_name": synthetic_structure["fixture_name"],
        "synthetic": True,
        "placement_count": placement_count,
        "mapblock_churn": structure_cost["mapblock_churn"],
        "recommended_chunk_size": chunk_size,
        "recommended_chunk_count": math.ceil(placement_count / chunk_size),
        "placements": synthetic_structure["placements"],
        "unsupported_field_count": len(synthetic_structure["unsupported_fields"]),
    }


def _planned_actions(counts, unsupported_features, structure_cost, synthetic_structure=None):
    actions = []
    if counts["textures"]:
        actions.append(_action("map_texture", "partial", "Map user-owned texture references after rights are confirmed.", counts, 0))
    if counts["sounds"]:
        actions.append(_action("map_sound", "partial", "Map user-owned sound references after rights are confirmed.", counts, 0))
    if counts["models"]:
        actions.append(_action("copy_asset_reference", "partial", "Reference model metadata for manual Luanti mapping.", counts, 1))
    if counts["entities"]:
        actions.append(_action("register_entity_stub", "partial", "Create placeholder entity definitions without imported behavior AI.", counts, 1))
    if counts["structures"]:
        actions.append(_action(
            "import_structure",
            "partial",
            "Estimate structure placement for a later apply phase.",
            counts,
            structure_cost["manual_review_items"],
            structure_cost,
            _structure_adapter_payload(synthetic_structure, structure_cost),
        ))
    if unsupported_features:
        actions.append(_action("skip_feature", "skipped", "Record unsupported features without importing them.", counts, len(unsupported_features)))
    if not actions:
        actions.append(_action("skip_feature", "skipped", "No importable content was detected.", counts, 0))
    return actions


def _action(action, status, description, counts, manual_review_items,
            structure_cost=None, structure_adapter=None):
    structure_cost = structure_cost or {
        "node_writes": 0,
        "mapblock_churn": 0,
    }
    payload = {
        "action": action,
        "status": status,
        "description": description,
        "required_capabilities": ["import.assets"],
        "mutation_cost": {
            "node_writes": structure_cost["node_writes"] if action == "import_structure" else 0,
            "mapblock_churn": structure_cost["mapblock_churn"] if action == "import_structure" else 0,
            "media_files": counts["textures"] + counts["sounds"] + counts["models"],
            "entity_definitions": counts["entities"] if action == "register_entity_stub" else 0,
            "manual_review_items": manual_review_items,
        },
    }
    if action == "import_structure" and structure_adapter:
        payload["structure_adapter"] = structure_adapter
    return payload


def _risk_level(source_class, counts, unsupported_count):
    if source_class in {"world", "structure"} or counts["structures"] or counts["world"]:
        return "high"
    if unsupported_count or counts["entities"] or counts["behaviors"]:
        return "medium"
    return "low"


def _build_report(source, synthetic_structure=None):
    source = pathlib.Path(source)
    if not source.exists():
        raise FileNotFoundError(source)

    entries = _entries_for(source)
    source_class, metadata = _metadata_for(source, entries, synthetic_structure)
    inventory = _source_inventory(entries, source_class, synthetic_structure)
    counts = _category_counts(entries, synthetic_structure)
    structure_cost = _structure_cost(entries, synthetic_structure)
    unsupported_features = _unsupported_features(entries, source_class, synthetic_structure)
    unsupported_count = len(unsupported_features)
    partial_count = sum(1 for value in counts.values() if value > 0) - (1 if counts["metadata"] else 0)
    supported_count = 1 if counts["metadata"] else 0
    skipped_count = 1 if unsupported_features else 0

    return {
        "report_version": REPORT_VERSION,
        "mode": "dry_run",
        "generated_at": _utc_now(),
        "source": {
            "source_id": source.name,
            "source_class": source_class,
            "path_policy": "synthetic_fixture" if synthetic_structure else "external_reference",
            "license_status": "synthetic" if synthetic_structure else "user_supplied",
            "metadata": metadata,
            "inventory": inventory,
            "content_hashes": [{
                "algorithm": "sha256",
                "value": _inventory_hash(entries),
                "purpose": "inventory path and size hash",
            }],
        },
        "summary": {
            "risk_level": _risk_level(source_class, counts, unsupported_count),
            "items_total": len(entries),
            "supported": supported_count,
            "partial": max(0, partial_count),
            "unsupported": unsupported_count,
            "skipped": skipped_count,
            "unknown": 1 if source_class == "unknown" else 0,
            "estimated_world_mutations": {
                **_mutation_cost(counts, unsupported_count),
                **{
                    "node_writes": structure_cost["node_writes"],
                    "mapblock_churn": structure_cost["mapblock_churn"],
                    "manual_review_items": (
                        unsupported_count + counts["models"] + counts["world"]
                        + structure_cost["manual_review_items"]
                    ),
                },
            },
        },
        "sections": _sections(counts, unsupported_features, structure_cost),
        "unsupported_features": unsupported_features,
        "planned_actions": _planned_actions(
            counts,
            unsupported_features,
            structure_cost,
            synthetic_structure,
        ),
        "safety": {
            "no_assets_copied": True,
            "no_world_mutation": True,
            "source_paths_redacted": True,
            "user_rights_required": True,
            "notes": [
                "Dry run inventories metadata and paths only.",
                "Apply-phase work must run through reviewed import tasks.",
            ],
        },
    }


def build_structure_adapter_report(source):
    """Build a dry-run report for a public-safe synthetic structure fixture."""
    source = pathlib.Path(source)
    synthetic_structure = _load_synthetic_structure_fixture(source)
    if not synthetic_structure:
        raise ValueError("source is not a supported synthetic structure fixture")
    return _build_report(source, synthetic_structure)


def build_report(source):
    source = pathlib.Path(source)
    synthetic_structure = _load_synthetic_structure_fixture(source)
    return _build_report(source, synthetic_structure)


def _require_mapping(errors, value, path):
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")
        return False
    return True


def _require_sequence(errors, value, path):
    if not isinstance(value, list):
        errors.append(f"{path} must be an array")
        return False
    return True


def _require_keys(errors, mapping, path, keys):
    if not _require_mapping(errors, mapping, path):
        return
    for key in keys:
        if key not in mapping:
            errors.append(f"{path}.{key} is required")


def _validate_mutation_cost(errors, value, path):
    _require_keys(errors, value, path, MUTATION_COST_REQUIRED)


def _validate_structure_adapter(errors, value, path):
    required = (
        "adapter_kind",
        "fixture_name",
        "synthetic",
        "placement_count",
        "mapblock_churn",
        "recommended_chunk_size",
        "recommended_chunk_count",
        "placements",
    )
    _require_keys(errors, value, path, required)
    if not isinstance(value, dict):
        return
    if value.get("adapter_kind") != SYNTHETIC_STRUCTURE_ADAPTER_KIND:
        errors.append(f"{path}.adapter_kind must be {SYNTHETIC_STRUCTURE_ADAPTER_KIND}")
    if value.get("synthetic") is not True:
        errors.append(f"{path}.synthetic must be true")
    placements = value.get("placements")
    if _require_sequence(errors, placements, f"{path}.placements"):
        if len(placements) != value.get("placement_count"):
            errors.append(f"{path}.placement_count must match placements length")
        for index, placement in enumerate(placements):
            _require_keys(errors, placement, f"{path}.placements[{index}]", ("pos", "node_name"))
            if isinstance(placement, dict):
                _require_keys(errors, placement.get("pos"), f"{path}.placements[{index}].pos", ("x", "y", "z"))


def validate_report(report, expected_unsupported_features=None):
    """Return validation errors for the dry-run report contract."""
    errors = []
    _require_keys(errors, report, "report", TOP_LEVEL_REQUIRED)
    if errors:
        return errors

    if report.get("report_version") != REPORT_VERSION:
        errors.append(f"report.report_version must be {REPORT_VERSION}")
    if report.get("mode") != "dry_run":
        errors.append("report.mode must be dry_run")

    source = report.get("source")
    _require_keys(errors, source, "source", SOURCE_REQUIRED)
    if isinstance(source, dict):
        inventory = source.get("inventory")
        if _require_sequence(errors, inventory, "source.inventory"):
            for index, entry in enumerate(inventory):
                _require_keys(errors, entry, f"source.inventory[{index}]", INVENTORY_ENTRY_REQUIRED)

    summary = report.get("summary")
    _require_keys(errors, summary, "summary", SUMMARY_REQUIRED)
    if isinstance(summary, dict):
        _validate_mutation_cost(
            errors,
            summary.get("estimated_world_mutations"),
            "summary.estimated_world_mutations",
        )

    sections = report.get("sections")
    if _require_sequence(errors, sections, "sections"):
        if not sections:
            errors.append("sections must contain at least one section")
        for index, section in enumerate(sections):
            _require_keys(errors, section, f"sections[{index}]", SECTION_REQUIRED)

    unsupported_features = report.get("unsupported_features")
    if _require_sequence(errors, unsupported_features, "unsupported_features"):
        present_features = set()
        for index, feature in enumerate(unsupported_features):
            _require_keys(errors, feature, f"unsupported_features[{index}]", UNSUPPORTED_FEATURE_REQUIRED)
            if isinstance(feature, dict) and "feature" in feature:
                present_features.add(feature["feature"])
        for feature in sorted(expected_unsupported_features or ()):
            if feature not in present_features:
                errors.append(f"unsupported_features missing expected feature {feature}")

    planned_actions = report.get("planned_actions")
    if _require_sequence(errors, planned_actions, "planned_actions"):
        for index, action in enumerate(planned_actions):
            _require_keys(errors, action, f"planned_actions[{index}]", PLANNED_ACTION_REQUIRED)
            if isinstance(action, dict):
                _validate_mutation_cost(errors, action.get("mutation_cost"), f"planned_actions[{index}].mutation_cost")
                if "structure_adapter" in action:
                    _validate_structure_adapter(
                        errors,
                        action.get("structure_adapter"),
                        f"planned_actions[{index}].structure_adapter",
                    )

    safety = report.get("safety")
    _require_keys(errors, safety, "safety", SAFETY_REQUIRED_TRUE)
    if isinstance(safety, dict):
        for key in SAFETY_REQUIRED_TRUE:
            if key in safety and safety[key] is not True:
                errors.append(f"safety.{key} must be true")

    return errors


def _validate_number_fields(errors, mapping, path, keys):
    if not isinstance(mapping, dict):
        return
    for key in keys:
        if key in mapping and (not isinstance(mapping[key], int) or mapping[key] < 0):
            errors.append(f"{path}.{key} must be a non-negative integer")


def validate_apply_request(request):
    """Return validation errors for an apply-plan request."""
    errors = []
    _require_keys(errors, request, "request", APPLY_REQUEST_REQUIRED)
    if errors:
        return errors

    if request.get("request_version") != APPLY_REQUEST_VERSION:
        errors.append(f"request.request_version must be {APPLY_REQUEST_VERSION}")
    if request.get("mode") != "apply_plan":
        errors.append("request.mode must be apply_plan")

    _require_keys(errors, request.get("source_reference"), "source_reference", SOURCE_REFERENCE_REQUIRED)

    approved_actions = request.get("approved_actions")
    if _require_sequence(errors, approved_actions, "approved_actions"):
        if not approved_actions:
            errors.append("approved_actions must contain at least one action")
        for index, action in enumerate(approved_actions):
            _require_keys(errors, action, f"approved_actions[{index}]", APPROVED_ACTION_REQUIRED)

    _require_keys(errors, request.get("budget"), "budget", APPLY_BUDGET_REQUIRED)
    _validate_number_fields(errors, request.get("budget"), "budget", APPLY_BUDGET_REQUIRED)

    _require_keys(errors, request.get("rollback_policy"), "rollback_policy", ROLLBACK_POLICY_REQUIRED)
    rollback_policy = request.get("rollback_policy")
    if isinstance(rollback_policy, dict):
        if rollback_policy.get("metadata_required") is not True:
            errors.append("rollback_policy.metadata_required must be true")
        if rollback_policy.get("policy") not in ROLLBACK_POLICIES:
            errors.append(
                "rollback_policy.policy must be snapshot, manifest_only, chunked, or no_world_mutation"
            )

    return errors


def validate_apply_summary(summary):
    """Return validation errors for a no-mutation apply summary."""
    errors = []
    _require_keys(errors, summary, "summary", APPLY_SUMMARY_REQUIRED)
    if errors:
        return errors

    if summary.get("summary_version") != APPLY_SUMMARY_VERSION:
        errors.append(f"summary.summary_version must be {APPLY_SUMMARY_VERSION}")
    if summary.get("status") != "planned":
        errors.append("summary.status must be planned")

    for field in ("approved_actions", "queued_tasks", "running_tasks", "completed_tasks", "blocked_tasks",
            "rollback_records", "operator_next_actions"):
        _require_sequence(errors, summary.get(field), field)

    _validate_mutation_cost(errors, summary.get("mutation_cost_actual"), "mutation_cost_actual")
    _require_keys(errors, summary.get("safety"), "safety", APPLY_SUMMARY_SAFETY_REQUIRED)
    safety = summary.get("safety")
    if isinstance(safety, dict):
        if safety.get("assets_remain_operator_supplied") is not True:
            errors.append("safety.assets_remain_operator_supplied must be true")
        if safety.get("dry_run_report_unchanged") is not True:
            errors.append("safety.dry_run_report_unchanged must be true")
        if safety.get("world_mutation_executed") is not False:
            errors.append("safety.world_mutation_executed must be false")

    mutation_cost = summary.get("mutation_cost_actual")
    if isinstance(mutation_cost, dict) and mutation_cost.get("node_writes") != 0:
        errors.append("mutation_cost_actual.node_writes must be 0 for apply_plan")
    if summary.get("queued_tasks") != []:
        errors.append("queued_tasks must be empty for apply_plan")
    if summary.get("running_tasks") != []:
        errors.append("running_tasks must be empty for apply_plan")
    return errors


def _report_inventory_hash(report):
    hashes = report.get("source", {}).get("content_hashes", [])
    if not hashes:
        return None
    return hashes[0].get("value")


def _planned_action_by_index(report, index):
    actions = report.get("planned_actions", [])
    if not isinstance(index, int) or index < 0 or index >= len(actions):
        raise ValueError(f"approved action index {index} is not present in dry-run report")
    return actions[index]


def _estimated_wall_time_ms(cost):
    return (
        cost.get("node_writes", 0) * 2
        + cost.get("mapblock_churn", 0) * 25
        + cost.get("media_files", 0) * 5
        + cost.get("entity_definitions", 0) * 50
        + cost.get("manual_review_items", 0) * 100
    )


def _calibrated_action_cost(planned):
    cost = dict(planned.get("mutation_cost") or {})
    cost["estimated_wall_time_ms"] = _estimated_wall_time_ms(cost)
    return cost


def _approved_cost_totals(approved_actions):
    totals = {
        "media_files": 0,
        "entity_definitions": 0,
        "node_writes": 0,
        "mapblock_churn": 0,
        "manual_review_items": 0,
        "estimated_wall_time_ms": 0,
    }
    for _action_index, _requested, planned in approved_actions:
        cost = _calibrated_action_cost(planned)
        for key in totals:
            totals[key] += cost.get(key, 0)
    return totals


def _enforce_budget(totals, budget):
    checks = (
        ("media_files", "max_media_files"),
        ("entity_definitions", "max_entity_definitions"),
        ("node_writes", "max_node_writes_total"),
        ("mapblock_churn", "max_mapblock_churn_total"),
        ("manual_review_items", "max_manual_review_items"),
        ("estimated_wall_time_ms", "max_wall_time_ms"),
    )
    for cost_key, budget_key in checks:
        if totals[cost_key] > budget[budget_key]:
            raise ValueError(
                f"approved actions exceed budget.{budget_key}: "
                f"{totals[cost_key]} > {budget[budget_key]}"
            )
    if totals["node_writes"] > 0 and budget["max_node_writes_per_step"] <= 0:
        raise ValueError(
            "budget.max_node_writes_per_step must be positive for structure apply tasks"
        )


def _enforce_runtime_handoff_gates(report, request, approved_actions):
    budget = request["budget"]
    rollback_policy = request["rollback_policy"]["policy"]
    totals = _approved_cost_totals(approved_actions)
    _enforce_budget(totals, budget)

    for _action_index, _requested, planned in approved_actions:
        required_capabilities = planned.get("required_capabilities") or []
        if "import.assets" not in required_capabilities:
            raise ValueError("approved actions must require import.assets")
        if planned["action"] != "import_structure":
            continue

        cost = _calibrated_action_cost(planned)
        if cost["node_writes"] <= 0 and cost["mapblock_churn"] <= 0:
            continue
        if request.get("target_world", {}).get("staging") is not True:
            raise ValueError("target_world.staging must be true for import_structure prototype")
        if rollback_policy not in WORLD_MUTATING_ROLLBACK_POLICIES:
            raise ValueError(
                "rollback_policy.policy must be manifest_only, snapshot, or chunked for import_structure"
            )
        if report.get("source", {}).get("source_class") not in {"structure", "world"}:
            raise ValueError("import_structure requires a structure or world dry-run source")
        adapter = planned.get("structure_adapter")
        if adapter:
            if adapter.get("synthetic") is not True:
                raise ValueError("structure_adapter.synthetic must be true")
            if adapter.get("placement_count") != cost["node_writes"]:
                raise ValueError("structure_adapter placement_count must match node writes")


def _validated_approved_actions(report, request):
    report_errors = validate_report(report)
    if report_errors:
        raise ValueError(report_errors[0])

    request_errors = validate_apply_request(request)
    if request_errors:
        raise ValueError(request_errors[0])

    if request["report_version"] != report["report_version"]:
        raise ValueError("request.report_version does not match dry-run report")

    expected_hash = _report_inventory_hash(report)
    supplied_hash = request["source_reference"]["inventory_hash"]
    if expected_hash and supplied_hash != expected_hash:
        raise ValueError("source_reference.inventory_hash does not match dry-run report")

    approved_actions = []
    for requested in request["approved_actions"]:
        planned = _planned_action_by_index(report, requested["action_index"])
        if requested["action"] != planned["action"]:
            raise ValueError(f"approved action index {requested['action_index']} action mismatch")
        approved_actions.append((requested["action_index"], requested, planned))
    _enforce_runtime_handoff_gates(report, request, approved_actions)
    return approved_actions


def _structure_runtime_entrypoint(planned, request):
    if planned["action"] != "import_structure":
        return None
    cost = _calibrated_action_cost(planned)
    if (
        request["rollback_policy"]["policy"] == "chunked"
        or cost["node_writes"] > request["budget"]["max_node_writes_per_step"]
    ):
        return "core.ai_import_ops.define_chunked_structure_apply_task"
    return "core.ai_import_ops.define_structure_apply_task"


def _structure_staged_apply_handoff(planned, request, runtime_entrypoint):
    adapter = planned.get("structure_adapter")
    if not adapter:
        return None
    placement_count = adapter["placement_count"]
    chunk_size = min(
        adapter["recommended_chunk_size"],
        max(1, request["budget"]["max_node_writes_per_step"]),
    )
    return {
        "status": "review_required",
        "task_constructor": runtime_entrypoint,
        "rollback_plan_entrypoint": "core.ai_import_ops.plan_structure_rollback",
        "rollback_execute_entrypoint": "core.ai_import_ops.queue_chunked_structure_rollback_task",
        "placements": adapter["placements"],
        "placement_count": placement_count,
        "chunk_size": chunk_size,
        "chunk_count": math.ceil(placement_count / chunk_size),
        "target_world": {
            "world_id": request["target_world"]["world_id"],
            "staging": request["target_world"]["staging"],
        },
        "rollback_policy": request["rollback_policy"]["policy"],
        "requires_explicit_approval": True,
        "allow_mutation": False,
    }


def build_apply_task_definitions(report, request):
    """Map approved compatibility actions to inert AI task definition records."""
    task_definitions = []
    for action_index, _requested, planned in _validated_approved_actions(report, request):
        mapping = PLANNED_ACTION_TASK_MAPPINGS.get(planned["action"])
        if mapping is None:
            raise ValueError(f"planned action {planned['action']} cannot be mapped to a task definition")
        required_capabilities = sorted({
            "import.assets",
            *planned.get("required_capabilities", []),
            *mapping.get("extra_capabilities", ()),
        })
        runtime_entrypoint = _structure_runtime_entrypoint(planned, request)
        runtime_handoff = {
            "status": "staged_executor_available"
                if planned["action"] == "import_structure" else "staging_noop",
            "operation": mapping["label"],
            "mutation_enabled": False,
            "requires_capabilities": required_capabilities,
            "runtime_entrypoint": runtime_entrypoint,
            "rollback_plan_entrypoint": "core.ai_import_ops.plan_structure_rollback"
                if planned["action"] == "import_structure" else None,
            "rollback_execute_entrypoint": "core.ai_import_ops.queue_chunked_structure_rollback_task"
                if planned["action"] == "import_structure" else None,
        }
        definition = {
            "task_id": f"compat:{request['report_id']}:{action_index}",
            "agent_id": request["agent_id"],
            "owner": request["operator"],
            "label": mapping["label"],
            "status": "defined",
            "inert": True,
            "queue_state": "not_queued",
            "required_capabilities": required_capabilities,
            "mutation_class": mapping["mutation_class"],
            "requires_safe_world_ops": mapping["requires_safe_world_ops"],
            "budget": {
                "max_steps_per_step": 1,
                "max_media_files": request["budget"]["max_media_files"],
                "max_entity_definitions": request["budget"]["max_entity_definitions"],
                "max_node_writes_total": request["budget"]["max_node_writes_total"],
                "max_node_writes_per_step": request["budget"]["max_node_writes_per_step"],
                "max_mapblock_churn_total": request["budget"]["max_mapblock_churn_total"],
                "max_manual_review_items": request["budget"]["max_manual_review_items"],
                "max_wall_time_ms": request["budget"]["max_wall_time_ms"],
            },
            "rollback": {
                "required": True,
                "policy": request["rollback_policy"]["policy"],
                "metadata_required": request["rollback_policy"]["metadata_required"],
                "world_mutating": mapping["requires_safe_world_ops"],
            },
            "runtime_handoff": {
                **runtime_handoff,
            },
            "calibrated_cost": _calibrated_action_cost(planned),
            "provenance": {
                "report_id": request["report_id"],
                "report_version": report["report_version"],
                "source_class": report["source"]["source_class"],
                "source_reference": {
                    "reference_type": request["source_reference"]["reference_type"],
                    "redacted_id": request["source_reference"]["redacted_id"],
                    "inventory_hash": request["source_reference"]["inventory_hash"],
                },
                "action_index": action_index,
                "dry_run_action": planned["action"],
            },
            "source_action": {
                "action_index": action_index,
                "action": planned["action"],
                "status": planned["status"],
                "description": planned["description"],
                "mutation_cost": planned["mutation_cost"],
            },
        }
        staged_apply = _structure_staged_apply_handoff(
            planned,
            request,
            runtime_entrypoint,
        )
        if staged_apply:
            definition["staged_apply"] = staged_apply
        task_definitions.append(definition)
    return task_definitions


def build_apply_plan(report, request):
    """Build a no-mutation apply summary from a dry-run report and approval request."""
    approved_actions = []
    for action_index, requested, _planned in _validated_approved_actions(report, request):
        approved_actions.append({
            "action_index": action_index,
            "action": requested["action"],
        })

    summary = {
        "summary_version": APPLY_SUMMARY_VERSION,
        "apply_id": "apply-plan:" + request["report_id"],
        "report_id": request["report_id"],
        "status": "planned",
        "approved_actions": approved_actions,
        "queued_tasks": [],
        "running_tasks": [],
        "completed_tasks": [],
        "blocked_tasks": [],
        "mutation_cost_actual": {
            "node_writes": 0,
            "mapblock_churn": 0,
            "media_files": 0,
            "entity_definitions": 0,
            "manual_review_items": 0,
        },
        "rollback_records": [{
            "record_id": "apply-plan:" + request["report_id"] + ":no-world-mutation",
            "policy": request["rollback_policy"]["policy"],
            "world_mutating": False,
        }],
        "audit_record_count": 0,
        "operator_next_actions": [
            "Review generated task definitions before enabling apply mode.",
        ],
        "safety": {
            "assets_remain_operator_supplied": True,
            "dry_run_report_unchanged": True,
            "world_mutation_executed": False,
        },
    }

    summary_errors = validate_apply_summary(summary)
    if summary_errors:
        raise ValueError(summary_errors[0])
    return summary


def _print_summary(report):
    summary = report["summary"]
    print(
        "source={source} class={source_class} risk={risk} "
        "items={items} unsupported={unsupported} partial={partial}".format(
            source=report["source"]["source_id"],
            source_class=report["source"]["source_class"],
            risk=summary["risk_level"],
            items=summary["items_total"],
            unsupported=summary["unsupported"],
            partial=summary["partial"],
        )
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", help="User-owned pack, structure, or world source to inspect.")
    parser.add_argument("--apply-plan", help="Dry-run report JSON to plan for apply without mutation.")
    parser.add_argument("--approval", help="Apply request JSON containing explicit operator approvals.")
    parser.add_argument("--output", help="Write machine-readable JSON report to this path.")
    parser.add_argument("--summary", action="store_true", help="Print a concise human-readable summary.")
    args = parser.parse_args(argv)

    try:
        if args.apply_plan:
            if not args.approval:
                raise ValueError("--approval is required with --apply-plan")
            report = _read_json(pathlib.Path(args.apply_plan))
            request = _read_json(pathlib.Path(args.approval))
            payload_obj = build_apply_plan(report, request)
        else:
            if not args.source:
                raise ValueError("source is required unless --apply-plan is used")
            payload_obj = build_report(args.source)
        payload = json.dumps(payload_obj, indent=2, sort_keys=True) + "\n"
        if args.output:
            pathlib.Path(args.output).write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        if args.summary and not args.apply_plan:
            _print_summary(payload_obj)
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
