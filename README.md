# OpenRealm

Describe a voxel world. Play it with friends. Own the code.

OpenRealm is an open-source AI-native voxel creation platform built on
[Luanti](https://www.luanti.org/). Nova is the in-world AI assistant. The
first showcase world is Luminara: a small, polished creator playground where a
player can ask Nova to build, preview the plan, approve it, walk through the
result, and undo the change.

This fork is not trying to be a Minecraft clone with a chatbot bolted on. The
project goal is a safe AI creation layer for voxel worlds: human players and AI
agents share a world through bounded tasks, visible previews, capability gates,
audit trails, and rollback.

## What Works Today

- AI-native runtime docs and verification gates under
  [`doc/ai-native-runtime/`](doc/ai-native-runtime/).
- A clean `ai_runtime` game profile for early runtime playtesting.
- First-party agent surfaces for build, repair, guide, defender, and import
  workflows.
- Nova player-facing controls through `/nova`, `/bot`, and `/aibot`.
- Agent SDK model-adapter integration with tool traces and reviewed prompt
  memory.
- Prompt-to-plan build flows that route world mutation through Luanti-owned
  capability, preview, task, audit, and rollback APIs.
- Request/response logging and quality gates for reviewing weak agent behavior
  and promoting good cases into repeatable evals.

## The Magic Moment

The first public milestone is intentionally narrow:

1. Open a small creator world.
2. Type: `Nova, build a small cabin by the lake.`
3. See what Nova plans to build, including size, material, location, block
   count, and rollback status.
4. Approve the plan.
5. Watch Nova build it.
6. Walk inside.
7. Ask for a campfire and path.
8. Undo one change.
9. Share the world recipe.

Everything else serves that loop.

## Product Direction

OpenRealm is the platform. Nova is the AI assistant. Luminara is the first
showcase world.

The product lane is safe, open, AI-native world creation:

- **Creator first:** prompt -> plan -> preview -> approve -> apply -> audit ->
  rollback.
- **Player visible trust:** show what Nova will change before it mutates the
  world.
- **Bounded agent power:** agents use approved runtime tools, not arbitrary
  hidden world mutation.
- **Public-safe content:** no private family worlds, copied proprietary assets,
  or one-off showcase builds in the core fork.
- **Compatibility later:** Minecraft-style compatibility and import tooling come
  after runtime safety and observability are reliable.
- **Ecosystem friendly:** make ContentDB and Luanti packages easier to install,
  verify, run, share, and host instead of replacing that ecosystem.

See:

- [OpenRealm goal](doc/product/openrealm-goal.md)
- [Product roadmap](doc/product/roadmap.md)
- [Canonical demo script](doc/product/demo-script.md)
- [Golden prompts](doc/product/golden-prompts.md)
- [AI-native runtime](doc/ai-native-runtime/README.md)

## Safety Model

Nova and other agents should never be trusted just because a model produced a
confident answer. The engine remains the world mutation authority.

The runtime pattern is:

1. Agent receives a bounded public context.
2. Agent proposes or selects a safe operation.
3. Runtime validates capabilities, protected areas, budgets, and rollback
   policy.
4. Player sees a preview.
5. Player approves, edits, or cancels.
6. Runtime applies the task in slices.
7. Runtime records result, metrics, audit events, and rollback metadata.

This is the core unfair advantage of the fork.

## Try The Runtime

For local runtime validation from a built checkout:

```bash
bin/luantiserver --run-unittests --test-module TestAIRuntime
python3 util/ai_native_runtime_verify.py --server-bin bin/luantiserver
```

For product-profile hygiene:

```bash
python3 util/ai_native_product_profile_verify.py
```

For the local public-repo secret guard:

```bash
python3 util/install_public_repo_secret_guard.py
python3 util/scan_public_repo_secrets.py --tracked --untracked
```

## Built On Luanti

OpenRealm is built on Luanti, a free open-source voxel game engine with easy
modding and game creation.

Useful upstream resources:

- Website: https://www.luanti.org/
- Documentation: https://docs.luanti.org/
- Forum: https://forum.luanti.org/
- Upstream GitHub: https://github.com/luanti-org/luanti/
- Developer documentation: [`doc/developing/`](doc/developing/)

## License

This fork retains the upstream Luanti licensing structure. See
[`LICENSE.txt`](LICENSE.txt), [`COPYING.LESSER`](COPYING.LESSER), and source
file headers.
