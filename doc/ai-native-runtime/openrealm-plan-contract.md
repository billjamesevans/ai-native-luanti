# OpenRealm Plan Contract

Status: canonical data contract for Nova-created OpenRealm content plans.

Nova is allowed to propose an `openrealm.plan.v1` document. OpenRealm validates
the document. Luanti remains the world authority and only mutates the world
after the required control chain: preview, human approval, queued execution,
audit recording, and rollback metadata.

Required control chain: preview, human approval, queued execution, audit recording, and rollback metadata.

The contract is intentionally data-first. It does not carry raw Lua, shell
commands, provider credentials, private paths, copied assets, or direct world
mutation instructions.

## Artifacts

- Schema: `doc/ai-native-runtime/schemas/openrealm-plan-v1.schema.json`
- Example: `doc/ai-native-runtime/examples/openrealm-plan-v1.example.json`
- Verifier: `python3 util/openrealm_plan_contract.py`

The verifier is dependency-free and performs safety checks that JSON Schema
alone does not express well, including raw-code payload detection, identifier
safety, node/write budgets, external node prefix allowlisting, and rollback
policy enforcement.

## Required Sections

An OpenRealm Plan must include:

- product identity: `schema_version`, `product`, `assistant`, `plan_id`,
  `plan_kind`, `title`, `source_prompt`, `created_at`, `mod_name`, `summary`,
  and `tags`;
- budgets and mutation policy: `safety_budget.requires_preview = true`,
  `requires_approval = true`, `rollback_required = true`, and
  `ai_direct_world_mutation_allowed = false`;
- generated content data: `nodes`, `craft_items`, `tools`, `recipes`, `ores`,
  `structures`, and `world_recipe`;
- human-control data: `approval_steps`;
- transparency data: `ai_disclosure` and `provenance`.

## Runtime Boundary

The plan is not executable code. Generated Luanti code must be deterministic
template output from a validated plan. Structure placement must enter the AI
runtime task queue first and must carry audit and rollback metadata before any
world mutation is applied.

Compatibility import may later produce the same plan shape, but imported assets
remain operator-supplied references unless rights and packaging are separately
validated.

## Verification

Run:

```bash
python3 util/openrealm_plan_contract.py
```

The report fails if:

- contract files are missing;
- the public example is invalid;
- generated kit plans no longer satisfy the contract;
- unsafe identifiers, raw code payloads, over-budget structures, private paths,
  provider secret markers, or missing rollback policy are accepted;
- docs stop linking the schema and verifier.
