from __future__ import annotations

import html
from pathlib import Path

from .models import OpenRealmPlan
from .safety import validate_plan

CSS = """
:root { color-scheme: dark; --bg:#0e1017; --panel:#151a27; --text:#f6f7fa; --muted:#aeb6d0; --blue:#4ea8ff; --violet:#7a5cff; --teal:#2ed4b7; --green:#8be36b; --warn:#ffd166; }
* { box-sizing: border-box; }
body { margin:0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif; background: radial-gradient(circle at 20% 0%, #1d2852 0, transparent 34%), radial-gradient(circle at 80% 10%, #2b145c 0, transparent 26%), var(--bg); color:var(--text); }
main { max-width: 1100px; margin: 0 auto; padding: 48px 24px; }
.hero { display:grid; grid-template-columns: 1.3fr .7fr; gap:24px; align-items:stretch; }
.card { background: linear-gradient(180deg, rgba(255,255,255,.06), rgba(255,255,255,.025)); border:1px solid rgba(255,255,255,.12); border-radius:22px; padding:24px; box-shadow: 0 24px 80px rgba(0,0,0,.35); }
h1 { font-size: clamp(36px, 7vw, 72px); line-height:.95; margin:0 0 16px; letter-spacing:-.06em; }
h2 { margin:0 0 16px; }
.pill { display:inline-flex; gap:8px; align-items:center; border:1px solid rgba(255,255,255,.12); border-radius:999px; padding:8px 12px; color:var(--muted); margin: 4px; }
.ok { color:var(--green); } .warn { color:var(--warn); } .blue { color:var(--blue); } .teal { color:var(--teal); } .violet { color:var(--violet); }
.grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:16px; margin-top:24px; }
.step { border-left:3px solid var(--teal); padding-left:14px; color:var(--muted); }
pre { white-space: pre-wrap; overflow:auto; background:#080a10; border-radius:14px; padding:16px; border:1px solid rgba(255,255,255,.08); }
table { width:100%; border-collapse:collapse; } td, th { text-align:left; border-bottom:1px solid rgba(255,255,255,.08); padding:10px; } th { color:var(--teal); }
small { color:var(--muted); }
"""


def write_preview(plan: OpenRealmPlan, path: Path) -> None:
    report = validate_plan(plan)
    issues = "".join(
        f"<li><strong>{html.escape(issue.severity)}</strong> {html.escape(issue.code)}: {html.escape(issue.message)}</li>"
        for issue in report.issues
    ) or "<li>No validation issues.</li>"
    structures = "".join(
        f"<tr><td>{html.escape(s.name)}</td><td>{len(s.placements)}</td><td>{html.escape(s.description)}</td></tr>"
        for s in plan.structures
    ) or "<tr><td colspan='3'>No structures in this plan.</td></tr>"
    nodes = "".join(
        f"<tr><td>{html.escape(n.name)}</td><td>{html.escape(n.description)}</td><td>{n.light_source}</td></tr>"
        for n in plan.nodes
    ) or "<tr><td colspan='3'>No nodes in this plan.</td></tr>"
    html_doc = f"""<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\" />
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
<title>{html.escape(plan.title)} - OpenRealm Preview</title>
<style>{CSS}</style>
</head>
<body>
<main>
  <section class=\"hero\">
    <div class=\"card\">
      <div class=\"pill violet\">OpenRealm Creator Preview</div>
      <div class=\"pill teal\">Nova assisted</div>
      <h1>{html.escape(plan.title)}</h1>
      <p>{html.escape(plan.summary)}</p>
      <p><small>Prompt: {html.escape(plan.source_prompt)}</small></p>
    </div>
    <div class=\"card\">
      <h2>Safety status</h2>
      <p class=\"{'ok' if report.ok else 'warn'}\">{'PASS' if report.ok else 'NEEDS REVIEW'}</p>
      <ul>{issues}</ul>
    </div>
  </section>

  <section class=\"grid\">
    <div class=\"card\"><h2>1. Prompt</h2><p class=\"step\">Describe the world or mod.</p></div>
    <div class=\"card\"><h2>2. Plan</h2><p class=\"step\">Nova produces a data-only recipe.</p></div>
    <div class=\"card\"><h2>3. Validate</h2><p class=\"step\">OpenRealm checks budgets, names, and safety.</p></div>
    <div class=\"card\"><h2>4. Approve</h2><p class=\"step\">Human review before install or mutation.</p></div>
  </section>

  <section class=\"card\" style=\"margin-top:24px\">
    <h2>Generated nodes</h2>
    <table><thead><tr><th>Name</th><th>Description</th><th>Light</th></tr></thead><tbody>{nodes}</tbody></table>
  </section>

  <section class=\"card\" style=\"margin-top:24px\">
    <h2>Structures</h2>
    <table><thead><tr><th>Name</th><th>Planned writes</th><th>Description</th></tr></thead><tbody>{structures}</tbody></table>
  </section>

  <section class=\"card\" style=\"margin-top:24px\">
    <h2>Approval checklist</h2>
    <ol>{''.join(f'<li>{html.escape(step)}</li>' for step in plan.approval_steps)}</ol>
  </section>

  <section class=\"card\" style=\"margin-top:24px\">
    <h2>Plan JSON</h2>
    <pre>{html.escape(plan.to_json())}</pre>
  </section>
</main>
</body>
</html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_doc, encoding="utf-8")
