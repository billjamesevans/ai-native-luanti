# OpenRealm Golden Prompts

These prompts define the Creator Loop MVP. They must pass locally and on the
Raspberry Pi fork test server before a public alpha cut.

The full OpenRealm backlog currently contains eleven product prompts. The
runtime gate enforces the implemented subset first: fire, strict fire-only, TNT
wall, agentic build-planner selection, the OpenRealm village template,
player-like multi-turn creator review, and model/tool routing. New prompts move
from backlog to enforced only when the
runtime can validate them with repeatable public-safe evidence.

| Prompt | Expected Build | Material | Writes | Approval | Rollback |
| --- | --- | --- | ---: | --- | --- |
| Build a campfire. | fire | fire-safe campfire nodes | 1-12 | required | required |
| Build a fire and only a fire. | fire | fire-safe campfire nodes | 1-12 | required | required |
| Build a stone bridge. | bridge/path | stone | 12-96 | required | required |
| Build a small cabin. | cabin | wood/stone/glass | 80-600 | required | required |
| Build a path to that hill. | path | gravel/stone/wood | 8-200 | required | required |
| Light this area. | lights | torch/lantern/glow node | 4-80 | required | required |
| Repair this wall. | repair | matched nearby material | 1-200 | required | required |
| Make a lookout tower. | tower | wood/stone | 80-800 | required | required |
| Make a small garden. | garden | soil/plant/water nodes | 16-240 | required | required |
| Build a wall of TNT. | wall | TNT node or public-safe TNT stand-in | 6-240 | required | required |
| Undo the last build. | rollback | previous rollback record | varies | confirmation | completes rollback |

## Regression Rules

- A prompt with "only" must not add unrelated structures.
- A material constraint such as "TNT" must be preserved in the selected option
  when the node is available in the profile.
- A player must be able to ask for pending build options without causing a model
  call or world mutation.
- The runtime must reject direct mutation without task, audit, and rollback
  metadata.
- Weak or wrong behavior must be logged into the request/response review queue
  for operator labeling.
- Golden-prompt failures block public demo claims.

## Current Enforcement

- Suite: `openrealm_creator_loop`
- Backlog total: `11`
- Enforced runtime prompt cases: `6`
- Supporting model/tool route case: `1`
- Player-loop option review: `Nova, options` returns selected and alternate
  pending build choices from runtime state, including an `openrealm.plan.v1`
  safety/preview contract for each executable option.
- Player-like creator loop: `Nova, Build a cozy lakeside village with floating
  lanterns` must queue a pending OpenRealm village preview; `Nova, options` and
  `Nova, pending plan` must return the same selected candidate without world
  mutation; `Nova, no` must discard the approval; the next `Nova, pending plan`
  must block with `no_pending_approval`.
- Natural-chat review turns such as `Nova, options` and `Nova, pending plan`
  must emit public-safe `natural_chat_review` request traces, so request/response
  review keeps normal player conversation turns instead of only model-backed
  build-planning turns.
- Adapter template generation: the Agents SDK sidecar can now turn "Build a
  cozy lakeside village with floating lanterns" into a bounded
  `generated_openrealm_lakeside_village` option with a 96-placement
  `openrealm.plan.v1` structure plan using registered `ai_runtime_base:*`
  placeholder nodes. This is now an enforced live golden prompt and must expose
  `agents_sdk_generated_tool_completion`, `propose_build_option`,
  `openrealm_structure`, `openrealm_template`, and `96` planned writes.
- Blocking gate: `python3 util/ai_native_agent_quality_gate.py ... --require-live-prompt-eval`
