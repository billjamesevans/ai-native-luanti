# OpenRealm Creator Studio Prototype

Open `index.html` in a browser, or serve the parent `openrealm_advantage_kit`
directory and visit `/studio/`.

This prototype is dependency-free and runs entirely offline. It demonstrates the product loop:

1. Prompt Nova.
2. Generate a deterministic safe plan.
3. Preview planned world changes.
4. Approve and apply.
5. Audit the changes.
6. Undo with rollback.
7. Export JSON or Lua.

Current planner checks cover strict simple requests:

- `Build only a fire` creates exactly one `fire:basic_flame` action.
- `Build a wall of tnt` creates a ready medium-risk TNT wall plan instead of
  refusing or falling back to a generic structure.

The code is intentionally framework-free so it can be moved into React, Tauri, Qt, Electron, or the Luanti UI layer later.
