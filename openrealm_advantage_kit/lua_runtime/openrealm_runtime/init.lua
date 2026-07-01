-- OpenRealm Runtime Concept
-- This tiny mod is not required by generated packs. It demonstrates the future
-- shared runtime layer that generated plans could call into.

local MOD = minetest.get_current_modname()
local storage = minetest.get_mod_storage()

openrealm_runtime = rawget(_G, "openrealm_runtime") or {}

function openrealm_runtime.record_audit(event)
    event = event or {}
    event.at = os.time()
    local raw = storage:get_string("audit")
    local audit = raw ~= "" and minetest.parse_json(raw) or {}
    audit[#audit + 1] = event
    while #audit > 100 do
        table.remove(audit, 1)
    end
    storage:set_string("audit", minetest.write_json(audit))
    minetest.log("action", "[OpenRealm Runtime] " .. (event.type or "event") .. " plan=" .. (event.plan_id or "unknown"))
end

minetest.register_chatcommand("or_runtime_status", {
    description = "Show OpenRealm runtime concept status.",
    func = function(name)
        local raw = storage:get_string("audit")
        local audit = raw ~= "" and minetest.parse_json(raw) or {}
        return true, "[OpenRealm Runtime] audit_records=" .. tostring(#audit)
    end,
})

minetest.log("action", "[OpenRealm Runtime] Loaded " .. MOD)
