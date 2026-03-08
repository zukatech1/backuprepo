"""
ZukaTech UI Bridge Server
---------------------------
Drop this into your ZukaTech folder and run:
    python server.py

Then open zukatechui.html in your browser.
Keep this terminal window open while using the UI.
"""

import http.server
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PORT = 5000
ZUKATECH_DIR = Path(__file__).parent.resolve()

# ── Lua executable discovery ──────────────────────────────────────────────────
def find_lua():
    candidates = ['lua.exe', 'lua5.1.exe', 'lua51.exe', 'luac5.1.exe', 'lua']
    for name in candidates:
        path = ZUKATECH_DIR / name
        if path.exists():
            return str(path)
    return 'lua'  # fallback to system lua

LUA_EXE = find_lua()
CLI_LUA  = str(ZUKATECH_DIR / 'src' / 'cli.lua')

# All valid presets — must match keys in src/presets.lua
PRESETS = ['Minify', 'Weak', 'Vmify', 'Medium', 'Strong', 'LuarmorStyle', 'IlStyle', 'IlStyleHeavy', 'Maximal', 'NoVm', 'HttpGet', 'Tier1']

# All injectable steps with their default Lua settings strings
VALID_STEPS = {
    'EncryptStrings':       '{}',
    'ConstantArray':        '{ Treshold=1; StringsOnly=true; Shuffle=true; Rotate=true; LocalWrapperTreshold=0; LocalWrapperCount=3; LocalWrapperArgCount=12; }',
    'NumbersToExpressions': '{ Treshold=1; InternalTreshold=0.2; }',
    'JunkStatements':       '{ InjectionCount=4; Treshold=0.85; TableWriteRatio=0.5; ChainLength=3; TableWriteCount=3; }',
    'FakeLoopWrap':         '{ Treshold=0.30; }',
    'AntiTamper':           '{ UseDebug=false; }',
    'ProxifyLocals':        '{ LiteralType="string"; }',
    'AddVararg':            '{}',
    'DynamicXOR':           '{ Treshold=1; }',
    'OpaquePredicates':     '{ Treshold=0.85; InjectionsPerBlock=2; }',
    'AntiDump':             '{ GCInterval=50; UseEnvProxy=false; }',
    'IntegrityHash':        '{ SampleSize=16; UseFakeExec=true; }',
    'VirtualGlobals':       '{ Treshold=1; UseNumericKeys=true; }',
}

print(f"""
╔══════════════════════════════════════════╗
║       ZukaTech UI Bridge v2.2          ║
╠══════════════════════════════════════════╣
║  Lua:    {LUA_EXE:<32} ║
║  CLI:    {CLI_LUA:<32} ║
║  Port:   {PORT:<32} ║
╚══════════════════════════════════════════╝

Open zukatechui.html in your browser.
Press Ctrl+C to stop.
""")

# ── Config override writer ────────────────────────────────────────────────────
# When the user toggles JunkStatements or FakeLoopWrap on a preset that doesn't
# already include them, we write a temporary config file that clones the preset
# and appends the extra steps. This avoids modifying presets.lua at runtime.

JUNK_STEP = """    {
        Name = "JunkStatements";
        Settings = {
            InjectionCount  = 4;
            Treshold        = 0.85;
            TableWriteRatio = 0.5;
            ChainLength     = 3;
            TableWriteCount = 3;
        };
    }"""

FAKE_LOOP_STEP = """    {
        Name = "FakeLoopWrap";
        Settings = {
            Treshold = 0.30;
        };
    }"""

# ── Tier 1 step snippets ──────────────────────────────────────────────────────
DYNAMIC_XOR_STEP = """    {
        Name = "DynamicXOR";
        Settings = { Treshold = 1; };
    }"""

OPAQUE_PREDICATES_STEP = """    {
        Name = "OpaquePredicates";
        Settings = { Treshold = 0.85; InjectionsPerBlock = 2; };
    }"""

