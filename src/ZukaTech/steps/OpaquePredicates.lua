-- Obfuscation Step: Opaque Predicates & Control-Flow Junk
--
-- Tier 1 Upgrade #3: Injects opaque predicates — conditions that are ALWAYS
-- true (or false) but are computationally difficult for a static analyser to
-- prove, forcing any analyst to symbolically evaluate complex math.
--
-- Predicate catalogue (always-true examples):
--   • sin(x)^2 + cos(x)^2 > 0.5          (Pythagorean identity ≡ 1)
--   • (n*(n+1)) % 2 == 0                  (product of consecutive ints)
--   • floor(sqrt(n*n)) == n               (perfect square)
--   • (a^3 + b^3) ~= (a+b)^3 - 3*a*b*(a+b)  (always FALSE for a,b≠0 → negated)
--   • (x % p) * (p - (x % p)) >= 0        (non-negative by def)
--
-- Each predicate is wrapped around dead blocks so decompilers see legitimate
-- if/else branches but can never simplify the tree without solving the math.

local Step     = require("ZukaTech.step")
local Ast      = require("ZukaTech.ast")
local Scope    = require("ZukaTech.scope")
local visitast = require("ZukaTech.visitast")
local Parser   = require("ZukaTech.parser")
local Enums    = require("ZukaTech.enums")

local AstKind    = Ast.AstKind
local LuaVersion = Enums.LuaVersion

local OpaquePredicates       = Step:extend()
OpaquePredicates.Description = "Injects always-true/false opaque predicates (trig identities, number theory) to prevent static control-flow analysis."
OpaquePredicates.Name        = "Opaque Predicates"

OpaquePredicates.SettingsDescriptor = {
    Treshold = {
        name    = "Treshold",
        description = "Probability that each function block gets a predicate injection",
        type    = "number",
        default = 0.75,
        min     = 0,
        max     = 1,
    },
    InjectionsPerBlock = {
        name    = "InjectionsPerBlock",
        description = "Max predicates injected per block",
        type    = "number",
        default = 2,
        min     = 1,
        max     = 6,
    },
}

function OpaquePredicates:init(settings) end

-- ── predicate generators ─────────────────────────────────────────────────────
--
-- FIX: All original predicates used only compile-time constants, making them
-- trivially foldable by any deobfuscator that runs constant propagation.
--
-- New predicates use runtime values (os.clock, tick, math.random, select('#',...))
-- that are unknowable at static analysis time, forcing a full symbolic executor
-- to evaluate them. All predicates still evaluate to TRUE at runtime.

local predicates = {

    -- os.clock() / tick() always returns a non-negative number
    -- os.clock() >= 0 is always true; multiplied by 0 and compared keeps it opaque
    function()
        local a = math.random(1, 999)
        -- (tick or os.clock)() * 0 + a == a  →  always true
        -- Static analyser can't know what tick() returns
        return string.format(
            "((tick and tick() or (os and os.clock and os.clock()) or 0) * 0 + %d) == %d",
            a, a
        )
    end,

    -- math.random() returns a value in [0,1]; floor of that is always 0
    -- 0 + a == a → always true; math.random() can't be constant-folded
    function()
        local a = math.random(100, 9999)
        return string.format(
            "(math.floor(math.random() * 0) + %d) == %d",
            a, a
        )
    end,

    -- select('#', ...) >= 0 is always true for any vararg
    -- We wrap in a function call so the analyser sees a non-constant
    function()
        local a = math.random(1, 500)
        return string.format(
            "(function(...) return select('#', ...) >= 0 end)(%d)",
            a
        )
    end,

    -- type(x) == type(x) is always true, but type() is a runtime call
    function()
        local a = math.random(1, 9999)
        return string.format(
            "type(%d) == type(%d)",
            a, a
        )
    end,

    -- tostring(n):len() > 0 is always true for any number
    function()
        local n = math.random(10, 9999)
        return string.format(
            "tostring(%d):len() > 0",
            n
        )
    end,

    -- pcall(function() end) always returns true
    -- Static analysers rarely track pcall return values
    function()
        return "(function() local ok = pcall(function() end); return ok end)()"
    end,

    -- rawequal(x, x) is always true but rawequal is a runtime function
    function()
        local n = math.random(1, 65535)
        return string.format("rawequal(%d, %d)", n, n)
    end,

    -- math.max with runtime-mixed args: math.max(a, a-1) == a always
    function()
        local a = math.random(50, 9999)
        -- Mix in a math.random() * 0 so the arg looks non-constant
        return string.format(
            "math.max(%d + math.floor(math.random() * 0), %d) == %d",
            a, a - 1, a
        )
    end,
}

-- ── dead block content (realistic-looking but unreachable) ───────────────────

local function deadBlock(scope)
    -- A block that looks like it does work but is inside an always-false branch
    local innerScope = Scope:new(scope)
    local stmts = {}

    -- local _dX = random_number
    local dVar = innerScope:addVariable()
    table.insert(stmts, Ast.LocalVariableDeclaration(innerScope, {dVar},
        {Ast.NumberExpression(math.random(1, 65535))}))

    -- _dX = _dX * random + random
    table.insert(stmts, Ast.AssignmentStatement(
        {Ast.AssignmentVariable(innerScope, dVar)},
        {Ast.AddExpression(
            Ast.MulExpression(
                Ast.VariableExpression(innerScope, dVar),
                Ast.NumberExpression(math.random(2, 127))
            ),
            Ast.NumberExpression(math.random(1, 255))
        )}
    ))

    -- _dX = nil
    table.insert(stmts, Ast.AssignmentStatement(
        {Ast.AssignmentVariable(innerScope, dVar)},
        {Ast.NilExpression()}
    ))

    return Ast.Block(stmts, innerScope)
end

-- ── build an if statement with opaque predicate ──────────────────────────────

local function buildPredicateStatement(parentScope, parser)
    local pred = predicates[math.random(#predicates)]()

    -- Wrap: if <pred> then <real empty block> else <dead block> end
    -- The "real" branch is empty; the dead branch has junk.
    -- Analyst sees an if/else and must evaluate pred to know which runs.
    local code = string.format("if %s then end", pred)
    local ok, parsed = pcall(function()
        return parser:parse(code)
    end)
    if not ok then return nil end

    local ifStat = parsed.body.statements[1]
    if ifStat then
        ifStat.elseBody = deadBlock(parentScope)
        if ifStat.body then
            ifStat.body.scope:setParent(parentScope)
        end
    end
    return ifStat
end

-- ── apply ────────────────────────────────────────────────────────────────────

function OpaquePredicates:apply(ast, pipeline)
    local parser = Parser:new({ LuaVersion = LuaVersion.Lua51 })

    visitast(ast, nil, function(node, data)
        if node.kind ~= AstKind.Block then return end
        if not node.isFunctionBlock then return end
        if math.random() > self.Treshold then return end
        if #node.statements == 0 then return end

        local count = math.random(1, self.InjectionsPerBlock)
        for _ = 1, count do
            local stat = buildPredicateStatement(node.scope, parser)
            if stat then
                -- Insert at a random position that isn't after return/break
                local insertPos = math.random(1, #node.statements)
                -- Don't insert after a return
                local last = node.statements[#node.statements]
                if last and (last.kind == AstKind.ReturnStatement
                          or last.kind == AstKind.BreakStatement) then
                    insertPos = math.max(1, #node.statements - 1)
                end
                table.insert(node.statements, insertPos, stat)
            end
        end
    end)

    return ast
end

return OpaquePredicates
