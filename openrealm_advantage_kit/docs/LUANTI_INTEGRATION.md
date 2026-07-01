# Luanti Integration Notes

This prototype intentionally avoids requiring changes to the engine. It generates normal Luanti mods.

## Install path

Copy the generated mod folder into a disposable Luanti world first. Do not test
generated content against a private family world or production server until the
plan, preview, approval, audit, and rollback evidence has been reviewed.

Generated mod folders can be copied into:

```text
~/.minetest/mods/<mod_name>
```

or into a game/world-specific mods folder.

## Generated commands

```text
/or_preview
/or_build <structure_name>
/or_rollback_last
```

## Future OpenRealm integration

The stronger long-term path is to connect this creator kernel to your existing AI-native runtime:

- Use `OpenRealmPlan` as the provider-neutral plan format.
- Add a Nova command: `/nova create mod <prompt>`.
- Add a formspec or launcher UI preview for plan approval.
- Queue world mutations through your runtime task queue instead of direct generated commands.
- Store rollback records through the runtime rollback API.
- Use the plan id as the audit correlation id.

## Safe defaults

The generated Lua:

- checks protected areas before structure placement;
- caps structure node count;
- stores previous nodes before writing;
- logs build and rollback actions;
- does not request HTTP access;
- does not use `dofile`, `loadstring`, `io`, `os`, or network APIs.
