#!/usr/bin/env python3
"""Verify the AI Runtime product profile keeps fixtures behind explicit gates."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


MANIFEST_PATH = pathlib.Path("games/ai_runtime/product_profile_manifest.json")
PROFILE_DIR = pathlib.Path("games/ai_runtime")
BUILTIN_INIT = pathlib.Path("builtin/game/init.lua")
AI_NATIVE_DEFAULT_BUILTINS = {
    "ai_runtime.lua",
    "ai_operator_status.lua",
    "ai_operator_task_control.lua",
    "ai_runtime_commands.lua",
    "repair_agent.lua",
    "build_agent.lua",
    "ai_agent_plugin.lua",
}
PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload|/Users/",
    re.I,
)
RUNTIME_SOURCE_PRIVATE_PATTERNS = re.compile(
    r"192\.168(?:\.\d{1,3}){2}|(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|"
    r"/Users/[A-Za-z0-9._-]+",
    re.I,
)
PROFILE_CODE_FIXTURE_PATTERNS = re.compile(
	r"ai_runtime_test|devtest|enable_smoke_command|enable_demo_benchmark_command|"
	r"enable_model_adapter_probe_command|enable_agents_sdk_adapter|"
	r"admin\.override|import\.assets|combat\.defend",
    re.I,
)


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _profile_mods(root):
    mods_dir = root / PROFILE_DIR / "mods"
    if not mods_dir.is_dir():
        return []
    return sorted(
        path.name
        for path in mods_dir.iterdir()
        if path.is_dir() and (path / "mod.conf").is_file()
    )


def _surface_status(root, surface):
    source_file = root / surface["source_file"]
    init_file = root / BUILTIN_INIT
    body = source_file.read_text(encoding="utf-8") if source_file.is_file() else ""
    init_body = init_file.read_text(encoding="utf-8") if init_file.is_file() else ""
    setting_expr = f'core.settings:get_bool("{surface["setting"]}", false)'
    command_expr = f'core.register_chatcommand("{surface["command"]}"'
    load_expr = f'dofile(gamepath .. "{pathlib.Path(surface["source_file"]).name}")'
    setting_index = body.find(setting_expr)
    command_index = body.find(command_expr)
    init_setting_index = init_body.find(setting_expr)
    load_index = init_body.find(load_expr)
    command_gated = setting_index >= 0 and command_index >= 0 and setting_index < command_index
    module_load_gated = init_setting_index >= 0 and load_index >= 0 and init_setting_index < load_index
    gated = command_gated and module_load_gated
    return {
        "name": surface["name"],
        "setting": surface["setting"],
        "source_file": surface["source_file"],
        "command": surface["command"],
        "default_enabled": surface.get("default_enabled") is True,
        "status": "gated" if gated and surface.get("default_enabled") is not True else "violation",
        "setting_gate_present": setting_index >= 0,
        "command_present": command_index >= 0,
        "module_load_gated": module_load_gated,
    }


def _runtime_surface_status(root, surface):
    source_file = root / surface["source_file"]
    init_file = root / BUILTIN_INIT
    body = source_file.read_text(encoding="utf-8") if source_file.is_file() else ""
    init_body = init_file.read_text(encoding="utf-8") if init_file.is_file() else ""
    module_name = pathlib.Path(surface["source_file"]).name
    load_expr = f'dofile(gamepath .. "{module_name}")'
    command_expr = f'core.register_chatcommand("{surface["command"]}"'
    privilege = surface["privilege"]
    privilege_re = re.compile(r"privs\s*=\s*\{[^}]*\b" + re.escape(privilege) + r"\s*=\s*true")
    loaded_by_default = load_expr in init_body
    command_registered = command_expr in body
    server_privilege_required = privilege_re.search(body) is not None
    public_safe_source = RUNTIME_SOURCE_PRIVATE_PATTERNS.search(body) is None
    public_safe_required = surface.get("public_safe_output_required") is True
    status = "present"
    if not (
        source_file.is_file()
        and loaded_by_default
        and command_registered
        and server_privilege_required
        and public_safe_source
        and public_safe_required
        and surface.get("loaded_by_default_product_profile") is True
    ):
        status = "violation"
    return {
        "name": surface["name"],
        "source_file": surface["source_file"],
        "command": surface["command"],
        "privilege": privilege,
        "mutation_scope": surface["mutation_scope"],
        "loaded_by_default_product_profile": loaded_by_default
        and surface.get("loaded_by_default_product_profile") is True,
        "public_safe_output_required": public_safe_required,
        "status": status,
        "source_file_present": source_file.is_file(),
        "module_loaded_by_default": loaded_by_default,
        "command_registered": command_registered,
        "server_privilege_required": server_privilege_required,
        "public_safe_source": public_safe_source,
    }


def _profile_private_matches(root):
    matches = []
    for path in sorted((root / PROFILE_DIR).rglob("*")):
        if not path.is_file():
            continue
        body = path.read_text(encoding="utf-8", errors="ignore")
        if PRIVATE_PATTERNS.search(body):
            matches.append(path.relative_to(root).as_posix())
    return matches


def _profile_code_fixture_matches(root):
    matches = []
    mods_dir = root / PROFILE_DIR / "mods"
    code_paths = [root / PROFILE_DIR / "game.conf"]
    if mods_dir.is_dir():
        code_paths.extend(mods_dir.rglob("*.lua"))
        code_paths.extend(mods_dir.rglob("*.conf"))
    for path in sorted(path for path in code_paths if path.is_file()):
        body = path.read_text(encoding="utf-8", errors="ignore")
        if PROFILE_CODE_FIXTURE_PATTERNS.search(body):
            matches.append(path.relative_to(root).as_posix())
    return matches


def _default_ai_builtin_modules(root):
    init_body = (root / BUILTIN_INIT).read_text(encoding="utf-8")
    modules = []
    for module_name in sorted(AI_NATIVE_DEFAULT_BUILTINS):
        load_expr = f'dofile(gamepath .. "{module_name}")'
        if load_expr in init_body:
            modules.append(f"builtin/game/{module_name}")
    return modules


def _manifest_default_builtin_modules(startup_inventory):
    return sorted(
        entry["path"]
        for entry in startup_inventory
        if entry["loaded_by_default_product_profile"] is True
        and entry["path"].startswith("builtin/game/")
    )


def build_report(root):
    root = pathlib.Path(root)
    manifest = _read_json(root / MANIFEST_PATH)
    actual_mods = _profile_mods(root)
    expected_mods = sorted(manifest["product_mods"])
    surfaces = [_surface_status(root, surface) for surface in manifest["explicit_dev_surfaces"]]
    runtime_surfaces = [
        _runtime_surface_status(root, surface)
        for surface in manifest.get("required_runtime_surfaces", [])
    ]
    startup_inventory = manifest["startup_inventory"]
    default_ai_builtin_modules = _default_ai_builtin_modules(root)
    manifest_default_builtin_modules = _manifest_default_builtin_modules(startup_inventory)

    violations = []
    if actual_mods != expected_mods:
        violations.append({
            "kind": "product_mods_mismatch",
            "expected": expected_mods,
            "actual": actual_mods,
        })
    missing_default_modules = sorted(
        set(default_ai_builtin_modules) - set(manifest_default_builtin_modules)
    )
    unexpected_default_modules = sorted(
        set(manifest_default_builtin_modules) - set(default_ai_builtin_modules)
    )
    if missing_default_modules:
        violations.append({
            "kind": "startup_inventory_missing_default_builtin_modules",
            "paths": missing_default_modules,
        })
    if unexpected_default_modules:
        violations.append({
            "kind": "startup_inventory_unexpected_default_builtin_modules",
            "paths": unexpected_default_modules,
        })
    for surface in surfaces:
        if surface["status"] != "gated":
            violations.append({
                "kind": "dev_surface_not_gated",
                "surface": surface["name"],
                "setting": surface["setting"],
            })
    for surface in runtime_surfaces:
        if surface["status"] != "present":
            violations.append({
                "kind": "required_runtime_surface_missing_or_invalid",
                "surface": surface["name"],
                "command": surface["command"],
            })
    private_matches = _profile_private_matches(root)
    if private_matches:
        violations.append({
            "kind": "private_or_fixture_content_in_profile",
            "paths": private_matches,
        })
    profile_code_fixture_matches = _profile_code_fixture_matches(root)
    if profile_code_fixture_matches:
        violations.append({
            "kind": "fixture_or_privileged_surface_in_profile_code",
            "paths": profile_code_fixture_matches,
        })
    for entry in startup_inventory:
        if entry["category"] in {"benchmark_fixture", "compatibility_fixture", "unit_test_helper"}:
            if entry["loaded_by_default_product_profile"] is True:
                violations.append({
                    "kind": "fixture_loaded_by_default_product_profile",
                    "name": entry["name"],
                    "category": entry["category"],
                })
            if entry["requires_explicit_dev_or_test_lane"] is not True:
                violations.append({
                    "kind": "fixture_missing_explicit_dev_or_test_lane",
                    "name": entry["name"],
                    "category": entry["category"],
                })

    return {
        "schema_version": 1,
        "status": "pass" if not violations else "fail",
        "profile": {
            "gameid": manifest["gameid"],
            "manifest_path": MANIFEST_PATH.as_posix(),
            "product_mods": actual_mods,
        },
        "startup_inventory": startup_inventory,
        "default_ai_builtin_modules": default_ai_builtin_modules,
        "manifest_default_builtin_modules": manifest_default_builtin_modules,
        "required_runtime_surfaces": runtime_surfaces,
        "explicit_dev_surfaces": surfaces,
        "test_only_files": manifest["test_only_files"],
        "test_only_paths": manifest["test_only_paths"],
        "violations": violations,
        "safety": {
            "no_private_content": not private_matches,
            "dev_surfaces_disabled_by_default": all(
                surface["status"] == "gated" and surface["default_enabled"] is False
                for surface in surfaces
            ),
            "test_fixtures_explicit_only": all(
                entry["loaded_by_default_product_profile"] is not True
                and entry["requires_explicit_dev_or_test_lane"] is True
                for entry in startup_inventory
                if entry["category"] in {
                    "benchmark_fixture",
                    "compatibility_fixture",
                    "unit_test_helper",
                }
            ),
            "runtime_surfaces_available": bool(runtime_surfaces)
            and all(surface["status"] == "present" for surface in runtime_surfaces),
            "startup_inventory_matches_default_runtime": (
                default_ai_builtin_modules == manifest_default_builtin_modules
            ),
            "profile_code_fixture_free": not profile_code_fixture_matches,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root to verify.")
    parser.add_argument("--output", help="Write JSON report to this path.")
    args = parser.parse_args(argv)

    try:
        report = build_report(pathlib.Path(args.root))
        payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.output:
            output_path = pathlib.Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        return 0 if report["status"] == "pass" else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
