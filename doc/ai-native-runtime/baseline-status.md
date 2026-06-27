# Baseline Status

Date: 2026-06-27
Repository: `billjamesevans/ai-native-luanti`
Upstream: `luanti-org/luanti`
Branch: `project/ai-native-runtime-mvp`

## Fork State

- Fork created from `luanti-org/luanti`.
- Local clone exists outside the private proving-ground workspace.
- Base commit at clone time: `143b167f0`.
- Version reported by server binary: `Luanti 5.17.0-dev-debug-143b167f0`.

## Configure

Command:

```bash
cmake -S . -B build/server-debug \
  -DCMAKE_BUILD_TYPE=Debug \
  -DBUILD_CLIENT=FALSE \
  -DBUILD_SERVER=TRUE \
  -DBUILD_UNITTESTS=TRUE \
  -DBUILD_BENCHMARKS=TRUE \
  -DBUILD_DOCUMENTATION=FALSE \
  -DRUN_IN_PLACE=TRUE \
  -DCMAKE_FIND_FRAMEWORK=LAST
```

Result:

- Configure passed.
- Server-only debug build selected.
- cURL enabled.
- SQLite enabled.
- Built-in Lua used because LuaJIT was not found.
- Prometheus client disabled because the dependency was not found.

## Build

Command:

```bash
cmake --build build/server-debug --parallel $(sysctl -n hw.logicalcpu)
```

Result:

- Build passed.
- Built target: `bin/luantiserver`.

## Unit Tests

Command:

```bash
bin/luantiserver --run-unittests
```

Result:

- Passed.
- Legacy unit tests: 44 modules, 328 individual tests, 0 failures.
- Catch2: all tests passed, 156392 assertions in 13 test cases.

## Native Benchmarks

Listing command:

```bash
bin/luantiserver --run-benchmarks --list-tests
```

Available benchmark/test cases include:

- `ActiveObjectMgr`
- `benchmark_lighting`
- `benchmark_map`
- `benchmark_mapblock`
- `benchmark_serialize`
- `benchmark_sha`

Short all-benchmark run:

```bash
bin/luantiserver --run-benchmarks \
  --benchmark-samples 3 \
  --benchmark-warmup-time 1 \
  --benchmark-no-analysis
```

Result:

- Failed with SIGSEGV in `benchmark_mapblock`, case `allocate_900`.
- This is a baseline upstream-fork finding before AI-runtime changes.

Targeted short benchmarks passed:

```bash
bin/luantiserver --run-benchmarks ActiveObjectMgr \
  --benchmark-samples 3 --benchmark-warmup-time 1 --benchmark-no-analysis

bin/luantiserver --run-benchmarks benchmark_lighting \
  --benchmark-samples 3 --benchmark-warmup-time 1 --benchmark-no-analysis

bin/luantiserver --run-benchmarks benchmark_serialize \
  --benchmark-samples 3 --benchmark-warmup-time 1 --benchmark-no-analysis

bin/luantiserver --run-benchmarks benchmark_sha \
  --benchmark-samples 3 --benchmark-warmup-time 1 --benchmark-no-analysis
```

## Baseline Gaps

- Prometheus support is not enabled in the local debug build.
- `ctest` found no registered tests; use `bin/luantiserver --run-unittests` for this build.
- `benchmark_mapblock` has a reproducible crash in the short benchmark run and needs triage before it can be used as a merge gate.

