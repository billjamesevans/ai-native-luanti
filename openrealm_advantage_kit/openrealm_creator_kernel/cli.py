from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from .luanti_generator import generate_luanti_mod
from .packager import write_audit_manifest, zip_directory
from .planner import plan_from_prompt
from .preview import write_preview
from .safety import validate_plan

DEMO_PROMPTS = [
    "Add a new ore called moonstone that spawns below level -200 and crafts a glowing sword",
    "Build a cozy lakeside village with floating lanterns",
    "Make this biome feel like Glacier National Park",
]


def build_artifacts(prompt: str, out: Path, *, package: bool = True) -> dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    plan = plan_from_prompt(prompt)
    report = validate_plan(plan)
    report.raise_for_errors()

    plan_path = out / "openrealm_plan.json"
    preview_path = out / "preview.html"
    audit_path = out / "audit_manifest.json"
    mod_root = out / "generated_luanti_mod"

    plan_path.write_text(plan.to_json() + "\n", encoding="utf-8")
    write_preview(plan, preview_path)
    write_audit_manifest(plan, audit_path)
    mod_dir = generate_luanti_mod(plan, mod_root)

    result = {
        "plan": plan_path,
        "preview": preview_path,
        "audit": audit_path,
        "mod_dir": mod_dir,
    }
    if package:
        result["package"] = zip_directory(mod_dir, out / "openrealm_package.zip")
    return result


def command_plan(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    plan = plan_from_prompt(args.prompt)
    report = validate_plan(plan)
    plan_path = out / "openrealm_plan.json"
    preview_path = out / "preview.html"
    plan_path.write_text(plan.to_json() + "\n", encoding="utf-8")
    write_preview(plan, preview_path)
    if not report.ok:
        for issue in report.issues:
            print(f"{issue.severity}: {issue.code}: {issue.message}")
        return 2
    print(f"OpenRealm plan written: {plan_path}")
    print(f"Preview written: {preview_path}")
    return 0


def command_generate(args: argparse.Namespace) -> int:
    result = build_artifacts(args.prompt, Path(args.out), package=not args.no_package)
    for key, path in result.items():
        print(f"{key}: {path}")
    return 0


def command_demo(args: argparse.Namespace) -> int:
    out = Path(args.out)
    if out.exists() and args.clean:
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    for i, prompt in enumerate(DEMO_PROMPTS, start=1):
        slug = f"demo_{i}"
        print(f"Creating {slug}: {prompt}")
        build_artifacts(prompt, out / slug, package=True)
    print(f"Demo artifacts written under: {out}")
    return 0



def command_serve(args: argparse.Namespace) -> int:
    from .server import serve
    serve(args.host, args.port)
    return 0

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenRealm Creator Kernel CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("plan", help="Create a safe OpenRealm plan and preview only.")
    p_plan.add_argument("prompt")
    p_plan.add_argument("--out", default="out/plan")
    p_plan.set_defaults(func=command_plan)

    p_gen = sub.add_parser("generate", help="Create plan, preview, audit manifest, Luanti mod, and package.")
    p_gen.add_argument("prompt")
    p_gen.add_argument("--out", default="out/generated")
    p_gen.add_argument("--no-package", action="store_true")
    p_gen.set_defaults(func=command_generate)

    p_demo = sub.add_parser("demo", help="Generate three demo outputs.")
    p_demo.add_argument("--out", default="out/demo")
    p_demo.add_argument("--clean", action="store_true")
    p_demo.set_defaults(func=command_demo)


    p_serve = sub.add_parser("serve", help="Run local HTTP API for launcher/Luanti prototypes.")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8787)
    p_serve.set_defaults(func=command_serve)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
