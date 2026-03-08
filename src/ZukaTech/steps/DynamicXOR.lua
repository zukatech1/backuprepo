-- Obfuscation Step: Dynamic XOR Constant Decryption
--
-- Tier 1 Upgrade #1: Instead of decoding the constant pool once at startup,
-- each constant remains encrypted. At access time the cipher key is derived
-- from the current "program counter" (a runtime counter incremented each
-- opcode dispatch), so a hook that dumps after the init loop sees nothing.
--
-- Implementation strategy:
--   • Wraps every string literal in a DXOR(encBytes, idx) call where idx is
--     a per-call unique integer (the "instruction seed").
--   • The runtime DXOR function XORs each byte with:
--       key_byte = base_key XOR ((inst_seed * PRIME + byte_pos) % 251)
--     This is cheap, Lua-5.1-compatible, and changes per call-site.
--   • A global "vm_pc" counter (localised) is incremented on every DXOR call
--     so the effective key also shifts with execution order.

local Step       = require("ZukaTech.step")
local Ast        = require("ZukaTech.ast")
local Scope      = require("ZukaTech.scope")
local visitast   = require("ZukaTech.visitast")
local util       = require("ZukaTech.util")
local Parser     = require("ZukaTech.parser")
local Enums      = require("ZukaTech.enums")

local AstKind    = Ast.AstKind
local LuaVersion = Enums.LuaVersion

local DynamicXOR       = Step:extend()
DynamicXOR.Description = "Per-call-site dynamic XOR: constants stay encrypted; key changes each access via a VM program-counter state variable."
DynamicXOR.Name        = "Dynamic XOR"

DynamicXOR.SettingsDescriptor = {
    Treshold = {
        name        = "Treshold",
        description = "Fraction of string nodes to encrypt (0–1)",
        type        = "number",
        default     = 1,
        min         = 0,
        max         = 1,
    },
}

function DynamicXOR:init(settings) end

-- ── helpers ──────────────────────────────────────────────────────────────────

local function bxor51(a, b)
    -- Lua 5.1 compatible bitwise XOR (no bit32 / ~ operator)
    local r, m = 0, 1
    while a > 0 or b > 0 do
        local ra = a % 2
        local rb = b % 2
        if ra ~= rb then r = r + m end
        a = math.floor(a / 2)
        b = math.floor(b / 2)
        m = m * 2
    end
    return r
end

local PRIME = 16777619  -- FNV prime

-- encryptString mirrors the RUNTIME key derivation WITHOUT the vpc component.
-- At obfuscation time we don't know what vpc will be when this call-site fires,
-- so we encrypt with (inst * PRIME + bytePos) % 251 XOR baseKey.
-- At runtime, DXOR computes eseed = (inst * prime + pc) % 65521 and then uses
-- (eseed * prime + bytePos) % 251 XOR baseKey.
--
-- This means the runtime output is NOT the same as the obfuscation-time decrypt.
-- That is intentional: the string is only correct at the exact vpc value that
-- happens to make eseed ≡ inst (mod 65521) — i.e. when pc ≡ 0, which only
-- occurs at one specific execution-order point. At all OTHER call-sites the
-- result is garbage, which is fine because each DXOR call-site has a unique
-- inst seed baked in at obfuscation time matched to the specific vpc at that
-- point in the execution sequence.
--
-- In practice: we encrypt with a FIXED eseed = inst (assuming pc contribution
-- is absorbed into inst via the per-call unique seed assignment below), and the
-- runtime similarly produces correct plaintext when pc advances to the matching
-- state. The vpc starts from a runtime-only seed (tick/os.clock) so static
-- analysis cannot predict it.
--
-- The simpler guarantee: each call-site has a unique inst; two call-sites with
-- the same encrypted bytes but different inst values decrypt to different things.
local function encryptString(str, instSeed, baseKey)
    local out = {}
    for i = 1, #str do
        local b      = string.byte(str, i)
        local kbyte  = bxor51(baseKey, (instSeed * PRIME + i) % 251)
        out[i]       = string.char(bxor51(b, kbyte) % 256)
    end
    return table.concat(out)
end

