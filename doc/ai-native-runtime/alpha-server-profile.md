# Alpha Server Profile

Status: player-ready profile boundary for the AI-native alpha.

## Purpose

The player-ready alpha profile is `games/ai_runtime`. It is the clean server
profile for trying first-party AI-native agents without private worlds,
showcase builds, copied assets, provider configuration, or test fixtures.

The fork should keep one clean profile until there is a concrete reason to
split another game package. Duplicating the profile now would create drift
without improving the player experience.

## Profile Boundary

`games/ai_runtime` may include:

- Minimal mapgen aliases required for a disposable public-safe world.
- Profile-owned first-party agent capability grants.
- Default rollback storage for rollback-backed build and repair tasks.
- Public-safe player/operator documentation.

`games/ai_runtime` must not include:

- Runtime unit-test fixtures.
- Devtest or benchmark-only nodes.
- Private family-server worlds, mods, coordinates, or player data.
- Showcase builds or local demo worlds.
- Provider prompts, API keys, or model-network configuration.
- Copied Minecraft, marketplace, or proprietary pack assets.

Synthetic smoke and benchmark code can remain in `builtin/game` and `util`
when it is explicitly documented as verification-only. Those paths are not the
player content profile.

## Default Capabilities

The clean profile grants only bounded first-party capabilities:

- `world.read`
- `world.place`
- `world.remove`
- `entity.spawn`
- `entity.control`
- `task.cancel`
- `http.llm`

The clean alpha profile does not grant `admin.override`, `import.assets`,
`combat.defend`, or other-player controls by default. Those belong in explicit
operator or optional plugin profiles.

## Required clean runtime surfaces

The clean profile must expose the product runtime surfaces operators need before
agent plugins become richer:

- `/ai_runtime_operator_status` returns bounded public-safe runtime status.
- `/ai_runtime_operator_task_control` applies receipt-gated task cancel/retry
  decisions only.

Both commands require the `server` privilege. They are loaded by default because
they are product runtime surfaces, not smoke tests or benchmark fixtures.
Rollback execution, import promotion, structure apply, and world mutation stay
outside the task-control command boundary.

## Operator Flow

Local alpha verification should use the normal pre-PR verifier:

```bash
python3 util/ai_native_runtime_verify.py \
  --hardware-class local-mac \
  --game-profile ai_runtime
```

Low-power proving-ground deployments should run side by side with any existing
family or private server. The alpha profile should be tested as its own service
and should not replace a family world unless an operator explicitly chooses to
do that outside the core fork.

## Readiness Rule

The alpha profile is ready for player testing only when the verifier passes,
the profile starts from a disposable world, first-party commands use task
queues and rollback-backed operations, and the profile scan shows no private or
test-only content in `games/ai_runtime`.
