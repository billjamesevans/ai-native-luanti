#!/usr/bin/env python3
"""Verify the OpenRealm Advantage Kit is present, public-safe, and usable."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import struct
import subprocess
import sys
import tomllib


KIT_DIR = pathlib.Path("openrealm_advantage_kit")
MANIFEST_PATH = KIT_DIR / "openrealm_advantage_manifest.json"
PYPROJECT_PATH = KIT_DIR / "pyproject.toml"
SCHEMA_PATH = KIT_DIR / "schemas/openrealm_plan.schema.json"

REQUIRED_FILES = [
    "README.md",
    "README_FIRST.md",
    "VALIDATION_REPORT.md",
    "openrealm_advantage_manifest.json",
    "pyproject.toml",
    "schemas/openrealm_plan.schema.json",
    "studio/index.html",
    "studio/app.js",
    "studio/styles.css",
    "web_demo/index.html",
    "web_demo/app.js",
    "web_demo/style.css",
    "openrealm_creator_kernel/cli.py",
    "openrealm_creator_kernel/parser.py",
    "openrealm_creator_kernel/planner.py",
    "openrealm_creator_kernel/safety.py",
    "openrealm_creator_kernel/luanti_generator.py",
    "openrealm_creator_kernel/server.py",
    "luanti_mod/openrealm_creator/init.lua",
    "luanti_mod/openrealm_creator/mod.conf",
    "lua_runtime/openrealm_runtime/init.lua",
    "lua_runtime/openrealm_runtime/mod.conf",
    "docs/PRODUCT_ADVANTAGE.md",
    "docs/ARCHITECTURE.md",
    "docs/LUANTI_INTEGRATION.md",
    "docs/LOCAL_HTTP_API.md",
    "docs/NEXT_ISSUES.md",
    "examples/prompts/moonstone_ore.txt",
    "examples/prompts/cozy_lakeside_village.txt",
    "examples/prompts/glacier_biome.txt",
]

REQUIRED_ASSETS = {
    "assets/openrealm_brand_style_guide.png": {
        "sha256": "fa3487807ec4339e43d8d7fbeb0c5499e3a516e321d0c40a7db82bb2225f5e23",
        "width": 1672,
        "height": 941,
        "role": "brand_style_guide",
    },
    "assets/openrealm_brand_assets_sheet.png": {
        "sha256": "934436955b8f7b8fe80d4dd73539ec53e27f210edfc0e9967555473ef9d796fe",
        "width": 1448,
        "height": 1086,
        "role": "brand_assets_sheet",
    },
    "assets/openrealm_creator_studio_mockup.png": {
        "sha256": "dd7350431b2fa1bd3e80831cb01e53413055633a7531e60c6759eef3f0e1b53e",
        "width": 1672,
        "height": 941,
        "role": "creator_studio_mockup",
    },
    "assets/openrealm_future_key_art.png": {
        "sha256": "23fe94d8bb588d592e672f1008c59d7fcfaeeae3d43d1650ad552ce2ef830f7d",
        "width": 1672,
        "height": 941,
        "role": "future_key_art",
    },
    "assets/openrealm_creator_flow.png": {
        "sha256": "1ee2d59034e1e971d294166ab709afbbfdd7bb1cb02225ebed6945244762cf25",
        "width": 1672,
        "height": 941,
        "role": "creator_flow",
    },
    "assets/how_nova_ai_works.png": {
        "sha256": "3c357568623eb7d04c742f6d825060248c2f9240005cbe2f5fdf7b8c899e13fe",
        "width": 1672,
        "height": 941,
        "role": "nova_architecture",
    },
    "assets/openrealm_roadmap_ecosystem.png": {
        "sha256": "8b4d728e6de96e73c6083267af05a68ca18eb17cac5a0e3b0440eb7c09721a89",
        "width": 1672,
        "height": 941,
        "role": "roadmap_ecosystem",
    },
}

REQUIRED_DOC_PHRASES = {
    "README.md": [
        "Nova may propose. OpenRealm validates. Luanti mutates only through safe generated runtime code.",
        "Prompt -> structured world recipe",
        "All mutation is approval-oriented, bounded, and rollback-aware",
    ],
    "docs/ARCHITECTURE.md": [
        "Nova is a planner. OpenRealm is the safety boundary. Luanti is the world authority.",
        "Why not direct code generation?",
        "Route generated plans into the existing AI runtime task queue.",
    ],
    "docs/LUANTI_INTEGRATION.md": [
        "Copy the generated mod folder into a disposable OpenRealm `ai_runtime` world",
        "/or_preview",
        "/or_rollback_last",
        "`/or_build` does not mutate directly.",
    ],
    "docs/NEXT_ISSUES.md": [
        "Add OpenRealm Plan schema as product contract",
        "Route generated structures through AI runtime task queue",
        "Add golden prompt evaluation suite",
    ],
}

GENERATED_RUNTIME_LUA_FILES = [
    "luanti_mod/openrealm_creator/init.lua",
    "examples/generated/demo_1/generated_luanti_mod/openrealm_moonstone/init.lua",
    "examples/generated/demo_2/generated_luanti_mod/openrealm_lakeside_village/init.lua",
    "examples/generated/demo_3/generated_luanti_mod/openrealm_glacier_biome/init.lua",
    "out/moonstone_check/generated_luanti_mod/openrealm_moonstone/init.lua",
]

GENERATED_RUNTIME_REQUIRED_PHRASES = (
    "queue_chunked_structure_apply_task",
    "OpenRealm AI runtime import queue is not available",
    'mutation_class = "compat_import"',
)

GENERATED_RUNTIME_FORBIDDEN_PHRASES = (
    "minetest.set_node",
    "minetest.get_node_or_nil",
)

REQUIRED_MANIFEST = {
    "schema_version": 1,
    "product_name": "OpenRealm",
    "assistant_name": "Nova",
}

REQUIRED_SAFETY_MODEL = {
    "direct_ai_world_mutation": False,
    "preview_required": True,
    "human_approval_required": True,
    "audit_required": True,
    "rollback_required": True,
}

PRIVATE_BOUNDARY_PATTERNS = (
    "spacebase",
    "themepark",
    "disneyland100",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GITHUB_TOKEN",
    "AWS_SECRET_ACCESS_KEY",
    "sk-proj-",
    "sk-svcacct-",
    "/Users/",
    "minecraftpi.home",
    "192.168.",
)

PRIVATE_BOUNDARY_GUARD_BLOCKS = {
    "openrealm_advantage_kit/studio/server.py": "PRIVATE_PATTERNS = (",
}

SKIP_TEXT_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".zip",
    ".pyc",
}


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_size(path: pathlib.Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"{path} is not a valid PNG")
    return struct.unpack(">II", header[16:24])


def read_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def text_files(root: pathlib.Path) -> list[pathlib.Path]:
    kit = root / KIT_DIR
    if not kit.is_dir():
        return []
    files = []
    for path in kit.rglob("*"):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts:
            continue
        if path.suffix.lower() in SKIP_TEXT_EXTS:
            continue
        files.append(path)
    return sorted(files)


def private_boundary_matches(root: pathlib.Path) -> list[dict]:
    matches = []
    for path in text_files(root):
        rel = path.relative_to(root).as_posix()
        guard_start = PRIVATE_BOUNDARY_GUARD_BLOCKS.get(rel)
        in_guard_block = False
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(),
            start=1,
        ):
            stripped = line.strip()
            if guard_start and stripped.startswith(guard_start):
                in_guard_block = True
                continue
            if in_guard_block:
                if stripped == ")":
                    in_guard_block = False
                continue
            for pattern in PRIVATE_BOUNDARY_PATTERNS:
                if pattern in line:
                    matches.append({
                        "path": rel,
                        "line": line_number,
                        "pattern": pattern,
                    })
    return matches


def run_command(command: list[str], *, cwd: pathlib.Path) -> dict:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "status": "pass" if completed.returncode == 0 else "fail",
        "stdout_tail": completed.stdout[-2000:],
        "stderr_tail": completed.stderr[-2000:],
    }


def build_report(
    root: pathlib.Path | str,
    *,
    run_tests: bool = False,
    run_js_check: bool = False,
) -> dict:
    root = pathlib.Path(root)
    kit = root / KIT_DIR
    violations: list[dict] = []

    missing_files = [rel for rel in REQUIRED_FILES if not (kit / rel).is_file()]
    if missing_files:
        violations.append({"kind": "missing_required_files", "paths": missing_files})

    asset_reports = []
    for rel, expected in REQUIRED_ASSETS.items():
        path = kit / rel
        asset_report = {
            "path": f"{KIT_DIR.as_posix()}/{rel}",
            "role": expected["role"],
            "expected_sha256": expected["sha256"],
            "expected_width": expected["width"],
            "expected_height": expected["height"],
            "status": "missing",
        }
        if path.is_file():
            digest = sha256_file(path)
            width, height = png_size(path)
            asset_report.update({
                "sha256": digest,
                "width": width,
                "height": height,
                "status": "pass",
            })
            if digest != expected["sha256"]:
                asset_report["status"] = "fail"
                violations.append({
                    "kind": "asset_hash_mismatch",
                    "path": asset_report["path"],
                    "expected": expected["sha256"],
                    "actual": digest,
                })
            if (width, height) != (expected["width"], expected["height"]):
                asset_report["status"] = "fail"
                violations.append({
                    "kind": "asset_dimensions_mismatch",
                    "path": asset_report["path"],
                    "expected": [expected["width"], expected["height"]],
                    "actual": [width, height],
                })
        else:
            violations.append({"kind": "missing_required_asset", "path": asset_report["path"]})
        asset_reports.append(asset_report)

    manifest = {}
    if (root / MANIFEST_PATH).is_file():
        manifest = read_json(root / MANIFEST_PATH)
        for key, expected in REQUIRED_MANIFEST.items():
            if manifest.get(key) != expected:
                violations.append({
                    "kind": "manifest_field_mismatch",
                    "field": key,
                    "expected": expected,
                    "actual": manifest.get(key),
                })
        safety_model = manifest.get("safety_model", {})
        for key, expected in REQUIRED_SAFETY_MODEL.items():
            if safety_model.get(key) is not expected:
                violations.append({
                    "kind": "manifest_safety_model_mismatch",
                    "field": key,
                    "expected": expected,
                    "actual": safety_model.get(key),
                })
    else:
        violations.append({"kind": "missing_manifest", "path": MANIFEST_PATH.as_posix()})

    pyproject = {}
    if (root / PYPROJECT_PATH).is_file():
        pyproject = tomllib.loads((root / PYPROJECT_PATH).read_text(encoding="utf-8"))
        tool_openrealm = pyproject.get("tool", {}).get("openrealm", {})
        if tool_openrealm.get("product") != "OpenRealm":
            violations.append({"kind": "pyproject_product_mismatch"})
        if tool_openrealm.get("assistant") != "Nova":
            violations.append({"kind": "pyproject_assistant_mismatch"})
    else:
        violations.append({"kind": "missing_pyproject", "path": PYPROJECT_PATH.as_posix()})

    schema = {}
    if (root / SCHEMA_PATH).is_file():
        schema = read_json(root / SCHEMA_PATH)
        required_schema_keys = {"plan_id", "title", "plan_kind", "mod_name", "summary", "safety_budget"}
        actual_schema_keys = set(schema.get("properties", {}))
        missing_schema_keys = sorted(required_schema_keys - actual_schema_keys)
        if missing_schema_keys:
            violations.append({
                "kind": "schema_missing_required_properties",
                "properties": missing_schema_keys,
            })
    else:
        violations.append({"kind": "missing_schema", "path": SCHEMA_PATH.as_posix()})

    doc_reports = []
    for rel, phrases in REQUIRED_DOC_PHRASES.items():
        path = kit / rel
        missing = []
        if path.is_file():
            body = path.read_text(encoding="utf-8")
            missing = [phrase for phrase in phrases if phrase not in body]
        else:
            missing = phrases
        doc_reports.append({
            "path": f"{KIT_DIR.as_posix()}/{rel}",
            "status": "pass" if not missing else "fail",
            "missing_phrases": missing,
        })
        if missing:
            violations.append({
                "kind": "required_doc_phrases_missing",
                "path": f"{KIT_DIR.as_posix()}/{rel}",
                "phrases": missing,
            })

    generated_runtime_reports = []
    for rel in GENERATED_RUNTIME_LUA_FILES:
        path = kit / rel
        missing = list(GENERATED_RUNTIME_REQUIRED_PHRASES)
        forbidden = []
        status = "missing"
        if path.is_file():
            body = path.read_text(encoding="utf-8")
            missing = [phrase for phrase in GENERATED_RUNTIME_REQUIRED_PHRASES if phrase not in body]
            forbidden = [phrase for phrase in GENERATED_RUNTIME_FORBIDDEN_PHRASES if phrase in body]
            status = "pass" if not missing and not forbidden else "fail"
        generated_runtime_reports.append({
            "path": f"{KIT_DIR.as_posix()}/{rel}",
            "status": status,
            "missing_phrases": missing,
            "forbidden_phrases": forbidden,
        })
        if status != "pass":
            violations.append({
                "kind": "generated_runtime_queue_contract_failed",
                "path": f"{KIT_DIR.as_posix()}/{rel}",
                "missing_phrases": missing,
                "forbidden_phrases": forbidden,
            })

    private_matches = private_boundary_matches(root)
    if private_matches:
        violations.append({
            "kind": "private_boundary_pattern_in_kit",
            "matches": private_matches,
        })

    test_result = {"status": "not_run"}
    if run_tests:
        test_result = run_command(["python3", "-m", "unittest", "discover", "tests"], cwd=kit)
        if test_result["status"] != "pass":
            violations.append({
                "kind": "advantage_kit_tests_failed",
                "returncode": test_result["returncode"],
            })

    js_result = {"status": "not_run"}
    if run_js_check:
        js_result = run_command(["node", "--check", "studio/app.js"], cwd=kit)
        if js_result["status"] != "pass":
            violations.append({
                "kind": "advantage_kit_js_check_failed",
                "returncode": js_result["returncode"],
            })

    safety = {
        "manifest_blocks_direct_ai_world_mutation": (
            manifest.get("safety_model", {}).get("direct_ai_world_mutation") is False
        ),
        "manifest_requires_preview_approval_audit_rollback": all(
            manifest.get("safety_model", {}).get(key) is True
            for key in ("preview_required", "human_approval_required", "audit_required", "rollback_required")
        ),
        "canonical_assets_present": all(asset["status"] == "pass" for asset in asset_reports),
        "schema_present": bool(schema),
        "private_boundary_clean": not private_matches,
        "required_docs_complete": all(doc["status"] == "pass" for doc in doc_reports),
        "generated_mods_use_runtime_queue": all(
            item["status"] == "pass" for item in generated_runtime_reports
        ),
    }
    for key, value in safety.items():
        if value is not True:
            violations.append({"kind": "advantage_kit_safety_gate_failed", "gate": key})

    return {
        "schema_version": 1,
        "status": "pass" if not violations else "fail",
        "kit": {
            "path": KIT_DIR.as_posix(),
            "manifest_path": MANIFEST_PATH.as_posix(),
            "schema_path": SCHEMA_PATH.as_posix(),
            "product_name": manifest.get("product_name"),
            "assistant_name": manifest.get("assistant_name"),
        },
        "assets": asset_reports,
        "docs": doc_reports,
        "generated_runtime": generated_runtime_reports,
        "test_result": test_result,
        "js_check_result": js_result,
        "safety": safety,
        "violations": violations,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root to verify.")
    parser.add_argument("--output", help="Write JSON report to this path.")
    parser.add_argument("--run-tests", action="store_true", help="Run Advantage Kit unit tests.")
    parser.add_argument("--run-js-check", action="store_true", help="Run node --check for the studio JS.")
    args = parser.parse_args(argv)

    try:
        report = build_report(args.root, run_tests=args.run_tests, run_js_check=args.run_js_check)
        payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.output:
            output_path = pathlib.Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        return 0 if report["status"] == "pass" else 2
    except (OSError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
