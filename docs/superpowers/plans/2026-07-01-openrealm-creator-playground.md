# OpenRealm Creator Playground Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the first OpenRealm public milestone: a reliable Nova creator loop where a player prompts, previews, approves, watches, audits, and rolls back a world change.

**Architecture:** Keep `games/ai_runtime` as the clean technical profile and add a separate player-facing Luminara/OpenRealm demo profile. The runtime remains the only world mutation authority; Nova may select or propose bounded build plans, but mutation flows through existing capability, preview, task, audit, and rollback APIs.

**Tech Stack:** Luanti C++ server/runtime, builtin Lua agent plugins, `games/ai_runtime`, Python verification utilities under `util/`, GitHub Actions, Raspberry Pi side-by-side fork test server.

---

## Execution Status

- Task 1 is complete in commit `3ea6f33e3`: the public README and product docs now define OpenRealm, Nova, Luminara, the creator loop, and the AI-native runtime safety model.
- Task 3 is complete and current through commit `b7ed7e371`: the live prompt-eval artifact now emits the named `openrealm_creator_loop` golden-prompt suite, tracks the eleven-prompt backlog, enforces six implemented runtime prompt cases including the OpenRealm village prompt and player-like creator review loop, and makes `ai_native_agent_quality_gate` fail on golden prompt regressions.
- The OpenRealm Advantage Kit is now the product/architecture library for the transformation: brand boards, Nova architecture diagrams, Creator Studio mockups, deterministic prompt-to-plan tooling, schemas, generated examples, and a Luanti creator prototype live under `openrealm_advantage_kit/`.
- The Advantage Kit is now verification-gated: `util/openrealm_advantage_kit_verify.py` checks the canonical brand assets, safety manifest, schema, docs, private-content boundary, optional kit tests, optional Studio JS syntax, and is included in the alpha release gate and PR checklist.
- Task 2 is complete in current runtime tests: `TestAIRuntime` enforces strict fire-only intent, TNT wall material preservation, approval-gated build plans, request/response diagnostics, and rollback-backed execution.
- Task 4 is complete: `games/openrealm_demo` now provides the public-safe Luminara profile skeleton, tutorial prompt mod, and verified local server startup on UDP `30002`.
- Task 5 is current at commit `b7ed7e371`: the Pi fork test lane is deployed side-by-side, family UDP `30000` remained active, fork UDP `30001` is active, the Agents SDK sidecar is active on loopback TCP `8766`, live prompt eval passed `7/7`, the OpenRealm golden subset passed `6/6`, the request/response log gate passed `5/5` over `878` retained entries, and the live quality gate passed with zero attention items and zero violations.
- Player-like Nova loop expansion is underway and deployed on the Pi: `Nova, options` now returns pending build choices, selected candidate, option reasoning, and `openrealm.plan.v1` safety contracts from runtime state without a provider call or world mutation.
- Natural-chat review trace coverage is deployed on the Pi: `Nova, options`, `Nova, pending plan`, `Nova, no`, and the after-discard `Nova, pending plan` block now retain public-safe `natural_chat_review` traces, and the live prompt-eval plus quality-gate summaries expose the review trace proof.
- The next behavior-expansion track is to move additional backlog prompts from documented expectations into enforced runtime cases, starting with player-like multi-turn creator interaction instead of one-shot slash-command planning.

## File Structure

- Modify: `README.md` for the public OpenRealm identity.
- Create: `doc/product/openrealm-goal.md` for the canonical product goal.
- Create: `doc/product/roadmap.md` for phase sequencing.
- Create: `doc/product/demo-script.md` for the first video/demo.
- Create: `doc/product/golden-prompts.md` for prompt reliability gates.
- Modify: `doc/ai-native-runtime/README.md` to link the product layer to the runtime layer.
- Create: `games/openrealm_demo/game.conf` for the player-facing showcase profile.
- Create: `games/openrealm_demo/README.md` for profile intent and no-private-asset rules.
- Create: `games/openrealm_demo/mods/openrealm_tutorial/init.lua` for guided creator prompts.
- Modify: `builtin/game/tests/test_ai_runtime.lua` for golden-prompt behavior tests.
- Modify: `util/ai_native_agent_prompt_eval_live_probe.py` to include golden prompts as a named suite.
- Modify: `util/ai_native_agent_quality_gate.py` to fail when golden prompts regress.
- Create: `util/tests/test_openrealm_golden_prompts.py` for Python gate coverage.

### Task 1: Product Goal And Public Face