ANTI_DUMP_STEP = """    {
        Name = "AntiDump";
        Settings = { GCInterval = 50; UseEnvProxy = false; };
    }"""

INTEGRITY_HASH_STEP = """    {
        Name = "IntegrityHash";
        Settings = { SampleSize = 16; UseFakeExec = true; };
    }"""

VIRTUAL_GLOBALS_STEP = """    {
        Name = "VirtualGlobals";
        Settings = { Treshold = 1; UseNumericKeys = true; };
    }"""

TIER1_KEY_STEPS = {
    "dynamicXOR":      DYNAMIC_XOR_STEP,
    "opaquePredicates": OPAQUE_PREDICATES_STEP,
    "antiDump":        ANTI_DUMP_STEP,
    "integrityHash":   INTEGRITY_HASH_STEP,
    "virtualGlobals":  VIRTUAL_GLOBALS_STEP,
}

def build_config_override(preset, add_junk, add_fake_loops, tier1_keys=None):
    """
    Returns a Lua config string that clones the named preset and appends
    any user-toggled extra steps. Returns None if no override needed.
    tier1_keys: dict of { keyName: True } for active Tier 1 toggle keys.
    """
    tier1_keys = tier1_keys or {}
    active_tier1 = [k for k, v in tier1_keys.items() if v and k in TIER1_KEY_STEPS]

    if not add_junk and not add_fake_loops and not active_tier1:
        return None

    extra_steps = []
    if add_junk:
        extra_steps.append(JUNK_STEP)
    if add_fake_loops:
        extra_steps.append(FAKE_LOOP_STEP)
    for k in active_tier1:
        extra_steps.append(TIER1_KEY_STEPS[k])

    inserts = "\n".join(f"table.insert(steps, {s.strip()})" for s in extra_steps)

    config_lua = f"""
local presets = require("presets")
local base = presets["{preset}"]

-- Deep-copy the Steps list so we don't mutate the cached preset
local steps = {{}}
for i, v in ipairs(base.Steps or {{}}) do
    steps[i] = v
end

-- Append the user-toggled extra steps
{inserts}

return {{
    LuaVersion    = base.LuaVersion    or "Lua51";
    VarNamePrefix = base.VarNamePrefix or "";
    NameGenerator = base.NameGenerator or "MangledShuffled";
    PrettyPrint   = base.PrettyPrint   or false;
    Seed          = base.Seed          or 0;
    Steps         = steps;
}}
"""
    return config_lua


def build_steps_override(preset, effective_steps):
    """
    Build a Lua config that clones preset and appends exactly the steps
    in effective_steps (already filtered to exclude preset-builtin ones).
    Returns None if nothing to add.
    """
    if not effective_steps:
        return None

    step_inserts = []
    for step in effective_steps:
        settings = VALID_STEPS.get(step, '{}')
        step_inserts.append(
            f'table.insert(steps, {{ Name = "{step}"; Settings = {settings}; }})'
        )

    inserts_lua = "\n".join(step_inserts)
    return f"""
local presets = require("presets")
local base = presets["{preset}"]
local steps = {{}}
for i, v in ipairs(base.Steps or {{}}) do steps[i] = v end
{inserts_lua}
return {{
    LuaVersion    = base.LuaVersion    or "Lua51";
    VarNamePrefix = base.VarNamePrefix or "";
    NameGenerator = base.NameGenerator or "MangledShuffled";
    PrettyPrint   = base.PrettyPrint   or false;
    Seed          = base.Seed          or 0;
    Steps         = steps;
}}
"""


