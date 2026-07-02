# OpenRealm Creator Studio Prototype

Open `index.html` in a browser, or serve the parent `openrealm_advantage_kit`
directory and visit `/studio/`.

For live Pi telemetry, serve the Studio through the bundled bridge:

```bash
python3 studio/server.py --root . --host 127.0.0.1 --port 8788
```

Then open `http://127.0.0.1:8788/studio/`. The bridge exposes `/api/status`
with public-safe service, fork, quality-gate, and Agents SDK adapter summaries.
It does not expose raw prompts, provider messages, credentials, private paths,
or world payloads. Adapter summaries separate current gate health from
historical lifetime counts so old failed probes do not obscure a passing live
release gate. Prompt-eval summaries expose only case IDs, pass counts, golden
prompt coverage, and safety flags.

Runtime-proof summaries expose only status and counts for rollback-backed Nova
auto-apply probes and compatibility import staging rehearsals. They prove that
world mutation goes through Luanti runtime tasks, rollback records exist, and
compatibility import stays in disposable/staging worlds without exposing raw
prompts, private coordinates, provider messages, or copied assets.

The Agent trace panel displays the newest public-safe adapter summaries: selected
option, tool-decision source, planned write count, required-tool status,
web-search availability, mutation authority, and a bounded tool-name list. It
does not display raw player prompts, model messages, provider prompts, secrets,
private paths, coordinates, or world payloads.

This prototype is dependency-free and can still run entirely offline. It demonstrates the product loop:

1. Prompt Nova.
2. Generate a deterministic safe plan.
3. Preview planned world changes.
4. Approve and apply.
5. Audit the changes.
6. Undo with rollback.
7. Export JSON or Lua.

Current planner checks cover strict simple requests:

- `Build only a fire` creates exactly one `fire:basic_flame` action.
- `Build a wall of tnt` creates a ready medium-risk TNT wall plan instead of
  refusing or falling back to a generic structure.

The code is intentionally framework-free so it can be moved into React, Tauri, Qt, Electron, or the Luanti UI layer later.
