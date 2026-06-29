# Clean AI Runtime Install

Status: public contributor setup path for the alpha profile.

## Clone

```bash
git clone https://github.com/billjamesevans/ai-native-luanti.git
cd ai-native-luanti
```

## Configure And Build

```bash
cmake -S . -B build/server-release \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DBUILD_CLIENT=FALSE \
  -DBUILD_SERVER=TRUE \
  -DBUILD_UNITTESTS=TRUE \
  -DRUN_IN_PLACE=TRUE

cmake --build build/server-release --parallel
```

If your local build writes the server binary somewhere other than
`bin/luantiserver`, pass that path to verification with `--server-bin`.

## Smoke Test

```bash
bin/luantiserver --run-unittests --test-module TestAIRuntime
```

## Run The Clean Profile

Use a disposable world. Do not point the alpha profile at private or family
worlds.

```bash
mkdir -p local/worlds/alpha-clean
bin/luantiserver --gameid ai_runtime --world local/worlds/alpha-clean --port 30001
```

The clean profile is `games/ai_runtime`. It should load the product runtime
surface and `ai_runtime_base` only. Synthetic smoke commands, benchmark
fixtures, and compatibility fixtures stay disabled unless a dev/test lane
explicitly enables them.

## Verify Before Opening A PR

```bash
python3 util/ai_native_alpha_release_gate.py
python3 util/ai_native_runtime_verify.py --hardware-class local-mac --game-profile ai_runtime
```

The alpha gate checks the clean profile package inventory, dev/test fixture
separation, default runtime module list, release docs, templates, and the
fresh-checkout build/run/verifier command plan.

When using a non-default build output:

```bash
python3 util/ai_native_runtime_verify.py \
  --hardware-class local-mac \
  --game-profile ai_runtime \
  --server-bin build/server-release/bin/luantiserver
```
