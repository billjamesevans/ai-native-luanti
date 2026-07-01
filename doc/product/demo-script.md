# OpenRealm Canonical Demo Script

## Purpose

The demo must show one thing clearly:

```text
Nova can safely create a visible world change from a player prompt, explain the
plan, apply it only after approval, and undo it.
```

## Setup

- Use the public-safe creator playground profile, not a private family world.
- Use a small lake, hill, or clearing as the anchor.
- Keep the first capture under three minutes.
- Show the preview and rollback affordance on screen.
- Do not show API keys, private paths, family coordinates, or server secrets.

## Script

1. Start in Luminara near a visible lake or clearing.
2. Open Nova.
3. Prompt:

   ```text
   Build a small cabin by the lake.
   ```

4. Nova shows a preview with:

   - selected build kind: cabin,
   - material palette,
   - approximate dimensions,
   - planned node writes,
   - location,
   - rollback available.

5. Approve the plan.
6. Show task progress while the build applies.
7. Walk around and inside the cabin.
8. Prompt:

   ```text
   Add a campfire and a path to the door.
   ```

9. Nova previews and applies the path and campfire.
10. Use undo for the last change.
11. Show "Nova changed N blocks. Undo available. View details."
12. End on the world recipe/share action.

## Failure Cases To Avoid

- Nova builds an unrelated default structure.
- Nova ignores "only a fire" or "wall of TNT" style constraints.
- Nova mutates the world before approval.
- The demo depends on private worlds, copied proprietary assets, or local-only
  credentials.
- The output looks like a developer console instead of a player experience.

## Capture Checklist

- Prompt text is visible.
- Preview is visible.
- Approval is visible.
- Build result is visible.
- Undo is visible.
- Request/response trace exists for the run.
- No secrets or private data are visible.