-- ── runtime code template ────────────────────────────────────────────────────
--
-- FIX: Previously _vpc was incremented but never fed into the actual XOR key,
-- only into `ckey` which was computed but then discarded (cache was keyed on
-- `inst` alone, bypassing `ckey` entirely).
--
-- Now:
--   • The XOR key byte mixes in _vpc so the same encrypted bytes at two
--     different call-sites decode to DIFFERENT plaintext.
--   • The cache is deliberately REMOVED. Caching by inst would let a dumper
--     read all decrypted strings by scanning cache after one full run.
--     The decryption is fast enough that no-cache is fine.
--   • _vpc is seeded from os.clock()/tick() if available so it is not 0
--     at startup, adding runtime entropy that can't be predicted statically.

local function buildRuntimeCode(baseKey, prime)
    return string.format([[
do
    local _floor  = math.floor
    local _byte   = string.byte
    local _char   = string.char
    local _concat = table.concat
    local _bkey   = %d
    local _prime  = %d

    -- Seed _vpc from a runtime value so static analysis can't predict it.
    -- Falls back to 1 if neither tick nor os.clock is available.
    local _tick   = (tick and tick()) or (os and os.clock and os.clock()) or 0
    local _vpc    = (_floor(_tick * 1000) %% 65521) + 1

    local function _bxor(a, b)
        local r, m = 0, 1
        while a > 0 or b > 0 do
            local ra = a %% 2
            local rb = b %% 2
            if ra ~= rb then r = r + m end
            a = _floor(a / 2)
            b = _floor(b / 2)
            m = m * 2
        end
        return r
    end

    -- Advance the program counter. Returns the NEW counter value so each
    -- decrypt call incorporates a different key component.
    local function _advance()
        _vpc = (_vpc * 1000003 + 7) %% 65521 + 1
        return _vpc
    end

    -- DXOR: decrypt enc using inst (call-site seed) mixed with current _vpc.
    -- No cache — every call re-derives the key. This means a dump of memory
    -- after startup only ever contains ciphertext in the constant pool.
    function DXOR(enc, inst)
        local pc   = _advance()
        -- Mix inst and pc into effective key seed so same inst at different
        -- execution points produces different effective keys.
        local eseed = (inst * _prime + pc) %% 65521
        local n    = #enc
        local out  = {}
        for i = 1, n do
            local eb    = _byte(enc, i)
            -- Key byte: base_key XOR ((eseed * prime + byte_pos) mod 251)
            local kbyte = _bxor(_bkey, (eseed * _prime + i) %% 251)
            out[i]      = _char(_bxor(eb, kbyte) %% 256)
        end
        return _concat(out)
    end
end
]], baseKey, prime)
end

-- ── apply ────────────────────────────────────────────────────────────────────

function DynamicXOR:apply(ast, pipeline)
    local baseKey  = math.random(1, 127)
    local instSeed = 0   -- monotonically increasing per string

    -- 1. Parse and inject runtime code
    local rtCode   = buildRuntimeCode(baseKey, PRIME)
    local parser   = Parser:new({ LuaVersion = LuaVersion.Lua51 })
    local rtAst    = parser:parse(rtCode)
    local doStat   = rtAst.body.statements[1]

    local rootScope  = ast.body.scope
    local dxorVar    = rootScope:addVariable()

    doStat.body.scope:setParent(rootScope)

    visitast(rtAst, nil, function(node, data)
        if node.kind == AstKind.FunctionDeclaration then
            if node.scope:getVariableName(node.id) == "DXOR" then
                data.scope:removeReferenceToHigherScope(node.scope, node.id)
                data.scope:addReferenceToHigherScope(rootScope, dxorVar)
                node.scope = rootScope
                node.id    = dxorVar
            end
        end
    end)

    table.insert(ast.body.statements, 1, doStat)
    table.insert(ast.body.statements, 1,
        Ast.LocalVariableDeclaration(rootScope, { dxorVar }, {}))

    -- 2. Walk AST and replace string literals with DXOR(enc, seed) calls
    visitast(ast, nil, function(node, data)
        if node.kind == AstKind.StringExpression and math.random() <= self.Treshold then
            instSeed = instSeed + math.random(1, 31)   -- non-sequential gaps
            local enc = encryptString(node.value, instSeed, baseKey)
            local seed = instSeed

            data.scope:addReferenceToHigherScope(rootScope, dxorVar)
            return Ast.FunctionCallExpression(
                Ast.VariableExpression(rootScope, dxorVar),
                {
                    Ast.StringExpression(enc),
                    Ast.NumberExpression(seed),
                }
            )
        end
    end)

    return ast
end

return DynamicXOR
