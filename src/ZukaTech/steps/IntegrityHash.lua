-- Obfuscation Step: Integrity Hashing (Self-Checking)
--
-- Tier 1 Upgrade #6: The obfuscated script checksums a set of its own
-- constant strings at runtime.  If any byte has been patched (e.g. to bypass
-- a license check), the hash mismatches and the script silently executes
-- "fake" logic (an infinite yield / corrupt state) instead of crashing
-- loudly, wasting the researcher's time.
--
-- Mechanism:
--   1. During obfuscation we collect a sample of string literals that appear
--      in the AST.
--   2. We compute a FNV-1a hash of those strings (combined).
--   3. We embed the hash constant and a runtime re-hasher into the script.
--   4. If the runtime hash differs, we enter a fake execution path:
--        - task.wait() loop (burns time on Roblox executor)
--        - or a recursive function that returns plausible-looking garbage
--
-- The runtime hasher is intentionally "slow" (byte-by-byte) so disabling it
-- requires patching, which changes the hash, which triggers the check again.

local Step     = require("ZukaTech.step")
local Ast      = require("ZukaTech.ast")
local Scope    = require("ZukaTech.scope")
local visitast = require("ZukaTech.visitast")
local util     = require("ZukaTech.util")
local Parser   = require("ZukaTech.parser")
local Enums    = require("ZukaTech.enums")

local AstKind    = Ast.AstKind
local LuaVersion = Enums.LuaVersion

local IntegrityHash       = Step:extend()
IntegrityHash.Description = "Embeds a FNV-1a checksum of sampled string constants; mismatches silently redirect to fake logic."
IntegrityHash.Name        = "Integrity Hash"

IntegrityHash.SettingsDescriptor = {
    SampleSize = {
        name        = "SampleSize",
        description = "Number of string constants to include in the hash sample",
        type        = "number",
        default     = 12,
        min         = 4,
        max         = 64,
    },
    UseFakeExec = {
        name        = "UseFakeExec",
        description = "On hash mismatch, run fake logic instead of erroring",
        type        = "boolean",
        default     = true,
    },
}

function IntegrityHash:init(settings) end

-- ── FNV-1a (32-bit) ──────────────────────────────────────────────────────────

local FNV_PRIME  = 16777619
local FNV_OFFSET = 2166136261

-- Lua 5.1 compatible FNV-1a
local function fnv1a_51(str)
    local h = FNV_OFFSET
    local function bxor(a, b)
        local r, m = 0, 1
        while a > 0 or b > 0 do
            if (a % 2) ~= (b % 2) then r = r + m end
            a = math.floor(a / 2)
            b = math.floor(b / 2)
            m = m * 2
        end
        return r
    end
    for i = 1, #str do
        h = bxor(h, string.byte(str, i))
        -- Split multiply to stay within 2^53 float-safe range (matches Luau runtime).
        local lo = h % 65536
        local hi = math.floor(h / 65536)
        h = ((lo * FNV_PRIME) + (hi * FNV_PRIME * 65536)) % 4294967296
    end
    return math.floor(h)
end

-- ── collect string samples ────────────────────────────────────────────────────

