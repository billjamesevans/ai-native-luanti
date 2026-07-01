Add compact, short information about your PR for easier understanding:

- Goal of the PR
- How does the PR work?
- Does it resolve any reported issue?
- Does this relate to a goal in [the roadmap](https://github.com/luanti-org/luanti/blob/master/doc/direction.md)?
- If not a bug fix, why is this PR needed? What usecases does it solve?
- If you have used an LLM/AI to help with code or assets, you must disclose this.

## To do

This PR is a Work in Progress / Ready for Review.
<!-- ^ delete one -->

- [ ] List
- [ ] Things
- [ ] To do

## AI-native alpha gate

- [ ] I ran `python3 util/ai_native_alpha_release_gate.py`
- [ ] I ran `python3 util/openrealm_advantage_kit_verify.py --run-tests --run-js-check` when product identity, OpenRealm library, creator-kernel, studio, or visual assets changed.
- [ ] I ran `python3 util/ai_native_agents_sdk_sidecar_readiness.py --mode offline-smoke` or verified it through the alpha gate.
- [ ] I ran `python3 util/ai_native_runtime_verify.py --hardware-class local-mac --game-profile ai_runtime` or explained why it is not applicable.
- [ ] Agent behavior changes include a live prompt eval and `python3 util/ai_native_agent_quality_gate.py ... --require-live-prompt-eval`.
- [ ] This PR keeps `spacebase`, `themepark`, `disneyland100`, private worlds, prompts, secrets, copied proprietary assets, and family-server content out of the main fork.
- [ ] Engine/runtime changes, optional plugin changes, and any private deployment notes are separated.

## How to test

<!-- Example code or instructions -->
