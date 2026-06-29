# AI Runtime Server Profile

Status: profile contract for issue #72

## Purpose

The `ai_runtime` game is a production-like server profile for checking AI-native runtime operator surfaces without test-only gameplay content. It gives the fork a cleaner path between synthetic verification and later proving-ground deployment.

Run this after `util/ai_native_runtime_verify.py` has passed for the branch under test.
For product-profile hygiene changes, also run `python3 util/ai_native_product_profile_verify.py`.

## Startup Inventory

`games/ai_runtime/product_profile_manifest.json` is the machine-readable source for the default profile boundary.

| Surface | Category | Default product profile |
| --- | --- | --- |
| `games/ai_runtime/game.conf` | Product runtime | Loaded |
| `games/ai_runtime/mods/ai_runtime_base` | First-party plugin | Loaded |
| `builtin/game/ai_runtime_smoke.lua` | Unit-test helper | Requires `ai_runtime.enable_smoke_command = true` |
| `builtin/game/demo_entity_benchmark.lua` | Benchmark fixture | Requires `ai_runtime.enable_demo_benchmark_command = true` |
| `util/tests/fixtures/compat` | Compatibility fixture | Test/dev path only |
| `builtin/game/tests/test_ai_runtime.lua` | Unit-test helper | Test/dev path only |

## Local Run

Create a disposable local world and run the profile:

```sh
mkdir -p local/worlds/ai-runtime-profile
cat > local/worlds/ai-runtime-profile/world.mt <<'EOF'
gameid = ai_runtime
backend = sqlite3
player_backend = sqlite3
auth_backend = sqlite3
mod_storage_backend = sqlite3
creative_mode = true
enable_damage = false
EOF

bin/luantiserver \
  --gameid ai_runtime \
  --world local/worlds/ai-runtime-profile \
  --config local/ai-runtime-profile.conf
```

Synthetic smoke and benchmark modules are disabled by default. For a disposable local smoke check, add this to `local/ai-runtime-profile.conf` before startup:

```conf
ai_runtime.enable_smoke_command = true
```

Grant the local operator `server` privilege in the disposable world, then run:

```text
/ai_runtime_smoke
```

## Boundaries

- This profile requires no live server.
- This profile requires no private world.
- This profile requires no private assets.
- This profile requires no provider prompt retention.
- This profile requires no model-network access.
- This profile is not a replacement for benchmark fixtures or engine unit tests.
- This profile keeps synthetic smoke and demo benchmark commands behind explicit dev/test settings.
- This profile declares first-party agent capability grants in `games/ai_runtime/mods/ai_runtime_base/init.lua`.
- This profile does not grant `admin.override`, `import.assets`, other-player teleport, or defensive-combat capabilities to player-owned first-party agents.

Future proving-ground deployment should remain side by side and backup-first.
