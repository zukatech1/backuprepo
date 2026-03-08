-- Obfuscation Step: Virtual Global Table
--
-- Tier 1 Upgrade: Moves all global references into a local proxy table at
-- startup. Executor "Global Call" scanners see only table index reads instead
-- of direct global access (game, workspace, require, print, …).
--
--   Before:  game:GetService("Players")
--   After:   _VG[7342]:GetService("Players")

local Step     = require("ZukaTech.step")
local Ast      = require("ZukaTech.ast")
local visitast = require("ZukaTech.visitast")

local AstKind = Ast.AstKind

local VirtualGlobals       = Step:extend()
VirtualGlobals.Description = "Routes global references through a numeric-keyed local proxy table, hiding them from executor global-call scanners."
VirtualGlobals.Name        = "Virtual Globals"

VirtualGlobals.SettingsDescriptor = {
    Treshold = {
        name        = "Treshold",
        description = "Fraction of global references to redirect (0-1)",
        type        = "number",
        default     = 1,
        min         = 0,
        max         = 1,
    },
    UseNumericKeys = {
        name        = "UseNumericKeys",
        description = "Use numeric keys instead of string keys",
        type        = "boolean",
        default     = true,
    },
}

function VirtualGlobals:init(settings) end

function VirtualGlobals:apply(ast, pipeline)
    local globalScope = ast.globalScope
    local rootScope   = ast.body.scope

    -- 1. Collect all global names used in the AST via variablesLookup (name->id)
    local nameToId = {}  -- name -> global scope id
    visitast(ast, nil, function(node)
        if node.kind == AstKind.VariableExpression and node.scope == globalScope then
            local name = globalScope:getVariableName(node.id)
            if name and not nameToId[name] then
                nameToId[name] = node.id
            end
        end
    end)

    if not next(nameToId) then return ast end

    -- 2. Assign each global a proxy key
    local nameToKey = {}
    local keyBase   = math.random(1000, 9000)
    local keyStep_  = math.random(7, 31)
    local idx       = 0
    for name, _ in pairs(nameToId) do
        if self.UseNumericKeys then
            nameToKey[name] = keyBase + idx * keyStep_
        else
            nameToKey[name] = name
        end
        idx = idx + 1
    end

    -- 3. Create proxy var in rootScope
    local proxyId = rootScope:addVariable()

    -- 4. Build: local _VG = {}
    local initStmts = {}
    table.insert(initStmts, Ast.LocalVariableDeclaration(
        rootScope, { proxyId }, { Ast.TableConstructorExpression({}) }
    ))

    -- 5. Build: _VG[key] = globalName  for each collected global
    for name, gid in pairs(nameToId) do
        local key     = nameToKey[name]
        local keyExpr = type(key) == "number"
            and Ast.NumberExpression(key)
            or  Ast.StringExpression(key)

        rootScope:addReferenceToHigherScope(globalScope, gid)
        table.insert(initStmts, Ast.AssignmentStatement(
            { Ast.AssignmentIndexing(
                Ast.VariableExpression(rootScope, proxyId),
                keyExpr
            )},
            { Ast.VariableExpression(globalScope, gid) }
        ))
    end

    -- 6. Rewrite VariableExpression(globalScope, id) -> _VG[key]
    visitast(ast, nil, function(node, data)
        if node.kind == AstKind.VariableExpression
            and node.scope == globalScope
            and math.random() <= self.Treshold then

            local name = globalScope:getVariableName(node.id)
            local key  = name and nameToKey[name]
            if key then
                local nodeScope = data and data.scope or rootScope
                nodeScope:addReferenceToHigherScope(rootScope, proxyId)
                local keyExpr = type(key) == "number"
                    and Ast.NumberExpression(key)
                    or  Ast.StringExpression(key)
                return Ast.IndexExpression(
                    Ast.VariableExpression(rootScope, proxyId),
                    keyExpr
                )
            end
        end
    end)

    -- 7. Prepend init statements
    for i = #initStmts, 1, -1 do
        table.insert(ast.body.statements, 1, initStmts[i])
    end

    return ast
end

return VirtualGlobals
