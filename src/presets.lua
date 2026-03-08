-- This Script is Part of the ZukaTech Obfuscator by Levno_710
--
-- pipeline.lua
--
-- This Script Provides some configuration presets

return {
    ["Minify"] = {
        -- The default LuaVersion is Lua51
        LuaVersion = "Lua51";
        -- For minifying no VarNamePrefix is applied
        VarNamePrefix = "";
        -- Name Generator for Variables
        NameGenerator = "MangledShuffled";
        -- No pretty printing
        PrettyPrint = false;
        -- Seed is generated based on current time
        Seed = 0;
        -- No obfuscation steps
        Steps = {

        }
    };
    ["Weak"] = {
        -- The default LuaVersion is Lua51
        LuaVersion = "Lua51";
        -- For minifying no VarNamePrefix is applied
        VarNamePrefix = "";
        -- Name Generator for Variables that look like this: IlI1lI1l
        NameGenerator = "MangledShuffled";
        -- No pretty printing
        PrettyPrint = false;
        -- Seed is generated based on current time
        Seed = 0;
        -- Obfuscation steps
        Steps = {
            {
                Name = "Vmify";
                Settings = {

                };
            },
            {
                Name = "ConstantArray";
                Settings = {
                    Treshold    = 1;
                    StringsOnly = true;
                }
            },
            {
                Name = "WrapInFunction";
                Settings = {

                }
            },
        }
    };
    ["Vmify"] = {
        -- The default LuaVersion is Lua51
        LuaVersion = "Lua51";
        -- For minifying no VarNamePrefix is applied
        VarNamePrefix = "";
        -- Name Generator for Variables that look like this: IlI1lI1l
        NameGenerator = "MangledShuffled";
        -- No pretty printing
        PrettyPrint = false;
        -- Seed is generated based on current time
        Seed = 0;
        -- Obfuscation steps
        Steps = {
            {
                Name = "Vmify";
                Settings = {

                };
            },
        }
    };
    ["Medium"] = {
        -- The default LuaVersion is Lua51
        LuaVersion = "Lua51";
        -- For minifying no VarNamePrefix is applied
        VarNamePrefix = "";
        -- Name Generator for Variables
        NameGenerator = "MangledShuffled";
        -- No pretty printing
        PrettyPrint = false;
        -- Seed is generated based on current time
        Seed = 0;
        -- Obfuscation steps
        Steps = {
            {
                Name = "EncryptStrings";
                Settings = {

                };
            },
            {
                Name = "AntiTamper";
                Settings = {
                    UseDebug = false;
                };
            },
            {
                Name = "Vmify";
                Settings = {

                };
            },
            {
                Name = "ConstantArray";
                Settings = {
                    Treshold    = 1;
                    StringsOnly = true;
                    Shuffle     = true;
                    Rotate      = true;
                    LocalWrapperTreshold = 0;
                }
            },
            {
                Name = "NumbersToExpressions";
                Settings = {

                }
            },
            {
                Name = "WrapInFunction";
                Settings = {

                }
            },
        }
    };
    ["Strong"] = {
        -- The default LuaVersion is Lua51
        LuaVersion = "Lua51";
        -- For minifying no VarNamePrefix is applied
        VarNamePrefix = "";
        -- Name Generator for Variables that look like this: IlI1lI1l
        NameGenerator = "MangledShuffled";
        -- No pretty printing
        PrettyPrint = false;
        -- Seed is generated based on current time
        Seed = 0;
        -- Obfuscation steps
        Steps = {
            {
                Name = "Vmify";
                Settings = {

                };
            },
            {
                Name = "EncryptStrings";
                Settings = {

                };
            },
            {
                Name = "AntiTamper";
                Settings = {

                };
            },
            {
                Name = "Vmify";
                Settings = {

                };
            },
            {
                Name = "ConstantArray";
                Settings = {
                    Treshold    = 1;
                    StringsOnly = true;
                    Shuffle     = true;
                    Rotate      = true;
                    LocalWrapperTreshold = 0;
                }
            },
            {
                Name = "NumbersToExpressions";
                Settings = {

                }
            },
            {
                Name = "WrapInFunction";
                Settings = {

                }
            },
        }
    },
    -- -------------------------------------------------------------------------
    -- Pure IlIlIIll style names — only I, l, 1 characters (il.lua generator)
    ["IlStyle"] = {
        LuaVersion    = "Lua51";
        VarNamePrefix = "";
        NameGenerator = "Il";
        PrettyPrint   = false;
        Seed          = 0;
        Steps = {
            {
                Name     = "Vmify";
                Settings = {};
            },
            {
                Name = "NumbersToExpressions";
                Settings = {
                    Treshold         = 1;
                    InternalTreshold = 0.5;
                };
            },
            {
                Name = "ConstantArray";
                Settings = {
                    Treshold             = 1;
                    StringsOnly          = false;
                    Shuffle              = true;
                    Rotate               = true;
                    LocalWrapperTreshold = 0;
                };
            },
            {
                Name     = "EncryptStrings";
                Settings = {};
            },
            {
                Name     = "WrapInFunction";
                Settings = {};
            },
        };
    };
    -- -------------------------------------------------------------------------
    -- Maximum everything — double Vmify, all steps, heavy junk, full ConstantArray
    ["Maximal"] = {
        LuaVersion    = "Lua51";
        VarNamePrefix = "";
        NameGenerator = "MangledShuffled";
        PrettyPrint   = false;
        Seed          = 0;
        Steps = {
            {
                Name     = "Vmify";
                Settings = {};
            },
            {
                Name     = "EncryptStrings";
                Settings = {};
            },
            {
                Name     = "AntiTamper";
                Settings = { UseDebug = false };
            },
            {
                Name     = "Vmify";
                Settings = {};
            },
            {
                Name = "ConstantArray";
                Settings = {
                    Treshold             = 1;
                    StringsOnly          = false;
                    Shuffle              = true;
                    Rotate               = true;
                    LocalWrapperTreshold = 0;
                };
            },
            {
                Name = "NumbersToExpressions";
                Settings = {
                    Treshold         = 1;
                    InternalTreshold = 0.5;
                };
            },
            {
                Name = "JunkStatements";
                Settings = {
                    InjectionCount  = 8;
                    Treshold        = 0.95;
                    TableWriteRatio = 0.6;
                    ChainLength     = 5;
                    TableWriteCount = 5;
                };
            },
            {
                Name = "DynamicXOR";
                Settings = { Treshold = 0.3; };
            },
            {
                Name = "FakeLoopWrap";
                Settings = { Treshold = 0.5; };
            },
            {
                Name     = "WrapInFunction";
                Settings = {};
            },
        };
    };
    -- -------------------------------------------------------------------------
    -- Fast obfuscation with no VM — good for large scripts that break under Vmify
    ["NoVm"] = {
        LuaVersion    = "Lua51";
        VarNamePrefix = "";
        NameGenerator = "MangledShuffled";
        PrettyPrint   = false;
        Seed          = 0;
        Steps = {
            {
                Name     = "EncryptStrings";
                Settings = {};
            },
            {
                Name     = "AntiTamper";
                Settings = { UseDebug = false };
            },
            {
                Name = "ConstantArray";
                Settings = {
                    Treshold             = 1;
                    StringsOnly          = false;
                    Shuffle              = true;
                    Rotate               = true;
                    LocalWrapperTreshold = 0;
                };
            },
            {
                Name = "NumbersToExpressions";
                Settings = {
                    Treshold         = 1;
                    InternalTreshold = 0.3;
                };
            },
            {
                Name = "JunkStatements";
                Settings = {
                    InjectionCount  = 5;
                    Treshold        = 0.8;
                    TableWriteRatio = 0.5;
                    ChainLength     = 3;
                    TableWriteCount = 3;
                };
            },
            {
                Name = "DynamicXOR";
                Settings = { Treshold = 0.2; };
            },
            {
                Name = "FakeLoopWrap";
                Settings = { Treshold = 0.35; };
            },
            {
                Name     = "WrapInFunction";
                Settings = {};
            },
        };
    };
    -- -------------------------------------------------------------------------
    -- IlIlIIll names + maximum junk/XOR — looks completely unreadable
    ["IlStyleHeavy"] = {
        LuaVersion    = "Lua51";
        VarNamePrefix = "";
        NameGenerator = "Il";
        PrettyPrint   = false;
        Seed          = 0;
        Steps = {
            {
                Name     = "Vmify";
                Settings = {};
            },
            {
                Name     = "EncryptStrings";
                Settings = {};
            },
            {
                Name     = "AntiTamper";
                Settings = { UseDebug = false };
            },
            {
                Name     = "Vmify";
                Settings = {};
            },
            {
                Name = "ConstantArray";
                Settings = {
                    Treshold             = 1;
                    StringsOnly          = false;
                    Shuffle              = true;
                    Rotate               = true;
                    LocalWrapperTreshold = 0;
                };
            },
            {
                Name = "NumbersToExpressions";
                Settings = {
                    Treshold         = 1;
                    InternalTreshold = 0.5;
                };
            },
            {
                Name = "JunkStatements";
                Settings = {
                    InjectionCount  = 8;
                    Treshold        = 0.95;
                    TableWriteRatio = 0.6;
                    ChainLength     = 5;
                    TableWriteCount = 5;
                };
            },
            {
                Name = "DynamicXOR";
                Settings = { Treshold = 0.3; };
            },
            {
                Name = "FakeLoopWrap";
                Settings = { Treshold = 0.5; };
            },
            {
                Name     = "WrapInFunction";
                Settings = {};
            },
        };
    };
    -- -------------------------------------------------------------------------
    ["LuarmorStyle"] = {
        LuaVersion    = "Lua51";
        VarNamePrefix = "";
        NameGenerator = "MangledShuffled";
        PrettyPrint   = false;
        Seed          = 0;
        Steps = {
            {
                Name     = "Vmify";
                Settings = {};
            },
            {
                Name     = "EncryptStrings";
                Settings = {};
            },
            {
                Name     = "AntiTamper";
                Settings = { UseDebug = false };
            },
            {
                Name     = "Vmify";
                Settings = {};
            },
            {
                Name = "ConstantArray";
                Settings = {
                    Treshold             = 1;
                    StringsOnly          = false;
                    Shuffle              = true;
                    Rotate               = true;
                    LocalWrapperTreshold = 0;
                };
            },
            {
                Name = "NumbersToExpressions";
                Settings = {
                    Treshold         = 1;
                    InternalTreshold = 0.2;
                };
            },
            {
                Name = "JunkStatements";
                Settings = {
                    InjectionCount  = 4;
                    Treshold        = 0.85;
                    TableWriteRatio = 0.5;
                    ChainLength     = 3;
                    TableWriteCount = 3;
                };
            },
            {
                Name = "DynamicXOR";
                Settings = { Treshold = 0.1; };
            },
            {
                Name = "FakeLoopWrap";
                Settings = {
                    Treshold = 0.30;
                };
            },
            {
                Name     = "WrapInFunction";
                Settings = {};
            },
        };
    };
    -- -------------------------------------------------------------------------
    -- Executor-compatible maximum security preset
    ["Tier1"] = {
        LuaVersion    = "Lua51";
        VarNamePrefix = "";
        NameGenerator = "MangledShuffled";
        PrettyPrint   = false;
        Seed          = 0;
        Steps = {
            { Name = "Vmify"; Settings = {}; },
            {
                Name = "DynamicXOR";
                Settings = { Treshold = 1; };
            },
            { Name = "EncryptStrings"; Settings = {}; },
            { Name = "AntiTamper"; Settings = { UseDebug = false; }; },
            {
                Name = "IntegrityHash";
                Settings = { SampleSize = 16; UseFakeExec = true; };
            },
            { Name = "Vmify"; Settings = {}; },
            {
                Name = "ConstantArray";
                Settings = {
                    Treshold             = 1;
                    StringsOnly          = true;
                    Shuffle              = true;
                    Rotate               = true;
                    LocalWrapperTreshold = 1;
                    LocalWrapperCount    = 3;
                    LocalWrapperArgCount = 12;
                };
            },
            {
                Name = "NumbersToExpressions";
                Settings = { Treshold = 1; InternalTreshold = 0.3; };
            },
            {
                Name = "OpaquePredicates";
                Settings = { Treshold = 0.85; InjectionsPerBlock = 2; };
            },
            {
                Name = "JunkStatements";
                Settings = {
                    InjectionCount  = 2;
                    Treshold        = 0.9;
                    TableWriteRatio = 0.5;
                    ChainLength     = 4;
                    TableWriteCount = 3;
                };
            },
            {
                Name = "AntiDump";
                Settings = { GCInterval = 50; UseEnvProxy = false; };
            },
            {
                Name = "VirtualGlobals";
                Settings = { Treshold = 1; UseNumericKeys = true; };
            },
            {
                Name = "FakeLoopWrap";
                Settings = { Treshold = 0.35; };
            },
            { Name = "WrapInFunction"; Settings = {}; },
        };
    };
    -- -------------------------------------------------------------------------
    -- Optimised for loadstring(game:HttpGet(...)) one-liners.
    -- Goal: hide the URL and call pattern without heavy VM overhead.
    -- No double-Vmify — keeps it executor-safe and fast to execute.
    ["HttpGet"] = {
        LuaVersion    = "Lua51";
        VarNamePrefix = "";
        NameGenerator = "MangledShuffled";
        PrettyPrint   = false;
        Seed          = 0;
        Steps = {
            -- Encrypt the URL string first before anything else touches it
            {
                Name     = "EncryptStrings";
                Settings = {};
            },
            -- XOR on top of the encrypted string — double-layers the URL
            {
                Name = "DynamicXOR";
                Settings = { Treshold = 1; };
            },
            -- Single Vmify to obscure the call pattern (loadstring/HttpGet)
            {
                Name     = "Vmify";
                Settings = {};
            },
            -- Pull all constants (including any residual string refs) into
            -- a shuffled/rotated array so nothing is readable at rest
            {
                Name = "ConstantArray";
                Settings = {
                    Treshold             = 1;
                    StringsOnly          = false;
                    Shuffle              = true;
                    Rotate               = true;
                    LocalWrapperTreshold = 1;
                    LocalWrapperCount    = 3;
                    LocalWrapperArgCount = 8;
                };
            },
            -- Light junk so the overall structure doesn't look like a
            -- one-liner wrapper — breaks naive pattern matching
            {
                Name = "JunkStatements";
                Settings = {
                    InjectionCount  = 2;
                    Treshold        = 0.7;
                    TableWriteRatio = 0.4;
                    ChainLength     = 2;
                    TableWriteCount = 2;
                };
            },
            -- Wrap so the entry point isn't a bare function call
            {
                Name     = "WrapInFunction";
                Settings = {};
            },
        };
    };
}
