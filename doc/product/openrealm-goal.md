# OpenRealm Goal

## Vision

OpenRealm is an open-source AI-native voxel world creator built on Luanti.
Players describe worlds, play them with friends, and own the code.

Nova is the in-world AI assistant. Nova helps players build, repair, modify,
explain, and share worlds through safe previews, approval, task execution,
audit trails, and rollback.

Luminara is the first showcase world: a polished creator playground designed to
prove that prompt-driven voxel creation can feel trustworthy, visual, and fun
without becoming a giant survival-content treadmill.

## Positioning

Primary phrase:

```text
Describe a voxel world. Play it with friends. Own the code.
```

Category phrase:

```text
The open-source AI-native voxel studio.
```

Internal project rule:

```text
Do not lead with "Minecraft clone." Lead with safe AI-native world creation.
```

## Product Hierarchy

- **OpenRealm:** platform and public project identity.
- **Nova:** player-facing AI assistant and agent runtime surface.
- **Luminara:** first default showcase world/game profile.
- **Luanti:** upstream engine foundation.
- **ai_runtime:** clean technical profile for runtime verification.

## Non-Negotiables

- The engine remains the world mutation authority.
- Agents use capability-gated tools and bounded context.
- Player-facing world mutation goes through preview, approval, task execution,
  audit, and rollback.
- The core fork excludes private family-server content, proprietary assets, and
  one-off showcase builds such as `spacebase`, `themepark`, and
  `disneyland100`.
- AI-generated Lua/mod content is treated as untrusted until template-validated
  and tested in a disposable world.
- Compatibility/import is important, but it follows runtime safety,
  observability, and the creator loop.

## First Public Milestone

The first milestone is not a full survival game, a marketplace, or a launcher
rewrite. It is one reliable emotional loop:

```text
I typed a prompt, Nova planned a world change, I approved it, Nova built it,
I played inside it, and I could undo it.
```

Ship this with:

- one polished creator playground,
- ten golden prompts that work every time,
- visible preview and rollback,
- request/response traces for improvement,
- a short demo script and video path,
- public docs that explain why this is AI-native rather than chatbot-driven.

## Long-Term Goal

OpenRealm becomes the easiest open-source way to create, play, share, and host
Minecraft-like voxel worlds with AI, while preserving user ownership, local
control, modding freedom, and a trustworthy runtime safety model.