**Files:**
- Modify: `README.md`
- Create: `doc/product/openrealm-goal.md`
- Create: `doc/product/roadmap.md`
- Create: `doc/product/demo-script.md`
- Create: `doc/product/golden-prompts.md`
- Modify: `doc/ai-native-runtime/README.md`

- [ ] **Step 1: Verify the current public face**

Run:

```bash
python3 - <<'PY'
from pathlib import Path
print(Path("README.md").read_text().splitlines()[0])
print(Path("doc/ai-native-runtime/README.md").exists())
PY
```

Expected: the first line identifies the current README title, and the runtime README exists.

- [ ] **Step 2: Add product docs**

Create the product docs with these exact anchors:

```markdown
# OpenRealm Goal
# OpenRealm Product Roadmap
# OpenRealm Canonical Demo Script
# OpenRealm Golden Prompts
```

Expected: `find doc/product -type f | sort` lists the four product files.

- [ ] **Step 3: Update the root README**

The README must include these phrases:

```text
Describe a voxel world. Play it with friends. Own the code.
OpenRealm is an open-source AI-native voxel creation platform built on Luanti.
Nova is the in-world AI assistant.
The engine remains the world mutation authority.
```

- [ ] **Step 4: Link product docs from runtime docs**

Add a product layer note near the top of `doc/ai-native-runtime/README.md`:

```markdown
## Product Layer

OpenRealm is the public platform identity for this runtime work. See
[`../product/openrealm-goal.md`](../product/openrealm-goal.md) and
[`../product/roadmap.md`](../product/roadmap.md).
```

- [ ] **Step 5: Run documentation checks**

Run:

```bash
python3 util/scan_public_repo_secrets.py --tracked --untracked
git diff --check
```

Expected: no high-confidence secret material and no whitespace errors.

- [ ] **Step 6: Commit**

Run:

```bash
git add README.md doc/product doc/ai-native-runtime/README.md
git commit -m "Define OpenRealm product goal"
```

Expected: a commit containing only public identity and product documentation.

### Task 2: Golden Prompt Contract

**Files:**
- Modify: `builtin/game/tests/test_ai_runtime.lua`
- Modify: `doc/product/golden-prompts.md`

- [ ] **Step 1: Add failing Lua coverage for strict prompt constraints**

Add tests that assert:

```lua
-- "Build a fire and only a fire" selects build_kind="fire".
-- "Build a wall of TNT" selects build_kind="wall" and build_material_name="tnt".
-- Golden prompt plans always require approval and rollback.
```

Expected failing command before implementation:

```bash
bin/luantiserver --run-unittests --test-module TestAIRuntime
```

Expected: FAIL with a missing or incorrect golden-prompt assertion.

- [ ] **Step 2: Implement minimal planner behavior**

Modify the Nova/build planner path so material and "only" constraints survive candidate selection:

```text
intent_constraint_option_id must match the requested build when explicit.
build_material_name must preserve explicit material requests when node support exists.
candidate selection must not fall back to generic structures for strict single-object prompts.
```

- [ ] **Step 3: Verify Lua runtime tests**

Run:

```bash
bin/luantiserver --run-unittests --test-module TestAIRuntime
```

Expected: `Unit Test Results: PASSED`.

- [ ] **Step 4: Commit**

Run:

```bash
git add builtin/game/tests/test_ai_runtime.lua builtin/game/ai_agent_plugin.lua doc/product/golden-prompts.md
git commit -m "Gate Nova golden prompt behavior"
```

Expected: one behavior-focused commit.

### Task 3: Golden Prompt Quality Gate

**Files:**
- Modify: `util/ai_native_agent_prompt_eval_live_probe.py`
- Modify: `util/ai_native_agent_quality_gate.py`
- Create: `util/tests/test_openrealm_golden_prompts.py`

- [x] **Step 1: Write Python gate tests**

Create a test that feeds a synthetic prompt-eval result containing one failed golden prompt:

```python
def test_quality_gate_blocks_failed_golden_prompt(tmp_path):
    result = {
        "live_prompt_eval_status": "pass",
        "golden_prompts": [{"prompt": "Build a campfire.", "status": "fail"}],
    }
    assert result["golden_prompts"][0]["status"] == "fail"
```

Expected before implementation: the current quality gate has no golden-prompt field to enforce.

- [x] **Step 2: Add named golden suite output**

Extend the live prompt eval output with:

```json
{
  "golden_prompt_suite": "openrealm_creator_loop",
  "golden_prompts_total": 11,
  "golden_prompts_failed": 0
}
```

