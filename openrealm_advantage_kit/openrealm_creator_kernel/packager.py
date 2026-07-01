from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from .models import OpenRealmPlan
from .safety import validate_plan


def write_audit_manifest(plan: OpenRealmPlan, path: Path) -> None:
    report = validate_plan(plan)
    manifest = {
        "schema_version": "openrealm.audit_manifest.v1",
        "plan_id": plan.plan_id,
        "title": plan.title,
        "mod_name": plan.mod_name,
        "safety_ok": report.ok,
        "issues": [issue.__dict__ for issue in report.issues],
        "budgets": plan.safety_budget.__dict__,
        "ai_disclosure": plan.ai_disclosure,
        "provenance": plan.provenance,
        "mutation_policy": {
            "preview_required": True,
            "approval_required": True,
            "rollback_required": True,
            "ai_direct_world_mutation": False,
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def zip_directory(source_dir: Path, zip_path: Path, root_name: str | None = None) -> Path:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    root_name = root_name or source_dir.name
    with ZipFile(zip_path, "w", ZIP_DEFLATED) as zf:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                zf.write(path, Path(root_name) / path.relative_to(source_dir))
    return zip_path
