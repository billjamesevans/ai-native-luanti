# Read This First

This zip is not just a concept deck. It contains a working **OpenRealm Creator Kernel**:

- `python -m openrealm_creator_kernel.cli plan ...` creates a validated OpenRealm plan and HTML preview.
- `python -m openrealm_creator_kernel.cli generate ...` creates a plan, preview, audit manifest, generated Luanti mod, and packaged mod zip.
- `python -m openrealm_creator_kernel.cli demo --out examples/generated` creates three canonical demo outputs.
- `python -m openrealm_creator_kernel.cli serve --port 8787` starts a local HTTP API for launcher/Luanti prototyping.
- `studio/index.html` is a polished local Creator Studio prototype with prompt, preview, approval, audit, rollback, and export flows.

The strategic advantage is the contract:

> Nova proposes. OpenRealm validates. Luanti mutates only through bounded, previewed, approval-oriented runtime code.

Best first integration step:

1. Put this folder next to your OpenRealm/Luanti fork.
2. Run the tests.
3. Run the demo generator.
4. Open `studio/index.html`.
5. Copy the generated Luanti mod from `examples/generated/demo_1/generated_luanti_mod/openrealm_moonstone` into a disposable Luanti test world.
6. Use the generated `/or_preview`, `/or_build`, and `/or_rollback_last` commands.