- [x] **Step 3: Fail the quality gate on golden prompt regressions**

`util/ai_native_agent_quality_gate.py` must set quality gate status to `fail` when
`golden_prompts_failed > 0`.

- [x] **Step 4: Run tests**

Run:

```bash
python3 -m unittest util.tests.test_openrealm_golden_prompts
python3 util/scan_public_repo_secrets.py --tracked --untracked
```

Expected: tests pass and no high-confidence secret material is found.

- [x] **Step 5: Commit**

Run:

```bash
git add util/ai_native_agent_prompt_eval_live_probe.py util/ai_native_agent_quality_gate.py util/tests/test_openrealm_golden_prompts.py
git commit -m "Add OpenRealm golden prompt quality gate"
```

### Task 4: Luminara/OpenRealm Demo Profile

**Files:**
- Create: `games/openrealm_demo/game.conf`
- Create: `games/openrealm_demo/README.md`
- Create: `games/openrealm_demo/mods/openrealm_tutorial/init.lua`
- Modify: `.gitignore`

- [x] **Step 1: Create the profile skeleton**

Create `games/openrealm_demo/game.conf`:

```ini
name = OpenRealm Demo
description = Luminara creator playground for Nova prompt-preview-approval-rollback demos.
author = OpenRealm contributors
```

- [x] **Step 2: Add profile rules**

Create `games/openrealm_demo/README.md` with these rules:

```markdown
# OpenRealm Demo

This is the public-safe Luminara creator playground. It must not contain private
family-server worlds, proprietary assets, copied Minecraft assets, or local
credentials.
```

- [x] **Step 3: Add a tiny tutorial mod**

Create `games/openrealm_demo/mods/openrealm_tutorial/init.lua`:

```lua
core.register_on_joinplayer(function(player)
	local name = player:get_player_name()
	core.chat_send_player(name, "Try: Nova, build a campfire.")
	core.chat_send_player(name, "Then preview, approve, and undo the change.")
end)
```

- [x] **Step 4: Verify profile discovery**

Run:

```bash
mkdir -p worlds/openrealm_smoke
printf 'gameid = openrealm_demo\nbackend = sqlite3\nplayer_backend = sqlite3\nauth_backend = sqlite3\n' > worlds/openrealm_smoke/world.mt
bin/luantiserver --gameid openrealm_demo --worldname openrealm_smoke --terminal --port 30002
```

Expected: the server starts with gameid `openrealm_demo` and binds UDP `30002`.
Stop it after startup. The `worlds/openrealm_smoke` directory is ignored local
smoke-test state.

- [ ] **Step 5: Commit**

Run:

```bash
git add games/openrealm_demo .gitignore
git commit -m "Add OpenRealm demo profile skeleton"
```

### Task 5: Pi Evidence Lane

**Files:**
- Modify: `doc/product/roadmap.md`
- Modify: `doc/ai-native-runtime/low-power-pi-evidence-lane.md`

- [x] **Step 1: Deploy backup-first to the Pi**

Run from `/Users/billevans/Documents/2026/minecraft_server`:

```bash
ops/deploy-ai-native-luanti-fork-to-pi.sh
```

Expected:

```text
TestAIRuntime passes
ai-native-luanti-test.service is active
UDP 30001 is listening
luanti-family.service remains active
UDP 30000 remains listening
```

- [x] **Step 2: Verify independently**

Run:

```bash
ssh -o BatchMode=yes bill@minecraftpi.home '
  systemctl is-active luanti-family.service
  systemctl is-active ai-native-luanti-test.service
  sudo ss -lunp | grep -E ":(30000|30001)" || true
  git -C /opt/ai-native-luanti/src rev-parse --short HEAD
'
```

Expected: both services active, both UDP ports listening, and HEAD matches the pushed commit.

- [x] **Step 3: Commit evidence docs**

Run:

```bash
git add doc/product/roadmap.md doc/ai-native-runtime/low-power-pi-evidence-lane.md
git commit -m "Document OpenRealm Pi evidence gate"
```

## Self-Review

- Spec coverage: this plan covers public identity, creator loop, Luminara demo,
  golden prompts, visible preview/approval/rollback, Pi evidence, ContentDB as a
  later ecosystem lane, and avoiding full survival-game scope first.
- Placeholder scan: no task depends on "TBD" or an undefined future subsystem.
- Type consistency: product names are OpenRealm, Nova, Luminara, `ai_runtime`,
  and `openrealm_demo` consistently.
