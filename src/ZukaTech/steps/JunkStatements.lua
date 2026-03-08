-- Obfuscation Step: Junk Statements
--
-- Inspired by the extra obfuscation layer seen in Luarmor's highest-tier output.
-- Injects two kinds of dead code that are 100% safe: they never touch real variables,
-- never affect control flow, and always evaluate to values that are immediately discarded.
--
-- Pattern 1 – Dead local + arithmetic chain:
--   local _jN = <rand>
--   _jN = _jN + <rand>        -- or *, -
--   _jN = _jN * <rand>
--   _jN = nil
--
-- Pattern 2 – Fake table-index writes (the L_42[213]=95 style):
--   local _tN = {}
--   _tN[<rand>] = <rand>
--   _tN[<rand>] = <rand>
--   _tN = nil
--
-- Safety guarantees:
--   * Only introduces brand-new scope-local variables (never touches existing ones).
--   * Uses only number literals and basic arithmetic – no globals, no upvalues.
--   * Never inserts after ReturnStatement or BreakStatement (would be unreachable).
--   * Fully compatible with Lua 5.1 / LuaU (Roblox).

local Step     = require("ZukaTech.step")
local Ast      = require("ZukaTech.ast")
local Scope    = require("ZukaTech.scope")
local visitast = require("ZukaTech.visitast")

local AstKind  = Ast.AstKind

local JunkStatements       = Step:extend()
JunkStatements.Description = "Injects dead local arithmetic chains and fake table-index writes to bloat and confuse decompilers (Luarmor-style)"
JunkStatements.Name        = "Junk Statements"

JunkStatements.SettingsDescriptor = {
    InjectionCount = {
        type    = "number",
        default = 3,
        min     = 0,
        max     = 20,
    },
    Treshold = {
        type    = "number",
        default = 0.85,
        min     = 0,
        max     = 1,
    },
    -- 0 = all arithmetic chains, 1 = all table writes
    TableWriteRatio = {
        type    = "number",
        default = 0.5,
        min     = 0,
        max     = 1,
    },
    ChainLength = {
        type    = "number",
        default = 3,
        min     = 1,
        max     = 6,
    },
    TableWriteCount = {
        type    = "number",
        default = 3,
        min     = 1,
        max     = 6,
    },
}

function JunkStatements:init(settings) end

local ArithConstructors = {
    Ast.AddExpression,
    Ast.SubExpression,
    Ast.MulExpression,
}

local function randNum()
    return math.random(1, 65535)
end

-- Build:  local _v = <seed>
--         _v = _v OP <rand>   (x ChainLength)
--         _v = nil
-- All ops reference only the new local variable. No cross-scope leaks.
function JunkStatements:buildArithChain(blockScope)
    local stmts = {}
    -- The LocalVariableDeclaration scope must be the BLOCK scope (where the
    -- local is declared), but the variable ID lives in a fresh child scope
    -- so that renaming never collides with real variables.
    local jScope = Scope:new(blockScope)
    local jId    = jScope:addVariable()

    -- local _v = <seed>
    table.insert(stmts, Ast.LocalVariableDeclaration(
        jScope,
        { jId },
        { Ast.NumberExpression(randNum()) }
    ))

    -- _v = _v OP <rand>
    for _ = 1, self.ChainLength do
        local ctor = ArithConstructors[math.random(#ArithConstructors)]
        -- Ast.VariableExpression and Ast.AssignmentVariable call scope:addReference
        -- internally, so no manual addReference needed.
        table.insert(stmts, Ast.AssignmentStatement(
            { Ast.AssignmentVariable(jScope, jId) },
            { ctor(
                Ast.VariableExpression(jScope, jId),
                Ast.NumberExpression(randNum())
            ) }
        ))
    end

    -- _v = nil
    table.insert(stmts, Ast.AssignmentStatement(
        { Ast.AssignmentVariable(jScope, jId) },
        { Ast.NilExpression() }
    ))

    return stmts
end

-- Build:  local _t = {}
--         _t[<rand>] = <rand>   (x TableWriteCount)
--         _t = nil
function JunkStatements:buildTableWrites(blockScope)
    local stmts = {}
    local jScope = Scope:new(blockScope)
    local jId    = jScope:addVariable()

    -- local _t = {}
    table.insert(stmts, Ast.LocalVariableDeclaration(
        jScope,
        { jId },
        { Ast.TableConstructorExpression({}) }
    ))

    -- _t[<rand>] = <rand>
    for _ = 1, self.TableWriteCount do
        table.insert(stmts, Ast.AssignmentStatement(
            {
                Ast.AssignmentIndexing(
                    Ast.VariableExpression(jScope, jId),
                    Ast.NumberExpression(randNum())
                )
            },
            { Ast.NumberExpression(randNum()) }
        ))
    end

    -- _t = nil
    table.insert(stmts, Ast.AssignmentStatement(
        { Ast.AssignmentVariable(jScope, jId) },
        { Ast.NilExpression() }
    ))

    return stmts
end

function JunkStatements:apply(ast)
    local self2 = self

    visitast(ast, nil, function(node, data)
        if node.kind ~= AstKind.Block then return end
        if math.random() > self2.Treshold then return end
        if #node.statements == 0 then return end

        -- Find the highest safe insertion index: don't put anything
        -- after a Return or Break (unreachable code upsets some executors).
        local maxInsert = #node.statements
        for i = #node.statements, 1, -1 do
            local k = node.statements[i].kind
            if k == AstKind.ReturnStatement or k == AstKind.BreakStatement then
                maxInsert = i - 1
            else
                break
            end
        end
        if maxInsert < 0 then return end

        for _ = 1, self2.InjectionCount do
            local pos   = math.random(1, maxInsert + 1)
            local stmts

            if math.random() < self2.TableWriteRatio then
                stmts = self2:buildTableWrites(node.scope)
            else
                stmts = self2:buildArithChain(node.scope)
            end

            for offset, stmt in ipairs(stmts) do
                table.insert(node.statements, pos + offset - 1, stmt)
            end

            maxInsert = maxInsert + #stmts
        end
    end)
end

return JunkStatements
