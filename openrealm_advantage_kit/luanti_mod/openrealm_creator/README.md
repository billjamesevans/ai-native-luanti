# openrealm_creator Luanti Mod Prototype

This is a conservative proof-of-flow mod for OpenRealm.

Commands:

```text
/realm_plan <prompt>
/realm_approve
/realm_undo
/realm_status
```

`/realm_approve` queues a chunked `compat_import` task through the AI runtime.
It fails closed if the runtime import queue is not available.

The mod demonstrates the OpenRealm principle:

> Nova plans. The player approves. The runtime mutates. Rollback is captured.

It is intentionally small and should be treated as a prototype, not the final AI runtime integration.
