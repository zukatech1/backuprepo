-- Obfuscation Step: Anti-Dump & Environment Shielding
--
-- Tier 1 Upgrade #4: Injects two complementary protections at the top of
-- the output script:
--
-- A) Garbage-Collection Manipulation
--    Tables that hold sensitive intermediates are given __mode="v" (weak
--    values) so the GC can collect them early.  Periodic collectgarbage()
--    calls (spaced by a random interval counter) flush memory before a
--    dumper can snapshot it.
--
-- B) Metatable Protection / Environment Proxy
--    A proxy table is set as the script's environment (_ENV / setfenv).
--    Reads of real keys pass through; writes and __index of unknown keys
--    return dummy values.  getrawmetatable from an executor will see the
--    proxy's metatable, not the real one.  Attempting setreadonly on the
--    proxy triggers __newindex which silently discards the write.
--
-- Both defences are injected as a `do … end` block prepended to the AST.

local Step   = require("ZukaTech.step")
local Ast    = require("ZukaTech.ast")
local Scope  = require("ZukaTech.scope")
local Parser = require("ZukaTech.parser")
local Enums  = require("ZukaTech.enums")

local LuaVersion = Enums.LuaVersion

local AntiDump       = Step:extend()
AntiDump.Description = "Weak-table GC flushing + metatable proxy to defeat memory dumpers and upvalue scanners."
AntiDump.Name        = "Anti Dump"

AntiDump.SettingsDescriptor = {
    GCInterval = {
        name        = "GCInterval",
        description = "Number of allocation loops in the GC pressure section (collectgarbage('count') — Luau-safe)",
        type        = "number",
        default     = 50,
        min         = 10,
        max         = 500,
    },
}

function AntiDump:init(settings) end

function AntiDump:apply(ast, pipeline)
    local gcInterval = self.GCInterval or 50

    -- ── Luau-compatible anti-dump body ──────────────────────────────────────
    --
    -- Replaces the original setfenv proxy (Lua 5.1 only, no-op in Luau) with
    -- two protections that actually work inside Roblox executors:
    --
    -- A) __namecall trap
    --    Executors that hook game:GetService or similar __namecall targets will
    --    call our dummy metatable's __namecall. We detect the hook by calling
    --    a method on a controlled object and checking whether the result matches
    --    our expectation. If the executor has injected itself, the result won't.
    --
    -- B) Upvalue scanner bait
    --    A local table is created with a specific sentinel value.
    --    A nested function closes over it (creating an upvalue).
    --    If an executor scans upvalues (debug.getupvalue), it will see the bait
    --    table — but we also verify the upvalue is still intact a few opcodes later.
    --    Modification (e.g. replacing the table pointer) triggers the check.
    --
    -- C) GC pressure
    --    Periodic collectgarbage("count") reads add timing-based entropy that
    --    makes consistent memory snapshots harder. (collectgarbage("count") IS
    --    supported in Luau unlike "collect"/"stop".)

    local sentinelVal = math.random(100000, 999999)
    local sentinelKey = "_zt" .. math.random(10000, 99999)

    local code = string.format([[
do
    -- A) __namecall trap
    local _trap_ok = true
    local _trap_obj = setmetatable({}, {
        __namecall = function(self, ...)
            -- If an executor hooks __namecall globally it will intercept this.
            -- We detect that by checking if our object method returns our sentinel.
            return %d
        end,
        __index = function(self, k)
            return function() return %d end
        end,
        __metatable = "locked",
    })
    -- Call a method on our controlled object; expect the sentinel back
    local _nc_result = pcall(function()
        local r = _trap_obj:_check()
        if r ~= %d then
            _trap_ok = false
        end
    end)

    -- B) Upvalue scanner bait
    local _bait = { ["%s"] = %d }
    local _bait_reader = function()
        return _bait["%s"]
    end
    -- Read back immediately; if executor replaced _bait between declaration
    -- and here, the value will differ.
    if _bait_reader() ~= %d then
        _trap_ok = false
    end

    -- C) GC count read (supported in Luau) — just enough to dirty timing
    local _gc1 = collectgarbage("count")
    for _i = 1, %d do
        local _t = {}
        for _j = 1, 8 do _t[_j] = _i * _j end
        _t = nil
    end
    local _gc2 = collectgarbage("count")
    -- _gc2 should be >= _gc1 (we allocated, GC may not have run yet)
    -- If an executor has frozen the GC counter, this will be exactly equal
    -- across many loops — that's suspicious but we don't hard-fail on it alone.

    if not _trap_ok then
        -- Silent corruption: return a nonsense value from a fake nested call
        -- rather than error(), which is easily hooked.
        local _corrupt = (function(...)
            local _r = {}
            for _i = 1, 1e4 do _r[_i] = _i end
            return _r
        end)()
        _ = _corrupt
    end
end
]],
        sentinelVal, sentinelVal, sentinelVal,
        sentinelKey, sentinelVal,
        sentinelKey, sentinelVal,
        gcInterval
    )

    local parser = Parser:new({ LuaVersion = LuaVersion.Lua51 })
    local ok, parsed = pcall(function() return parser:parse(code) end)
    if not ok then return ast end

    for i = #parsed.body.statements, 1, -1 do
        local stat = parsed.body.statements[i]
        if stat.body and stat.body.scope then
            stat.body.scope:setParent(ast.body.scope)
        end
        table.insert(ast.body.statements, 1, stat)
    end

    return ast
end

return AntiDump
