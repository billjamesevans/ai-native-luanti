# AI Runtime Server Profile

Status: profile contract for issue #72

## Purpose

The `ai_runtime` game is a production-like server profile for checking AI-native runtime operator surfaces without test-only gameplay content. It gives the fork a cleaner path between synthetic verification and later proving-ground deployment.

Run this after `util/ai_native_runtime_verify.py` has passed for the branch under test.

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

Future proving-ground deployment should remain side by side and backup-first.