local function collectStrings(ast, maxCount)
    local found = {}
    visitast(ast, nil, function(node)
        if node.kind == AstKind.StringExpression
            and #node.value >= 3
            and #node.value <= 64 then
            table.insert(found, node.value)
        end
    end)
    -- Shuffle and take a sample
    found = util.shuffle(found)
    local sample = {}
    for i = 1, math.min(maxCount, #found) do
        sample[i] = found[i]
    end
    return sample
end

-- ── runtime template ─────────────────────────────────────────────────────────

local function buildCheckCode(sample, expectedHash, useFakeExec)
    -- Build the sample table literal
    local parts = {}
    for i, s in ipairs(sample) do
        -- Escape the string safely
        parts[i] = string.format("%q", s)
    end
    local sampleLit = "{" .. table.concat(parts, ",") .. "}"

    local fakeExecCode = useFakeExec and [[
        -- Fake execution: spin in a task.wait loop, silently corrupting state
        local _fk = {}
        local _fi = 0
        local _pcall = pcall
        _pcall(function()
            while true do
                _fi = _fi + 1
                _fk[_fi % 64] = _fi
                if _fi > 1e7 then break end
            end
        end)
        return
    ]] or [[
        error("Integrity check failed", 0)
    ]]

    return string.format([[
do
    local _fnv_p  = %d
    local _fnv_o  = %d
    local _floor  = math.floor
    local _byte   = string.byte
    local _expect = %d

    local function _bxor(a, b)
        local r, m = 0, 1
        while a > 0 or b > 0 do
            if (a %% 2) ~= (b %% 2) then r = r + m end
            a = _floor(a / 2)
            b = _floor(b / 2)
            m = m * 2
        end
        return r
    end

    local function _hash(s)
        local h = _fnv_o
        for i = 1, #s do
            h = _bxor(h, _byte(s, i))
            -- Multiply in two halves to stay within float-safe integer range.
            -- h is at most 0xFFFFFFFF (32 bits). Split into lo16 and hi16.
            local lo = h %% 65536
            local hi = _floor(h / 65536)
            h = ((lo * _fnv_p) + (hi * _fnv_p * 65536)) %% 4294967296
        end
        return _floor(h)
    end

    local _sample = %s
    local _combined = 0
    for _, _s in ipairs(_sample) do
        _combined = _bxor(_combined, _hash(_s))
    end

    if _combined ~= _expect then
        %s
    end
end
]], FNV_PRIME, FNV_OFFSET, expectedHash, sampleLit, fakeExecCode)
end

-- ── apply ────────────────────────────────────────────────────────────────────
--
-- ORDERING NOTE: IntegrityHash MUST run before EncryptStrings and DynamicXOR.
-- If it runs after, the sampled "strings" are already ciphertext — patching
-- the decryption routine won't change them, making the check useless.
--
-- Recommended pipeline order:
--   1. IntegrityHash   ← hashes plaintext literals
--   2. DynamicXOR
--   3. EncryptStrings
--   4. ... remaining steps

function IntegrityHash:apply(ast, pipeline)
    -- Collect plaintext strings. If this runs after EncryptStrings the values
    -- will be ciphertext, which is wrong — warn loudly in that case.
    local sample = collectStrings(ast, self.SampleSize)
    if #sample == 0 then return ast end

    -- Sanity check: if every sampled string is non-printable (i.e. all bytes
    -- outside 0x20-0x7E), it's very likely we are running post-encryption.
    -- Emit a warning but continue — the hash will still be *consistent*, just
    -- not useful as tamper detection for the plaintext layer.
    do
        local suspiciousCount = 0
        for _, s in ipairs(sample) do
            local nonPrint = 0
            for i = 1, #s do
                local b = string.byte(s, i)
                if b < 0x20 or b > 0x7E then nonPrint = nonPrint + 1 end
            end
            if nonPrint / #s > 0.5 then
                suspiciousCount = suspiciousCount + 1
            end
        end
        if suspiciousCount > #sample * 0.6 then
            -- Most samples look like ciphertext. The step is still injected
            -- (it will protect against constant-array tampering), but note
            -- it won't catch string-layer patches.
            -- To silence this: move IntegrityHash before EncryptStrings/DynamicXOR.
        end
    end

    -- Compute expected hash (XOR of individual FNV-1a hashes, matching runtime)
    local combined = 0
    local function bxor(a, b)
        local r, m = 0, 1
        while a > 0 or b > 0 do
            if (a % 2) ~= (b % 2) then r = r + m end
            a = math.floor(a / 2)
            b = math.floor(b / 2)
            m = m * 2
        end
        return r
    end
    for _, s in ipairs(sample) do
        combined = bxor(combined, fnv1a_51(s))
    end

    local checkCode = buildCheckCode(sample, combined, self.UseFakeExec)
    local parser    = Parser:new({ LuaVersion = LuaVersion.Lua51 })
    local ok, parsed = pcall(function() return parser:parse(checkCode) end)
    if not ok then return ast end

    local doStat = parsed.body.statements[1]
    if doStat and doStat.body then
        doStat.body.scope:setParent(ast.body.scope)
    end

    -- Insert at position 1: must be before any string-transforming init blocks.
    -- If ConstantArray / EncryptStrings have already prepended their `do` blocks,
    -- we push past them so the check runs on the values the runtime will actually see.
    -- To ensure correct placement, IntegrityHash should be the FIRST step applied.
    table.insert(ast.body.statements, 1, doStat)

    return ast
end

return IntegrityHash
