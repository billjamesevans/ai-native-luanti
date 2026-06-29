#!/usr/bin/env python3
"""Dry-run compatibility reporter and no-mutation apply planner."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import pathlib
import re
import sys
import zipfile


REPORT_VERSION = 1
BATCH_INVENTORY_QUEUE_VERSION = 1
IMPORT_INVENTORY_DISCOVERY_REPORT_VERSION = 1
APPLY_REQUEST_VERSION = 1
APPLY_SUMMARY_VERSION = 1
ADAPTER_APPLY_SMOKE_VERSION = 1
ADAPTER_APPLY_SMOKE_REVIEW_VERSION = 1
STRUCTURE_IMPORT_PROMOTION_PACKAGE_VERSION = 1
ASSET_REFERENCE_PROMOTION_PACKAGE_VERSION = 1
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
    "dry_run_classification_counts",
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
PUBLIC_SAFE_STRUCTURE_FIXTURE_KIND = "ai_native_public_structure"
PUBLIC_SAFE_STRUCTURE_FORMAT = "ai_native_structure_v1"
PUBLIC_SAFE_STRUCTURE_ADAPTER_KIND = "public_safe_structure_v1"
PUBLIC_SAFE_SCHEMATIC_PREFLIGHT_KIND = "ai_native_public_schematic_preflight"
PUBLIC_SAFE_SCHEMATIC_PREFLIGHT_FORMAT = "ai_native_schematic_preflight_v1"
PUBLIC_SAFE_SCHEMATIC_PREFLIGHT_ADAPTER_KIND = "public_safe_schematic_preflight_v1"
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
ADAPTER_APPLY_SMOKE_REQUIRED = (
    "smoke_version",
    "mode",
    "generated_at",
    "report_id",
    "status",
    "target_world",
    "approved_actions",
    "apply_tasks",
    "rollback_plan",
    "rollback_tasks",
    "mutation_cost_expected",
    "operator_summary",
    "operator_next_actions",
    "safety",
)
ADAPTER_APPLY_SMOKE_SAFETY_REQUIRED = (
    "synthetic_only",
    "disposable_staging_only",
    "dry_run_report_unchanged",
    "assets_remain_operator_supplied",
    "no_live_family_world_mutation",
    "world_mutation_executed",
)
ADAPTER_APPLY_FORBIDDEN_WORLD_IDS = {
    "family",
    "family_voxelibre",
    "luanti-family",
    "live-family",
    "production",
}
ADAPTER_APPLY_REVIEW_REQUIRED_APPLY_HOOKS = (
    "get_node",
    "set_node",
    "persist_record",
)
ADAPTER_APPLY_REVIEW_REQUIRED_ROLLBACK_HOOKS = (
    "get_node",
    "set_node",
    "persist_record",
    "inspect_record",
)
PROMOTION_PACKAGE_REQUIRED_CAPABILITIES = (
    "import.assets",
    "world.place",
    "world.batch",
    "rollback.execute",
    "admin.override",
)
ASSET_REFERENCE_SOURCE_CLASSES = (
    "java_resource_pack",
    "bedrock_resource_pack",
)
ASSET_REFERENCE_ACTIONS = (
    "copy_asset_reference",
    "map_texture",
    "map_sound",
)
ASSET_REFERENCE_FORBIDDEN_KEYS = (
    "asset_payload",
    "raw_asset_payload",
    "payload_bytes",
    "asset_bytes",
    "raw_bytes",
    "source_payload",
    "private_payload",
    "texture_bytes",
    "sound_bytes",
    "model_bytes",
    "media_payload",
    "copied_protected_content",
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
DISCOVERY_CLASSIFICATIONS = ("supported", "partial", "unsupported", "skipped", "blocked")
DRY_RUN_CLASSIFICATIONS = ("mapped", "skipped", "blocked", "unsupported")
DISCOVERY_ACCEPTED_SOURCE_CLASSES = (
    "java_resource_pack",
    "bedrock_resource_pack",
    "bedrock_behavior_pack",
    "luanti_mod",
    "schematic",
    "structure",
    "world",
)
PRIVATE_DISCOVERY_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"/Users/|/opt/|asset_payload|raw_asset_payload|copied_protected_content|"
    r"family_voxelibre",
    re.I,
)
DISCOVERY_READY_BLOCKERS = (
    "private_source_reference_rejected",
    "source_classification_failed",
    "empty_inventory_root",
)


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


def _normalize_structure_dimensions(value, field):
    dimensions = _normalize_structure_pos(value, field)
    for axis, size in dimensions.items():
        if size <= 0:
            raise ValueError(f"{field}.{axis} must be positive")
    return dimensions


def _normalize_structure_palette(raw):
    palette = raw.get("palette", {})
    if not isinstance(palette, dict):
        raise ValueError("palette must be an object")
    return {
        str(alias): str(node_name)
        for alias, node_name in palette.items()
    }


def _pos_inside_dimensions(pos, dimensions):
    if not dimensions:
        return True
    return (
        0 <= pos["x"] < dimensions["x"]
        and 0 <= pos["y"] < dimensions["y"]
        and 0 <= pos["z"] < dimensions["z"]
    )


def _normalize_structure_placements(raw, normalized_palette, dimensions=None):
    placements = raw.get("placements")
    if not isinstance(placements, list) or not placements:
        raise ValueError("placements must be a non-empty array")

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
        pos = _normalize_structure_pos(placement.get("pos"), f"placements[{index}].pos")
        if not _pos_inside_dimensions(pos, dimensions):
            raise ValueError(f"placements[{index}].pos must be inside dimensions")
        normalized = {
            "pos": pos,
            "node_name": node_name,
        }
        if "param1" in placement:
            normalized["param1"] = _check_int(placement["param1"], f"placements[{index}].param1")
        if "param2" in placement:
            normalized["param2"] = _check_int(placement["param2"], f"placements[{index}].param2")
        normalized_placements.append(normalized)
    return normalized_placements


def _normalize_structure_unsupported_fields(raw):
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
    return normalized_unsupported


def _normalize_recommended_chunk_size(raw):
    chunk_size = raw.get("recommended_chunk_size", 2)
    chunk_size = _check_int(chunk_size, "recommended_chunk_size")
    if chunk_size <= 0:
        raise ValueError("recommended_chunk_size must be positive")
    return chunk_size


def _require_user_supplied_license(raw):
    license_info = raw.get("license")
    if not isinstance(license_info, dict):
        raise ValueError("license must be an object")
    if license_info.get("status") != "user_supplied":
        raise ValueError("license.status must be user_supplied")
    if license_info.get("rights_confirmed") is not True:
        raise ValueError("license.rights_confirmed must be true")
    return license_info


def _reject_public_safe_payload_fields(raw, adapter_label):
    forbidden_fields = (
        "asset_payload",
        "raw_schematic_payload",
        "nbt_payload",
        "copied_protected_content",
        "family_world_coordinates",
    )
    for field in forbidden_fields:
        if field in raw:
            raise ValueError(f"{field} is not supported by the {adapter_label}")
    private_path_fields = ("source_path", "local_path", "absolute_path", "path")
    for field in private_path_fields:
        if field in raw:
            raise ValueError("private source paths are not supported by public-safe adapters")


def _normalize_synthetic_structure_fixture(raw, source):
    if raw.get("fixture_kind") != SYNTHETIC_STRUCTURE_FIXTURE_KIND:
        return None
    if raw.get("fixture_version") != 1:
        raise ValueError("fixture_version must be 1")
    normalized_palette = _normalize_structure_palette(raw)
    normalized_placements = _normalize_structure_placements(raw, normalized_palette)
    normalized_unsupported = _normalize_structure_unsupported_fields(raw)
    chunk_size = _normalize_recommended_chunk_size(raw)

    return {
        "adapter_kind": SYNTHETIC_STRUCTURE_ADAPTER_KIND,
        "fixture_name": str(raw.get("name") or source.stem),
        "fixture_version": 1,
        "synthetic": True,
        "public_safe": False,
        "path_policy": "synthetic_fixture",
        "license_status": "synthetic",
        "palette": normalized_palette,
        "placements": normalized_placements,
        "recommended_chunk_size": chunk_size,
        "unsupported_fields": normalized_unsupported,
        "private_references": [],
    }


def _normalize_public_safe_structure_fixture(raw, source):
    if raw.get("format_kind") != PUBLIC_SAFE_STRUCTURE_FIXTURE_KIND:
        return None
    if raw.get("format_version") != 1:
        raise ValueError("format_version must be 1")
    if raw.get("structure_format") != PUBLIC_SAFE_STRUCTURE_FORMAT:
        raise ValueError(f"structure_format must be {PUBLIC_SAFE_STRUCTURE_FORMAT}")
    _require_user_supplied_license(raw)
    _reject_public_safe_payload_fields(raw, "public-safe structure adapter")

    dimensions = _normalize_structure_dimensions(raw.get("dimensions"), "dimensions")
    normalized_palette = _normalize_structure_palette(raw)
    normalized_placements = _normalize_structure_placements(
        raw,
        normalized_palette,
        dimensions=dimensions,
    )
    normalized_unsupported = _normalize_structure_unsupported_fields(raw)
    chunk_size = _normalize_recommended_chunk_size(raw)

    private_references = raw.get("private_references", [])
    if not isinstance(private_references, list):
        raise ValueError("private_references must be an array")
    normalized_private_refs = []
    for index, item in enumerate(private_references):
        if not isinstance(item, dict):
            raise ValueError(f"private_references[{index}] must be an object")
        if "path" in item or "payload" in item:
            raise ValueError("private_references must use redacted ids, not raw paths or payloads")
        ref_id = item.get("id")
        if not isinstance(ref_id, str) or not ref_id:
            raise ValueError(f"private_references[{index}].id must be a non-empty string")
        normalized_private_refs.append({
            "id": ref_id,
            "kind": str(item.get("kind") or "unknown"),
            "redacted_id": str(item.get("redacted_id") or f"asset-ref:{index + 1}"),
        })

    return {
        "adapter_kind": PUBLIC_SAFE_STRUCTURE_ADAPTER_KIND,
        "fixture_name": str(raw.get("name") or source.stem),
        "fixture_version": 1,
        "synthetic": False,
        "public_safe": True,
        "path_policy": "external_reference",
        "license_status": "user_supplied",
        "structure_format": PUBLIC_SAFE_STRUCTURE_FORMAT,
        "dimensions": dimensions,
        "palette": normalized_palette,
        "placements": normalized_placements,
        "recommended_chunk_size": chunk_size,
        "unsupported_fields": normalized_unsupported,
        "private_references": normalized_private_refs,
    }


def _normalize_public_safe_schematic_preflight(raw, source):
    if raw.get("format_kind") != PUBLIC_SAFE_SCHEMATIC_PREFLIGHT_KIND:
        return None
    if raw.get("format_version") != 1:
        raise ValueError("format_version must be 1")
    if raw.get("schematic_format") != PUBLIC_SAFE_SCHEMATIC_PREFLIGHT_FORMAT:
        raise ValueError(f"schematic_format must be {PUBLIC_SAFE_SCHEMATIC_PREFLIGHT_FORMAT}")
    _require_user_supplied_license(raw)
    _reject_public_safe_payload_fields(raw, "public-safe schematic preflight adapter")

    preflight = raw.get("preflight")
    if not isinstance(preflight, dict):
        raise ValueError("preflight must be an object")
    if preflight.get("payload_policy") != "metadata_only":
        raise ValueError("preflight.payload_policy must be metadata_only")
    if preflight.get("source_format") != "schematic":
        raise ValueError("preflight.source_format must be schematic")
    if "source_path" in preflight or "local_path" in preflight or "path" in preflight:
        raise ValueError("private source paths are not supported by public-safe adapters")

    dimensions = _normalize_structure_dimensions(raw.get("dimensions"), "dimensions")
    normalized_palette = _normalize_structure_palette(raw)
    placement_field = "placements" if raw.get("placements") is not None else "estimated_placements"
    if placement_field not in raw:
        raise ValueError("placements or estimated_placements must be a non-empty array")
    placement_source = dict(raw)
    placement_source["placements"] = raw[placement_field]
    normalized_placements = _normalize_structure_placements(
        placement_source,
        normalized_palette,
        dimensions=dimensions,
    )
    normalized_unsupported = _normalize_structure_unsupported_fields(raw)
    chunk_size = _normalize_recommended_chunk_size(raw)

    return {
        "adapter_kind": PUBLIC_SAFE_STRUCTURE_ADAPTER_KIND,
        "source_adapter_kind": PUBLIC_SAFE_SCHEMATIC_PREFLIGHT_ADAPTER_KIND,
        "fixture_name": str(raw.get("name") or source.stem),
        "fixture_version": 1,
        "synthetic": False,
        "public_safe": True,
        "path_policy": "external_reference",
        "license_status": "user_supplied",
        "structure_format": PUBLIC_SAFE_SCHEMATIC_PREFLIGHT_FORMAT,
        "source_format": "schematic",
        "payload_policy": "metadata_only",
        "estimated_from_preflight": placement_field == "estimated_placements",
        "dimensions": dimensions,
        "palette": normalized_palette,
        "placements": normalized_placements,
        "recommended_chunk_size": chunk_size,
        "unsupported_fields": normalized_unsupported,
        "private_references": [],
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


def _load_structure_adapter_fixture(source):
    if not source.is_file() or source.suffix.lower() != ".json":
        return None
    try:
        raw = _read_json(source)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    synthetic = _normalize_synthetic_structure_fixture(raw, source)
    if synthetic:
        return synthetic
    public_structure = _normalize_public_safe_structure_fixture(raw, source)
    if public_structure:
        return public_structure
    return _normalize_public_safe_schematic_preflight(raw, source)


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
        metadata = {
            "adapter_kind": synthetic_structure["adapter_kind"],
            "fixture_name": synthetic_structure["fixture_name"],
            "fixture_version": synthetic_structure["fixture_version"],
            "placement_count": len(synthetic_structure["placements"]),
            "palette_count": len(synthetic_structure["palette"]),
            "unsupported_field_count": len(synthetic_structure["unsupported_fields"]),
        }
        if synthetic_structure.get("structure_format"):
            metadata["structure_format"] = synthetic_structure["structure_format"]
        if synthetic_structure.get("source_adapter_kind"):
            metadata["source_adapter_kind"] = synthetic_structure["source_adapter_kind"]
        if synthetic_structure.get("source_format"):
            metadata["source_format"] = synthetic_structure["source_format"]
        if synthetic_structure.get("payload_policy"):
            metadata["payload_policy"] = synthetic_structure["payload_policy"]
        if synthetic_structure.get("estimated_from_preflight") is not None:
            metadata["estimated_from_preflight"] = (
                synthetic_structure["estimated_from_preflight"] is True
            )
        if synthetic_structure.get("dimensions"):
            metadata["dimensions"] = synthetic_structure["dimensions"]
        if synthetic_structure.get("private_references"):
            metadata["private_reference_count"] = len(synthetic_structure["private_references"])
        source_class = "schematic" if (
            synthetic_structure.get("source_adapter_kind")
            == PUBLIC_SAFE_SCHEMATIC_PREFLIGHT_ADAPTER_KIND
        ) else "structure"
        return source_class, metadata

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
            if synthetic_structure.get("synthetic"):
                reason = "synthetic_structure_adapter_review_required"
            elif (
                synthetic_structure.get("source_adapter_kind")
                == PUBLIC_SAFE_SCHEMATIC_PREFLIGHT_ADAPTER_KIND
            ):
                reason = "public_safe_schematic_preflight_review_required"
            else:
                reason = "public_safe_structure_adapter_review_required"
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
        for item in synthetic_structure.get("private_references", []):
            features.append({
                "feature": "structure.private_reference",
                "source_path": item["redacted_id"],
                "status": "unsupported",
                "reason": "private_reference_not_imported",
                "severity": "warning",
                "message": "Private or local-only structure asset references are reported but not imported.",
                "recommendation": "Replace private references with reviewed user-owned assets before apply.",
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
        strategy = (
            "synthetic_structure_adapter"
            if synthetic_structure.get("synthetic")
            else (
                "public_safe_schematic_preflight"
                if synthetic_structure.get("source_adapter_kind")
                == PUBLIC_SAFE_SCHEMATIC_PREFLIGHT_ADAPTER_KIND
                else "public_safe_structure_adapter"
            )
        )
        return {
            "structure_files": 1,
            "node_writes": node_writes,
            "mapblock_churn": mapblock_churn,
            "manual_review_items": 2,
            "calibration": {
                "strategy": strategy,
                "adapter_kind": synthetic_structure["adapter_kind"],
                "recommended_chunk_size": synthetic_structure["recommended_chunk_size"],
                "notes": [
                    "Structure placements are parsed as metadata for review.",
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
    payload = {
        "adapter_kind": synthetic_structure["adapter_kind"],
        "fixture_name": synthetic_structure["fixture_name"],
        "synthetic": synthetic_structure["synthetic"],
        "public_safe": synthetic_structure.get("public_safe") is True,
        "placement_count": placement_count,
        "mapblock_churn": structure_cost["mapblock_churn"],
        "recommended_chunk_size": chunk_size,
        "recommended_chunk_count": math.ceil(placement_count / chunk_size),
        "placements": synthetic_structure["placements"],
        "unsupported_field_count": len(synthetic_structure["unsupported_fields"]),
        "private_reference_count": len(synthetic_structure.get("private_references", [])),
    }
    if synthetic_structure.get("structure_format"):
        payload["structure_format"] = synthetic_structure["structure_format"]
    if synthetic_structure.get("source_adapter_kind"):
        payload["source_adapter_kind"] = synthetic_structure["source_adapter_kind"]
    if synthetic_structure.get("source_format"):
        payload["source_format"] = synthetic_structure["source_format"]
    if synthetic_structure.get("payload_policy"):
        payload["payload_policy"] = synthetic_structure["payload_policy"]
    if synthetic_structure.get("estimated_from_preflight") is not None:
        payload["estimated_from_preflight"] = (
            synthetic_structure["estimated_from_preflight"] is True
        )
    if synthetic_structure.get("dimensions"):
        payload["dimensions"] = synthetic_structure["dimensions"]
    return payload


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


def _zero_dry_run_classification_counts():
    return {classification: 0 for classification in DRY_RUN_CLASSIFICATIONS}


def _dry_run_classification_counts(inventory, planned_actions):
    counts = _zero_dry_run_classification_counts()
    for entry in inventory:
        classification = entry.get("classification")
        if classification == "mapped":
            counts["mapped"] += 1
        elif classification == "skipped":
            counts["skipped"] += 1
        elif classification == "blocked":
            counts["blocked"] += 1
        else:
            counts["unsupported"] += 1
    for action in planned_actions:
        status = action.get("status")
        if action.get("action") == "skip_feature" or status == "skipped":
            counts["skipped"] += 1
        elif status == "blocked":
            counts["blocked"] += 1
        elif status in {"unsupported", "unknown"}:
            counts["unsupported"] += 1
        else:
            counts["mapped"] += 1
    return counts


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
    if source_class in {"world", "structure", "schematic"} or counts["structures"] or counts["world"]:
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
    planned_actions = _planned_actions(
        counts,
        unsupported_features,
        structure_cost,
        synthetic_structure,
    )

    return {
        "report_version": REPORT_VERSION,
        "mode": "dry_run",
        "generated_at": _utc_now(),
        "source": {
            "source_id": source.name,
            "source_class": source_class,
            "path_policy": synthetic_structure.get("path_policy", "external_reference")
                if synthetic_structure else "external_reference",
            "license_status": synthetic_structure.get("license_status", "user_supplied")
                if synthetic_structure else "user_supplied",
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
            "dry_run_classification_counts": _dry_run_classification_counts(
                inventory,
                planned_actions,
            ),
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
        "planned_actions": planned_actions,
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
    """Build a dry-run report for a public-safe structure adapter fixture."""
    source = pathlib.Path(source)
    synthetic_structure = _load_structure_adapter_fixture(source)
    if not synthetic_structure:
        raise ValueError("source is not a supported structure adapter fixture")
    return _build_report(source, synthetic_structure)


def build_report(source):
    source = pathlib.Path(source)
    synthetic_structure = _load_structure_adapter_fixture(source)
    return _build_report(source, synthetic_structure)


def _safe_report_filename(index, source_id):
    safe = "".join(
        ch.lower() if ch.isalnum() or ch in {"-", "_", "."} else "_"
        for ch in str(source_id)
    ).strip("._-")
    return f"{index:03d}-{safe or 'source'}.json"


def _batch_source_candidates(root):
    root = pathlib.Path(root)
    if not root.is_dir():
        raise ValueError("batch inventory root must be a directory")
    return sorted(
        path for path in root.iterdir()
        if not path.name.startswith(".") and (path.is_file() or path.is_dir())
    )


def _batch_source_status(report):
    if report["source"]["source_class"] == "unknown":
        return "blocked"
    if any(item.get("severity") == "error" for item in report["unsupported_features"]):
        return "blocked"
    if any(
            entry["classification"] == "blocked"
            for entry in report["source"]["inventory"]):
        return "manual_review"
    if report["summary"]["estimated_world_mutations"]["manual_review_items"] > 0:
        return "manual_review"
    if report["source"]["inventory"] and all(
            entry["classification"] == "mapped"
            for entry in report["source"]["inventory"]):
        return "mappable"
    if all(action["action"] == "skip_feature" for action in report["planned_actions"]):
        return "skippable"
    return "mappable"


def _batch_required_capabilities(report):
    capabilities = set()
    for entry in report["source"]["inventory"]:
        capabilities.update(entry.get("required_capabilities", []))
    for action in report["planned_actions"]:
        capabilities.update(action.get("required_capabilities", []))
    return sorted(capabilities)


def _batch_queue_row(index, report, report_path):
    estimated = report["summary"]["estimated_world_mutations"]
    blocked_items = sum(
        1 for entry in report["source"]["inventory"]
        if entry["classification"] in {"blocked", "unsupported", "unknown"}
    )
    return {
        "queue_id": f"source:{index}",
        "source_id": report["source"]["source_id"],
        "source_class": report["source"]["source_class"],
        "license_status": report["source"]["license_status"],
        "path_policy": report["source"]["path_policy"],
        "status": _batch_source_status(report),
        "risk_level": report["summary"]["risk_level"],
        "inventory_count": len(report["source"]["inventory"]),
        "blocked_items": blocked_items,
        "unsupported_feature_count": len(report["unsupported_features"]),
        "planned_actions_count": len(report["planned_actions"]),
        "manual_review_items": estimated["manual_review_items"],
        "estimated_world_mutations": estimated,
        "content_hash": report["source"].get("content_hashes", [{}])[0].get("value"),
        "required_capabilities": _batch_required_capabilities(report),
        "report_path": report_path,
    }


def _blocked_batch_queue_row(index, source, reason):
    return {
        "queue_id": f"source:{index}",
        "source_id": pathlib.Path(source).name,
        "source_class": "unknown",
        "license_status": "blocked",
        "path_policy": "redacted",
        "status": "blocked",
        "risk_level": "high",
        "inventory_count": 0,
        "blocked_items": 1,
        "unsupported_feature_count": 1,
        "planned_actions_count": 0,
        "manual_review_items": 1,
        "estimated_world_mutations": {
            "node_writes": 0,
            "mapblock_churn": 0,
            "media_files": 0,
            "entity_definitions": 0,
            "manual_review_items": 1,
        },
        "content_hash": None,
        "required_capabilities": ["import.assets"],
        "report_path": None,
        "blocked_reason": reason,
    }


def _batch_summary(rows):
    by_source_class = {}
    by_status = {}
    for row in rows:
        by_source_class[row["source_class"]] = by_source_class.get(row["source_class"], 0) + 1
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
    return {
        "sources_total": len(rows),
        "by_source_class": by_source_class,
        "by_status": by_status,
        "inventory_items_total": sum(row["inventory_count"] for row in rows),
        "blocked_items_total": sum(row["blocked_items"] for row in rows),
        "unsupported_features_total": sum(row["unsupported_feature_count"] for row in rows),
        "planned_actions_total": sum(row["planned_actions_count"] for row in rows),
        "manual_review_items_total": sum(row["manual_review_items"] for row in rows),
    }


def build_batch_inventory_queue(root, reports_dir=None):
    """Build a public-safe batch inventory queue from immediate source children."""
    reports_root = pathlib.Path(reports_dir) if reports_dir else None
    if reports_root:
        reports_root.mkdir(parents=True, exist_ok=True)

    rows = []
    for index, source in enumerate(_batch_source_candidates(root), start=1):
        try:
            report = build_report(source)
            report_path = None
            if reports_root:
                report_path = _safe_report_filename(index, report["source"]["source_id"])
                (reports_root / report_path).write_text(
                    json.dumps(report, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            rows.append(_batch_queue_row(index, report, report_path))
        except (OSError, ValueError, json.JSONDecodeError):
            rows.append(_blocked_batch_queue_row(index, source, "source_classification_failed"))

    return {
        "queue_version": BATCH_INVENTORY_QUEUE_VERSION,
        "mode": "batch_inventory",
        "generated_at": _utc_now(),
        "root": {
            "path_policy": "redacted",
            "source_count": len(rows),
        },
        "summary": _batch_summary(rows),
        "sources": rows,
        "safety": {
            "dry_run_only": True,
            "no_assets_copied": True,
            "no_world_mutation": True,
            "source_paths_redacted": True,
            "no_raw_payloads": True,
            "no_private_paths": True,
        },
    }


def _zero_discovery_counts():
    return {name: 0 for name in DISCOVERY_CLASSIFICATIONS}


def _inventory_discovery_classification(entry):
    classification = entry.get("classification")
    if classification == "mapped":
        return "supported"
    if classification == "blocked":
        return "blocked"
    if classification in {"unsupported", "unknown"}:
        return "unsupported"
    return "partial"


def _source_discovery_status(report):
    source_class = report["source"]["source_class"]
    if source_class == "unknown":
        return "blocked"
    if source_class == "world":
        return "blocked"
    if any(item.get("severity") == "error" for item in report["unsupported_features"]):
        return "blocked"

    inventory_counts = _zero_discovery_counts()
    for entry in report["source"]["inventory"]:
        inventory_counts[_inventory_discovery_classification(entry)] += 1
    if inventory_counts["blocked"] or inventory_counts["unsupported"]:
        return "partial"
    if report["summary"]["estimated_world_mutations"]["manual_review_items"] > 0:
        return "partial"
    if any(section.get("status") == "partial" for section in report["sections"]):
        return "partial"
    if report["source"]["inventory"]:
        return "supported"
    if all(action["action"] == "skip_feature" for action in report["planned_actions"]):
        return "skipped"
    return "unsupported"


def _planned_action_discovery_summary(action):
    mapping = PLANNED_ACTION_TASK_MAPPINGS.get(action.get("action"), {})
    return {
        "action": action.get("action"),
        "status": action.get("status"),
        "mutation_class": mapping.get("mutation_class", "unknown"),
        "requires_safe_world_ops": mapping.get("requires_safe_world_ops", False),
        "required_capabilities": list(action.get("required_capabilities") or []),
    }


def _source_classification_counts(report):
    counts = _zero_discovery_counts()
    for entry in report["source"]["inventory"]:
        counts[_inventory_discovery_classification(entry)] += 1
    return counts


def _source_section_counts(report):
    counts = _zero_discovery_counts()
    for section in report["sections"]:
        status = section.get("status")
        if status in counts:
            counts[status] += 1
    return counts


def _source_action_names(source_row):
    return {action.get("action") for action in source_row.get("planned_actions") or []}


def _promotion_queue_row(index, source_row):
    source_class = source_row.get("source_class")
    action_names = _source_action_names(source_row)
    base = {
        "promotion_id": f"promotion:{index}",
        "source_id": source_row.get("source_id"),
        "source_class": source_class,
        "source_status": source_row.get("status"),
        "report_path": source_row.get("report_path"),
        "required_capabilities": list(source_row.get("required_capabilities") or []),
        "estimated_world_mutations": dict(source_row.get("estimated_world_mutations") or {}),
        "safety": {
            "dry_run_only": True,
            "no_assets_copied": True,
            "no_raw_payloads": True,
            "no_live_server_mutation": True,
            "promotion_package_executes_world_mutation": False,
        },
    }

    if source_class in ASSET_REFERENCE_SOURCE_CLASSES and action_names.intersection(ASSET_REFERENCE_ACTIONS):
        base.update({
            "promotion_kind": "asset_reference_promotion_package",
            "status": "ready_for_no_mutation_package",
            "package_builder": "build_asset_reference_promotion_package",
            "cli_mode": "--asset-promotion-package",
            "required_artifacts": ["dry_run_report", "operator_no_world_mutation_approval"],
            "requires_operator_approval": True,
            "requires_rollback_metadata": False,
            "staged_apply_can_mutate_disposable_world": False,
            "next_action": "Package reviewed asset references without copying asset bytes or mutating a world.",
        })
    elif source_class in {"structure", "schematic"} and "import_structure" in action_names:
        base.update({
            "promotion_kind": "structure_import_promotion_package",
            "status": "requires_disposable_staging_review",
            "package_builder": "build_structure_import_promotion_package",
            "cli_mode": "--promotion-package",
            "required_artifacts": [
                "dry_run_report",
                "operator_approval",
                "adapter_apply_smoke",
                "adapter_smoke_review",
            ],
            "requires_operator_approval": True,
            "requires_rollback_metadata": True,
            "staged_apply_can_mutate_disposable_world": True,
            "next_action": "Run adapter smoke and review before building a disposable-staging promotion package.",
        })
    elif source_class == "luanti_mod":
        base.update({
            "promotion_kind": "luanti_mod_metadata_review",
            "status": "metadata_ready",
            "package_builder": None,
            "cli_mode": None,
            "required_artifacts": ["dry_run_report"],
            "requires_operator_approval": False,
            "requires_rollback_metadata": False,
            "staged_apply_can_mutate_disposable_world": False,
            "next_action": "Review mapped Luanti mod metadata before defining any runtime registration task.",
        })
    elif source_class == "world":
        base.update({
            "promotion_kind": "world_metadata_deferral",
            "status": "deferred_until_conversion_design",
            "package_builder": None,
            "cli_mode": None,
            "required_artifacts": ["dry_run_report", "future_world_conversion_design"],
            "requires_operator_approval": True,
            "requires_rollback_metadata": False,
            "staged_apply_can_mutate_disposable_world": False,
            "next_action": "Keep world imports metadata-only until a separate safe conversion path is reviewed.",
        })
    else:
        base.update({
            "promotion_kind": "blocked_source",
            "status": "blocked",
            "package_builder": None,
            "cli_mode": None,
            "required_artifacts": ["safe_source_reclassification"],
            "requires_operator_approval": True,
            "requires_rollback_metadata": False,
            "staged_apply_can_mutate_disposable_world": False,
            "next_action": "Resolve source classification or privacy blockers before promotion.",
        })

    return base


def _promotion_queue(rows):
    return [
        _promotion_queue_row(index, row)
        for index, row in enumerate(rows, start=1)
    ]


def _promotion_queue_summary(queue):
    by_kind = {}
    by_status = {}
    for row in queue:
        by_kind[row["promotion_kind"]] = by_kind.get(row["promotion_kind"], 0) + 1
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
    return {
        "promotion_sources_total": len(queue),
        "by_promotion_kind": by_kind,
        "by_status": by_status,
        "ready_package_count": sum(1 for row in queue if row.get("package_builder")),
        "disposable_staging_candidate_count": sum(
            1 for row in queue if row.get("staged_apply_can_mutate_disposable_world")
        ),
        "metadata_only_or_deferred_count": sum(
            1 for row in queue
            if not row.get("staged_apply_can_mutate_disposable_world")
        ),
    }


def _promotion_plan_lane(row):
    promotion_kind = row.get("promotion_kind")
    if promotion_kind == "luanti_mod_metadata_review":
        return "metadata_review"
    if promotion_kind == "asset_reference_promotion_package":
        return "asset_reference_review"
    if promotion_kind == "structure_import_promotion_package":
        return "disposable_structure_staging"
    if promotion_kind == "world_metadata_deferral":
        return "world_conversion_design"
    return "source_reclassification"


def _promotion_plan_priority(row):
    status_order = {
        "metadata_ready": 0,
        "ready_for_no_mutation_package": 1,
        "requires_disposable_staging_review": 2,
        "deferred_until_conversion_design": 3,
        "blocked": 4,
    }
    mutation_order = 1 if row.get("staged_apply_can_mutate_disposable_world") else 0
    return (
        status_order.get(row.get("status"), 5),
        mutation_order,
        str(row.get("source_class") or ""),
        str(row.get("source_id") or ""),
    )


def _promotion_plan_risk_label(row):
    if row.get("promotion_kind") == "world_metadata_deferral":
        return "deferred_world_conversion"
    if row.get("status") == "blocked":
        return "blocked_source"
    if row.get("staged_apply_can_mutate_disposable_world"):
        return "disposable_staging_with_rollback"
    if row.get("requires_operator_approval"):
        return "no_world_mutation_operator_review"
    return "metadata_only_review"


def _ranked_promotion_plan(queue):
    plan = []
    for rank, row in enumerate(sorted(queue, key=_promotion_plan_priority), start=1):
        plan.append({
            "rank": rank,
            "promotion_id": row.get("promotion_id"),
            "source_id": row.get("source_id"),
            "source_class": row.get("source_class"),
            "promotion_kind": row.get("promotion_kind"),
            "status": row.get("status"),
            "owner_lane": _promotion_plan_lane(row),
            "risk_label": _promotion_plan_risk_label(row),
            "report_path": row.get("report_path"),
            "package_builder": row.get("package_builder"),
            "cli_mode": row.get("cli_mode"),
            "required_artifacts": list(row.get("required_artifacts") or []),
            "required_capabilities": list(row.get("required_capabilities") or []),
            "requires_operator_approval": row.get("requires_operator_approval") is True,
            "requires_rollback_metadata": row.get("requires_rollback_metadata") is True,
            "staged_apply_can_mutate_disposable_world":
                row.get("staged_apply_can_mutate_disposable_world") is True,
            "next_action": row.get("next_action"),
            "safety": dict(row.get("safety") or {}),
        })
    return plan


def _promotion_plan_summary(plan):
    by_owner_lane = {}
    by_risk_label = {}
    for row in plan:
        by_owner_lane[row["owner_lane"]] = by_owner_lane.get(row["owner_lane"], 0) + 1
        by_risk_label[row["risk_label"]] = by_risk_label.get(row["risk_label"], 0) + 1
    return {
        "plan_items_total": len(plan),
        "by_owner_lane": by_owner_lane,
        "by_risk_label": by_risk_label,
        "disposable_staging_items_total": sum(
            1 for row in plan if row["staged_apply_can_mutate_disposable_world"]
        ),
        "world_conversion_deferred": any(
            row["owner_lane"] == "world_conversion_design" for row in plan
        ),
    }


def _discovery_source_row(index, report, report_path):
    status = _source_discovery_status(report)
    capabilities = _batch_required_capabilities(report)
    inventory_counts = _source_classification_counts(report)
    section_counts = _source_section_counts(report)
    return {
        "source_id": report["source"]["source_id"],
        "source_class": report["source"]["source_class"],
        "status": status,
        "license_status": report["source"]["license_status"],
        "path_policy": report["source"]["path_policy"],
        "risk_level": report["summary"]["risk_level"],
        "inventory_count": len(report["source"]["inventory"]),
        "inventory_classification_counts": inventory_counts,
        "dry_run_classification_counts": report["summary"].get(
            "dry_run_classification_counts",
            _zero_dry_run_classification_counts(),
        ),
        "section_status_counts": section_counts,
        "unsupported_feature_count": len(report["unsupported_features"]),
        "planned_actions_count": len(report["planned_actions"]),
        "planned_actions": [
            _planned_action_discovery_summary(action)
            for action in report["planned_actions"]
        ],
        "estimated_world_mutations": report["summary"]["estimated_world_mutations"],
        "required_capabilities": capabilities,
        "provenance": {
            "redacted_id": f"source:{index}",
            "content_hash": report["source"].get("content_hashes", [{}])[0].get("value"),
            "path_policy": report["source"]["path_policy"],
            "report_path": report_path,
        },
        "report_path": report_path,
    }


def _private_source_reference(source):
    path = pathlib.Path(source)
    candidates = [path.name]
    try:
        if path.is_dir():
            candidates.extend(
                _normalized_relpath(item.relative_to(path))
                for item in path.rglob("*")
                if item.is_file()
            )
        else:
            candidates.append(path.suffix)
    except OSError:
        return True
    return any(PRIVATE_DISCOVERY_PATTERNS.search(value) for value in candidates)


def _blocked_discovery_source_row(index, reason):
    counts = _zero_discovery_counts()
    counts["blocked"] = 1
    dry_run_counts = _zero_dry_run_classification_counts()
    dry_run_counts["blocked"] = 1
    return {
        "source_id": f"redacted-private-source:{index}" if reason == "private_source_reference_rejected" else f"blocked-source:{index}",
        "source_class": "unknown",
        "status": "blocked",
        "license_status": "blocked",
        "path_policy": "redacted",
        "risk_level": "high",
        "inventory_count": 0,
        "inventory_classification_counts": counts,
        "dry_run_classification_counts": dry_run_counts,
        "section_status_counts": _zero_discovery_counts(),
        "unsupported_feature_count": 1,
        "planned_actions_count": 0,
        "planned_actions": [],
        "estimated_world_mutations": {
            "node_writes": 0,
            "mapblock_churn": 0,
            "media_files": 0,
            "entity_definitions": 0,
            "manual_review_items": 1,
        },
        "required_capabilities": ["import.assets"],
        "provenance": {
            "redacted_id": f"source:{index}",
            "content_hash": None,
            "path_policy": "redacted",
            "report_path": None,
        },
        "report_path": None,
        "blocked_reason": reason,
    }


def _discovery_summary(rows):
    by_source_class = {}
    source_status_counts = _zero_discovery_counts()
    inventory_classification_counts = _zero_discovery_counts()
    dry_run_classification_counts = _zero_dry_run_classification_counts()
    capabilities = set()
    for row in rows:
        by_source_class[row["source_class"]] = by_source_class.get(row["source_class"], 0) + 1
        source_status_counts[row["status"]] += 1
        for classification, count in row["inventory_classification_counts"].items():
            inventory_classification_counts[classification] += count
        for classification, count in row["dry_run_classification_counts"].items():
            dry_run_classification_counts[classification] += count
        capabilities.update(row.get("required_capabilities") or [])
    blocking_reasons = sorted({
        row.get("blocked_reason")
        for row in rows
        if row.get("blocked_reason") in DISCOVERY_READY_BLOCKERS
    })
    if not rows:
        blocking_reasons.append("empty_inventory_root")
    return {
        "compatibility_import_inventory_ready": not blocking_reasons,
        "sources_total": len(rows),
        "by_source_class": by_source_class,
        "source_status_counts": source_status_counts,
        "inventory_classification_counts": inventory_classification_counts,
        "dry_run_classification_counts": dry_run_classification_counts,
        "inventory_items_total": sum(row["inventory_count"] for row in rows),
        "unsupported_features_total": sum(row["unsupported_feature_count"] for row in rows),
        "planned_actions_total": sum(row["planned_actions_count"] for row in rows),
        "manual_review_items_total": sum(
            row["estimated_world_mutations"]["manual_review_items"] for row in rows
        ),
        "required_capabilities": sorted(capabilities),
        "blocking_reasons": blocking_reasons,
    }


def build_import_inventory_discovery_report(root, reports_dir=None):
    """Build an aggregate public-safe compatibility/import inventory discovery report."""
    reports_root = pathlib.Path(reports_dir) if reports_dir else None
    if reports_root:
        reports_root.mkdir(parents=True, exist_ok=True)

    rows = []
    for index, source in enumerate(_batch_source_candidates(root), start=1):
        if _private_source_reference(source):
            rows.append(_blocked_discovery_source_row(index, "private_source_reference_rejected"))
            continue
        try:
            report = build_report(source)
            report_path = None
            if reports_root:
                report_path = _safe_report_filename(index, report["source"]["source_id"])
                (reports_root / report_path).write_text(
                    json.dumps(report, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            rows.append(_discovery_source_row(index, report, report_path))
        except (OSError, ValueError, json.JSONDecodeError):
            rows.append(_blocked_discovery_source_row(index, "source_classification_failed"))

    summary = _discovery_summary(rows)
    promotion_queue = _promotion_queue(rows)
    ranked_promotion_plan = _ranked_promotion_plan(promotion_queue)
    ready = summary["compatibility_import_inventory_ready"]
    report = {
        "report_version": IMPORT_INVENTORY_DISCOVERY_REPORT_VERSION,
        "mode": "import_inventory_discovery",
        "generated_at": _utc_now(),
        "status": "ready_for_import_preview" if ready else "blocked",
        "inventory_input_format": {
            "accepted_source_classes": list(DISCOVERY_ACCEPTED_SOURCE_CLASSES),
            "path_policy": "package_relative_or_redacted",
            "payload_policy": "metadata_and_references_only",
            "required_capabilities": ["import.assets"],
        },
        "root": {
            "path_policy": "redacted",
            "source_count": len(rows),
        },
        "summary": summary,
        "promotion_queue_summary": _promotion_queue_summary(promotion_queue),
        "promotion_plan_summary": _promotion_plan_summary(ranked_promotion_plan),
        "readiness": {
            "compatibility_import_inventory_ready": ready,
            "blocking_reasons": summary["blocking_reasons"],
        },
        "sources": rows,
        "promotion_queue": promotion_queue,
        "ranked_promotion_plan": ranked_promotion_plan,
        "safety": {
            "dry_run_only": True,
            "no_assets_copied": True,
            "no_world_mutation": True,
            "source_paths_redacted": True,
            "no_raw_payloads": True,
            "no_private_paths": True,
            "uses_proprietary_minecraft_code_or_assets": False,
            "uses_copied_server_jars_or_game_data": False,
        },
    }
    serialized = json.dumps(report, sort_keys=True)
    if PRIVATE_DISCOVERY_PATTERNS.search(serialized):
        raise ValueError("inventory discovery report contains private or raw payload references")
    return report


def validate_import_inventory_discovery_report(report):
    errors = []
    if report.get("report_version") != IMPORT_INVENTORY_DISCOVERY_REPORT_VERSION:
        errors.append("report_version must be 1")
    if report.get("mode") != "import_inventory_discovery":
        errors.append("mode must be import_inventory_discovery")
    if report.get("status") not in {"ready_for_import_preview", "blocked"}:
        errors.append("status must be ready_for_import_preview or blocked")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        errors.append("summary must be an object")
        summary = {}
    for field in (
        "compatibility_import_inventory_ready",
        "sources_total",
        "by_source_class",
        "source_status_counts",
        "inventory_classification_counts",
        "dry_run_classification_counts",
        "inventory_items_total",
        "planned_actions_total",
        "required_capabilities",
    ):
        if field not in summary:
            errors.append(f"summary.{field} is required")
    for counts_name in ("source_status_counts", "inventory_classification_counts"):
        counts = summary.get(counts_name) or {}
        for classification in DISCOVERY_CLASSIFICATIONS:
            if classification not in counts:
                errors.append(f"summary.{counts_name}.{classification} is required")
    counts = summary.get("dry_run_classification_counts") or {}
    for classification in DRY_RUN_CLASSIFICATIONS:
        if classification not in counts:
            errors.append(f"summary.dry_run_classification_counts.{classification} is required")
    if "import.assets" not in (summary.get("required_capabilities") or []):
        errors.append("summary.required_capabilities must include import.assets")
    safety = report.get("safety") or {}
    for field in (
        "dry_run_only",
        "no_assets_copied",
        "no_world_mutation",
        "source_paths_redacted",
        "no_raw_payloads",
        "no_private_paths",
    ):
        if safety.get(field) is not True:
            errors.append(f"safety.{field} must be true")
    for field in (
        "uses_proprietary_minecraft_code_or_assets",
        "uses_copied_server_jars_or_game_data",
    ):
        if safety.get(field) is not False:
            errors.append(f"safety.{field} must be false")
    sources = report.get("sources")
    if not isinstance(sources, list):
        errors.append("sources must be an array")
        sources = []
    if summary.get("sources_total") != len(sources):
        errors.append("summary.sources_total must match sources length")
    for index, source in enumerate(sources):
        for field in (
            "source_id",
            "source_class",
            "status",
            "inventory_count",
            "inventory_classification_counts",
            "dry_run_classification_counts",
            "planned_actions",
            "required_capabilities",
            "provenance",
            "report_path",
        ):
            if field not in source:
                errors.append(f"sources[{index}].{field} is required")
        if source.get("status") not in DISCOVERY_CLASSIFICATIONS:
            errors.append(f"sources[{index}].status is invalid")
        counts = source.get("dry_run_classification_counts") or {}
        for classification in DRY_RUN_CLASSIFICATIONS:
            if classification not in counts:
                errors.append(
                    f"sources[{index}].dry_run_classification_counts.{classification} is required"
                )
        if "import.assets" not in (source.get("required_capabilities") or []):
            errors.append(f"sources[{index}].required_capabilities must include import.assets")
    promotion_queue = report.get("promotion_queue")
    if not isinstance(promotion_queue, list):
        errors.append("promotion_queue must be an array")
        promotion_queue = []
    if len(promotion_queue) != len(sources):
        errors.append("promotion_queue length must match sources length")
    promotion_summary = report.get("promotion_queue_summary")
    if not isinstance(promotion_summary, dict):
        errors.append("promotion_queue_summary must be an object")
        promotion_summary = {}
    for field in (
        "promotion_sources_total",
        "by_promotion_kind",
        "by_status",
        "ready_package_count",
        "disposable_staging_candidate_count",
        "metadata_only_or_deferred_count",
    ):
        if field not in promotion_summary:
            errors.append(f"promotion_queue_summary.{field} is required")
    for index, row in enumerate(promotion_queue):
        for field in (
            "promotion_id",
            "source_id",
            "source_class",
            "source_status",
            "promotion_kind",
            "status",
            "required_artifacts",
            "required_capabilities",
            "requires_operator_approval",
            "requires_rollback_metadata",
            "staged_apply_can_mutate_disposable_world",
            "next_action",
            "safety",
        ):
            if field not in row:
                errors.append(f"promotion_queue[{index}].{field} is required")
        safety = row.get("safety") or {}
        for field in (
            "dry_run_only",
            "no_assets_copied",
            "no_raw_payloads",
            "no_live_server_mutation",
        ):
            if safety.get(field) is not True:
                errors.append(f"promotion_queue[{index}].safety.{field} must be true")
        if safety.get("promotion_package_executes_world_mutation") is not False:
            errors.append(
                f"promotion_queue[{index}].safety.promotion_package_executes_world_mutation must be false"
            )
    promotion_plan = report.get("ranked_promotion_plan")
    if not isinstance(promotion_plan, list):
        errors.append("ranked_promotion_plan must be an array")
        promotion_plan = []
    if len(promotion_plan) != len(promotion_queue):
        errors.append("ranked_promotion_plan length must match promotion_queue length")
    promotion_plan_summary = report.get("promotion_plan_summary")
    if not isinstance(promotion_plan_summary, dict):
        errors.append("promotion_plan_summary must be an object")
        promotion_plan_summary = {}
    for field in (
        "plan_items_total",
        "by_owner_lane",
        "by_risk_label",
        "disposable_staging_items_total",
        "world_conversion_deferred",
    ):
        if field not in promotion_plan_summary:
            errors.append(f"promotion_plan_summary.{field} is required")
    expected_rank = 1
    queue_ids = {row.get("promotion_id") for row in promotion_queue}
    for index, row in enumerate(promotion_plan):
        for field in (
            "rank",
            "promotion_id",
            "source_id",
            "source_class",
            "promotion_kind",
            "status",
            "owner_lane",
            "risk_label",
            "required_artifacts",
            "required_capabilities",
            "requires_operator_approval",
            "requires_rollback_metadata",
            "staged_apply_can_mutate_disposable_world",
            "next_action",
            "safety",
        ):
            if field not in row:
                errors.append(f"ranked_promotion_plan[{index}].{field} is required")
        if row.get("rank") != expected_rank:
            errors.append(f"ranked_promotion_plan[{index}].rank must be {expected_rank}")
        expected_rank += 1
        if row.get("promotion_id") not in queue_ids:
            errors.append(f"ranked_promotion_plan[{index}].promotion_id must match promotion_queue")
        if "import.assets" not in (row.get("required_capabilities") or []):
            errors.append(
                f"ranked_promotion_plan[{index}].required_capabilities must include import.assets"
            )
        safety = row.get("safety") or {}
        if safety.get("promotion_package_executes_world_mutation") is not False:
            errors.append(
                f"ranked_promotion_plan[{index}].safety.promotion_package_executes_world_mutation must be false"
            )
    serialized = json.dumps(report, sort_keys=True)
    if PRIVATE_DISCOVERY_PATTERNS.search(serialized):
        errors.append("report contains private or raw payload references")
    return errors


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
    if value.get("adapter_kind") not in {
        SYNTHETIC_STRUCTURE_ADAPTER_KIND,
        PUBLIC_SAFE_STRUCTURE_ADAPTER_KIND,
    }:
        errors.append(
            f"{path}.adapter_kind must be {SYNTHETIC_STRUCTURE_ADAPTER_KIND} "
            f"or {PUBLIC_SAFE_STRUCTURE_ADAPTER_KIND}"
        )
    if not (value.get("synthetic") is True or value.get("public_safe") is True):
        errors.append(f"{path} must be synthetic or public_safe")
    if value.get("adapter_kind") == PUBLIC_SAFE_STRUCTURE_ADAPTER_KIND:
        _require_keys(errors, value, path, ("structure_format", "dimensions"))
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
        counts = summary.get("dry_run_classification_counts") or {}
        for classification in DRY_RUN_CLASSIFICATIONS:
            if classification not in counts:
                errors.append(
                    f"summary.dry_run_classification_counts.{classification} is required"
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


def validate_adapter_apply_smoke(smoke):
    """Return validation errors for a reviewed adapter apply smoke manifest."""
    errors = []
    _require_keys(errors, smoke, "smoke", ADAPTER_APPLY_SMOKE_REQUIRED)
    if errors:
        return errors

    if smoke.get("smoke_version") != ADAPTER_APPLY_SMOKE_VERSION:
        errors.append(f"smoke.smoke_version must be {ADAPTER_APPLY_SMOKE_VERSION}")
    if smoke.get("mode") != "adapter_apply_smoke":
        errors.append("smoke.mode must be adapter_apply_smoke")
    if smoke.get("status") != "ready":
        errors.append("smoke.status must be ready")

    target_world = smoke.get("target_world")
    _require_keys(errors, target_world, "target_world", ("world_id", "staging", "disposable"))
    if isinstance(target_world, dict):
        if target_world.get("staging") is not True:
            errors.append("target_world.staging must be true")
        if target_world.get("disposable") is not True:
            errors.append("target_world.disposable must be true")

    for field in ("approved_actions", "apply_tasks", "rollback_tasks", "operator_next_actions"):
        _require_sequence(errors, smoke.get(field), field)
    if isinstance(smoke.get("apply_tasks"), list) and not smoke["apply_tasks"]:
        errors.append("apply_tasks must contain at least one task")
    if isinstance(smoke.get("rollback_tasks"), list) and not smoke["rollback_tasks"]:
        errors.append("rollback_tasks must contain at least one task")

    _validate_mutation_cost(
        errors,
        smoke.get("mutation_cost_expected"),
        "mutation_cost_expected",
    )
    safety = smoke.get("safety")
    _require_keys(errors, safety, "safety", ADAPTER_APPLY_SMOKE_SAFETY_REQUIRED)
    if isinstance(safety, dict):
        for key in ADAPTER_APPLY_SMOKE_SAFETY_REQUIRED:
            if key == "world_mutation_executed":
                if safety.get(key) is not False:
                    errors.append("safety.world_mutation_executed must be false")
            elif safety.get(key) is not True:
                errors.append(f"safety.{key} must be true")

    return errors


def _review_finding(code, message, field=None, severity="blocked"):
    finding = {
        "severity": severity,
        "code": code,
        "message": message,
    }
    if field:
        finding["field"] = field
    return finding


def _append_unique_finding(findings, seen, code, message, field=None, severity="blocked"):
    key = (code, field)
    if key in seen:
        return
    seen.add(key)
    findings.append(_review_finding(code, message, field=field, severity=severity))


def _task_world(task):
    target_world = task.get("target_world")
    if isinstance(target_world, dict):
        return target_world
    return {
        "world_id": task.get("world_id"),
        "staging": task.get("staging"),
        "disposable": task.get("disposable"),
    }


def _review_target_world(findings, seen, target_world, field_prefix):
    if not isinstance(target_world, dict):
        _append_unique_finding(
            findings,
            seen,
            "target_world_missing",
            "Target world must be present for adapter smoke review.",
            field_prefix,
        )
        return None
    world_id = str(target_world.get("world_id") or "")
    if not world_id:
        _append_unique_finding(
            findings,
            seen,
            "target_world_missing",
            "Target world id is required.",
            field_prefix + ".world_id",
        )
    if target_world.get("staging") is not True:
        _append_unique_finding(
            findings,
            seen,
            "target_world_not_staging",
            "Adapter smoke review requires a staging target world.",
            field_prefix + ".staging",
        )
    if target_world.get("disposable") is not True:
        _append_unique_finding(
            findings,
            seen,
            "target_world_not_disposable",
            "Adapter smoke review requires a disposable target world.",
            field_prefix + ".disposable",
        )
    if world_id in ADAPTER_APPLY_FORBIDDEN_WORLD_IDS:
        _append_unique_finding(
            findings,
            seen,
            "forbidden_target_world",
            "Adapter smoke review cannot target the live family or production world.",
            field_prefix + ".world_id",
        )
    return world_id


def _review_required_hooks(findings, seen, task, required_hooks, field_prefix):
    hooks = task.get("operator_supplied_runtime_hooks")
    if not isinstance(hooks, list):
        hooks = []
    missing_hooks = [hook for hook in required_hooks if hook not in hooks]
    for hook in missing_hooks:
        _append_unique_finding(
            findings,
            seen,
            "missing_runtime_hook",
            f"Runtime hook {hook} is required before operator promotion.",
            field_prefix + ".operator_supplied_runtime_hooks",
        )


def _review_task_budget(findings, seen, task, expected, budget_limit, field_prefix):
    max_node_writes = task.get("max_node_writes_total")
    if isinstance(max_node_writes, int) and max_node_writes > expected["node_writes"]:
        _append_unique_finding(
            findings,
            seen,
            "excessive_node_write_budget",
            "Task node-write budget exceeds the reviewed smoke mutation estimate.",
            field_prefix + ".max_node_writes_total",
        )
    max_mapblock_churn = task.get("max_mapblock_churn_total")
    if isinstance(max_mapblock_churn, int) and max_mapblock_churn > budget_limit:
        _append_unique_finding(
            findings,
            seen,
            "excessive_mapblock_budget",
            "Task mapblock-churn budget exceeds the reviewed smoke mutation estimate.",
            field_prefix + ".max_mapblock_churn_total",
        )


def review_adapter_apply_smoke(smoke):
    """Build an operator-facing review gate for an adapter apply smoke manifest."""
    findings = []
    seen = set()
    if not isinstance(smoke, dict):
        return {
            "review_version": ADAPTER_APPLY_SMOKE_REVIEW_VERSION,
            "mode": "adapter_apply_smoke_review",
            "generated_at": _utc_now(),
            "report_id": None,
            "status": "blocked",
            "target_world": {},
            "summary": {
                "apply_task_count": 0,
                "rollback_task_count": 0,
                "placement_count": 0,
                "chunk_count": 0,
                "expected_node_writes": 0,
                "expected_mapblock_churn": 0,
                "runtime_entrypoints": [],
                "required_capabilities": [],
                "runtime_hooks": [],
                "approval_state": "blocked",
            },
            "findings": [
                _review_finding(
                    "manifest_not_object",
                    "Adapter smoke review requires a JSON object manifest.",
                    "smoke",
                ),
            ],
            "machine_gate": {
                "promotable": False,
                "world_mutation_executed": False,
                "reviewed_for": "disposable_staging_adapter_smoke",
            },
            "operator_next_actions": [
                "Generate an adapter smoke manifest before operator review.",
            ],
        }

    for error in validate_adapter_apply_smoke(smoke):
        _append_unique_finding(
            findings,
            seen,
            "validation_error",
            error,
            "smoke",
        )

    target_world = smoke.get("target_world")
    _review_target_world(findings, seen, target_world, "target_world")

    apply_tasks = smoke.get("apply_tasks") if isinstance(smoke.get("apply_tasks"), list) else []
    rollback_tasks = smoke.get("rollback_tasks") if isinstance(smoke.get("rollback_tasks"), list) else []
    if not apply_tasks:
        _append_unique_finding(
            findings,
            seen,
            "apply_task_missing",
            "Adapter smoke review requires at least one apply task.",
            "apply_tasks",
        )
    if not rollback_tasks:
        _append_unique_finding(
            findings,
            seen,
            "rollback_task_missing",
            "Adapter smoke review requires at least one rollback task.",
            "rollback_tasks",
        )

    expected = smoke.get("mutation_cost_expected") if isinstance(smoke.get("mutation_cost_expected"), dict) else {}
    expected_node_writes = expected.get("node_writes", 0) if isinstance(expected.get("node_writes", 0), int) else 0
    expected_mapblock_churn = (
        expected.get("mapblock_churn", 0)
        if isinstance(expected.get("mapblock_churn", 0), int) else 0
    )
    expected_cost = {
        "node_writes": expected_node_writes,
        "mapblock_churn": expected_mapblock_churn,
    }
    mapblock_budget_limit = max(expected_node_writes, expected_mapblock_churn)

    entrypoints = set()
    capabilities = set()
    hooks = set()
    placement_count = 0
    chunk_count = 0
    approvals_ok = True

    rollback_plan = smoke.get("rollback_plan")
    if isinstance(rollback_plan, dict) and rollback_plan.get("entrypoint"):
        entrypoints.add(rollback_plan["entrypoint"])

    for index, task in enumerate(apply_tasks):
        field_prefix = f"apply_tasks[{index}]"
        if not isinstance(task, dict):
            _append_unique_finding(
                findings,
                seen,
                "apply_task_malformed",
                "Apply task must be an object.",
                field_prefix,
            )
            continue
        entrypoint = task.get("entrypoint")
        if entrypoint:
            entrypoints.add(entrypoint)
        if entrypoint != "core.ai_import_ops.define_chunked_structure_apply_task":
            _append_unique_finding(
                findings,
                seen,
                "unexpected_apply_entrypoint",
                "Adapter smoke apply must use chunked structure apply.",
                field_prefix + ".entrypoint",
            )
        if task.get("explicit_approval") is not True:
            approvals_ok = False
            _append_unique_finding(
                findings,
                seen,
                "missing_explicit_approval",
                "Apply task must carry explicit operator approval.",
                field_prefix + ".explicit_approval",
            )
        if task.get("allow_mutation") is not True:
            _append_unique_finding(
                findings,
                seen,
                "mutation_not_enabled_for_smoke",
                "Apply task must explicitly enable mutation for the staging smoke.",
                field_prefix + ".allow_mutation",
            )
        if task.get("rollback_policy") != "chunked":
            _append_unique_finding(
                findings,
                seen,
                "rollback_policy_not_chunked",
                "Apply task must use chunked rollback policy.",
                field_prefix + ".rollback_policy",
            )
        _review_target_world(findings, seen, _task_world(task), field_prefix + ".target_world")
        _review_required_hooks(
            findings,
            seen,
            task,
            ADAPTER_APPLY_REVIEW_REQUIRED_APPLY_HOOKS,
            field_prefix,
        )
        _review_task_budget(
            findings,
            seen,
            task,
            expected_cost,
            expected_mapblock_churn,
            field_prefix,
        )
        for capability in task.get("required_capabilities") or []:
            capabilities.add(capability)
        for hook in task.get("operator_supplied_runtime_hooks") or []:
            hooks.add(hook)
        placement_count += task.get("placement_count", 0) if isinstance(task.get("placement_count"), int) else 0
        chunk_count += task.get("chunk_count", 0) if isinstance(task.get("chunk_count"), int) else 0

    for index, task in enumerate(rollback_tasks):
        field_prefix = f"rollback_tasks[{index}]"
        if not isinstance(task, dict):
            _append_unique_finding(
                findings,
                seen,
                "rollback_task_malformed",
                "Rollback task must be an object.",
                field_prefix,
            )
            continue
        entrypoint = task.get("entrypoint")
        if entrypoint:
            entrypoints.add(entrypoint)
        if entrypoint != "core.ai_import_ops.queue_chunked_structure_rollback_task":
            _append_unique_finding(
                findings,
                seen,
                "unexpected_rollback_entrypoint",
                "Adapter smoke rollback must use chunked rollback execution.",
                field_prefix + ".entrypoint",
            )
        if task.get("explicit_approval") is not True:
            approvals_ok = False
            _append_unique_finding(
                findings,
                seen,
                "missing_explicit_approval",
                "Rollback task must carry explicit operator approval.",
                field_prefix + ".explicit_approval",
            )
        if task.get("allow_mutation") is not True:
            _append_unique_finding(
                findings,
                seen,
                "mutation_not_enabled_for_smoke",
                "Rollback task must explicitly enable mutation for the staging smoke.",
                field_prefix + ".allow_mutation",
            )
        if task.get("rollback_policy") != "chunked":
            _append_unique_finding(
                findings,
                seen,
                "rollback_policy_not_chunked",
                "Rollback task must use chunked rollback policy.",
                field_prefix + ".rollback_policy",
            )
        _review_target_world(findings, seen, _task_world(task), field_prefix + ".target_world")
        _review_required_hooks(
            findings,
            seen,
            task,
            ADAPTER_APPLY_REVIEW_REQUIRED_ROLLBACK_HOOKS,
            field_prefix,
        )
        _review_task_budget(
            findings,
            seen,
            task,
            expected_cost,
            mapblock_budget_limit,
            field_prefix,
        )
        for capability in task.get("required_capabilities") or []:
            capabilities.add(capability)
        for hook in task.get("operator_supplied_runtime_hooks") or []:
            hooks.add(hook)

    safety = smoke.get("safety") if isinstance(smoke.get("safety"), dict) else {}
    world_mutation_executed = safety.get("world_mutation_executed") is True
    if world_mutation_executed:
        _append_unique_finding(
            findings,
            seen,
            "world_mutation_already_executed",
            "Review manifests must be generated before world mutation executes.",
            "safety.world_mutation_executed",
        )

    status = "ready" if not findings else "blocked"
    return {
        "review_version": ADAPTER_APPLY_SMOKE_REVIEW_VERSION,
        "mode": "adapter_apply_smoke_review",
        "generated_at": _utc_now(),
        "report_id": smoke.get("report_id"),
        "status": status,
        "target_world": target_world if isinstance(target_world, dict) else {},
        "summary": {
            "apply_task_count": len(apply_tasks),
            "rollback_task_count": len(rollback_tasks),
            "placement_count": placement_count,
            "chunk_count": chunk_count,
            "expected_node_writes": expected_node_writes,
            "expected_mapblock_churn": expected_mapblock_churn,
            "runtime_entrypoints": sorted(entrypoints),
            "required_capabilities": sorted(capabilities),
            "runtime_hooks": sorted(hooks),
            "approval_state": "approved" if approvals_ok else "blocked",
        },
        "findings": findings,
        "machine_gate": {
            "promotable": status == "ready",
            "world_mutation_executed": world_mutation_executed,
            "reviewed_for": "disposable_staging_adapter_smoke",
        },
        "operator_next_actions": [
            "Run the smoke apply only in the declared disposable staging world.",
            "Review rollback records with core.ai_import_ops.plan_structure_rollback.",
            "Run the smoke rollback before discarding or promoting any import workflow.",
        ] if status == "ready" else [
            "Resolve blocked findings before running any adapter smoke apply task.",
        ],
    }


def _assert_promotion_target_world(target_world, field_prefix):
    if not isinstance(target_world, dict):
        raise ValueError(f"{field_prefix} is required for promotion package")
    world_id = str(target_world.get("world_id") or "")
    if not world_id:
        raise ValueError(f"{field_prefix}.world_id is required for promotion package")
    if target_world.get("staging") is not True:
        raise ValueError(f"{field_prefix}.staging must be true for promotion package")
    if target_world.get("disposable") is not True:
        raise ValueError(f"{field_prefix}.disposable must be true for promotion package")
    if world_id in ADAPTER_APPLY_FORBIDDEN_WORLD_IDS:
        raise ValueError("promotion package cannot target the live family world")
    return {
        "world_id": world_id,
        "staging": True,
        "disposable": True,
    }


def _assert_same_target_world(expected, candidate, field_prefix):
    candidate_world = _assert_promotion_target_world(candidate, field_prefix)
    if candidate_world != expected:
        raise ValueError(f"{field_prefix} must match the approved promotion target")


def _public_safe_structure_adapter_actions(approved_actions):
    public_safe_actions = []
    for action_index, requested, planned in approved_actions:
        if planned["action"] != "import_structure":
            continue
        adapter = planned.get("structure_adapter")
        if not isinstance(adapter, dict) or adapter.get("public_safe") is not True:
            raise ValueError("promotion package requires a public-safe structure adapter")
        if adapter.get("adapter_kind") != PUBLIC_SAFE_STRUCTURE_ADAPTER_KIND:
            raise ValueError("promotion package requires a public-safe structure adapter")
        public_safe_actions.append((action_index, requested, planned, adapter))
    if not public_safe_actions:
        raise ValueError("promotion package requires a public-safe structure adapter action")
    return public_safe_actions


def _assert_review_ready(smoke, supplied_review):
    if not isinstance(supplied_review, dict):
        raise ValueError("review gate artifact must be an object")
    if supplied_review.get("status") != "ready":
        raise ValueError("review gate status must be ready for promotion package")
    machine_gate = supplied_review.get("machine_gate")
    if not isinstance(machine_gate, dict) or machine_gate.get("promotable") is not True:
        raise ValueError("review gate must be promotable for promotion package")
    if supplied_review.get("findings"):
        raise ValueError("review gate findings must be empty for promotion package")

    computed_review = review_adapter_apply_smoke(smoke)
    if computed_review.get("status") != "ready":
        first_finding = (
            computed_review.get("findings", [{}])[0].get("message")
            if computed_review.get("findings") else "adapter smoke review is blocked"
        )
        raise ValueError(f"review gate blocked: {first_finding}")
    return computed_review


def _assert_promotion_chain_matches(report, request, smoke, review):
    if request["report_id"] != smoke.get("report_id"):
        raise ValueError("adapter smoke report_id must match approval report_id")
    if review.get("report_id") != request["report_id"]:
        raise ValueError("review gate report_id must match approval report_id")
    expected_target = _assert_promotion_target_world(
        request.get("target_world"),
        "target_world",
    )
    _assert_same_target_world(expected_target, smoke.get("target_world"), "smoke.target_world")
    _assert_same_target_world(expected_target, review.get("target_world"), "review.target_world")
    if report.get("source", {}).get("license_status") != "user_supplied":
        raise ValueError("promotion package requires user_supplied source license status")
    if smoke.get("status") != "ready":
        raise ValueError("adapter smoke status must be ready for promotion package")
    if smoke.get("rollback_plan", {}).get("readback_required") is not True:
        raise ValueError("rollback metadata readback is required for promotion package")
    if not smoke.get("rollback_tasks"):
        raise ValueError("rollback metadata tasks are required for promotion package")


def _source_inventory_summary(report):
    return [
        {
            "entry_id": entry["entry_id"],
            "source_path": entry["source_path"],
            "source_kind": entry["source_kind"],
            "classification": entry["classification"],
            "reason": entry["reason"],
            "required_capabilities": entry["required_capabilities"],
        }
        for entry in report["source"]["inventory"]
    ]


def _unsupported_feature_summary(report):
    features = []
    for item in report.get("unsupported_features", []):
        features.append({
            "feature": item["feature"],
            "status": item["status"],
            "reason": item["reason"],
            "severity": item["severity"],
            "source_path": item.get("source_path", ""),
        })
    return {
        "count": len(features),
        "features": features,
    }


def _package_budget_gate(name, expected, limit):
    return {
        "expected": expected,
        "limit": limit,
        "status": "within_reviewed_limit" if expected <= limit else "blocked",
    }


def _promotion_budget_gates(request, smoke):
    expected = smoke["mutation_cost_expected"]
    budget = request["budget"]
    return {
        "node_writes": _package_budget_gate(
            "node_writes",
            expected["node_writes"],
            budget["max_node_writes_total"],
        ),
        "node_writes_per_step": _package_budget_gate(
            "node_writes_per_step",
            min(expected["node_writes"], budget["max_node_writes_per_step"]),
            budget["max_node_writes_per_step"],
        ),
        "mapblock_churn": _package_budget_gate(
            "mapblock_churn",
            expected["mapblock_churn"],
            budget["max_mapblock_churn_total"],
        ),
        "manual_review_items": _package_budget_gate(
            "manual_review_items",
            expected["manual_review_items"],
            budget["max_manual_review_items"],
        ),
        "wall_time_ms": {
            "limit": budget["max_wall_time_ms"],
            "status": "explicit_limit_declared",
        },
    }


def _promotion_apply_task_summary(smoke):
    tasks = smoke.get("apply_tasks", [])
    capabilities = sorted({
        capability
        for task in tasks
        for capability in task.get("required_capabilities", [])
    })
    return {
        "task_count": len(tasks),
        "task_ids": [task["task_id"] for task in tasks],
        "entrypoints": sorted({task["entrypoint"] for task in tasks}),
        "placement_count": sum(task.get("placement_count", 0) for task in tasks),
        "chunk_count": sum(task.get("chunk_count", 0) for task in tasks),
        "required_capabilities": capabilities,
    }


def _promotion_rollback_task_summary(request, smoke):
    tasks = smoke.get("rollback_tasks", [])
    capabilities = sorted({
        capability
        for task in tasks
        for capability in task.get("required_capabilities", [])
    })
    return {
        "task_count": len(tasks),
        "task_ids": [task["task_id"] for task in tasks],
        "source_task_ids": [task["source_task_id"] for task in tasks],
        "entrypoints": sorted({task["entrypoint"] for task in tasks}),
        "rollback_policy": request["rollback_policy"]["policy"],
        "metadata_required": request["rollback_policy"]["metadata_required"] is True
            and smoke.get("rollback_plan", {}).get("readback_required") is True,
        "required_capabilities": capabilities,
    }


def _promotion_capability_gates(review, apply_summary, rollback_summary):
    required_capabilities = sorted({
        *PROMOTION_PACKAGE_REQUIRED_CAPABILITIES,
        *review.get("summary", {}).get("required_capabilities", []),
        *apply_summary["required_capabilities"],
        *rollback_summary["required_capabilities"],
    })
    return {
        "required_capabilities": required_capabilities,
        "operator_runtime_hooks": review.get("summary", {}).get("runtime_hooks", []),
        "status": "ready",
    }


def _package_has_private_source_paths(package):
    for entry in package["dry_run"]["source_inventory"]:
        source_path = entry.get("source_path", "")
        if source_path.startswith("/") or "\\" in source_path or ".." in source_path:
            return True
    return False


def build_structure_import_promotion_package(report, request, smoke, review):
    """Build a public-safe operator promotion package for reviewed structure imports."""
    approved_actions = _validated_approved_actions(report, request)
    public_safe_actions = _public_safe_structure_adapter_actions(approved_actions)
    smoke_errors = validate_adapter_apply_smoke(smoke)
    if smoke_errors:
        raise ValueError(smoke_errors[0])
    computed_review = _assert_review_ready(smoke, review)
    _assert_promotion_chain_matches(report, request, smoke, review)

    adapters = [adapter for _index, _requested, _planned, adapter in public_safe_actions]
    structure_formats = sorted({
        adapter.get("structure_format", "")
        for adapter in adapters
        if adapter.get("structure_format")
    })
    apply_summary = _promotion_apply_task_summary(smoke)
    rollback_summary = _promotion_rollback_task_summary(request, smoke)
    if not rollback_summary["metadata_required"]:
        raise ValueError("rollback metadata is required for promotion package")

    review_summary = computed_review["summary"]
    package = {
        "package_version": STRUCTURE_IMPORT_PROMOTION_PACKAGE_VERSION,
        "mode": "structure_import_promotion_package",
        "generated_at": _utc_now(),
        "report_id": request["report_id"],
        "status": "ready_for_operator_promotion",
        "dry_run": {
            "report_id": request["report_id"],
            "report_version": report["report_version"],
            "source_id": report["source"]["source_id"],
            "source_class": report["source"]["source_class"],
            "source_reference": {
                "reference_type": request["source_reference"]["reference_type"],
                "redacted_id": request["source_reference"]["redacted_id"],
                "inventory_hash": request["source_reference"]["inventory_hash"],
            },
            "source_inventory": _source_inventory_summary(report),
            "license_status": report["source"]["license_status"],
            "rights_status": "operator_confirmed",
            "source_adapter_kind": report["source"].get("metadata", {}).get("source_adapter_kind"),
            "structure_format": structure_formats[0] if structure_formats else None,
            "estimated_world_mutations": report["summary"]["estimated_world_mutations"],
        },
        "operator_approval": {
            "approval_state": review_summary["approval_state"],
            "operator": request["operator"],
            "agent_id": request["agent_id"],
            "approved_actions": request["approved_actions"],
            "target_world": request["target_world"],
            "rollback_policy": request["rollback_policy"],
            "budget": request["budget"],
        },
        "adapter_smoke_summary": {
            **smoke["operator_summary"],
            "smoke_version": smoke["smoke_version"],
            "target_world": smoke["target_world"],
        },
        "review_gate": {
            "review_version": review["review_version"],
            "status": review["status"],
            "promotable": review["machine_gate"]["promotable"] is True,
            "reviewed_for": review["machine_gate"]["reviewed_for"],
            "findings": review["findings"],
            "summary": review["summary"],
        },
        "apply_task_summary": apply_summary,
        "rollback_task_summary": rollback_summary,
        "budget_gates": _promotion_budget_gates(request, smoke),
        "capability_gates": _promotion_capability_gates(
            review,
            apply_summary,
            rollback_summary,
        ),
        "unsupported_feature_summary": _unsupported_feature_summary(report),
        "operator_next_actions": [
            "Archive this package with the reviewed dry-run, approval, smoke, and review artifacts.",
            "Run apply and rollback only in the declared disposable staging world.",
            "Use the package as promotion evidence before adding broader compatibility formats.",
        ],
        "safety": {
            "public_safe_source": True,
            "no_private_source_paths": True,
            "no_raw_payloads": True,
            "no_proprietary_assets": True,
            "no_private_prompts": True,
            "no_server_secrets": True,
            "no_family_world_coordinates": True,
            "no_live_family_world_mutation": True,
            "world_mutation_executed": False,
        },
    }
    if _package_has_private_source_paths(package):
        raise ValueError("promotion package cannot include private source paths")
    return package


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
        if report.get("source", {}).get("source_class") not in {"structure", "schematic", "world"}:
            raise ValueError("import_structure requires a structure, schematic, or world dry-run source")
        adapter = planned.get("structure_adapter")
        if adapter:
            if not (adapter.get("synthetic") is True or adapter.get("public_safe") is True):
                raise ValueError("structure_adapter must be synthetic or public_safe")
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


def _require_disposable_staging_world(request):
    target_world = request.get("target_world") or {}
    if target_world.get("staging") is not True:
        raise ValueError("target_world.staging must be true for adapter apply smoke")
    if target_world.get("disposable") is not True:
        raise ValueError("target_world.disposable must be true for adapter apply smoke")
    world_id = str(target_world.get("world_id") or "")
    if not world_id:
        raise ValueError("target_world.world_id is required for adapter apply smoke")
    if world_id in ADAPTER_APPLY_FORBIDDEN_WORLD_IDS:
        raise ValueError("adapter apply smoke cannot target the live family world")
    return {
        "world_id": world_id,
        "staging": True,
        "disposable": True,
    }


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


def _find_forbidden_asset_payload(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).lower()
            if normalized in ASSET_REFERENCE_FORBIDDEN_KEYS:
                return normalized
            found = _find_forbidden_asset_payload(nested)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_forbidden_asset_payload(nested)
            if found:
                return found
    return None


def _assert_no_asset_payloads(value):
    forbidden = _find_forbidden_asset_payload(value)
    if not forbidden:
        return
    if forbidden == "copied_protected_content":
        raise ValueError("copied protected content cannot be packaged")
    if "bytes" in forbidden:
        raise ValueError("asset bytes cannot be embedded in promotion packages")
    raise ValueError("raw asset payloads cannot be packaged")


def _assert_asset_reference_target(request):
    target_world = request.get("target_world")
    if not isinstance(target_world, dict):
        raise ValueError("target_world is required for asset-reference promotion package")
    world_id = str(target_world.get("world_id") or "")
    if not world_id:
        raise ValueError("target_world.world_id is required for asset-reference promotion package")
    if world_id in ADAPTER_APPLY_FORBIDDEN_WORLD_IDS:
        raise ValueError("asset-reference promotion cannot target the live family world")
    if target_world.get("world_mutation_allowed") is True:
        raise ValueError("live-world mutation is not allowed for asset-reference promotion")
    return {
        "world_id": world_id,
        "staging": target_world.get("staging") is True,
        "disposable": target_world.get("disposable") is True,
        "world_mutation_allowed": False,
    }


def _assert_asset_reference_report(report):
    source = report.get("source", {})
    source_class = source.get("source_class")
    if source_class not in ASSET_REFERENCE_SOURCE_CLASSES:
        raise ValueError("asset-reference promotion requires a Java or Bedrock resource-pack dry-run")
    if source.get("license_status") != "user_supplied":
        raise ValueError("asset-reference promotion requires user_supplied license status")
    if source.get("path_policy") != "external_reference":
        raise ValueError("asset-reference promotion requires external_reference path policy")
    _assert_no_asset_payloads(report)


def _asset_reference_approved_actions(approved_actions):
    asset_actions = []
    for action_index, requested, planned in approved_actions:
        action = planned["action"]
        cost = _calibrated_action_cost(planned)
        if action not in ASSET_REFERENCE_ACTIONS:
            if "behavior" in action:
                raise ValueError("behavior-script execution is not allowed for asset-reference promotion")
            if action == "import_structure" or cost["node_writes"] > 0 or cost["mapblock_churn"] > 0:
                raise ValueError("asset-reference promotion cannot include world-mutating actions")
            raise ValueError(f"approved action {action} is not an asset-reference action")
        if cost["node_writes"] != 0 or cost["mapblock_churn"] != 0:
            raise ValueError("asset-reference promotion cannot include world-mutating actions")
        asset_actions.append((action_index, requested, planned))
    if not asset_actions:
        raise ValueError("asset-reference promotion requires an approved asset-reference action")
    return asset_actions


def _assert_request_has_no_world_mutating_asset_actions(report, request):
    planned_actions = report.get("planned_actions", [])
    approved_actions = request.get("approved_actions", [])
    if not isinstance(planned_actions, list) or not isinstance(approved_actions, list):
        return
    for requested in approved_actions:
        if not isinstance(requested, dict):
            continue
        action_index = requested.get("action_index")
        if not isinstance(action_index, int) or action_index < 0 or action_index >= len(planned_actions):
            continue
        planned = planned_actions[action_index]
        if not isinstance(planned, dict):
            continue
        cost = planned.get("mutation_cost") or {}
        if (
            planned.get("action") == "import_structure"
            or cost.get("node_writes", 0) > 0
            or cost.get("mapblock_churn", 0) > 0
        ):
            raise ValueError("asset-reference promotion cannot include world-mutating actions")


def _asset_reference_approval_summary(asset_actions, task_definitions):
    task_by_index = {
        definition["provenance"]["action_index"]: definition
        for definition in task_definitions
    }
    actions = []
    for action_index, requested, planned in asset_actions:
        task = task_by_index[action_index]
        actions.append({
            "action_index": action_index,
            "action": planned["action"],
            "status": requested["status"],
            "description": planned["description"],
            "task_id": task["task_id"],
            "mutation_cost": planned["mutation_cost"],
        })
    return actions


def _asset_task_summary(task_definitions):
    planned_tasks = []
    for definition in task_definitions:
        planned_tasks.append({
            "task_id": definition["task_id"],
            "action_index": definition["provenance"]["action_index"],
            "action": definition["source_action"]["action"],
            "label": definition["label"],
            "mutation_class": definition["mutation_class"],
            "queue_state": definition["queue_state"],
            "required_capabilities": definition["required_capabilities"],
            "runtime_handoff": {
                "status": definition["runtime_handoff"]["status"],
                "mutation_enabled": definition["runtime_handoff"]["mutation_enabled"],
                "operation": definition["runtime_handoff"]["operation"],
            },
            "calibrated_cost": definition["calibrated_cost"],
        })
    return {
        "task_count": len(task_definitions),
        "task_ids": [task["task_id"] for task in planned_tasks],
        "labels": sorted({task["label"] for task in planned_tasks}),
        "mutation_classes": sorted({task["mutation_class"] for task in planned_tasks}),
        "queued_task_count": sum(1 for task in planned_tasks if task["queue_state"] != "not_queued"),
        "required_capabilities": sorted({
            capability
            for task in planned_tasks
            for capability in task["required_capabilities"]
        }),
        "planned_tasks": planned_tasks,
    }


def _asset_budget_gates(request, asset_actions):
    totals = _approved_cost_totals(asset_actions)
    budget = request["budget"]
    return {
        "media_files": _package_budget_gate(
            "media_files",
            totals["media_files"],
            budget["max_media_files"],
        ),
        "entity_definitions": _package_budget_gate(
            "entity_definitions",
            totals["entity_definitions"],
            budget["max_entity_definitions"],
        ),
        "node_writes": _package_budget_gate(
            "node_writes",
            totals["node_writes"],
            budget["max_node_writes_total"],
        ),
        "node_writes_per_step": _package_budget_gate(
            "node_writes_per_step",
            0,
            budget["max_node_writes_per_step"],
        ),
        "mapblock_churn": _package_budget_gate(
            "mapblock_churn",
            totals["mapblock_churn"],
            budget["max_mapblock_churn_total"],
        ),
        "manual_review_items": _package_budget_gate(
            "manual_review_items",
            totals["manual_review_items"],
            budget["max_manual_review_items"],
        ),
        "wall_time_ms": _package_budget_gate(
            "wall_time_ms",
            totals["estimated_wall_time_ms"],
            budget["max_wall_time_ms"],
        ),
    }


def _asset_capability_gates(task_summary):
    required_capabilities = sorted({
        "import.assets",
        *task_summary["required_capabilities"],
    })
    return {
        "required_capabilities": required_capabilities,
        "operator_runtime_hooks": [],
        "world_mutation": "disabled",
        "status": "ready",
    }


def build_asset_reference_promotion_package(report, request):
    """Build no-mutation promotion evidence for reviewed resource-pack asset references."""
    _assert_asset_reference_report(report)
    _assert_request_has_no_world_mutating_asset_actions(report, request)
    approved_actions = _validated_approved_actions(report, request)
    asset_actions = _asset_reference_approved_actions(approved_actions)
    if request["rollback_policy"]["policy"] != "no_world_mutation":
        raise ValueError("rollback_policy.policy must be no_world_mutation for asset-reference promotion")
    target_world = _assert_asset_reference_target(request)
    if request["budget"]["max_node_writes_total"] != 0 or request["budget"]["max_mapblock_churn_total"] != 0:
        raise ValueError("asset-reference promotion must keep node and mapblock mutation budgets at 0")

    task_definitions = build_apply_task_definitions(report, request)
    task_summary = _asset_task_summary(task_definitions)
    apply_plan = build_apply_plan(report, request)
    package = {
        "package_version": ASSET_REFERENCE_PROMOTION_PACKAGE_VERSION,
        "mode": "asset_reference_promotion_package",
        "generated_at": _utc_now(),
        "report_id": request["report_id"],
        "status": "ready_for_operator_asset_reference_promotion",
        "dry_run": {
            "report_id": request["report_id"],
            "report_version": report["report_version"],
            "source_id": report["source"]["source_id"],
            "source_class": report["source"]["source_class"],
            "source_reference": {
                "reference_type": request["source_reference"]["reference_type"],
                "redacted_id": request["source_reference"]["redacted_id"],
                "inventory_hash": request["source_reference"]["inventory_hash"],
            },
            "source_inventory": _source_inventory_summary(report),
            "license_status": report["source"]["license_status"],
            "rights_status": "operator_confirmed",
            "estimated_world_mutations": report["summary"]["estimated_world_mutations"],
        },
        "operator_approval": {
            "approval_state": "approved",
            "operator": request["operator"],
            "agent_id": request["agent_id"],
            "approved_actions": request["approved_actions"],
            "target_world": target_world,
            "rollback_policy": request["rollback_policy"],
            "budget": request["budget"],
        },
        "approved_asset_reference_actions": _asset_reference_approval_summary(
            asset_actions,
            task_definitions,
        ),
        "apply_plan_summary": {
            "summary_version": apply_plan["summary_version"],
            "apply_id": apply_plan["apply_id"],
            "status": apply_plan["status"],
            "approved_actions": apply_plan["approved_actions"],
            "mutation_cost_actual": apply_plan["mutation_cost_actual"],
            "rollback_records": apply_plan["rollback_records"],
            "audit_record_count": apply_plan["audit_record_count"],
            "safety": apply_plan["safety"],
        },
        "no_world_mutation_task_summary": task_summary,
        "budget_gates": _asset_budget_gates(request, asset_actions),
        "capability_gates": _asset_capability_gates(task_summary),
        "unsupported_feature_summary": _unsupported_feature_summary(report),
        "operator_next_actions": [
            "Archive this package with the reviewed dry-run and approval artifacts.",
            "Keep source textures, sounds, and model metadata operator-supplied outside the fork.",
            "Use the planned tasks as manifest intent only; do not copy asset bytes or mutate a world.",
        ],
        "safety": {
            "public_safe_source": True,
            "assets_remain_operator_supplied": True,
            "no_asset_bytes_embedded": True,
            "no_raw_payloads": True,
            "no_private_source_paths": True,
            "no_proprietary_assets": True,
            "no_behavior_script_execution": True,
            "no_world_mutation": True,
            "no_live_family_world_mutation": True,
            "world_mutation_executed": False,
        },
    }
    if _package_has_private_source_paths(package):
        raise ValueError("asset-reference promotion package cannot include private source paths")
    _assert_no_asset_payloads(package)
    return package


def _runtime_apply_task_from_definition(definition, target_world):
    staged_apply = definition["staged_apply"]
    return {
        "task_id": definition["task_id"] + ":apply-smoke",
        "entrypoint": staged_apply["task_constructor"],
        "agent_id": definition["agent_id"],
        "owner": definition["owner"],
        "label": definition["label"],
        "report_id": definition["provenance"]["report_id"],
        "action_index": definition["provenance"]["action_index"],
        "world_id": target_world["world_id"],
        "target_world": target_world,
        "staging": True,
        "explicit_approval": True,
        "allow_mutation": True,
        "rollback_policy": definition["rollback"]["policy"],
        "placements": staged_apply["placements"],
        "placement_count": staged_apply["placement_count"],
        "chunk_size": staged_apply["chunk_size"],
        "chunk_count": staged_apply["chunk_count"],
        "max_node_writes_total": definition["budget"]["max_node_writes_total"],
        "max_node_writes_per_step": definition["budget"]["max_node_writes_per_step"],
        "max_mapblock_churn_total": definition["budget"]["max_mapblock_churn_total"],
        "max_wall_time_ms": definition["budget"]["max_wall_time_ms"],
        "required_capabilities": definition["required_capabilities"],
        "source_reference": definition["provenance"]["source_reference"],
        "operator_supplied_runtime_hooks": [
            "get_node",
            "set_node",
            "persist_record",
        ],
    }


def _runtime_rollback_task_from_definition(definition, apply_task, target_world):
    staged_apply = definition["staged_apply"]
    rollback_mapblock_budget = max(
        definition["budget"]["max_mapblock_churn_total"],
        staged_apply["placement_count"],
    )
    return {
        "task_id": definition["task_id"] + ":rollback-smoke",
        "entrypoint": staged_apply["rollback_execute_entrypoint"],
        "agent_id": "compat_rollback:runtime",
        "owner": definition["owner"],
        "label": "compat.structure.rollback",
        "source_task_id": apply_task["task_id"],
        "world_id": target_world["world_id"],
        "target_world": target_world,
        "staging": True,
        "explicit_approval": True,
        "allow_mutation": True,
        "rollback_policy": definition["rollback"]["policy"],
        "reverse_order": True,
        "max_node_writes_total": definition["budget"]["max_node_writes_total"],
        "max_node_writes_per_step": definition["budget"]["max_node_writes_per_step"],
        "max_mapblock_churn_total": rollback_mapblock_budget,
        "max_wall_time_ms": definition["budget"]["max_wall_time_ms"],
        "required_capabilities": [
            "admin.override",
            "rollback.execute",
            "world.batch",
            "world.place",
        ],
        "operator_supplied_runtime_hooks": [
            "get_node",
            "set_node",
            "persist_record",
            "inspect_record",
        ],
    }


def build_adapter_apply_smoke(report, request):
    """Build a reviewed synthetic adapter apply-and-rollback smoke manifest."""
    target_world = _require_disposable_staging_world(request)
    task_definitions = build_apply_task_definitions(report, request)
    apply_tasks = []
    rollback_tasks = []
    approved_actions = []
    totals = {
        "node_writes": 0,
        "mapblock_churn": 0,
        "media_files": 0,
        "entity_definitions": 0,
        "manual_review_items": 0,
    }

    for definition in task_definitions:
        staged_apply = definition.get("staged_apply")
        if not staged_apply:
            continue
        if staged_apply.get("task_constructor") != "core.ai_import_ops.define_chunked_structure_apply_task":
            raise ValueError("adapter apply smoke requires chunked structure apply")
        if staged_apply.get("rollback_execute_entrypoint") != "core.ai_import_ops.queue_chunked_structure_rollback_task":
            raise ValueError("adapter apply smoke requires chunked rollback execution")
        if definition["rollback"]["policy"] != "chunked":
            raise ValueError("adapter apply smoke requires rollback_policy.policy chunked")
        apply_task = _runtime_apply_task_from_definition(definition, target_world)
        rollback_task = _runtime_rollback_task_from_definition(definition, apply_task, target_world)
        apply_tasks.append(apply_task)
        rollback_tasks.append(rollback_task)
        approved_actions.append({
            "action_index": definition["provenance"]["action_index"],
            "action": definition["source_action"]["action"],
            "task_id": apply_task["task_id"],
        })
        cost = definition["source_action"]["mutation_cost"]
        for key in totals:
            totals[key] += cost.get(key, 0)

    if not apply_tasks:
        raise ValueError("adapter apply smoke requires an approved synthetic structure adapter action")

    smoke = {
        "smoke_version": ADAPTER_APPLY_SMOKE_VERSION,
        "mode": "adapter_apply_smoke",
        "generated_at": _utc_now(),
        "report_id": request["report_id"],
        "status": "ready",
        "target_world": target_world,
        "approved_actions": approved_actions,
        "apply_tasks": apply_tasks,
        "rollback_plan": {
            "entrypoint": "core.ai_import_ops.plan_structure_rollback",
            "source_task_ids": [task["task_id"] for task in apply_tasks],
            "readback_required": True,
            "will_mutate": False,
        },
        "rollback_tasks": rollback_tasks,
        "mutation_cost_expected": totals,
        "operator_summary": {
            "status": "ready_for_disposable_staging_smoke",
            "apply_task_count": len(apply_tasks),
            "rollback_task_count": len(rollback_tasks),
            "expected_node_writes": totals["node_writes"],
            "expected_mapblock_churn": totals["mapblock_churn"],
            "expected_apply_chunks": sum(task["chunk_count"] for task in apply_tasks),
            "expected_rollback_chunks": sum(task["chunk_count"] for task in apply_tasks),
        },
        "operator_next_actions": [
            "Run apply tasks only in the declared disposable staging world.",
            "Read rollback records back through core.ai_import_ops.plan_structure_rollback.",
            "Run rollback tasks only after reviewing the rollback plan.",
            "Discard the disposable staging world after the smoke.",
        ],
        "safety": {
            "synthetic_only": True,
            "disposable_staging_only": True,
            "dry_run_report_unchanged": True,
            "assets_remain_operator_supplied": True,
            "no_live_family_world_mutation": True,
            "world_mutation_executed": False,
        },
    }
    smoke_errors = validate_adapter_apply_smoke(smoke)
    if smoke_errors:
        raise ValueError(smoke_errors[0])
    return smoke


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


def _print_adapter_apply_smoke_summary(smoke):
    operator_summary = smoke["operator_summary"]
    print(
        "smoke={status} report={report} apply_tasks={apply_tasks} "
        "chunks={chunks} expected_writes={writes} rollback_tasks={rollback_tasks}".format(
            status=operator_summary["status"],
            report=smoke["report_id"],
            apply_tasks=operator_summary["apply_task_count"],
            chunks=operator_summary["expected_apply_chunks"],
            writes=operator_summary["expected_node_writes"],
            rollback_tasks=operator_summary["rollback_task_count"],
        )
    )


def _print_adapter_smoke_review_summary(review):
    summary = review["summary"]
    print(
        "review={status} report={report} target={target} placements={placements} "
        "chunks={chunks} findings={findings} rollback_tasks={rollback_tasks}".format(
            status=review["status"],
            report=review.get("report_id"),
            target=review.get("target_world", {}).get("world_id"),
            placements=summary["placement_count"],
            chunks=summary["chunk_count"],
            findings=len(review["findings"]),
            rollback_tasks=summary["rollback_task_count"],
        )
    )


def _print_promotion_package_summary(package):
    apply_summary = package["apply_task_summary"]
    rollback_summary = package["rollback_task_summary"]
    print(
        "promotion={status} report={report} target={target} apply_tasks={apply_tasks} "
        "placements={placements} rollback_tasks={rollback_tasks}".format(
            status=package["status"],
            report=package["report_id"],
            target=package["operator_approval"]["target_world"]["world_id"],
            apply_tasks=apply_summary["task_count"],
            placements=apply_summary["placement_count"],
            rollback_tasks=rollback_summary["task_count"],
        )
    )


def _print_asset_reference_promotion_package_summary(package):
    task_summary = package["no_world_mutation_task_summary"]
    print(
        "asset_promotion={status} report={report} target={target} asset_tasks={asset_tasks} "
        "unsupported={unsupported}".format(
            status=package["status"],
            report=package["report_id"],
            target=package["operator_approval"]["target_world"]["world_id"],
            asset_tasks=task_summary["task_count"],
            unsupported=package["unsupported_feature_summary"]["count"],
        )
    )


def _print_batch_inventory_summary(queue):
    summary = queue["summary"]
    print(
        "batch_sources={sources} inventory_items={items} manual_review={manual} "
        "blocked={blocked} reports={reports}".format(
            sources=summary["sources_total"],
            items=summary["inventory_items_total"],
            manual=summary["by_status"].get("manual_review", 0),
            blocked=summary["by_status"].get("blocked", 0),
            reports=sum(1 for item in queue["sources"] if item.get("report_path")),
        )
    )


def _print_import_inventory_discovery_summary(report):
    summary = report["summary"]
    print(
        "inventory_discovery={status} sources={sources} inventory_items={items} "
        "partial={partial} blocked={blocked} planned_actions={actions}".format(
            status=report["status"],
            sources=summary["sources_total"],
            items=summary["inventory_items_total"],
            partial=summary["source_status_counts"].get("partial", 0),
            blocked=summary["source_status_counts"].get("blocked", 0),
            actions=summary["planned_actions_total"],
        )
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", help="User-owned pack, structure, or world source to inspect.")
    parser.add_argument("--batch-inventory", help="Directory of user-owned sources to inventory as a dry-run queue.")
    parser.add_argument("--inventory-discovery", help="Directory of user-owned sources to classify for import preview readiness.")
    parser.add_argument("--reports-dir", help="Directory for per-source dry-run reports used with --batch-inventory.")
    parser.add_argument("--apply-plan", help="Dry-run report JSON to plan for apply without mutation.")
    parser.add_argument("--adapter-apply-smoke", help="Dry-run report JSON to turn into a reviewed adapter apply smoke.")
    parser.add_argument("--review-adapter-smoke", help="Adapter apply smoke JSON to review for operator gating.")
    parser.add_argument("--promotion-package", help="Dry-run report JSON to package with reviewed adapter smoke evidence.")
    parser.add_argument("--asset-promotion-package", help="Dry-run resource-pack report JSON to package as no-mutation asset-reference evidence.")
    parser.add_argument("--approval", help="Apply request JSON containing explicit operator approvals.")
    parser.add_argument("--adapter-smoke", help="Adapter apply smoke JSON for --promotion-package.")
    parser.add_argument("--adapter-review", help="Adapter smoke review JSON for --promotion-package.")
    parser.add_argument("--output", help="Write machine-readable JSON report to this path.")
    parser.add_argument("--summary", action="store_true", help="Print a concise human-readable summary.")
    args = parser.parse_args(argv)

    try:
        selected_modes = [
            bool(args.batch_inventory),
            bool(args.inventory_discovery),
            bool(args.apply_plan),
            bool(args.adapter_apply_smoke),
            bool(args.review_adapter_smoke),
            bool(args.promotion_package),
            bool(args.asset_promotion_package),
        ]
        if sum(selected_modes) > 1:
            raise ValueError(
                "--batch-inventory, --inventory-discovery, --apply-plan, --adapter-apply-smoke, "
                "--review-adapter-smoke, --promotion-package, and --asset-promotion-package "
                "cannot be used together"
            )
        if args.reports_dir and not (args.batch_inventory or args.inventory_discovery):
            raise ValueError("--reports-dir is only valid with --batch-inventory or --inventory-discovery")
        if (args.adapter_smoke or args.adapter_review) and not args.promotion_package:
            raise ValueError("--adapter-smoke and --adapter-review are only valid with --promotion-package")
        if args.batch_inventory:
            if not args.reports_dir:
                raise ValueError("--reports-dir is required with --batch-inventory")
            payload_obj = build_batch_inventory_queue(
                args.batch_inventory,
                reports_dir=args.reports_dir,
            )
        elif args.inventory_discovery:
            if not args.reports_dir:
                raise ValueError("--reports-dir is required with --inventory-discovery")
            payload_obj = build_import_inventory_discovery_report(
                args.inventory_discovery,
                reports_dir=args.reports_dir,
            )
        elif args.asset_promotion_package:
            if not args.approval:
                raise ValueError("--approval is required with --asset-promotion-package")
            report = _read_json(pathlib.Path(args.asset_promotion_package))
            request = _read_json(pathlib.Path(args.approval))
            payload_obj = build_asset_reference_promotion_package(report, request)
        elif args.promotion_package:
            if not args.approval:
                raise ValueError("--approval is required with --promotion-package")
            if not args.adapter_smoke:
                raise ValueError("--adapter-smoke is required with --promotion-package")
            if not args.adapter_review:
                raise ValueError("--adapter-review is required with --promotion-package")
            report = _read_json(pathlib.Path(args.promotion_package))
            request = _read_json(pathlib.Path(args.approval))
            smoke = _read_json(pathlib.Path(args.adapter_smoke))
            review = _read_json(pathlib.Path(args.adapter_review))
            payload_obj = build_structure_import_promotion_package(
                report,
                request,
                smoke,
                review,
            )
        elif args.review_adapter_smoke:
            smoke = _read_json(pathlib.Path(args.review_adapter_smoke))
            payload_obj = review_adapter_apply_smoke(smoke)
        elif args.adapter_apply_smoke:
            if not args.approval:
                raise ValueError("--approval is required with --adapter-apply-smoke")
            report = _read_json(pathlib.Path(args.adapter_apply_smoke))
            request = _read_json(pathlib.Path(args.approval))
            payload_obj = build_adapter_apply_smoke(report, request)
        elif args.apply_plan:
            if not args.approval:
                raise ValueError("--approval is required with --apply-plan")
            report = _read_json(pathlib.Path(args.apply_plan))
            request = _read_json(pathlib.Path(args.approval))
            payload_obj = build_apply_plan(report, request)
        else:
            if not args.source:
                raise ValueError("source is required unless a dry-run report mode is used")
            payload_obj = build_report(args.source)
        payload = json.dumps(payload_obj, indent=2, sort_keys=True) + "\n"
        if args.output:
            pathlib.Path(args.output).write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        if args.summary and args.batch_inventory:
            _print_batch_inventory_summary(payload_obj)
        elif args.summary and args.inventory_discovery:
            _print_import_inventory_discovery_summary(payload_obj)
        elif args.summary and args.review_adapter_smoke:
            _print_adapter_smoke_review_summary(payload_obj)
        elif args.summary and args.asset_promotion_package:
            _print_asset_reference_promotion_package_summary(payload_obj)
        elif args.summary and args.promotion_package:
            _print_promotion_package_summary(payload_obj)
        elif args.summary and args.adapter_apply_smoke:
            _print_adapter_apply_smoke_summary(payload_obj)
        elif args.summary and not args.apply_plan:
            _print_summary(payload_obj)
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