class Handler(http.server.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        print(f"  [{self.address_string()}] {format % args}")

    def send_cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors()
        self.end_headers()

    def do_GET(self):
        if self.path == '/ping':
            self.send_response(200)
            self.send_cors()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'status': 'ok',
                'lua':     LUA_EXE,
                'cli':     CLI_LUA,
                'presets': PRESETS,
                'tier1_keys': list(TIER1_KEY_STEPS.keys()),
            }).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path != '/obfuscate':
            self.send_response(404)
            self.end_headers()
            return

        tmp_in_path   = None
        tmp_out_path  = None
        tmp_cfg_path  = None

        try:
            length  = int(self.headers.get('Content-Length', 0))
            body    = self.rfile.read(length)
            payload = json.loads(body.decode('utf-8'))

            lua_code       = payload.get('code', '')
            preset         = payload.get('preset', 'Medium')
            lua_ver        = payload.get('luaVersion', 'LuaU')
            # New unified step list from options panel
            step_keys      = payload.get('stepKeys', [])
            if not isinstance(step_keys, list):
                step_keys = []
            # Legacy fields still accepted for backward compat
            add_junk       = bool(payload.get('junkStatements', False))
            add_fake_loops = bool(payload.get('fakeLoopWrap', False))
            tier1_keys     = payload.get('tier1Keys', {})
            if not isinstance(tier1_keys, dict):
                tier1_keys = {}
            # Merge legacy flags into step_keys so everything goes through one path
            if add_junk and 'JunkStatements' not in step_keys:
                step_keys.append('JunkStatements')
            if add_fake_loops and 'FakeLoopWrap' not in step_keys:
                step_keys.append('FakeLoopWrap')
            for k, v in tier1_keys.items():
                step_map = {
                    'dynamicXOR': 'DynamicXOR', 'opaquePredicates': 'OpaquePredicates',
                    'antiDump': 'AntiDump', 'integrityHash': 'IntegrityHash',
                    'virtualGlobals': 'VirtualGlobals',
                }
                if v and k in step_map and step_map[k] not in step_keys:
                    step_keys.append(step_map[k])

            if not lua_code.strip():
                self._json(400, {'error': 'No Lua code provided'})
                return

            if preset not in PRESETS:
                preset = 'Medium'
            if lua_ver not in ('LuaU', 'Lua51'):
                lua_ver = 'LuaU'

            # If the preset already contains these steps, don't double-add them
            # Steps already baked into each preset — don't double-inject
            PRESET_STEPS = {
                'Minify':       set(),
                'Weak':         {'Vmify', 'ConstantArray', 'WrapInFunction'},
                'Vmify':        {'Vmify'},
                'Medium':       {'EncryptStrings', 'AntiTamper', 'Vmify', 'ConstantArray',
                                 'NumbersToExpressions', 'WrapInFunction'},
                'Strong':       {'Vmify', 'EncryptStrings', 'AntiTamper', 'ConstantArray',
                                 'NumbersToExpressions', 'WrapInFunction'},
                'LuarmorStyle': {'Vmify', 'EncryptStrings', 'AntiTamper', 'ConstantArray',
                                 'NumbersToExpressions', 'JunkStatements', 'FakeLoopWrap',
                                 'WrapInFunction'},
                'IlStyle':      {'Vmify', 'EncryptStrings', 'ConstantArray',
                                 'NumbersToExpressions', 'WrapInFunction'},
                'IlStyleHeavy': {'Vmify', 'EncryptStrings', 'AntiTamper', 'ConstantArray',
                                 'NumbersToExpressions', 'JunkStatements', 'DynamicXOR',
                                 'FakeLoopWrap', 'WrapInFunction'},
                'Maximal':      {'Vmify', 'EncryptStrings', 'AntiTamper', 'ConstantArray',
                                 'NumbersToExpressions', 'JunkStatements', 'DynamicXOR',
                                 'FakeLoopWrap', 'WrapInFunction'},
                'NoVm':         {'EncryptStrings', 'AntiTamper', 'ConstantArray',
                                 'NumbersToExpressions', 'JunkStatements', 'DynamicXOR',
                                 'FakeLoopWrap', 'WrapInFunction'},
                'HttpGet':      {'EncryptStrings', 'DynamicXOR', 'Vmify', 'ConstantArray',
                                 'JunkStatements', 'WrapInFunction'},
                'Tier1':        {'Vmify', 'DynamicXOR', 'EncryptStrings', 'AntiTamper',
                                 'IntegrityHash', 'ConstantArray', 'NumbersToExpressions',
                                 'OpaquePredicates', 'JunkStatements', 'AntiDump',
                                 'VirtualGlobals', 'FakeLoopWrap', 'WrapInFunction'},
            }
            already_in_preset = PRESET_STEPS.get(preset, set())
            effective_steps = [s for s in step_keys
                               if s in VALID_STEPS and s not in already_in_preset]
            # Legacy compat vars (used by build_config_override signature)
            effective_junk = 'JunkStatements' in effective_steps
            effective_fake = 'FakeLoopWrap' in effective_steps
            effective_t1   = {k: True for k in effective_steps
                              if k in ('DynamicXOR','OpaquePredicates','AntiDump',
                                       'IntegrityHash','VirtualGlobals')}

            # Write input to temp file
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.lua', delete=False,
                dir=str(ZUKATECH_DIR), encoding='utf-8'
            ) as tmp_in:
                tmp_in.write(lua_code)
                tmp_in_path = tmp_in.name

            tmp_out_path = tmp_in_path.replace('.lua', '_obf.lua')

            # Decide: use --preset or a dynamic --config override
            cfg_override = build_steps_override(preset, effective_steps)

            if cfg_override:
                with tempfile.NamedTemporaryFile(
                    mode='w', suffix='.lua', delete=False,
                    dir=str(ZUKATECH_DIR), encoding='utf-8'
                ) as tmp_cfg:
                    tmp_cfg.write(cfg_override)
                    tmp_cfg_path = tmp_cfg.name

                cmd = [
                    LUA_EXE, CLI_LUA,
                    '--config', tmp_cfg_path,
                    f'--{lua_ver}',
                    '--out', tmp_out_path,
                    tmp_in_path,
                ]
            else:
                cmd = [
                    LUA_EXE, CLI_LUA,
                    '--preset', preset,
                    f'--{lua_ver}',
                    '--out', tmp_out_path,
                    tmp_in_path,
                ]

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=str(ZUKATECH_DIR / 'src'),
                    timeout=60,
                )

                if result.returncode != 0:
                    error_msg = result.stderr.strip() or result.stdout.strip() or 'Unknown error'
                    self._json(200, {
                        'success': False,
                        'error':   error_msg,
                        'stdout':  result.stdout,
                        'stderr':  result.stderr,
                    })
                    return

                if os.path.exists(tmp_out_path):
                    with open(tmp_out_path, 'r', encoding='utf-8') as f:
                        obfuscated = f.read()
                    self._json(200, {
                        'success':  True,
                        'output':   obfuscated,
                        'stdout':   result.stdout,
                        'size_in':  len(lua_code),
                        'size_out': len(obfuscated),
                    })
                elif result.stdout.strip():
                    self._json(200, {
                        'success':  True,
                        'output':   result.stdout,
                        'size_in':  len(lua_code),
                        'size_out': len(result.stdout),
                    })
                else:
                    self._json(200, {
                        'success': False,
                        'error':  'Output file was not created.',
                        'stderr':  result.stderr,
                    })

            finally:
                for path in [tmp_in_path, tmp_out_path, tmp_cfg_path]:
                    try:
                        if path and os.path.exists(path):
                            os.remove(path)
                    except Exception:
                        pass

        except subprocess.TimeoutExpired:
            self._json(200, {'success': False, 'error': 'Obfuscation timed out (60s limit)'})
        except Exception as e:
            self._json(500, {'error': str(e)})

    def _json(self, code, data):
        body = json.dumps(data).encode('utf-8')
        self.send_response(code)
        self.send_cors()
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == '__main__':
    server = http.server.HTTPServer(('localhost', PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n\nServer stopped.')
        sys.exit(0)
