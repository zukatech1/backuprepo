import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import re
import json
import os
import pyperclip

# ── Theme ────────────────────────────────────────────────────────────────────
BG       = "#0e0e12"
BG2      = "#16161c"
BG3      = "#1e1e26"
ACCENT   = "#c32123"
ACCENT2  = "#ff4444"
CYAN     = "#00e5ff"
GREEN    = "#50c850"
YELLOW   = "#ffc832"
SUBTEXT  = "#888899"
TEXT     = "#e8e8f0"
BORDER   = "#2a2a38"
FONT_UI  = ("Consolas", 10)
FONT_SM  = ("Consolas", 9)
FONT_LG  = ("Consolas", 13, "bold")
FONT_TITLE = ("Consolas", 11, "bold")

# ── Converter Logic ──────────────────────────────────────────────────────────

def convert_to_addcmd(source: str) -> str:
    """Convert RegisterCommand / Modules.X:Initialize patterns to addcmd style."""
    output_lines = []
    source = source.strip()

    # Pattern 1: RegisterCommand({Name=..., Aliases={...}, ...}, function(args) ... end)
    reg_pattern = re.compile(
        r'RegisterCommand\s*\(\s*\{[^}]*Name\s*=\s*"([^"]+)"[^}]*(?:Aliases\s*=\s*\{([^}]*)\})?[^}]*\}\s*,\s*function\s*\((.*?)\)(.*?)end\s*\)',
        re.DOTALL
    )

    # Pattern 2: Modules.X:Initialize() wrapper — extract inner RegisterCommand calls
    init_pattern = re.compile(
        r'function\s+Modules\.(\w+):Initialize\(\)(.*?)end',
        re.DOTALL
    )

    converted = source
    found_any = False

    # Handle Modules.X:Initialize blocks first — unwrap them
    for init_match in init_pattern.finditer(source):
        mod_name = init_match.group(1)
        body = init_match.group(2)
        output_lines.append(f"-- ── Module: {mod_name} ──────────────────────────────────────")
        inner = convert_to_addcmd(body)
        output_lines.append(inner)
        found_any = True

    if found_any:
        return "\n".join(output_lines)

    # Handle RegisterCommand calls
    for m in reg_pattern.finditer(source):
        found_any = True
        name = m.group(1)
        aliases_raw = m.group(2) or ""
        params = m.group(3).strip()
        body = m.group(4).strip()

        # Parse aliases
        aliases = [a.strip().strip('"').strip("'")
                   for a in aliases_raw.split(",") if a.strip().strip('"').strip("'")]
        alias_str = "{" + ", ".join(f'"{a}"' for a in aliases) + "}"

        # Normalise params — addcmd always passes (args, speaker)
        if not params or params == "":
            params = "args, speaker"
        elif "args" not in params:
            params = "args, speaker"

        # Re-indent body
        body_lines = body.split("\n")
        indented = "\n".join("    " + l if l.strip() else "" for l in body_lines)

        output_lines.append(
            f'addcmd("{name}", {alias_str}, function({params})\n{indented}\nend)'
        )

    if not found_any:
        # Nothing to convert — wrap raw function body as a template
        output_lines.append(build_template_from_raw(source))

    return "\n\n".join(output_lines)


def build_template_from_raw(body: str) -> str:
    """Wrap raw Lua code into an addcmd template."""
    lines = body.strip().split("\n")
    indented = "\n".join("    " + l if l.strip() else "" for l in lines)
    return (
        'addcmd("commandname", {"alias1"}, function(args, speaker)\n'
        + indented
        + "\nend)"
    )


def generate_addcmd(name: str, aliases: list, body: str,
                    use_getplayer: bool, use_donotif: bool,
                    use_speaker: bool, use_runservice: bool) -> str:
    alias_str = "{" + ", ".join(f'"{a.strip()}"' for a in aliases if a.strip()) + "}"
    lines = []
    lines.append(f'addcmd("{name}", {alias_str}, function(args, speaker)')

    if use_getplayer:
        lines.append('    local targets = getPlayer(args[1], speaker)')
        lines.append('    if #targets == 0 then')
        lines.append(f'        DoNotif("No players found.", 2)')
        lines.append('        return')
        lines.append('    end')
        lines.append('    for _, plr in ipairs(targets) do')
        lines.append('        -- your code here')
        lines.append('    end')
    elif use_speaker:
        lines.append('    local char = speaker.Character')
        lines.append('    local hum = char and char:FindFirstChildOfClass("Humanoid")')
        lines.append('    local root = char and char:FindFirstChild("HumanoidRootPart")')
        lines.append('    if not (hum and root) then return end')
        lines.append('    -- your code here')
    else:
        if body.strip():
            for l in body.strip().split("\n"):
                lines.append("    " + l if l.strip() else "")
        else:
            lines.append('    -- your code here')

    if use_runservice:
        lines.append('')
        lines.append('    local conn')
        lines.append('    conn = RunService.Heartbeat:Connect(function()')
        lines.append('        -- loop body')
        lines.append('    end)')

    if use_donotif:
        lines.append(f'    DoNotif("{name}: DONE", 2)')

    lines.append('end)')
    return "\n".join(lines)


def generate_toggle_cmd(name: str, aliases: list, on_body: str, off_body: str) -> str:
    alias_str = "{" + ", ".join(f'"{a.strip()}"' for a in aliases if a.strip()) + "}"
    on_ind  = "\n".join("        " + l if l.strip() else "" for l in on_body.strip().split("\n"))
    off_ind = "\n".join("        " + l if l.strip() else "" for l in off_body.strip().split("\n"))
    return (
        f"do\n"
        f"    local {name}Enabled = false\n"
        f"    local {name}Conn\n\n"
        f'    addcmd("{name}", {alias_str}, function(args, speaker)\n'
        f"        {name}Enabled = not {name}Enabled\n"
        f"        if {name}Enabled then\n"
        f"{on_ind}\n"
        f'            DoNotif("{name}: ENABLED", 2)\n'
        f"        else\n"
        f"            if {name}Conn then {name}Conn:Disconnect() {name}Conn = nil end\n"
        f"{off_ind}\n"
        f'            DoNotif("{name}: DISABLED", 2)\n'
        f"        end\n"
        f"    end)\n"
        f"end"
    )


def generate_module(mod_name: str, cmds: list) -> str:
    lines = []
    lines.append(f"Modules.{mod_name} = {{")
    lines.append("    State = { IsEnabled = false, Connection = nil },")
    lines.append("    Config = {}")
    lines.append("}")
    lines.append(f"function Modules.{mod_name}:Initialize()")
    for cmd in cmds:
        alias_str = "{" + ", ".join(f'"{a.strip()}"' for a in cmd["aliases"] if a.strip()) + "}"
        lines.append(f'    addcmd("{cmd["name"]}", {alias_str}, function(args, speaker)')
        lines.append(f'        -- {cmd["name"]} logic')
        lines.append(f'        DoNotif("{cmd["name"]}: called", 2)')
        lines.append('    end)')
    lines.append("end")
    return "\n".join(lines)


def generate_module_register(mod_name: str, cmds: list) -> str:
    """Generate standalone RegisterCommand style — no Modules wrapper, just bare RegisterCommand calls."""
    lines = []
    lines.append(f"-- ── {mod_name} ──────────────────────────────────────────")
    lines.append(f"-- RegisterCommand style for ZukaPanel")
    lines.append("")

    for cmd in cmds:
        name       = cmd["name"]
        alias_list = [a.strip() for a in cmd["aliases"] if a.strip()]
        alias_str  = "{" + ", ".join(f'"{a}"' for a in alias_list) + "}"
        lines.append(f'RegisterCommand({{')
        lines.append(f'    Name        = "{name}",')
        lines.append(f'    Aliases     = {alias_str},')
        lines.append(f'    Description = "{name} command",')
        lines.append(f'    ArgsDesc    = {{}},')
        lines.append(f'    Permissions = {{}},')
        lines.append(f'}}, function(args, speaker)')
        lines.append(f'    -- {name} logic here')
        lines.append(f'    DoNotif("{name}: called by " .. speaker.Name, 2)')
        lines.append(f'end)')
        lines.append("")

    return "\n".join(lines).rstrip()


# ── GUI ──────────────────────────────────────────────────────────────────────

class ZukaCmdBuilder(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Zuka Panel — Command Builder v2 + Dex")
        self.geometry("1100x720")
        self.minsize(900, 600)
        self.configure(bg=BG)
        self.resizable(True, True)

        # try pyperclip silently
        self._clip_ok = True
        try:
            pyperclip.copy("")
        except Exception:
            self._clip_ok = False

        self._build_ui()

    # ── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_titlebar()
        self._build_tabs()

    def _build_titlebar(self):
        bar = tk.Frame(self, bg=BG2, height=44)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        accent_line = tk.Frame(bar, bg=ACCENT, width=4)
        accent_line.pack(side="left", fill="y", padx=(0, 12))

        tk.Label(bar, text="ZUKA", font=("Consolas", 15, "bold"),
                 fg=ACCENT, bg=BG2).pack(side="left")
        tk.Label(bar, text=" PANEL", font=("Consolas", 15, "bold"),
                 fg=CYAN, bg=BG2).pack(side="left")
        tk.Label(bar, text="  //  Command Builder",
                 font=FONT_UI, fg=SUBTEXT, bg=BG2).pack(side="left")

        tk.Label(bar, text="v2.0  addcmd + dex",
                 font=FONT_SM, fg=SUBTEXT, bg=BG2).pack(side="right", padx=12)

    def _build_tabs(self):
        # Tab bar
        tab_bar = tk.Frame(self, bg=BG2, height=36)
        tab_bar.pack(fill="x")
        tab_bar.pack_propagate(False)

        content = tk.Frame(self, bg=BG)
        content.pack(fill="both", expand=True)

        self._pages = {}
        self._tab_btns = {}
        self._active_tab = tk.StringVar(value="")

        tabs = [
            ("⚡  Builder",   self._build_builder_page),
            ("🔄  Converter", self._build_converter_page),
            ("🔀  Toggle",    self._build_toggle_page),
            ("📦  Module",    self._build_module_page),
            ("📋  Templates", self._build_templates_page),
            ("🔬  Dex",       self._build_dex_page),
            ("🏠  Hub",       self._build_hub_page),
            ("📥  Import",    self._build_import_page),
            ("🎨  GUI Maker", self._build_guimaker_page),
        ]

        for name, builder in tabs:
            page = tk.Frame(content, bg=BG)
            self._pages[name] = page
            builder(page)

        def switch(name):
            for n, p in self._pages.items():
                p.pack_forget()
            self._pages[name].pack(fill="both", expand=True)
            self._active_tab.set(name)
            for n, b in self._tab_btns.items():
                b.configure(
                    fg=TEXT if n == name else SUBTEXT,
                    bg=BG3 if n == name else BG2,
                )

        for name, _ in tabs:
            btn = tk.Button(
                tab_bar, text=name, font=FONT_SM,
                bg=BG2, fg=SUBTEXT, bd=0,
                activebackground=BG3, activeforeground=TEXT,
                cursor="hand2", padx=14,
                command=lambda n=name: switch(n)
            )
            btn.pack(side="left", fill="y")
            self._tab_btns[name] = btn

        switch("⚡  Builder")

    # ── Page: Builder ────────────────────────────────────────────────────────

    def _build_builder_page(self, parent):
        # Left: form
        left = tk.Frame(parent, bg=BG, width=380)
        left.pack(side="left", fill="y", padx=(14, 0), pady=14)
        left.pack_propagate(False)

        # Right: output
        right = tk.Frame(parent, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=14, pady=14)

        self._label(left, "COMMAND NAME")
        self._name_var = tk.StringVar()
        self._entry(left, self._name_var)

        self._label(left, "ALIASES  (comma separated)")
        self._alias_var = tk.StringVar()
        self._entry(left, self._alias_var, placeholder="alias1, alias2")

        self._label(left, "BODY  (raw Lua, optional)")
        self._body_box = self._text_area(left, height=6)

        # Options
        self._label(left, "OPTIONS")
        opt_frame = tk.Frame(left, bg=BG)
        opt_frame.pack(fill="x", pady=(2, 8))

        self._opt_getplayer  = self._checkbox(opt_frame, "getPlayer() loop")
        self._opt_speaker    = self._checkbox(opt_frame, "speaker.Character")
        self._opt_donotif    = self._checkbox(opt_frame, "DoNotif on finish")
        self._opt_runservice = self._checkbox(opt_frame, "RunService.Heartbeat")

        btn_row = tk.Frame(left, bg=BG)
        btn_row.pack(fill="x", pady=(4, 0))
        self._btn(btn_row, "⚡  GENERATE", self._do_generate, ACCENT).pack(side="left", padx=(0, 6))
        self._btn(btn_row, "🗑  CLEAR", self._clear_builder, BG3).pack(side="left")

        # Output
        self._label(right, "OUTPUT")
        self._builder_out = self._text_area(right, height=30, expand=True)
        self._builder_out.configure(state="disabled")

        out_btns = tk.Frame(right, bg=BG)
        out_btns.pack(fill="x", pady=(6, 0))
        self._btn(out_btns, "📋  COPY", lambda: self._copy(self._builder_out), CYAN).pack(side="left", padx=(0,6))
        self._btn(out_btns, "💾  SAVE", lambda: self._save(self._builder_out), BG3).pack(side="left")

    def _do_generate(self):
        name = self._name_var.get().strip()
        if not name:
            messagebox.showwarning("Missing", "Command name is required.")
            return
        aliases = [a.strip() for a in self._alias_var.get().split(",") if a.strip()]
        body = self._body_box.get("1.0", "end-1c")
        result = generate_addcmd(
            name, aliases, body,
            self._opt_getplayer.get(),
            self._opt_donotif.get(),
            self._opt_speaker.get(),
            self._opt_runservice.get(),
        )
        self._set_output(self._builder_out, result)

    def _clear_builder(self):
        self._name_var.set("")
        self._alias_var.set("")
        self._body_box.delete("1.0", "end")
        self._set_output(self._builder_out, "")

    # ── Page: Converter ──────────────────────────────────────────────────────

    def _build_converter_page(self, parent):
        top = tk.Frame(parent, bg=BG)
        top.pack(fill="x", padx=14, pady=(14, 6))
        self._label(top, "PASTE EXISTING LUA  (RegisterCommand / Modules.X:Initialize)")

        self._conv_input = self._text_area(parent, height=14)
        self._conv_input.pack(fill="x", padx=14)

        btn_row = tk.Frame(parent, bg=BG)
        btn_row.pack(fill="x", padx=14, pady=6)
        self._btn(btn_row, "🔄  CONVERT", self._do_convert, ACCENT).pack(side="left", padx=(0,6))
        self._btn(btn_row, "📂  LOAD FILE", self._load_file, BG3).pack(side="left", padx=(0,6))
        self._btn(btn_row, "🗑  CLEAR", lambda: (self._conv_input.delete("1.0","end"), self._set_output(self._conv_out, "")), BG3).pack(side="left")

        self._label_frame(parent, "CONVERTED OUTPUT")
        self._conv_out = self._text_area(parent, height=14, expand=True)

        out_btns = tk.Frame(parent, bg=BG)
        out_btns.pack(fill="x", padx=14, pady=(6, 14))
        self._btn(out_btns, "📋  COPY", lambda: self._copy(self._conv_out), CYAN).pack(side="left", padx=(0,6))
        self._btn(out_btns, "💾  SAVE", lambda: self._save(self._conv_out), BG3).pack(side="left")

    def _do_convert(self):
        src = self._conv_input.get("1.0", "end-1c").strip()
        if not src:
            messagebox.showwarning("Empty", "Paste some Lua first.")
            return
        result = convert_to_addcmd(src)
        self._set_output(self._conv_out, result)

    def _load_file(self):
        path = filedialog.askopenfilename(filetypes=[("Lua files", "*.lua"), ("All files", "*.*")])
        if path:
            with open(path, "r", encoding="utf-8") as f:
                self._conv_input.delete("1.0", "end")
                self._conv_input.insert("1.0", f.read())

    # ── Page: Toggle ─────────────────────────────────────────────────────────

    def _build_toggle_page(self, parent):
        left = tk.Frame(parent, bg=BG, width=380)
        left.pack(side="left", fill="y", padx=(14,0), pady=14)
        left.pack_propagate(False)

        right = tk.Frame(parent, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=14, pady=14)

        self._label(left, "COMMAND NAME")
        self._tog_name = tk.StringVar()
        self._entry(left, self._tog_name)

        self._label(left, "ALIASES")
        self._tog_alias = tk.StringVar()
        self._entry(left, self._tog_alias, placeholder="alias1, alias2")

        self._label(left, "ON BODY  (enabled branch)")
        self._tog_on = self._text_area(left, height=6)

        self._label(left, "OFF BODY  (disabled branch)")
        self._tog_off = self._text_area(left, height=6)

        btn_row = tk.Frame(left, bg=BG)
        btn_row.pack(fill="x", pady=(6,0))
        self._btn(btn_row, "⚡  GENERATE", self._do_toggle, ACCENT).pack(side="left", padx=(0,6))
        self._btn(btn_row, "🗑  CLEAR", self._clear_toggle, BG3).pack(side="left")

        self._label(right, "OUTPUT")
        self._tog_out = self._text_area(right, height=30, expand=True)
        self._tog_out.configure(state="disabled")

        out_btns = tk.Frame(right, bg=BG)
        out_btns.pack(fill="x", pady=(6,0))
        self._btn(out_btns, "📋  COPY", lambda: self._copy(self._tog_out), CYAN).pack(side="left", padx=(0,6))
        self._btn(out_btns, "💾  SAVE", lambda: self._save(self._tog_out), BG3).pack(side="left")

    def _do_toggle(self):
        name = self._tog_name.get().strip()
        if not name:
            messagebox.showwarning("Missing", "Command name required.")
            return
        aliases = [a.strip() for a in self._tog_alias.get().split(",") if a.strip()]
        on_body  = self._tog_on.get("1.0", "end-1c")
        off_body = self._tog_off.get("1.0", "end-1c")
        result = generate_toggle_cmd(name, aliases, on_body, off_body)
        self._set_output(self._tog_out, result)

    def _clear_toggle(self):
        self._tog_name.set("")
        self._tog_alias.set("")
        self._tog_on.delete("1.0", "end")
        self._tog_off.delete("1.0", "end")
        self._set_output(self._tog_out, "")

    # ── Page: Module ─────────────────────────────────────────────────────────

    def _build_module_page(self, parent):
        left = tk.Frame(parent, bg=BG, width=380)
        left.pack(side="left", fill="y", padx=(14,0), pady=14)
        left.pack_propagate(False)

        right = tk.Frame(parent, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=14, pady=14)

        self._label(left, "MODULE NAME")
        self._mod_name = tk.StringVar()
        self._entry(left, self._mod_name, placeholder="e.g. Aimbot")

        # Style selector
        self._label(left, "OUTPUT STYLE")
        style_row = tk.Frame(left, bg=BG)
        style_row.pack(fill="x", pady=(0, 8))
        self._mod_style = tk.StringVar(value="Modules")

        tk.Radiobutton(
            style_row, text="Modules.X:Initialize()", variable=self._mod_style,
            value="Modules", font=FONT_SM, fg=CYAN, bg=BG, selectcolor=BG2,
            activebackground=BG, activeforeground=CYAN,
            highlightthickness=0, cursor="hand2"
        ).pack(side="left", padx=(0, 12))

        tk.Radiobutton(
            style_row, text="RegisterCommand", variable=self._mod_style,
            value="Register", font=FONT_SM, fg=YELLOW, bg=BG, selectcolor=BG2,
            activebackground=BG, activeforeground=YELLOW,
            highlightthickness=0, cursor="hand2"
        ).pack(side="left")

        # Style hint label
        self._mod_style_hint = tk.Label(left, text="", font=("Consolas", 8),
                                        fg=SUBTEXT, bg=BG, anchor="w", wraplength=340, justify="left")
        self._mod_style_hint.pack(fill="x", pady=(0, 6))

        def _update_hint(*_):
            s = self._mod_style.get()
            if s == "Modules":
                self._mod_style_hint.configure(
                    text="Modules.Name = {} → :Initialize() → addcmd() wrappers",
                    fg=CYAN)
            else:
                self._mod_style_hint.configure(
                    text="RegisterCommand({Name,Aliases,Description,...}, func) — bare, no Modules table",
                    fg=YELLOW)
        self._mod_style.trace_add("write", _update_hint)
        _update_hint()

        self._label(left, "COMMANDS  (one per line: name|alias1,alias2)")
        self._mod_cmds = self._text_area(left, height=10)
        self._mod_cmds.insert("1.0", "fly|noclip,f\nnofly|unfly")

        btn_row = tk.Frame(left, bg=BG)
        btn_row.pack(fill="x", pady=(6,0))
        self._btn(btn_row, "⚡  GENERATE", self._do_module, ACCENT).pack(side="left", padx=(0,6))
        self._btn(btn_row, "🗑  CLEAR", self._clear_module, BG3).pack(side="left")

        self._label(right, "OUTPUT")
        self._mod_out = self._text_area(right, height=30, expand=True)
        self._mod_out.configure(state="disabled")

        out_btns = tk.Frame(right, bg=BG)
        out_btns.pack(fill="x", pady=(6,0))
        self._btn(out_btns, "📋  COPY", lambda: self._copy(self._mod_out), CYAN).pack(side="left", padx=(0,6))
        self._btn(out_btns, "💾  SAVE", lambda: self._save(self._mod_out), BG3).pack(side="left")

    def _do_module(self):
        mod_name = self._mod_name.get().strip()
        if not mod_name:
            messagebox.showwarning("Missing", "Module name required.")
            return
        raw_cmds = self._mod_cmds.get("1.0", "end-1c").strip().split("\n")
        cmds = []
        for line in raw_cmds:
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            name = parts[0].strip()
            aliases = [a.strip() for a in parts[1].split(",")] if len(parts) > 1 else []
            cmds.append({"name": name, "aliases": aliases})

        style = self._mod_style.get()
        if style == "Register":
            result = generate_module_register(mod_name, cmds)
        else:
            result = generate_module(mod_name, cmds)

        self._set_output(self._mod_out, result)

    def _clear_module(self):
        self._mod_name.set("")
        self._mod_cmds.delete("1.0", "end")
        self._set_output(self._mod_out, "")

    # ── Page: Templates ──────────────────────────────────────────────────────

    TEMPLATES = {
        "Basic Command": (
            'addcmd("commandname", {"alias"}, function(args, speaker)\n'
            '    DoNotif("Command fired by " .. speaker.Name, 2)\n'
            'end)'
        ),
        "getPlayer Loop": (
            'addcmd("commandname", {"alias"}, function(args, speaker)\n'
            '    local targets = getPlayer(args[1], speaker)\n'
            '    if #targets == 0 then return DoNotif("No players found.", 2) end\n'
            '    for _, plr in ipairs(targets) do\n'
            '        -- do something with plr\n'
            '        DoNotif("Applied to: " .. plr.Name, 2)\n'
            '    end\n'
            'end)'
        ),
        "Toggle with Heartbeat": (
            'do\n'
            '    local cmdEnabled = false\n'
            '    local cmdConn\n\n'
            '    addcmd("commandname", {"alias"}, function(args, speaker)\n'
            '        cmdEnabled = not cmdEnabled\n'
            '        if cmdEnabled then\n'
            '            cmdConn = RunService.Heartbeat:Connect(function()\n'
            '                -- loop body\n'
            '            end)\n'
            '            DoNotif("commandname: ENABLED", 2)\n'
            '        else\n'
            '            if cmdConn then cmdConn:Disconnect() cmdConn = nil end\n'
            '            DoNotif("commandname: DISABLED", 2)\n'
            '        end\n'
            '    end)\n'
            'end'
        ),
        "Remote FireServer": (
            'do\n'
            '    local Remote = game:GetService("ReplicatedStorage"):WaitForChild("RemoteName")\n\n'
            '    addcmd("commandname", {"alias"}, function(args, speaker)\n'
            '        local targets = getPlayer(args[1], speaker)\n'
            '        for _, plr in ipairs(targets) do\n'
            '            pcall(function()\n'
            '                Remote:FireServer(plr)\n'
            '            end)\n'
            '        end\n'
            '        DoNotif("Fired remote for " .. #targets .. " players.", 2)\n'
            '    end)\n'
            'end'
        ),
        "Character Teleport": (
            'addcmd("tp", {"teleport"}, function(args, speaker)\n'
            '    local target = getPlayer(args[1], speaker)[1]\n'
            '    if not target or not target.Character then\n'
            '        return DoNotif("Target not found.", 2)\n'
            '    end\n'
            '    local myRoot = speaker.Character and speaker.Character:FindFirstChild("HumanoidRootPart")\n'
            '    local tRoot  = target.Character:FindFirstChild("HumanoidRootPart")\n'
            '    if myRoot and tRoot then\n'
            '        myRoot.CFrame = tRoot.CFrame * CFrame.new(0, 0, -3)\n'
            '        DoNotif("Teleported to " .. target.Name, 2)\n'
            '    end\n'
            'end)'
        ),
        "Keybind addbind": (
            '-- Toggle fly on G key\n'
            'addbind("fly", "Enum.KeyCode.G", false, "nofly")\n\n'
            '-- Fire command on Left click\n'
            'addbind("commandname", "LeftClick", false)\n\n'
            '-- Fire on key release\n'
            'addbind("commandname", "Enum.KeyCode.F", true)'
        ),
        # ── Character / Player ───────────────────────────────────────────────
        "Fly Toggle": (
            'do\n'
            '    local flyEnabled = false\n'
            '    local flyConn\n'
            '    local bodyVel, bodyGyro\n\n'
            '    local function enableFly(char)\n'
            '        local root = char:FindFirstChild("HumanoidRootPart")\n'
            '        if not root then return end\n'
            '        bodyVel = Instance.new("BodyVelocity", root)\n'
            '        bodyVel.MaxForce = Vector3.new(1e9,1e9,1e9)\n'
            '        bodyVel.Velocity = Vector3.zero\n'
            '        bodyGyro = Instance.new("BodyGyro", root)\n'
            '        bodyGyro.MaxTorque = Vector3.new(1e9,1e9,1e9)\n'
            '        bodyGyro.P = 1e6\n'
            '        local cam = workspace.CurrentCamera\n'
            '        local speed = 50\n'
            '        local UIS = game:GetService("UserInputService")\n'
            '        flyConn = game:GetService("RunService").Heartbeat:Connect(function()\n'
            '            local dir = Vector3.zero\n'
            '            if UIS:IsKeyDown(Enum.KeyCode.W) then dir = dir + cam.CFrame.LookVector end\n'
            '            if UIS:IsKeyDown(Enum.KeyCode.S) then dir = dir - cam.CFrame.LookVector end\n'
            '            if UIS:IsKeyDown(Enum.KeyCode.A) then dir = dir - cam.CFrame.RightVector end\n'
            '            if UIS:IsKeyDown(Enum.KeyCode.D) then dir = dir + cam.CFrame.RightVector end\n'
            '            if UIS:IsKeyDown(Enum.KeyCode.Space) then dir = dir + Vector3.yAxis end\n'
            '            if UIS:IsKeyDown(Enum.KeyCode.LeftShift) then dir = dir - Vector3.yAxis end\n'
            '            bodyVel.Velocity = dir.Magnitude > 0 and dir.Unit * speed or Vector3.zero\n'
            '            bodyGyro.CFrame = cam.CFrame\n'
            '        end)\n'
            '    end\n\n'
            '    local function disableFly(char)\n'
            '        if flyConn then flyConn:Disconnect() flyConn = nil end\n'
            '        if bodyVel then bodyVel:Destroy() bodyVel = nil end\n'
            '        if bodyGyro then bodyGyro:Destroy() bodyGyro = nil end\n'
            '        local hum = char and char:FindFirstChildOfClass("Humanoid")\n'
            '        if hum then hum.PlatformStand = false end\n'
            '    end\n\n'
            '    addcmd("fly", {"noclipfly", "ffly"}, function(args, speaker)\n'
            '        flyEnabled = not flyEnabled\n'
            '        local char = speaker.Character\n'
            '        if not char then return end\n'
            '        if flyEnabled then\n'
            '            local hum = char:FindFirstChildOfClass("Humanoid")\n'
            '            if hum then hum.PlatformStand = true end\n'
            '            enableFly(char)\n'
            '            DoNotif("Fly: ENABLED", 2)\n'
            '        else\n'
            '            disableFly(char)\n'
            '            DoNotif("Fly: DISABLED", 2)\n'
            '        end\n'
            '    end)\n'
            'end'
        ),
        "Noclip Toggle": (
            'do\n'
            '    local noclipEnabled = false\n'
            '    local noclipConn\n\n'
            '    addcmd("noclip", {"nc", "ghost"}, function(args, speaker)\n'
            '        noclipEnabled = not noclipEnabled\n'
            '        if noclipEnabled then\n'
            '            noclipConn = game:GetService("RunService").Stepped:Connect(function()\n'
            '                local char = speaker.Character\n'
            '                if not char then return end\n'
            '                for _, part in ipairs(char:GetDescendants()) do\n'
            '                    if part:IsA("BasePart") and part.CanCollide then\n'
            '                        part.CanCollide = false\n'
            '                    end\n'
            '                end\n'
            '            end)\n'
            '            DoNotif("Noclip: ON", 2)\n'
            '        else\n'
            '            if noclipConn then noclipConn:Disconnect() noclipConn = nil end\n'
            '            DoNotif("Noclip: OFF", 2)\n'
            '        end\n'
            '    end)\n'
            'end'
        ),
        "Speed Toggle": (
            'do\n'
            '    local origSpeed = 16\n'
            '    local speedEnabled = false\n\n'
            '    addcmd("speed", {"ws", "walkspeed"}, function(args, speaker)\n'
            '        local char = speaker.Character\n'
            '        local hum = char and char:FindFirstChildOfClass("Humanoid")\n'
            '        if not hum then return DoNotif("No humanoid.", 2) end\n\n'
            '        local newSpeed = tonumber(args[1])\n'
            '        if newSpeed then\n'
            '            origSpeed = hum.WalkSpeed\n'
            '            hum.WalkSpeed = newSpeed\n'
            '            DoNotif("Speed set to " .. newSpeed, 2)\n'
            '        else\n'
            '            speedEnabled = not speedEnabled\n'
            '            if speedEnabled then\n'
            '                origSpeed = hum.WalkSpeed\n'
            '                hum.WalkSpeed = 100\n'
            '                DoNotif("Speed: FAST (100)", 2)\n'
            '            else\n'
            '                hum.WalkSpeed = origSpeed\n'
            '                DoNotif("Speed: RESET (" .. origSpeed .. ")", 2)\n'
            '            end\n'
            '        end\n'
            '    end)\n'
            'end'
        ),
        "Infinite Jump": (
            'do\n'
            '    local ijEnabled = false\n'
            '    local ijConn\n\n'
            '    addcmd("ijump", {"infjump", "ij"}, function(args, speaker)\n'
            '        ijEnabled = not ijEnabled\n'
            '        if ijEnabled then\n'
            '            local UIS = game:GetService("UserInputService")\n'
            '            ijConn = UIS.JumpRequest:Connect(function()\n'
            '                local char = speaker.Character\n'
            '                local hum = char and char:FindFirstChildOfClass("Humanoid")\n'
            '                if hum and hum:GetState() ~= Enum.HumanoidStateType.Dead then\n'
            '                    hum:ChangeState(Enum.HumanoidStateType.Jumping)\n'
            '                end\n'
            '            end)\n'
            '            DoNotif("Infinite Jump: ON", 2)\n'
            '        else\n'
            '            if ijConn then ijConn:Disconnect() ijConn = nil end\n'
            '            DoNotif("Infinite Jump: OFF", 2)\n'
            '        end\n'
            '    end)\n'
            'end'
        ),
        "Goto / Bring Player": (
            '-- goto <player> teleports you to them; bring <player> brings them to you\n'
            'addcmd("goto", {"goto"}, function(args, speaker)\n'
            '    local target = getPlayer(args[1], speaker)[1]\n'
            '    if not (target and target.Character) then return DoNotif("Player not found.", 2) end\n'
            '    local myRoot = speaker.Character and speaker.Character:FindFirstChild("HumanoidRootPart")\n'
            '    local tRoot  = target.Character:FindFirstChild("HumanoidRootPart")\n'
            '    if myRoot and tRoot then\n'
            '        myRoot.CFrame = tRoot.CFrame * CFrame.new(2, 0, -3)\n'
            '        DoNotif("Went to " .. target.Name, 2)\n'
            '    end\n'
            'end)\n\n'
            'addcmd("bring", {"br"}, function(args, speaker)\n'
            '    local targets = getPlayer(args[1], speaker)\n'
            '    if #targets == 0 then return DoNotif("No players found.", 2) end\n'
            '    local myRoot = speaker.Character and speaker.Character:FindFirstChild("HumanoidRootPart")\n'
            '    if not myRoot then return end\n'
            '    for i, plr in ipairs(targets) do\n'
            '        local root = plr.Character and plr.Character:FindFirstChild("HumanoidRootPart")\n'
            '        if root then\n'
            '            root.CFrame = myRoot.CFrame * CFrame.new(i * 3, 0, -3)\n'
            '        end\n'
            '    end\n'
            '    DoNotif("Brought " .. #targets .. " player(s).", 2)\n'
            'end)'
        ),
        "Fake Lag / Ping Spike": (
            '-- Artificially delays RunService to simulate lag\n'
            'do\n'
            '    local lagEnabled = false\n'
            '    local lagConn\n\n'
            '    addcmd("fakelag", {"lag", "pingspike"}, function(args, speaker)\n'
            '        lagEnabled = not lagEnabled\n'
            '        local delay = tonumber(args[1]) or 0.3  -- seconds\n'
            '        if lagEnabled then\n'
            '            lagConn = game:GetService("RunService").Heartbeat:Connect(function()\n'
            '                local t = tick()\n'
            '                -- Busy-wait to block the thread\n'
            '                while tick() - t < delay do end\n'
            '            end)\n'
            '            DoNotif("Fake Lag: ON (" .. delay .. "s)", 2)\n'
            '        else\n'
            '            if lagConn then lagConn:Disconnect() lagConn = nil end\n'
            '            DoNotif("Fake Lag: OFF", 2)\n'
            '        end\n'
            '    end)\n'
            'end'
        ),
        "Keybind Toggle Alias Changer": (
            '-- Dynamically remap a command alias at runtime, or bind toggle to a key\n'
            'do\n'
            '    -- Change an existing command alias on the fly:\n'
            '    addcmd("setalias", {"remap", "alias"}, function(args, speaker)\n'
            '        local cmdName = args[1]\n'
            '        local newAlias = args[2]\n'
            '        if not (cmdName and newAlias) then\n'
            '            return DoNotif("Usage: setalias <cmd> <newalias>", 3)\n'
            '        end\n'
            '        -- addcmd re-registration with extra alias\n'
            '        -- This wraps the existing command under a new name:\n'
            '        addcmd(newAlias, {}, function(a, s)\n'
            '            execCmd(cmdName, s)\n'
            '        end)\n'
            '        DoNotif("Alias added: " .. newAlias .. " -> " .. cmdName, 2)\n'
            '    end)\n\n'
            '    -- Bind any command to a key toggle:\n'
            '    addcmd("bindkey", {"keybind", "kb"}, function(args, speaker)\n'
            '        local key = args[1]   -- e.g. "F", "G", "X"\n'
            '        local cmd = args[2]   -- e.g. "fly"\n'
            '        if not (key and cmd) then\n'
            '            return DoNotif("Usage: bindkey <Key> <cmd>", 3)\n'
            '        end\n'
            '        local keyCode = Enum.KeyCode[key]\n'
            '        if not keyCode then return DoNotif("Invalid key: " .. key, 2) end\n'
            '        addbind(cmd, "Enum.KeyCode." .. key, false)\n'
            '        DoNotif("Bound " .. key .. " -> " .. cmd, 2)\n'
            '    end)\n'
            'end'
        ),
        "Anti-Admin Hook": (
            'do\n'
            '    local conns = {}\n\n'
            '    addcmd("antiadmin", {"blockadmin"}, function(args, speaker)\n'
            '        -- Disconnect existing\n'
            '        for _, c in pairs(conns) do c:Disconnect() end\n'
            '        conns = {}\n\n'
            '        local hdc = game:GetService("ReplicatedStorage"):FindFirstChild("HDAdminHDClient")\n'
            '        if hdc and hdc:FindFirstChild("Signals") then\n'
            '            for _, sigName in ipairs({"ExecuteClientCommand", "ActivateClientCommand"}) do\n'
            '                local s = hdc.Signals:FindFirstChild(sigName)\n'
            '                if s then\n'
            '                    table.insert(conns, s.OnClientEvent:Connect(function(cmd)\n'
            '                        print("[AntiAdmin] Blocked:", tostring(cmd))\n'
            '                    end))\n'
            '                end\n'
            '            end\n'
            '        end\n'
            '        DoNotif("Anti-Admin: ACTIVE", 2)\n'
            '    end)\n'
            'end'
        ),
    }

    def _build_templates_page(self, parent):
        left = tk.Frame(parent, bg=BG, width=220)
        left.pack(side="left", fill="y", padx=(14,0), pady=14)
        left.pack_propagate(False)

        right = tk.Frame(parent, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=14, pady=14)

        self._label(left, "TEMPLATES")

        listbox = tk.Listbox(
            left, bg=BG2, fg=TEXT, selectbackground=ACCENT,
            selectforeground=TEXT, font=FONT_SM, bd=0,
            highlightthickness=1, highlightcolor=BORDER,
            activestyle="none", cursor="hand2",
        )
        listbox.pack(fill="both", expand=True)
        for name in self.TEMPLATES:
            listbox.insert("end", "  " + name)

        self._label(right, "PREVIEW")
        self._tpl_out = self._text_area(right, height=28, expand=True)

        out_btns = tk.Frame(right, bg=BG)
        out_btns.pack(fill="x", pady=(6,0))
        self._btn(out_btns, "📋  COPY", lambda: self._copy(self._tpl_out), CYAN).pack(side="left", padx=(0,6))
        self._btn(out_btns, "💾  SAVE", lambda: self._save(self._tpl_out), BG3).pack(side="left")

        def on_select(event):
            sel = listbox.curselection()
            if not sel:
                return
            name = listbox.get(sel[0]).strip()
            code = self.TEMPLATES.get(name, "")
            self._tpl_out.configure(state="normal")
            self._tpl_out.delete("1.0", "end")
            self._tpl_out.insert("1.0", code)

        listbox.bind("<<ListboxSelect>>", on_select)

    # ── Widget Helpers ───────────────────────────────────────────────────────

    def _label(self, parent, text):
        tk.Label(parent, text=text, font=FONT_SM, fg=ACCENT,
                 bg=BG, anchor="w").pack(fill="x", pady=(8, 2))

    def _label_frame(self, parent, text):
        tk.Label(parent, text=text, font=FONT_SM, fg=ACCENT,
                 bg=BG, anchor="w").pack(fill="x", padx=14, pady=(8,2))

    def _entry(self, parent, var, placeholder=""):
        e = tk.Entry(parent, textvariable=var, font=FONT_UI,
                     bg=BG2, fg=TEXT, insertbackground=CYAN,
                     bd=0, highlightthickness=1,
                     highlightcolor=ACCENT, highlightbackground=BORDER)
        e.pack(fill="x", ipady=5)
        if placeholder and not var.get():
            e.insert(0, placeholder)
            e.configure(fg=SUBTEXT)
            def on_focus_in(ev):
                if e.get() == placeholder:
                    e.delete(0, "end")
                    e.configure(fg=TEXT)
            def on_focus_out(ev):
                if not e.get():
                    e.insert(0, placeholder)
                    e.configure(fg=SUBTEXT)
            e.bind("<FocusIn>", on_focus_in)
            e.bind("<FocusOut>", on_focus_out)
        return e

    def _text_area(self, parent, height=8, expand=False):
        frame = tk.Frame(parent, bg=BORDER, bd=1)
        if expand:
            frame.pack(fill="both", expand=True)
        else:
            frame.pack(fill="x")

        t = tk.Text(frame, font=("Consolas", 10), bg=BG2, fg=TEXT,
                    insertbackground=CYAN, bd=0, wrap="none",
                    height=height, selectbackground=ACCENT,
                    selectforeground=TEXT, padx=8, pady=6,
                    tabs=("1c",))

        vsb = tk.Scrollbar(frame, orient="vertical", command=t.yview,
                           bg=BG2, troughcolor=BG2, bd=0, width=8)
        hsb = tk.Scrollbar(frame, orient="horizontal", command=t.xview,
                           bg=BG2, troughcolor=BG2, bd=0, width=8)
        t.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        t.pack(fill="both", expand=True)

        # Syntax-ish highlighting (basic keywords)
        t.tag_configure("kw",    foreground="#cc99ff")
        t.tag_configure("str",   foreground="#99dd66")
        t.tag_configure("fn",    foreground=CYAN)
        t.tag_configure("zuka",    foreground=YELLOW)
        t.tag_configure("exploit", foreground="#ab54f7")  # purple for exploit APIs
        t.tag_configure("cmt",   foreground=SUBTEXT)
        t.tag_configure("num",   foreground="#ff9966")

        def highlight(event=None):
            t.tag_remove("kw", "1.0", "end")
            t.tag_remove("str", "1.0", "end")
            t.tag_remove("fn", "1.0", "end")
            t.tag_remove("zuka", "1.0", "end")
            t.tag_remove("cmt", "1.0", "end")
            t.tag_remove("num", "1.0", "end")
            content = t.get("1.0", "end")
            for match in re.finditer(r'\b(local|function|end|if|then|else|elseif|for|while|do|return|not|and|or|true|false|nil|in|pairs|ipairs|repeat|until|break)\b', content):
                s = f"1.0+{match.start()}c"
                e2 = f"1.0+{match.end()}c"
                t.tag_add("kw", s, e2)
            for match in re.finditer(r'"[^"]*"|\'[^\']*\'', content):
                t.tag_add("str", f"1.0+{match.start()}c", f"1.0+{match.end()}c")
            # Zuka/Roblox APIs (yellow)
            for match in re.finditer(
                r'\b(addcmd|execCmd|DoNotif|getPlayer|addbind|removecmd|removebind|execCmd|'
                r'game|workspace|math|string|table|task|Enum|Instance|CFrame|Vector3|Vector2|Color3|UDim|UDim2|'
                r'TweenService|LogService|UserInputService|ReplicatedStorage|HttpService|RunService|Players|LocalPlayer|'
                r'pcall|xpcall|pairs|ipairs|setmetatable|getmetatable|rawget|rawset|rawequal|select|unpack|type|typeof|tostring|tonumber)\b',
                content):
                t.tag_add("zuka", f"1.0+{match.start()}c", f"1.0+{match.end()}c")
            # Exploit-only APIs (purple)
            for match in re.finditer(
                r'\b(hookmetamethod|hookfunction|getnamecallmethod|getgc|filtergc|Drawing|'
                r'getgenv|getsenv|getrenv|getfenv|setfenv|setclipboard|getclipboard|'
                r'decompile|saveinstance|getrawmetatable|setrawmetatable|checkcaller|'
                r'cloneref|clonefunction|iscclosure|islclosure|isexecutorclosure|newcclosure|getfunctionhash|'
                r'writefile|appendfile|loadfile|readfile|listfiles|makefolder|isfolder|isfile|delfile|delfolder|'
                r'getcustomasset|fireclickdetector|firetouchinterest|fireproximityprompt|'
                r'crypt|identifyexecutor|getexecutorname|syn|rconsole|rconsoleclear)\b',
                content):
                t.tag_add("exploit", f"1.0+{match.start()}c", f"1.0+{match.end()}c")
            for match in re.finditer(r'--[^\n]*', content):
                t.tag_add("cmt", f"1.0+{match.start()}c", f"1.0+{match.end()}c")
            for match in re.finditer(r'\b\d+\.?\d*\b', content):
                t.tag_add("num", f"1.0+{match.start()}c", f"1.0+{match.end()}c")

        t.bind("<KeyRelease>", highlight)
        return t

    def _checkbox(self, parent, text):
        var = tk.BooleanVar()
        cb = tk.Checkbutton(parent, text=text, variable=var,
                            font=FONT_SM, fg=TEXT, bg=BG,
                            selectcolor=BG2, activebackground=BG,
                            activeforeground=TEXT,
                            highlightthickness=0, cursor="hand2")
        cb.pack(anchor="w")
        return var

    def _btn(self, parent, text, command, color=ACCENT):
        b = tk.Button(
            parent, text=text, font=FONT_SM,
            bg=color, fg=TEXT, bd=0,
            activebackground=ACCENT2, activeforeground=TEXT,
            cursor="hand2", padx=12, pady=5,
            command=command,
        )
        return b

    def _set_output(self, widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _copy(self, widget):
        text = widget.get("1.0", "end-1c")
        if not text.strip():
            messagebox.showinfo("Empty", "Nothing to copy.")
            return
        if self._clip_ok:
            try:
                pyperclip.copy(text)
                messagebox.showinfo("Copied", "Copied to clipboard!")
            except Exception:
                self._fallback_copy(text)
        else:
            self._fallback_copy(text)

    def _fallback_copy(self, text):
        win = tk.Toplevel(self)
        win.title("Copy this")
        win.configure(bg=BG)
        tk.Label(win, text="pyperclip not available — select all & copy:",
                 font=FONT_SM, fg=SUBTEXT, bg=BG).pack(padx=10, pady=(10,4))
        t = tk.Text(win, font=FONT_UI, bg=BG2, fg=TEXT, width=80, height=20)
        t.pack(padx=10, pady=(0,10))
        t.insert("1.0", text)
        t.focus()
        t.tag_add("sel", "1.0", "end")

    def _save(self, widget):
        text = widget.get("1.0", "end-1c")
        if not text.strip():
            messagebox.showinfo("Empty", "Nothing to save.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".lua",
            filetypes=[("Lua files", "*.lua"), ("All files", "*.*")],
            initialfile="zuka_commands.lua"
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            messagebox.showinfo("Saved", f"Saved to:\n{path}")


    # ── Page: Dex Integration ────────────────────────────────────────────────

    DEX_SNIPPETS = {
        "Open Dex Explorer": (
            'addcmd("dex", {"explorer", "opendex"}, function(args, speaker)\n'
            '    -- Load and open Dex Explorer (Zex)\n'
            '    local ok, err = pcall(function()\n'
            '        loadstring(game:HttpGet("https://raw.githubusercontent.com/zukatech1/Main-Repo/refs/heads/main/Zex.lua"))()\n'
            '    end)\n'
            '    if not ok then\n'
            '        DoNotif("Dex failed: " .. tostring(err), 3)\n'
            '    else\n'
            '        DoNotif("Dex opened!", 2)\n'
            '    end\n'
            'end)'
        ),
        "Decompile Clicked Script": (
            '-- Right-click any LocalScript/ModuleScript in Explorer and run this\n'
            'addcmd("decompile", {"dc", "decomp"}, function(args, speaker)\n'
            '    local target = game:GetService("Selection"):Get()[1]\n'
            '    if not target or not (target:IsA("LocalScript") or target:IsA("ModuleScript") or target:IsA("Script")) then\n'
            '        return DoNotif("Select a script first.", 2)\n'
            '    end\n'
            '    local ok, src = pcall(decompile, target)\n'
            '    if ok and src and #src > 0 then\n'
            '        setclipboard(src)\n'
            '        DoNotif("Decompiled & copied: " .. target.Name, 2)\n'
            '    else\n'
            '        DoNotif("Decompile failed.", 2)\n'
            '    end\n'
            'end)'
        ),
        "Dump All RemoteEvents": (
            'addcmd("dumpremotes", {"remotes", "listremotes"}, function(args, speaker)\n'
            '    local results = {}\n'
            '    local function scan(obj, path)\n'
            '        for _, child in ipairs(obj:GetChildren()) do\n'
            '            local p = path .. "." .. child.Name\n'
            '            if child:IsA("RemoteEvent") or child:IsA("RemoteFunction") or child:IsA("BindableEvent") then\n'
            '                table.insert(results, child.ClassName .. ": " .. p)\n'
            '            end\n'
            '            scan(child, p)\n'
            '        end\n'
            '    end\n'
            '    scan(game:GetService("ReplicatedStorage"), "ReplicatedStorage")\n'
            '    scan(game:GetService("ReplicatedFirst"), "ReplicatedFirst")\n'
            '    local out = table.concat(results, "\\n")\n'
            '    setclipboard(out)\n'
            '    DoNotif("Dumped " .. #results .. " remotes — copied!", 2)\n'
            '    print(out)\n'
            'end)'
        ),
        "Hook Remote + Log Args": (
            'do\n'
            '    local hookedRemotes = {}\n\n'
            '    addcmd("hookremote", {"hr", "watchremote"}, function(args, speaker)\n'
            '        local remotePath = args[1]\n'
            '        if not remotePath then return DoNotif("Usage: hookremote <name>", 2) end\n\n'
            '        -- Search ReplicatedStorage for matching remote\n'
            '        local function findRemote(name, parent)\n'
            '            for _, v in ipairs(parent:GetDescendants()) do\n'
            '                if v.Name:lower() == name:lower() and\n'
            '                   (v:IsA("RemoteEvent") or v:IsA("RemoteFunction")) then\n'
            '                    return v\n'
            '                end\n'
            '            end\n'
            '        end\n\n'
            '        local remote = findRemote(remotePath, game:GetService("ReplicatedStorage"))\n'
            '        if not remote then return DoNotif("Remote not found: " .. remotePath, 2) end\n\n'
            '        -- Hook FireServer\n'
            '        local orig = hookmetamethod(game, "__namecall", function(self, ...)\n'
            '            local method = getnamecallmethod()\n'
            '            if self == remote and (method == "FireServer" or method == "InvokeServer") then\n'
            '                local argList = {...}\n'
            '                local strs = {}\n'
            '                for i, v in ipairs(argList) do\n'
            '                    strs[i] = tostring(v)\n'
            '                end\n'
            '                print("[HookRemote] " .. remote.Name .. " fired: " .. table.concat(strs, ", "))\n'
            '                DoNotif("[HR] " .. remote.Name .. " fired!", 1.5)\n'
            '            end\n'
            '            return orig(self, ...)\n'
            '        end)\n'
            '        table.insert(hookedRemotes, orig)\n'
            '        DoNotif("Now hooking: " .. remote.Name, 2)\n'
            '    end)\n'
            'end'
        ),
        "Module Poisoning Template": (
            '-- Poison a ModuleScript so any future require() returns your data\n'
            'addcmd("poison", {"poisonmod", "hookmodule"}, function(args, speaker)\n'
            '    local modName = args[1]\n'
            '    if not modName then return DoNotif("Usage: poison <ModuleName>", 2) end\n\n'
            '    local function findModule(name, root)\n'
            '        for _, v in ipairs(root:GetDescendants()) do\n'
            '            if v:IsA("ModuleScript") and v.Name:lower() == name:lower() then\n'
            '                return v\n'
            '            end\n'
            '        end\n'
            '    end\n\n'
            '    local mod = findModule(modName, game)\n'
            '    if not mod then return DoNotif("Module not found: " .. modName, 2) end\n\n'
            '    local orig = clonefunction(require)\n'
            '    hookfunction(require, newcclosure(function(m, ...)\n'
            '        local result = orig(m, ...)\n'
            '        if m == mod then\n'
            '            print("[Poison] Module " .. modName .. " required — intercepted!")\n'
            '            -- Modify result table here, or return a fake one:\n'
            '            -- return {}\n'
            '        end\n'
            '        return result\n'
            '    end))\n'
            '    DoNotif("Poisoned: " .. modName, 2)\n'
            'end)'
        ),
        "SaveInstance (Rip Game)": (
            'addcmd("rip", {"saveinstance", "ripgame"}, function(args, speaker)\n'
            '    DoNotif("Saving instance... check console.", 3)\n'
            '    task.spawn(function()\n'
            '        local opts = {\n'
            '            SavePlayers    = false,\n'
            '            SaveNonCreatable = true,\n'
            '            IsolateStarterPlayer = true,\n'
            '        }\n'
            '        local ok, err = pcall(saveinstance, game, opts)\n'
            '        if ok then\n'
            '            DoNotif("Save complete!", 2)\n'
            '        else\n'
            '            DoNotif("Save failed: " .. tostring(err), 3)\n'
            '        end\n'
            '    end)\n'
            'end)'
        ),
        "GetGC — Scan Closures": (
            '-- Scan garbage collector for hidden tables/functions matching a name\n'
            'addcmd("gcfind", {"getgc", "scanmem"}, function(args, speaker)\n'
            '    local needle = args[1] and args[1]:lower() or ""\n'
            '    if needle == "" then return DoNotif("Usage: gcfind <keyword>", 2) end\n\n'
            '    local found = 0\n'
            '    for _, v in ipairs(getgc(true)) do\n'
            '        if type(v) == "table" then\n'
            '            for k, _ in pairs(v) do\n'
            '                if tostring(k):lower():find(needle) then\n'
            '                    print("[GCFind] Table key match:", k, "->", tostring(v[k]):sub(1, 80))\n'
            '                    found = found + 1\n'
            '                    if found > 50 then\n'
            '                        DoNotif("50+ results — check console.", 2)\n'
            '                        return\n'
            '                    end\n'
            '                end\n'
            '            end\n'
            '        elseif type(v) == "function" then\n'
            '            local info = debug.getinfo and debug.getinfo(v) or {}\n'
            '            if tostring(info.name or ""):lower():find(needle) then\n'
            '                print("[GCFind] Function match:", tostring(v))\n'
            '                found = found + 1\n'
            '            end\n'
            '        end\n'
            '    end\n'
            '    DoNotif("GCFind done: " .. found .. " matches.", 2)\n'
            'end)'
        ),
        "Hook Metamethod __index": (
            'do\n'
            '    local orig\n'
            '    local logging = false\n\n'
            '    addcmd("hookmeta", {"hookindex", "spyindex"}, function(args, speaker)\n'
            '        logging = not logging\n'
            '        if logging then\n'
            '            orig = hookmetamethod(game, "__index", newcclosure(function(self, key)\n'
            '                -- Filter to interesting keys only:\n'
            '                if type(key) == "string" and key:find("Data") then\n'
            '                    print("[__index spy]", tostring(self), ".", key)\n'
            '                end\n'
            '                return orig(self, key)\n'
            '            end))\n'
            '            DoNotif("__index hook: ENABLED", 2)\n'
            '        else\n'
            '            if orig then\n'
            '                hookmetamethod(game, "__index", orig)\n'
            '                orig = nil\n'
            '            end\n'
            '            DoNotif("__index hook: DISABLED", 2)\n'
            '        end\n'
            '    end)\n'
            'end'
        ),
        "Spy on __newindex": (
            'do\n'
            '    local orig\n'
            '    local active = false\n\n'
            '    addcmd("spynew", {"newindex", "watchwrite"}, function(args, speaker)\n'
            '        active = not active\n'
            '        if active then\n'
            '            orig = hookmetamethod(game, "__newindex", newcclosure(function(self, key, value)\n'
            '                print("[__newindex]", tostring(self), key, "=", tostring(value))\n'
            '                return orig(self, key, value)\n'
            '            end))\n'
            '            DoNotif("__newindex spy: ON", 2)\n'
            '        else\n'
            '            if orig then hookmetamethod(game, "__newindex", orig) orig = nil end\n'
            '            DoNotif("__newindex spy: OFF", 2)\n'
            '        end\n'
            '    end)\n'
            'end'
        ),
        "LogService Output Capture": (
            '-- Capture all game print/warn/error into a file\n'
            'do\n'
            '    local conn\n'
            '    local log = {}\n\n'
            '    addcmd("capturelog", {"logcap", "dumplog"}, function(args, speaker)\n'
            '        if conn then\n'
            '            conn:Disconnect() conn = nil\n'
            '            local out = table.concat(log, "\\n")\n'
            '            writefile("zuka_log_" .. os.time() .. ".txt", out)\n'
            '            DoNotif("Log saved! " .. #log .. " lines.", 2)\n'
            '            log = {}\n'
            '        else\n'
            '            local LogService = game:GetService("LogService")\n'
            '            conn = LogService.MessageOut:Connect(function(msg, msgType)\n'
            '                local prefix = ({[Enum.MessageType.MessageOutput]="[OUT]",[Enum.MessageType.MessageWarning]="[WRN]",[Enum.MessageType.MessageError]="[ERR]"})[msgType] or "[?]"\n'
            '                table.insert(log, prefix .. " " .. msg)\n'
            '            end)\n'
            '            DoNotif("Log capture: STARTED", 2)\n'
            '        end\n'
            '    end)\n'
            'end'
        ),

        # ── Memory & GC ──────────────────────────────────────────────────────
        "_G / shared Environment Monitor": (
            '-- Toggle monitoring _G and shared for unexpected writes\n'
            'do\n'
            '    local monitorConn\n'
            '    local snapshot = {}\n\n'
            '    local function takeSnapshot()\n'
            '        snapshot = {}\n'
            '        for k, v in pairs(_G) do snapshot[k] = v end\n'
            '        for k, v in pairs(shared) do snapshot["__shared_" .. tostring(k)] = v end\n'
            '    end\n\n'
            '    addcmd("gwatch", {"watchg", "envmonitor"}, function(args, speaker)\n'
            '        if monitorConn then\n'
            '            task.cancel(monitorConn)\n'
            '            monitorConn = nil\n'
            '            DoNotif("_G monitor: OFF", 2)\n'
            '            return\n'
            '        end\n\n'
            '        takeSnapshot()\n'
            '        monitorConn = task.spawn(function()\n'
            '            while task.wait(1) do\n'
            '                -- Check _G\n'
            '                for k, v in pairs(_G) do\n'
            '                    local key = tostring(k)\n'
            '                    if snapshot[key] ~= v then\n'
            '                        warn(("[_G CHANGE] \'%s\' %s -> %s"):format(key, tostring(snapshot[key]), tostring(v)))\n'
            '                        snapshot[key] = v\n'
            '                    end\n'
            '                end\n'
            '                for k in pairs(snapshot) do\n'
            '                    if not k:find("^__shared_") and _G[k] == nil then\n'
            '                        warn(("[_G DELETE] \'%s\' was removed"):format(tostring(k)))\n'
            '                        snapshot[k] = nil\n'
            '                    end\n'
            '                end\n'
            '                -- Check shared\n'
            '                for k, v in pairs(shared) do\n'
            '                    local key = "__shared_" .. tostring(k)\n'
            '                    if snapshot[key] ~= v then\n'
            '                        warn(("[shared CHANGE] \'%s\' %s -> %s"):format(tostring(k), tostring(snapshot[key]), tostring(v)))\n'
            '                        snapshot[key] = v\n'
            '                    end\n'
            '                end\n'
            '            end\n'
            '        end)\n'
            '        DoNotif("_G monitor: ON", 2)\n'
            '    end)\n'
            'end'
        ),
        "GC Table Crawler": (
            '-- Crawl GC for tables matching a field/value pattern\n'
            'addcmd("gctable", {"crawlgc", "gctrawl"}, function(args, speaker)\n'
            '    local needle = args[1] and args[1]:lower() or ""\n'
            '    if needle == "" then return DoNotif("Usage: gctable <fieldname>", 2) end\n\n'
            '    local results = {}\n'
            '    for _, obj in ipairs(getgc(true)) do\n'
            '        if type(obj) == "table" then\n'
            '            local ok, val = pcall(function() return rawget(obj, needle) end)\n'
            '            if ok and val ~= nil then\n'
            '                table.insert(results, {tbl=obj, val=val})\n'
            '            end\n'
            '            -- also fuzzy-search keys\n'
            '            for k, v in pairs(obj) do\n'
            '                if tostring(k):lower():find(needle, 1, true) then\n'
            '                    table.insert(results, {tbl=obj, key=k, val=v})\n'
            '                    break\n'
            '                end\n'
            '            end\n'
            '        end\n'
            '        if #results >= 30 then break end\n'
            '    end\n'
            '    for i, r in ipairs(results) do\n'
            '        print(("[GCTable #%d] key=%s val=%s"):format(i, tostring(r.key or needle), tostring(r.val):sub(1,60)))\n'
            '    end\n'
            '    DoNotif("GC crawl: " .. #results .. " hits", 2)\n'
            'end)'
        ),
        "Upvalue Scanner & Patcher": (
            '-- Read or patch an upvalue inside a target function from GC\n'
            'addcmd("upvalue", {"uv", "patchuv"}, function(args, speaker)\n'
            '    local fnName  = args[1]  -- function name to find in GC\n'
            '    local uvIndex = tonumber(args[2]) or 1\n'
            '    local newVal  = args[3]  -- if provided, patch it\n'
            '    if not fnName then return DoNotif("Usage: upvalue <fnName> [index] [newval]", 3) end\n\n'
            '    local found\n'
            '    for _, fn in ipairs(getgc()) do\n'
            '        if type(fn) == "function" then\n'
            '            local info = debug.getinfo and debug.getinfo(fn, "n")\n'
            '            if info and (info.name or ""):lower() == fnName:lower() then\n'
            '                found = fn\n'
            '                break\n'
            '            end\n'
            '        end\n'
            '    end\n'
            '    if not found then return DoNotif("Function not found: " .. fnName, 2) end\n\n'
            '    local ok, name, val = pcall(debug.getupvalue, found, uvIndex)\n'
            '    if not ok then return DoNotif("getupvalue failed", 2) end\n'
            '    print(("[UV] fn=%s idx=%d name=%s val=%s"):format(fnName, uvIndex, tostring(name), tostring(val)))\n\n'
            '    if newVal then\n'
            '        local patchVal = tonumber(newVal) or (newVal == "true") or (newVal ~= "false" and newVal)\n'
            '        pcall(debug.setupvalue, found, uvIndex, patchVal)\n'
            '        DoNotif("Patched upvalue " .. uvIndex .. " = " .. tostring(patchVal), 2)\n'
            '    else\n'
            '        DoNotif(("UV[%d] %s = %s"):format(uvIndex, tostring(name), tostring(val)), 3)\n'
            '    end\n'
            'end)'
        ),
        "Closure Integrity Check": (
            '-- Verify if a function is a native/C closure or has been hooked\n'
            'addcmd("checkfn", {"isfunc", "closurecheck"}, function(args, speaker)\n'
            '    local fnName = args[1]\n'
            '    if not fnName then return DoNotif("Usage: checkfn <globalFnName>", 2) end\n\n'
            '    local fn = getgenv()[fnName] or _G[fnName]\n'
            '    if type(fn) ~= "function" then\n'
            '        return DoNotif(fnName .. " is not a function in env.", 2)\n'
            '    end\n\n'
            '    local results = {}\n'
            '    table.insert(results, "fn: " .. tostring(fn))\n'
            '    table.insert(results, "isC: " .. tostring(iscclosure(fn)))\n'
            '    table.insert(results, "isL: " .. tostring(islclosure(fn)))\n'
            '    table.insert(results, "isExec: " .. tostring(isexecutorclosure(fn)))\n'
            '    local hash = pcall(getfunctionhash, fn) and getfunctionhash(fn) or "N/A"\n'
            '    table.insert(results, "hash: " .. tostring(hash))\n'
            '    print("[CheckFn] " .. fnName .. "\\n" .. table.concat(results, " | "))\n'
            '    DoNotif("CheckFn: " .. fnName .. " — see console", 2)\n'
            'end)'
        ),
        # ── Remote / Network ─────────────────────────────────────────────────
        "Remote Bruteforce Fuzzer": (
            '-- Fire every remote in the game with test args and log responses\n'
            'addcmd("fuzzremotes", {"fuzzer", "rfuzz"}, function(args, speaker)\n'
            '    local testArgs = {nil, true, false, 0, 1, "", "test",\n'
            '        speaker, speaker.Character,\n'
            '        Vector3.zero, CFrame.identity}\n\n'
            '    local remotes = {}\n'
            '    for _, v in ipairs(game:GetDescendants()) do\n'
            '        if v:IsA("RemoteEvent") or v:IsA("RemoteFunction") then\n'
            '            table.insert(remotes, v)\n'
            '        end\n'
            '    end\n\n'
            '    DoNotif("Fuzzing " .. #remotes .. " remotes...", 3)\n'
            '    task.spawn(function()\n'
            '        for _, remote in ipairs(remotes) do\n'
            '            for _, arg in ipairs(testArgs) do\n'
            '                pcall(function()\n'
            '                    if remote:IsA("RemoteEvent") then\n'
            '                        remote:FireServer(arg)\n'
            '                    else\n'
            '                        local res = remote:InvokeServer(arg)\n'
            '                        if res ~= nil then\n'
            '                            print(("[Fuzz] " .. remote:GetFullName() .. " responded: " .. tostring(res)))\n'
            '                        end\n'
            '                    end\n'
            '                end)\n'
            '                task.wait(0.05)\n'
            '            end\n'
            '        end\n'
            '        DoNotif("Fuzz complete!", 2)\n'
            '    end)\n'
            'end)'
        ),
        "Remote Spy (namecall hook)": (
            '-- Full remote spy via __namecall — logs every FireServer/InvokeServer\n'
            'do\n'
            '    local spyEnabled = false\n'
            '    local orig\n'
            '    local blacklist = {}  -- add remote names to mute: blacklist["noisyRemote"] = true\n\n'
            '    addcmd("rspy", {"remotespy", "spy"}, function(args, speaker)\n'
            '        spyEnabled = not spyEnabled\n'
            '        if spyEnabled then\n'
            '            orig = hookmetamethod(game, "__namecall", newcclosure(function(self, ...)\n'
            '                local method = getnamecallmethod()\n'
            '                if (method == "FireServer" or method == "InvokeServer") and\n'
            '                   (self:IsA("RemoteEvent") or self:IsA("RemoteFunction")) and\n'
            '                   not blacklist[self.Name] then\n'
            '                    local argList = {...}\n'
            '                    local strs = {}\n'
            '                    for i, v in ipairs(argList) do\n'
            '                        strs[i] = typeof(v) .. "(" .. tostring(v) .. ")"\n'
            '                    end\n'
            '                    print(("[RemoteSpy] %s:%s(%s)"):format(\n'
            '                        self:GetFullName(), method, table.concat(strs, ", ")))\n'
            '                end\n'
            '                return orig(self, ...)\n'
            '            end))\n'
            '            DoNotif("Remote Spy: ON", 2)\n'
            '        else\n'
            '            if orig then hookmetamethod(game, "__namecall", orig) orig = nil end\n'
            '            DoNotif("Remote Spy: OFF", 2)\n'
            '        end\n'
            '    end)\n'
            'end'
        ),
        "Block Specific Remote": (
            '-- Intercept and block a named remote from firing to server\n'
            'do\n'
            '    local blocked = {}\n'
            '    local orig\n'
            '    local active = false\n\n'
            '    local function ensureHook()\n'
            '        if active then return end\n'
            '        active = true\n'
            '        orig = hookmetamethod(game, "__namecall", newcclosure(function(self, ...)\n'
            '            local method = getnamecallmethod()\n'
            '            if blocked[self.Name] and\n'
            '               (method == "FireServer" or method == "InvokeServer") then\n'
            '                warn("[BlockRemote] Blocked: " .. self:GetFullName())\n'
            '                return  -- drop the call\n'
            '            end\n'
            '            return orig(self, ...)\n'
            '        end))\n'
            '    end\n\n'
            '    addcmd("blockremote", {"br", "silenceremote"}, function(args, speaker)\n'
            '        local name = args[1]\n'
            '        if not name then return DoNotif("Usage: blockremote <RemoteName>", 2) end\n'
            '        if blocked[name] then\n'
            '            blocked[name] = nil\n'
            '            DoNotif("Unblocked: " .. name, 2)\n'
            '        else\n'
            '            blocked[name] = true\n'
            '            ensureHook()\n'
            '            DoNotif("Blocking: " .. name, 2)\n'
            '        end\n'
            '    end)\n'
            'end'
        ),
        "Replay Last Remote Call": (
            '-- Capture the last FireServer call and replay it on demand\n'
            'do\n'
            '    local lastCall = nil\n'
            '    local orig\n\n'
            '    orig = hookmetamethod(game, "__namecall", newcclosure(function(self, ...)\n'
            '        local method = getnamecallmethod()\n'
            '        if method == "FireServer" and self:IsA("RemoteEvent") then\n'
            '            lastCall = {remote = self, args = {...}}\n'
            '        end\n'
            '        return orig(self, ...)\n'
            '    end))\n\n'
            '    addcmd("replay", {"refire", "repeatremote"}, function(args, speaker)\n'
            '        if not lastCall then return DoNotif("No call captured yet.", 2) end\n'
            '        local count = tonumber(args[1]) or 1\n'
            '        for i = 1, count do\n'
            '            pcall(function()\n'
            '                lastCall.remote:FireServer(table.unpack(lastCall.args))\n'
            '            end)\n'
            '            if count > 1 then task.wait(0.05) end\n'
            '        end\n'
            '        DoNotif("Replayed " .. count .. "x: " .. lastCall.remote.Name, 2)\n'
            '    end)\n'
            'end'
        ),
        # ── Identity / Metatable ─────────────────────────────────────────────
        "Identity Spoof (setidentity)": (
            '-- Temporarily elevate script identity level for privileged API access\n'
            'addcmd("setid", {"identity", "elevate"}, function(args, speaker)\n'
            '    local level = tonumber(args[1]) or 7\n'
            '    local ok, err = pcall(setidentity, level)\n'
            '    if ok then\n'
            '        DoNotif("Identity set to " .. level, 2)\n'
            '        print("[Identity] Current level:", identifyexecutor and identifyexecutor() or "unknown")\n'
            '    else\n'
            '        DoNotif("setidentity failed: " .. tostring(err), 3)\n'
            '    end\n'
            'end)'
        ),
        "Metatable Lock Bypass": (
            '-- Read a locked/protected table by bypassing __index restrictions\n'
            'addcmd("readmeta", {"metamread", "bypassmt"}, function(args, speaker)\n'
            '    local objName = args[1]\n'
            '    local propName = args[2]\n'
            '    if not (objName and propName) then\n'
            '        return DoNotif("Usage: readmeta <global> <prop>", 2)\n'
            '    end\n\n'
            '    local obj = getgenv()[objName] or _G[objName]\n'
            '    if not obj then return DoNotif("Object not found: " .. objName, 2) end\n\n'
            '    -- rawget bypasses __index metamethods\n'
            '    local rawVal = rawget(obj, propName)\n'
            '    -- Also try getrawmetatable to peek at hidden fields\n'
            '    local mt = getrawmetatable(obj)\n'
            '    local mtVal = mt and rawget(mt, propName)\n\n'
            '    print(("[ReadMeta] rawget:", tostring(rawVal)))\n'
            '    print(("[ReadMeta] metatable[" .. propName .. "]:", tostring(mtVal)))\n'
            '    DoNotif("ReadMeta: check console", 2)\n'
            'end)'
        ),
        "Freeze Metatable (__newindex block)": (
            '-- Freeze a table so writes to it are silently dropped\n'
            'addcmd("freezetable", {"freeze", "locktable"}, function(args, speaker)\n'
            '    local objName = args[1]\n'
            '    if not objName then return DoNotif("Usage: freezetable <globalName>", 2) end\n\n'
            '    local obj = getgenv()[objName] or _G[objName]\n'
            '    if type(obj) ~= "table" then return DoNotif("Not a table: " .. objName, 2) end\n\n'
            '    local mt = getrawmetatable(obj) or {}\n'
            '    -- setrawmetatable bypasses __metatable lock\n'
            '    mt.__newindex = newcclosure(function(t, k, v)\n'
            '        warn(("[Freeze] Write blocked: %s.%s = %s"):format(objName, tostring(k), tostring(v)))\n'
            '        -- do nothing — drop the write\n'
            '    end)\n'
            '    mt.__index = mt.__index or obj  -- preserve reads\n'
            '    setrawmetatable(obj, mt)\n'
            '    DoNotif("Frozen: " .. objName, 2)\n'
            'end)'
        ),
        "Spoof Instance ClassName": (
            '-- Make an instance report a fake ClassName via __index hook on its metatable\n'
            'addcmd("spoofinst", {"faketype", "classname"}  , function(args, speaker)\n'
            '    -- Usage: select an instance in Explorer, then run this\n'
            '    local fakeClass = args[1] or "Script"\n\n'
            '    -- Get the selected instance from Dex/Explorer selection\n'
            '    local target = game:GetService("Selection"):Get()[1]\n'
            '    if not target then return DoNotif("Select an instance first.", 2) end\n\n'
            '    local mt = getrawmetatable(target)\n'
            '    if not mt then return DoNotif("No metatable accessible.", 2) end\n\n'
            '    local origIndex = mt.__index\n'
            '    setrawmetatable(target, {\n'
            '        __index = newcclosure(function(self, key)\n'
            '            if key == "ClassName" then return fakeClass end\n'
            '            return origIndex(self, key)\n'
            '        end),\n'
            '        __newindex = mt.__newindex,\n'
            '        __namecall = mt.__namecall,\n'
            '    })\n'
            '    DoNotif("Spoofed " .. target.Name .. " as " .. fakeClass, 2)\n'
            'end)'
        ),
        "Infinite Yield Spam": (
            '-- Spam a task indefinitely with configurable delay — useful for stress testing\n'
            'do\n'
            '    local spamThreads = {}\n\n'
            '    addcmd("spam", {"taskspam", "iyspam"}, function(args, speaker)\n'
            '        local cmd    = args[1]  -- command to spam-exec, or leave nil for custom body\n'
            '        local delay  = tonumber(args[2]) or 0.1\n'
            '        local limit  = tonumber(args[3]) or 0   -- 0 = infinite\n\n'
            '        if cmd == "stop" then\n'
            '            for _, t in ipairs(spamThreads) do pcall(task.cancel, t) end\n'
            '            spamThreads = {}\n'
            '            return DoNotif("Spam: STOPPED", 2)\n'
            '        end\n\n'
            '        local count = 0\n'
            '        local thread\n'
            '        thread = task.spawn(function()\n'
            '            while true do\n'
            '                if cmd then\n'
            '                    pcall(execCmd, cmd, speaker)\n'
            '                else\n'
            '                    -- Replace with your own action:\n'
            '                    print("[spam] tick", count)\n'
            '                end\n'
            '                count = count + 1\n'
            '                if limit > 0 and count >= limit then break end\n'
            '                task.wait(delay)\n'
            '            end\n'
            '            DoNotif("Spam done: " .. count .. "x", 2)\n'
            '        end)\n'
            '        table.insert(spamThreads, thread)\n'
            '        DoNotif("Spam started (" .. (limit>0 and limit.."x" or "inf") .. ", " .. delay .. "s)", 2)\n'
            '    end)\n'
            'end'
        ),
    }

    def _build_dex_page(self, parent):
        # Split layout: left = snippet list, right = preview + info
        left = tk.Frame(parent, bg=BG, width=230)
        left.pack(side="left", fill="y", padx=(14, 0), pady=14)
        left.pack_propagate(False)

        right = tk.Frame(parent, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=14, pady=14)

        # Header info
        hdr = tk.Frame(left, bg=BG2)
        hdr.pack(fill="x", pady=(0, 8))
        tk.Label(hdr, text="🔬 DEX INTEGRATION", font=FONT_TITLE,
                 fg=ACCENT, bg=BG2, anchor="w").pack(fill="x", padx=8, pady=(6,2))
        tk.Label(hdr, text="Snippets using exploit APIs:\nhookmetamethod · getgc · debug.getupvalue\nremote spy · metatable · identity spoof",
                 font=FONT_SM, fg=SUBTEXT, bg=BG2, justify="left", anchor="w").pack(fill="x", padx=8, pady=(0,6))

        self._label(left, "SNIPPETS")

        listbox = tk.Listbox(
            left, bg=BG2, fg=TEXT, selectbackground=ACCENT,
            selectforeground=TEXT, font=FONT_SM, bd=0,
            highlightthickness=1, highlightcolor=BORDER,
            activestyle="none", cursor="hand2",
        )
        listbox.pack(fill="both", expand=True)
        for name in self.DEX_SNIPPETS:
            listbox.insert("end", "  " + name)

        # Right side
        # Small info bar
        info_bar = tk.Frame(right, bg=BG3)
        info_bar.pack(fill="x", pady=(0, 8))
        tk.Label(info_bar,
                 text="⚠  These snippets use exploit-only APIs. Requires hookmetamethod, getgc, decompile, etc. to be available in your executor.",
                 font=FONT_SM, fg=YELLOW, bg=BG3, wraplength=620, justify="left").pack(anchor="w", padx=8, pady=6)

        self._label(right, "PREVIEW")
        self._dex_out = self._text_area(right, height=28, expand=True)

        out_btns = tk.Frame(right, bg=BG)
        out_btns.pack(fill="x", pady=(6, 0))
        self._btn(out_btns, "📋  COPY", lambda: self._copy(self._dex_out), CYAN).pack(side="left", padx=(0, 6))
        self._btn(out_btns, "💾  SAVE", lambda: self._save(self._dex_out), BG3).pack(side="left", padx=(0, 6))
        self._btn(out_btns, "⚡  SEND TO BUILDER", self._dex_to_builder, ACCENT).pack(side="left")

        def on_select(event):
            sel = listbox.curselection()
            if not sel:
                return
            name = listbox.get(sel[0]).strip()
            code = self.DEX_SNIPPETS.get(name, "")
            self._dex_out.configure(state="normal")
            self._dex_out.delete("1.0", "end")
            self._dex_out.insert("1.0", code)

        listbox.bind("<<ListboxSelect>>", on_select)
        self._dex_listbox = listbox

    def _dex_to_builder(self):
        """Send Dex snippet to Converter tab for further editing."""
        code = self._dex_out.get("1.0", "end-1c").strip()
        if not code:
            messagebox.showinfo("Empty", "Select a snippet first.")
            return
        # Populate converter input and switch to converter tab
        self._conv_input.delete("1.0", "end")
        self._conv_input.insert("1.0", code)
        # Switch tab
        for name, btn in self._tab_btns.items():
            if "Converter" in name:
                btn.invoke()
                break

    # ── Page: Hub Creator ────────────────────────────────────────────────────

    # Verified loadstring URLs
    LIB_URLS = {
        "Luna":  "https://raw.githubusercontent.com/zukatech1/Main-Repo/refs/heads/main/Luna.lua",
        "Orion": "https://raw.githubusercontent.com/shlexware/Orion/main/source",
    }

    def _build_hub_page(self, parent):
        self._hub_elements = []   # list of dicts: {kind, label, desc, cmd, args, options, flag}

        # ── Left: settings + element builder ─────────────────────────────────
        left = tk.Frame(parent, bg=BG, width=370)
        left.pack(side="left", fill="y", padx=(14, 0), pady=14)
        left.pack_propagate(False)

        # Library picker
        self._label(left, "UI LIBRARY")
        lib_row = tk.Frame(left, bg=BG)
        lib_row.pack(fill="x", pady=(0, 8))
        self._hub_lib = tk.StringVar(value="Luna")
        for lib in ("Luna", "Orion"):
            col = CYAN if lib == "Luna" else YELLOW
            tk.Radiobutton(lib_row, text=lib, variable=self._hub_lib, value=lib,
                           font=FONT_SM, fg=col, bg=BG, selectcolor=BG2,
                           activebackground=BG, activeforeground=col,
                           highlightthickness=0, cursor="hand2").pack(side="left", padx=(0, 16))

        # Window settings
        self._label(left, "WINDOW SETTINGS")
        ws = tk.Frame(left, bg=BG2)
        ws.pack(fill="x", pady=(0, 8))

        def wrow(label, var, placeholder=""):
            r = tk.Frame(ws, bg=BG2)
            r.pack(fill="x", padx=6, pady=2)
            tk.Label(r, text=label, font=FONT_SM, fg=SUBTEXT,
                     bg=BG2, width=12, anchor="w").pack(side="left")
            e = tk.Entry(r, textvariable=var, font=FONT_UI, bg=BG3, fg=TEXT,
                         insertbackground=CYAN, bd=0, highlightthickness=1,
                         highlightcolor=ACCENT, highlightbackground=BORDER)
            e.pack(side="left", fill="x", expand=True, ipady=4)
            if placeholder and not var.get():
                e.insert(0, placeholder)
                e.configure(fg=SUBTEXT)
                def _fi(ev, _e=e, _v=var, _p=placeholder):
                    if _e.get() == _p: _e.delete(0, "end"); _e.configure(fg=TEXT)
                def _fo(ev, _e=e, _v=var, _p=placeholder):
                    if not _e.get(): _e.insert(0, _p); _e.configure(fg=SUBTEXT)
                e.bind("<FocusIn>", _fi); e.bind("<FocusOut>", _fo)
            return var

        self._hub_title   = tk.StringVar(value="Zuka Hub")
        self._hub_intro   = tk.StringVar(value="Welcome!")
        self._hub_config  = tk.StringVar(value="ZukaHub")
        self._hub_intro_en = tk.BooleanVar(value=True)
        self._hub_save_cfg = tk.BooleanVar(value=True)

        wrow("Title:",   self._hub_title)
        wrow("Intro txt:", self._hub_intro)
        wrow("CfgFolder:", self._hub_config)

        flag_row = tk.Frame(ws, bg=BG2)
        flag_row.pack(fill="x", padx=6, pady=(2, 6))
        tk.Checkbutton(flag_row, text="Intro anim", variable=self._hub_intro_en,
                       font=FONT_SM, fg=TEXT, bg=BG2, selectcolor=BG3,
                       activebackground=BG2, highlightthickness=0).pack(side="left", padx=(0, 12))
        tk.Checkbutton(flag_row, text="Save config", variable=self._hub_save_cfg,
                       font=FONT_SM, fg=TEXT, bg=BG2, selectcolor=BG3,
                       activebackground=BG2, highlightthickness=0).pack(side="left")

        # Element kind selector
        self._label(left, "ADD ELEMENT")
        kind_row = tk.Frame(left, bg=BG)
        kind_row.pack(fill="x", pady=(0, 6))
        self._hub_kind = tk.StringVar(value="Button")
        KIND_COLORS = {"Button": CYAN, "Toggle": YELLOW, "Textbox": "#ab54f7", "Dropdown": GREEN}
        for k, col in KIND_COLORS.items():
            tk.Radiobutton(kind_row, text=k, variable=self._hub_kind, value=k,
                           font=FONT_SM, fg=col, bg=BG, selectcolor=BG2,
                           activebackground=BG, activeforeground=col,
                           highlightthickness=0, cursor="hand2",
                           command=self._hub_refresh_form).pack(side="left", padx=(0, 10))

        # Dynamic element form
        self._hub_form_frame = tk.Frame(left, bg=BG2)
        self._hub_form_frame.pack(fill="x", pady=(0, 6))
        self._hub_form_vars = {}
        self._hub_refresh_form()

        add_btn_row = tk.Frame(left, bg=BG)
        add_btn_row.pack(fill="x", pady=(4, 0))
        self._btn(add_btn_row, "➕  ADD ELEMENT", self._hub_add_element, ACCENT).pack(side="left", padx=(0, 6))
        self._btn(add_btn_row, "🗑  CLEAR ALL",
                  lambda: (self._hub_elements.clear(), self._hub_refresh_list()), BG3).pack(side="left")

        # ── Right: element list + output ──────────────────────────────────────
        right = tk.Frame(parent, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=14, pady=14)

        self._label(right, "ELEMENTS  (drag to reorder — use ↑↓ buttons)")

        list_frame = tk.Frame(right, bg=BORDER, bd=1)
        list_frame.pack(fill="x")
        self._hub_listbox = tk.Listbox(
            list_frame, bg=BG2, fg=TEXT, selectbackground=ACCENT,
            font=FONT_SM, bd=0, highlightthickness=0, activestyle="none",
            height=8
        )
        self._hub_listbox.pack(side="left", fill="both", expand=True)
        lb_vsb = tk.Scrollbar(list_frame, orient="vertical", command=self._hub_listbox.yview,
                              bg=BG2, troughcolor=BG2, bd=0, width=8)
        lb_vsb.pack(side="right", fill="y")
        self._hub_listbox.configure(yscrollcommand=lb_vsb.set)

        lb_ctrl = tk.Frame(right, bg=BG)
        lb_ctrl.pack(fill="x", pady=(4, 8))
        self._btn(lb_ctrl, "↑", self._hub_move_up,   BG3).pack(side="left", padx=(0, 4))
        self._btn(lb_ctrl, "↓", self._hub_move_down, BG3).pack(side="left", padx=(0, 4))
        self._btn(lb_ctrl, "🗑 Remove", self._hub_remove_selected, "#aa2222").pack(side="left")

        self._label(right, "GENERATED OUTPUT")
        self._hub_out = self._text_area(right, height=16, expand=True)
        self._hub_out.configure(state="disabled")

        out_row = tk.Frame(right, bg=BG)
        out_row.pack(fill="x", pady=(6, 0))
        self._btn(out_row, "⚡  GENERATE", self._hub_generate, ACCENT).pack(side="left", padx=(0, 6))
        self._btn(out_row, "📋  COPY", lambda: self._copy(self._hub_out), CYAN).pack(side="left", padx=(0, 6))
        self._btn(out_row, "💾  SAVE", lambda: self._save(self._hub_out), BG3).pack(side="left")

    def _hub_refresh_form(self):
        """Rebuild the element input form based on selected kind."""
        for w in self._hub_form_frame.winfo_children():
            w.destroy()
        self._hub_form_vars = {}
        kind = self._hub_kind.get()
        f = self._hub_form_frame

        KIND_COLORS = {"Button": CYAN, "Toggle": YELLOW, "Textbox": "#ab54f7", "Dropdown": GREEN}
        col = KIND_COLORS.get(kind, TEXT)

        def frow(label, key, placeholder="", color=TEXT):
            r = tk.Frame(f, bg=BG2)
            r.pack(fill="x", padx=6, pady=2)
            tk.Label(r, text=label, font=FONT_SM, fg=SUBTEXT,
                     bg=BG2, width=12, anchor="w").pack(side="left")
            var = tk.StringVar()
            e = tk.Entry(r, textvariable=var, font=FONT_UI, bg=BG3, fg=color,
                         insertbackground=CYAN, bd=0, highlightthickness=1,
                         highlightcolor=ACCENT, highlightbackground=BORDER)
            e.pack(side="left", fill="x", expand=True, ipady=4)
            if placeholder:
                e.insert(0, placeholder)
                e.configure(fg=SUBTEXT)
                def _fi(ev, _e=e, _p=placeholder):
                    if _e.get() == _p: _e.delete(0, "end"); _e.configure(fg=color)
                def _fo(ev, _e=e, _p=placeholder):
                    if not _e.get(): _e.insert(0, _p); _e.configure(fg=SUBTEXT)
                e.bind("<FocusIn>", _fi); e.bind("<FocusOut>", _fo)
            self._hub_form_vars[key] = var

        tk.Label(f, text=f"── {kind} settings ──", font=FONT_SM,
                 fg=col, bg=BG2).pack(anchor="w", padx=6, pady=(6, 2))

        frow("Label:",   "label",   "Button label",  col)
        frow("Desc:",    "desc",    "optional",       SUBTEXT)

        if kind == "Button":
            frow("Command:", "cmd",  "fly",            CYAN)
            frow("Args:",    "args", "optional args",  SUBTEXT)

        elif kind == "Toggle":
            frow("Command:", "cmd",  "fly",            YELLOW)
            frow("Flag:",    "flag", "toggle_fly",     SUBTEXT)

        elif kind == "Textbox":
            frow("Command:", "cmd",     "speed",           "#ab54f7")
            frow("Placeholder:", "placeholder", "Enter value...", SUBTEXT)
            frow("Flag:",    "flag",    "textbox_speed",   SUBTEXT)

        elif kind == "Dropdown":
            frow("Command:", "cmd",     "goto",           GREEN)
            frow("Options:", "options", "opt1, opt2, opt3", SUBTEXT)
            frow("Flag:",    "flag",    "dropdown_goto",   SUBTEXT)

    def _hub_get_form(self, key, default=""):
        var = self._hub_form_vars.get(key)
        if not var:
            return default
        v = var.get().strip()
        # Strip placeholder-colored ghost text (placeholders never have spaces at start)
        return v if v else default

    def _hub_add_element(self):
        kind  = self._hub_kind.get()
        label = self._hub_get_form("label")
        if not label or label in ("Button label", "optional"):
            messagebox.showwarning("Missing", "Enter a label for the element.")
            return
        elem = {
            "kind":        kind,
            "label":       label,
            "desc":        self._hub_get_form("desc", "nil"),
            "cmd":         self._hub_get_form("cmd", "commandname"),
            "args":        self._hub_get_form("args", ""),
            "placeholder": self._hub_get_form("placeholder", "Enter value..."),
            "options":     self._hub_get_form("options", "Option 1, Option 2"),
            "flag":        self._hub_get_form("flag", label.lower().replace(" ", "_")),
        }
        self._hub_elements.append(elem)
        self._hub_refresh_list()

    def _hub_refresh_list(self):
        self._hub_listbox.delete(0, "end")
        KIND_ICONS = {"Button": "🎯", "Toggle": "🔀", "Textbox": "✏️", "Dropdown": "📂"}
        for elem in self._hub_elements:
            icon = KIND_ICONS.get(elem["kind"], "?")
            cmd_info = f'→ execCmd("{elem["cmd"]}")' if elem["kind"] == "Button" else f'→ {elem["cmd"]}'
            self._hub_listbox.insert("end",
                f'  {icon} [{elem["kind"]}]  "{elem["label"]}"  {cmd_info}')

    def _hub_move_up(self):
        sel = self._hub_listbox.curselection()
        if not sel or sel[0] == 0: return
        i = sel[0]
        self._hub_elements[i-1], self._hub_elements[i] = self._hub_elements[i], self._hub_elements[i-1]
        self._hub_refresh_list()
        self._hub_listbox.selection_set(i-1)

    def _hub_move_down(self):
        sel = self._hub_listbox.curselection()
        if not sel or sel[0] >= len(self._hub_elements)-1: return
        i = sel[0]
        self._hub_elements[i], self._hub_elements[i+1] = self._hub_elements[i+1], self._hub_elements[i]
        self._hub_refresh_list()
        self._hub_listbox.selection_set(i+1)

    def _hub_remove_selected(self):
        sel = self._hub_listbox.curselection()
        if not sel: return
        self._hub_elements.pop(sel[0])
        self._hub_refresh_list()

    def _hub_generate(self):
        if not self._hub_elements:
            messagebox.showwarning("Empty", "Add at least one element first.")
            return

        lib   = self._hub_lib.get()
        title = self._hub_title.get().strip() or "Zuka Hub"
        intro = self._hub_intro.get().strip() or "Welcome!"
        cfg   = self._hub_config.get().strip() or "ZukaHub"
        use_intro = self._hub_intro_en.get()
        save_cfg  = self._hub_save_cfg.get()
        lp_name   = '" .. game.Players.LocalPlayer.Name .. "'

        lines = []
        def w(s=""): lines.append(s)

        w("-- ════════════════════════════════════════════════")
        w(f"-- Hub: {title}  |  Library: {lib}")
        w(f"-- Generated by Zuka Panel Hub Creator")
        w("-- ════════════════════════════════════════════════")
        w()
        w("local Players     = game:GetService('Players')")
        w("local speaker     = Players.LocalPlayer")
        w()

        # ── Library loadstring ─────────────────────────────────────────────
        url = self.LIB_URLS[lib]

        if lib == "Luna":
            w(f"local Luna = loadstring(game:HttpGet('{url}'))()")
            w()
            desc_str = f'"{intro}, " .. speaker.Name'
            w("local Window = Luna:CreateWindow({")
            w(f'    Name            = "{title}",')
            w(f'    Subtitle        = nil,')
            w(f'    LogoID          = nil,')
            w(f'    LoadingEnabled  = {str(use_intro).lower()},')
            w(f'    LoadingTitle    = "{title}",')
            w(f'    LoadingSubtitle = "by Zuka",')
            w(f'    ConfigSettings  = {{')
            w(f'        ConfigFolder = "{cfg}"')
            w(f'    }},')
            w(f'    KeySystem = false,')
            w("})")
            w()
            w("local Tab = Window:MakeTab({")
            w(f'    Name = "Main",')
            w(f'    Icon = nil,')
            w("})")
            w()

            for elem in self._hub_elements:
                cmd   = elem["cmd"]
                label = elem["label"]
                desc  = f'"{elem["desc"]}"' if elem["desc"] not in ("nil","optional","") else "nil"
                flag  = elem["flag"] or label.lower().replace(" ", "_")

                if elem["kind"] == "Button":
                    args = elem["args"].strip()
                    arg_str = f', "{args}"' if args else ""
                    w(f'Tab:CreateButton({{')
                    w(f'    Name        = "{label}",')
                    w(f'    Description = {desc},')
                    w(f'    Callback    = function()')
                    w(f'        pcall(execCmd, "{cmd}"{arg_str}, speaker)')
                    w(f'    end,')
                    w(f'}})')

                elif elem["kind"] == "Toggle":
                    w(f'Tab:CreateToggle({{')
                    w(f'    Name         = "{label}",')
                    w(f'    Description  = {desc},')
                    w(f'    CurrentValue = false,')
                    w(f'    Callback     = function(Value)')
                    w(f'        pcall(execCmd, "{cmd}", speaker)')
                    w(f'    end,')
                    w(f'}}, "{flag}")')

                elif elem["kind"] == "Textbox":
                    ph = elem["placeholder"] or "Enter value..."
                    w(f'Tab:CreateInput({{')
                    w(f'    Name                = "{label}",')
                    w(f'    Description         = {desc},')
                    w(f'    PlaceholderText     = "{ph}",')
                    w(f'    ClearTextAfterFocusLost = true,')
                    w(f'    Numeric             = false,')
                    w(f'    Enter               = true,')
                    w(f'    Callback            = function(Text)')
                    w(f'        if Text and Text ~= "" then')
                    w(f'            pcall(execCmd, "{cmd} " .. Text, speaker)')
                    w(f'        end')
                    w(f'    end,')
                    w(f'}}, "{flag}")')

                elif elem["kind"] == "Dropdown":
                    opts = [o.strip() for o in elem["options"].split(",") if o.strip()]
                    opt_lua = "{" + ", ".join(f'"{o}"' for o in opts) + "}"
                    first   = f'"{opts[0]}"' if opts else '"Option 1"'
                    w(f'Tab:CreateDropdown({{')
                    w(f'    Name            = "{label}",')
                    w(f'    Description     = {desc},')
                    w(f'    Options         = {opt_lua},')
                    w(f'    CurrentOption   = {{{first}}},')
                    w(f'    MultipleOptions = false,')
                    w(f'    Callback        = function(Option)')
                    w(f'        if Option and Option ~= "" then')
                    w(f'            pcall(execCmd, "{cmd} " .. Option, speaker)')
                    w(f'        end')
                    w(f'    end,')
                    w(f'}}, "{flag}")')

                w()

        else:  # Orion
            w(f"local OrionLib = loadstring(game:HttpGet('{url}'))()")
            w()
            w("local Window = OrionLib:MakeWindow({")
            w(f'    Name          = "{title}",')
            w(f'    HidePremium   = true,')
            w(f'    SaveConfig    = {str(save_cfg).lower()},')
            w(f'    ConfigFolder  = "{cfg}",')
            w(f'    IntroEnabled  = {str(use_intro).lower()},')
            w(f'    IntroText     = "{intro}, " .. speaker.Name,')
            w("})")
            w()
            w("local Tab = Window:MakeTab({")
            w(f'    Name        = "Main",')
            w(f'    Icon        = "rbxassetid://4483345998",')
            w(f'    PremiumOnly = false,')
            w("})")
            w()

            for elem in self._hub_elements:
                cmd   = elem["cmd"]
                label = elem["label"]
                flag  = elem["flag"] or label.lower().replace(" ", "_")

                if elem["kind"] == "Button":
                    args = elem["args"].strip()
                    arg_str = f', "{args}"' if args else ""
                    w(f'Tab:AddButton({{')
                    w(f'    Name     = "{label}",')
                    w(f'    Callback = function()')
                    w(f'        pcall(execCmd, "{cmd}"{arg_str}, speaker)')
                    w(f'    end,')
                    w(f'}})')

                elif elem["kind"] == "Toggle":
                    w(f'Tab:AddToggle({{')
                    w(f'    Name     = "{label}",')
                    w(f'    Default  = false,')
                    w(f'    Save     = {str(save_cfg).lower()},')
                    w(f'    Flag     = "{flag}",')
                    w(f'    Callback = function(Value)')
                    w(f'        pcall(execCmd, "{cmd}", speaker)')
                    w(f'    end,')
                    w(f'}})')

                elif elem["kind"] == "Textbox":
                    ph = elem["placeholder"] or "Enter value..."
                    w(f'Tab:AddTextbox({{')
                    w(f'    Name          = "{label}",')
                    w(f'    Default       = "{ph}",')
                    w(f'    TextDisappear = true,')
                    w(f'    Callback      = function(Value)')
                    w(f'        if Value and Value ~= "" then')
                    w(f'            pcall(execCmd, "{cmd} " .. Value, speaker)')
                    w(f'        end')
                    w(f'    end,')
                    w(f'}})')

                elif elem["kind"] == "Dropdown":
                    opts = [o.strip() for o in elem["options"].split(",") if o.strip()]
                    opt_lua = "{" + ", ".join(f'"{o}"' for o in opts) + "}"
                    first   = f'"{opts[0]}"' if opts else '"Option 1"'
                    w(f'Tab:AddDropdown({{')
                    w(f'    Name     = "{label}",')
                    w(f'    Default  = {first},')
                    w(f'    Options  = {opt_lua},')
                    w(f'    Save     = {str(save_cfg).lower()},')
                    w(f'    Flag     = "{flag}",')
                    w(f'    Callback = function(Value)')
                    w(f'        if Value and Value ~= "" then')
                    w(f'            pcall(execCmd, "{cmd} " .. Value, speaker)')
                    w(f'        end')
                    w(f'    end,')
                    w(f'}})')

                w()

            w("OrionLib:Init()")

        code = "\n".join(lines)
        self._set_output(self._hub_out, code)

    # ── Page: Script Importer ────────────────────────────────────────────────

    # Regex patterns for format detection
    _IMPORT_PATTERNS = {
        "loadstring": [
            r'loadstring\s*\(\s*game\s*:\s*HttpGet\s*\(',
            r'loadstring\s*\(\s*game\.HttpGet\s*\(',
            r'loadstring\s*\(\s*HttpGet\s*\(',
            r'require\s*\(\s*\d+\s*\)',
        ],
        "modules": [
            r'Modules\s*\.\s*\w+\s*=\s*\{',
            r'function\s+Modules\s*\.\s*\w+\s*:\s*Initialize\s*\(',
        ],
        "register": [
            r'RegisterCommand\s*\(',
            r'RegisterCommandDual\s*\(',
        ],
    }

    def _build_import_page(self, parent):
        # ── Left: input + detection ───────────────────────────────────────────
        left = tk.Frame(parent, bg=BG, width=500)
        left.pack(side="left", fill="y", padx=(14, 0), pady=14)
        left.pack_propagate(False)

        self._label(left, "PASTE SCRIPT  (any format)")

        self._imp_input = self._text_area(left, height=16)
        self._imp_input.bind("<KeyRelease>", self._imp_auto_detect)
        self._imp_input.bind("<ButtonRelease>", self._imp_auto_detect)

        # Detection result bar
        det_row = tk.Frame(left, bg=BG2)
        det_row.pack(fill="x", pady=(4, 0))
        tk.Label(det_row, text="DETECTED:", font=FONT_SM, fg=SUBTEXT,
                 bg=BG2, padx=6).pack(side="left")
        self._imp_det_label = tk.Label(det_row, text="—  paste a script above",
                                       font=FONT_SM, fg=SUBTEXT, bg=BG2)
        self._imp_det_label.pack(side="left")

        # Command metadata
        sep = tk.Frame(left, bg=BORDER, height=1)
        sep.pack(fill="x", pady=10)

        self._label(left, "WRAP AS COMMAND")

        meta = tk.Frame(left, bg=BG2)
        meta.pack(fill="x")

        def mrow(label, var, col=TEXT, placeholder=""):
            r = tk.Frame(meta, bg=BG2)
            r.pack(fill="x", padx=6, pady=2)
            tk.Label(r, text=label, font=FONT_SM, fg=SUBTEXT,
                     bg=BG2, width=12, anchor="w").pack(side="left")
            e = tk.Entry(r, textvariable=var, font=FONT_UI, bg=BG3, fg=col,
                         insertbackground=CYAN, bd=0, highlightthickness=1,
                         highlightcolor=ACCENT, highlightbackground=BORDER)
            e.pack(side="left", fill="x", expand=True, ipady=4)
            if placeholder:
                e.insert(0, placeholder)
                e.configure(fg=SUBTEXT)
                def _fi(ev, _e=e, _c=col, _p=placeholder):
                    if _e.get() == _p: _e.delete(0,"end"); _e.configure(fg=_c)
                def _fo(ev, _e=e, _c=col, _p=placeholder):
                    if not _e.get(): _e.insert(0,_p); _e.configure(fg=SUBTEXT)
                e.bind("<FocusIn>",_fi); e.bind("<FocusOut>",_fo)
            return var

        self._imp_cmd      = tk.StringVar()
        self._imp_aliases  = tk.StringVar()
        self._imp_args_desc = tk.StringVar()

        mrow("Cmd name:",  self._imp_cmd,       CYAN,    "e.g. myscript")
        mrow("Aliases:",   self._imp_aliases,    YELLOW,  "a, ms  (comma sep)")
        mrow("Args desc:", self._imp_args_desc,  SUBTEXT, "optional description")

        # Output style
        self._label(left, "OUTPUT STYLE")
        style_row = tk.Frame(left, bg=BG)
        style_row.pack(fill="x", pady=(0, 8))
        self._imp_style = tk.StringVar(value="addcmd")
        tk.Radiobutton(style_row, text="addcmd()", variable=self._imp_style,
                       value="addcmd", font=FONT_SM, fg=CYAN, bg=BG,
                       selectcolor=BG2, activebackground=BG, activeforeground=CYAN,
                       highlightthickness=0, cursor="hand2").pack(side="left", padx=(0,14))
        tk.Radiobutton(style_row, text="RegisterCommand()", variable=self._imp_style,
                       value="register", font=FONT_SM, fg=YELLOW, bg=BG,
                       selectcolor=BG2, activebackground=BG, activeforeground=YELLOW,
                       highlightthickness=0, cursor="hand2").pack(side="left")

        btn_row = tk.Frame(left, bg=BG)
        btn_row.pack(fill="x", pady=(8, 0))
        self._btn(btn_row, "⚡  CONVERT & WRAP",   self._imp_do_convert, ACCENT).pack(side="left", padx=(0,6))
        self._btn(btn_row, "➡  SEND TO BUILDER",   self._imp_to_builder, CYAN).pack(side="left", padx=(0,6))
        self._btn(btn_row, "🗑  CLEAR",             self._imp_clear,      BG3).pack(side="left")

        # ── Right: output ─────────────────────────────────────────────────────
        right = tk.Frame(parent, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=14, pady=14)

        self._label(right, "OUTPUT  —  ready to paste into your panel")
        self._imp_out = self._text_area(right, height=32, expand=True)
        self._imp_out.configure(state="disabled")

        out_row = tk.Frame(right, bg=BG)
        out_row.pack(fill="x", pady=(6, 0))
        self._btn(out_row, "📋  COPY", lambda: self._copy(self._imp_out), CYAN).pack(side="left", padx=(0,6))
        self._btn(out_row, "💾  SAVE", lambda: self._save(self._imp_out), BG3).pack(side="left")

    # ── Import helpers ────────────────────────────────────────────────────────

    def _imp_detect_format(self, src: str) -> str:
        """Return 'loadstring' | 'modules' | 'register' | 'raw'."""
        import re
        for fmt, patterns in self._IMPORT_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, src, re.IGNORECASE):
                    return fmt
        return "raw"

    def _imp_auto_detect(self, event=None):
        src = self._imp_input.get("1.0", "end-1c").strip()
        if not src:
            self._imp_det_label.configure(text="—  paste a script above", fg=SUBTEXT)
            return
        fmt = self._imp_detect_format(src)
        FMT_LABELS = {
            "loadstring": ("🌐  loadstring / HttpGet",         CYAN),
            "modules":    ("📦  Modules.X:Initialize() style", YELLOW),
            "register":   ("📋  RegisterCommand style",        "#ab54f7"),
            "raw":        ("📝  Raw Lua",                      GREEN),
        }
        text, color = FMT_LABELS[fmt]
        self._imp_det_label.configure(text=text, fg=color)

    def _imp_extract_body(self, src: str, fmt: str) -> str:
        """
        Pull the executable core out of the detected format.
        For loadstring  → keep as-is (it IS the executable call).
        For modules     → extract the body of :Initialize().
        For register    → extract the function body of each RegisterCommand.
        For raw         → keep as-is.
        """
        import re

        if fmt in ("raw", "loadstring"):
            return src

        if fmt == "modules":
            # Extract everything inside :Initialize() ... end
            m = re.search(
                r'function\s+Modules\s*\.\s*\w+\s*:\s*Initialize\s*\(\s*\)(.*?)^end',
                src, re.DOTALL | re.MULTILINE
            )
            if m:
                body = m.group(1).strip()
                return body if body else src
            return src

        if fmt == "register":
            # Pull all RegisterCommand / RegisterCommandDual calls and keep them intact
            # (They already contain the function body)
            calls = re.findall(
                r'RegisterCommand(?:Dual)?\s*\(.*?\)\s*\)',
                src, re.DOTALL
            )
            if calls:
                return "\n\n".join(c.strip() for c in calls)
            return src

        return src

    def _imp_do_convert(self):
        import re
        src = self._imp_input.get("1.0", "end-1c").strip()
        if not src:
            messagebox.showwarning("Empty", "Paste a script first.")
            return

        cmd_raw = self._imp_cmd.get().strip()
        # strip placeholder text
        if cmd_raw in ("e.g. myscript", ""):
            cmd_raw = "myscript"
        cmd = cmd_raw.lower().replace(" ", "_")

        aliases_raw = self._imp_aliases.get().strip()
        if aliases_raw in ("a, ms  (comma sep)", ""):
            aliases_raw = ""
        aliases = [a.strip() for a in aliases_raw.split(",") if a.strip() and a.strip() not in ("a", "ms")]

        desc_raw = self._imp_args_desc.get().strip()
        if desc_raw == "optional description":
            desc_raw = ""

        fmt   = self._imp_detect_format(src)
        body  = self._imp_extract_body(src, fmt)
        style = self._imp_style.get()

        # Indent body for inside a function
        def indent(text, n=4):
            pad = " " * n
            return "\n".join(pad + line if line.strip() else line for line in text.splitlines())

        lines = []
        def w(s=""): lines.append(s)

        w(f"-- ── Imported: {cmd}  [{fmt} → {style}] ──────────────────────")
        w()

        if style == "addcmd":
            alias_lua = "{" + ", ".join(f'"{a}"' for a in aliases) + "}"
            w(f'addcmd("{cmd}", {alias_lua}, function(args, speaker)')
            for line in body.splitlines():
                w("    " + line if line.strip() else line)
            w("end)")

        else:  # RegisterCommand
            alias_lua = "{" + ", ".join(f'"{a}"' for a in aliases) + "}"
            w(f'RegisterCommand({{')
            w(f'    Name        = "{cmd}",')
            w(f'    Aliases     = {alias_lua},')
            w(f'    Description = "{desc_raw or cmd + " command"}",')
            w(f'    ArgsDesc    = {{}},')
            w(f'    Permissions = {{}},')
            w(f'}}, function(args, speaker)')
            for line in body.splitlines():
                w("    " + line if line.strip() else line)
            w("end)")

        result = "\n".join(lines)
        self._set_output(self._imp_out, result)

    def _imp_to_builder(self):
        """Push the output directly into the Builder tab's body field."""
        code = self._imp_out.get("1.0", "end-1c").strip()
        if not code:
            # Try converting first if there's input
            src = self._imp_input.get("1.0", "end-1c").strip()
            if not src:
                messagebox.showinfo("Empty", "Convert a script first, or paste input.")
                return
            self._imp_do_convert()
            code = self._imp_out.get("1.0", "end-1c").strip()
            if not code:
                return

        # Push cmd name into builder
        cmd_raw = self._imp_cmd.get().strip()
        if cmd_raw and cmd_raw not in ("e.g. myscript",):
            try:
                self._cmd_name.set(cmd_raw.lower().replace(" ", "_"))
            except Exception:
                pass

        # Push aliases
        aliases_raw = self._imp_aliases.get().strip()
        if aliases_raw and aliases_raw not in ("a, ms  (comma sep)",):
            try:
                self._cmd_aliases.set(aliases_raw)
            except Exception:
                pass

        # Push body into builder body box
        try:
            self._body_box.configure(state="normal")
            self._body_box.delete("1.0", "end")
            # Strip the outer addcmd/RegisterCommand wrapper — push just the body
            import re
            inner = re.search(
                r'function\s*\(args,\s*speaker\)(.*?)^end\)',
                code, re.DOTALL | re.MULTILINE
            )
            body = inner.group(1).strip() if inner else code
            self._body_box.insert("1.0", body)
        except Exception:
            pass

        # Switch to Builder tab
        for name, btn in self._tab_btns.items():
            if "Builder" in name:
                btn.invoke()
                break

        messagebox.showinfo("Sent", f'Script body sent to Builder tab as "{cmd_raw}".')

    def _imp_clear(self):
        self._imp_input.configure(state="normal")
        self._imp_input.delete("1.0", "end")
        self._set_output(self._imp_out, "")
        self._imp_det_label.configure(text="—  paste a script above", fg=SUBTEXT)
        self._imp_cmd.set("")
        self._imp_aliases.set("")
        self._imp_args_desc.set("")

    # ── Page: GUI Maker ──────────────────────────────────────────────────────



    def _build_guimaker_page(self, parent):
        self._gm = GUIMaker(parent)

# ── GUI Maker ─────────────────────────────────────────────────────────────────

CANVAS_W = 480
CANVAS_H = 360
GRID     = 20

ELEM_DEFAULTS = {
    "Frame":          {"bg": "#4a6fa5", "w": 200, "h": 100, "text": None},
    "TextLabel":      {"bg": "#5aaa5a", "w": 180, "h":  40, "text": "Label"},
    "TextButton":     {"bg": "#c87832", "w": 140, "h":  36, "text": "Button"},
    "TextBox":        {"bg": "#a03278", "w": 160, "h":  36, "text": "TextBox"},
    "ImageLabel":     {"bg": "#7832c8", "w": 120, "h": 120, "text": "[ IMG ]"},
    "ScrollingFrame": {"bg": "#28aa82", "w": 200, "h": 150, "text": None},
}

HANDLE_SIZE = 8


class GMElement:
    """Represents one GUI element on the canvas."""
    _counter = 0

    def __init__(self, etype, x, y, w=None, h=None):
        GMElement._counter += 1
        d = ELEM_DEFAULTS[etype]
        self.etype    = etype
        self.name     = f"{etype}_{GMElement._counter}"
        self.x        = x
        self.y        = y
        self.w        = w or d["w"]
        self.h        = h or d["h"]
        self.bg       = d["bg"]
        self.text     = d["text"] or ""
        self.text_color = "#ffffff"
        self.text_size  = 14
        self.transparency = 0.0
        self.visible    = True
        self.corner_r   = 8
        self.zindex     = GMElement._counter + 2
        self.anchor_x   = 0.0
        self.anchor_y   = 0.0
        # scrollingframe extras
        self.canvas_w   = 480
        self.canvas_h   = 720
        # image
        self.image_id   = ""
        # logic wiring  {event: str, logic_type: str, payload: str}
        # logic_type: "execCmd" | "toggle" | "raw"
        # event: "MouseButton1Click" | "MouseButton2Click" | "MouseEnter" | "MouseLeave"
        self.logic      = []   # list of logic dicts

    def rect(self):
        return (self.x, self.y, self.x + self.w, self.y + self.h)

    def contains(self, px, py):
        return self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h

    def handle_rects(self):
        """Returns dict of handle_name -> (x1,y1,x2,y2) in canvas coords."""
        s = HANDLE_SIZE
        cx, cy = self.x, self.y
        w, h   = self.w, self.h
        mids   = {
            "NW": (cx,       cy),
            "N":  (cx+w//2,  cy),
            "NE": (cx+w,     cy),
            "W":  (cx,       cy+h//2),
            "E":  (cx+w,     cy+h//2),
            "SW": (cx,       cy+h),
            "S":  (cx+w//2,  cy+h),
            "SE": (cx+w,     cy+h),
        }
        out = {}
        for name, (hx, hy) in mids.items():
            out[name] = (hx-s//2, hy-s//2, hx+s//2, hy+s//2)
        return out


def snap(v, grid=GRID, enabled=True):
    if not enabled:
        return v
    return round(v / grid) * grid


class GUIMaker:
    def __init__(self, parent):
        self.parent       = parent
        self.elements     = []        # list of GMElement, bottom=index0
        self.selected     = None
        self.undo_stack   = []
        self.redo_stack   = []
        self.snap_enabled = False
        self.grid_enabled = True
        self.proj_name    = "Untitled"
        self._drag_mode   = None      # "move" | handle name
        self._drag_start  = None      # (mx, my, orig_x, orig_y, orig_w, orig_h)
        self._prop_widgets = {}
        self._build()

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build(self):
        p = self.parent

        # ── Top toolbar
        toolbar = tk.Frame(p, bg=BG2, height=36)
        toolbar.pack(fill="x", padx=8, pady=(8, 0))
        toolbar.pack_propagate(False)

        def tbtn(text, cmd, color=BG3):
            b = tk.Button(toolbar, text=text, font=FONT_SM, bg=color, fg=TEXT,
                          bd=0, padx=10, pady=4, cursor="hand2",
                          activebackground=ACCENT, activeforeground=TEXT,
                          command=cmd)
            b.pack(side="left", padx=2)
            return b

        tbtn("↩ Undo",    self.undo,  "#3a4aaa")
        tbtn("↪ Redo",    self.redo,  "#3a4aaa")
        tbtn("⧉ Dup",     self.duplicate_selected, "#2a6aaa")
        tbtn("🗑 Delete", self.delete_selected, "#aa2222")
        tbtn("🗑 Clear",  self.clear_all, "#882222")

        self._grid_btn = tbtn("Grid: ON", self._toggle_grid, "#223880")
        self._snap_btn = tbtn("Snap: OFF", self._toggle_snap, "#442288")

        tbtn("⬆ Export Lua", self.export_lua, "#007744")

        # project name
        tk.Label(toolbar, text="  Project:", font=FONT_SM, fg=SUBTEXT, bg=BG2).pack(side="left")
        self._proj_var = tk.StringVar(value=self.proj_name)
        e = tk.Entry(toolbar, textvariable=self._proj_var, font=FONT_SM,
                     bg=BG3, fg=TEXT, bd=0, insertbackground=CYAN, width=14)
        e.pack(side="left", padx=(2, 8))
        self._proj_var.trace_add("write", lambda *_: setattr(self, "proj_name", self._proj_var.get()))

        # ── Main area
        main = tk.Frame(p, bg=BG)
        main.pack(fill="both", expand=True, padx=8, pady=8)

        # Left toolbox
        toolbox = tk.Frame(main, bg=BG2, width=130)
        toolbox.pack(side="left", fill="y", padx=(0, 6))
        toolbox.pack_propagate(False)

        tk.Label(toolbox, text="ELEMENTS", font=FONT_SM, fg=ACCENT,
                 bg=BG2).pack(pady=(8, 4))

        for etype, d in ELEM_DEFAULTS.items():
            icon = {"Frame":"▭","TextLabel":"T","TextButton":"B",
                    "TextBox":"I","ImageLabel":"🖼","ScrollingFrame":"⇅"}.get(etype,"?")
            btn = tk.Button(
                toolbox, text=f"{icon}  {etype}", font=FONT_SM,
                bg=BG3, fg=d["bg"], bd=0, anchor="w", padx=8, pady=6,
                cursor="hand2", activebackground=BG2, activeforeground=TEXT,
                command=lambda et=etype: self.add_element(et)
            )
            btn.pack(fill="x", pady=1)

        # Canvas area
        canvas_wrap = tk.Frame(main, bg=BG3)
        canvas_wrap.pack(side="left", fill="both", expand=True)

        tk.Label(canvas_wrap, text=f"CANVAS  ({CANVAS_W} × {CANVAS_H})",
                 font=FONT_SM, fg=SUBTEXT, bg=BG3).pack(anchor="w", padx=6, pady=(4,2))

        canvas_container = tk.Frame(canvas_wrap, bg=BG3)
        canvas_container.pack(fill="both", expand=True, padx=6, pady=(0,6))

        self.canvas = tk.Canvas(
            canvas_container,
            width=CANVAS_W, height=CANVAS_H,
            bg="#2e2e3a", highlightthickness=2,
            highlightbackground="#505070",
            cursor="crosshair"
        )
        self.canvas.pack(expand=True)

        self.canvas.bind("<ButtonPress-1>",   self._on_press)
        self.canvas.bind("<B1-Motion>",       self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Double-Button-1>", self._on_double)
        self.canvas.bind("<ButtonPress-3>",   self._on_right_click)

        # Right panels
        right = tk.Frame(main, bg=BG, width=220)
        right.pack(side="left", fill="y", padx=(6,0))
        right.pack_propagate(False)

        # Properties
        tk.Label(right, text="PROPERTIES", font=FONT_SM, fg=ACCENT, bg=BG).pack(anchor="w", pady=(4,2))
        prop_outer = tk.Frame(right, bg=BORDER, bd=1)
        prop_outer.pack(fill="both", expand=True)

        prop_canvas = tk.Canvas(prop_outer, bg=BG2, highlightthickness=0)
        prop_vsb    = tk.Scrollbar(prop_outer, orient="vertical", command=prop_canvas.yview,
                                   bg=BG2, troughcolor=BG2, bd=0, width=8)
        prop_canvas.configure(yscrollcommand=prop_vsb.set)
        prop_vsb.pack(side="right", fill="y")
        prop_canvas.pack(fill="both", expand=True)

        self._prop_frame = tk.Frame(prop_canvas, bg=BG2)
        self._prop_frame_id = prop_canvas.create_window((0,0), window=self._prop_frame, anchor="nw")

        def _prop_configure(event):
            prop_canvas.configure(scrollregion=prop_canvas.bbox("all"))
            prop_canvas.itemconfig(self._prop_frame_id, width=event.width)
        prop_canvas.bind("<Configure>", _prop_configure)
        self._prop_frame.bind("<Configure>", lambda e: prop_canvas.configure(scrollregion=prop_canvas.bbox("all")))
        prop_canvas.bind("<MouseWheel>", lambda e: prop_canvas.yview_scroll(-1*(e.delta//120), "units"))

        # Hierarchy
        tk.Label(right, text="HIERARCHY", font=FONT_SM, fg=ACCENT, bg=BG).pack(anchor="w", pady=(8,2))
        hier_outer = tk.Frame(right, bg=BORDER, bd=1, height=180)
        hier_outer.pack(fill="x")
        hier_outer.pack_propagate(False)

        self._hier_list = tk.Listbox(
            hier_outer, bg=BG2, fg=TEXT, selectbackground=ACCENT,
            font=FONT_SM, bd=0, highlightthickness=0, activestyle="none"
        )
        self._hier_list.pack(fill="both", expand=True)
        self._hier_list.bind("<<ListboxSelect>>", self._hier_select)

        self._redraw()

    # ── Toolbar actions ───────────────────────────────────────────────────────

    def _toggle_grid(self):
        self.grid_enabled = not self.grid_enabled
        self._grid_btn.configure(text=f"Grid: {'ON' if self.grid_enabled else 'OFF'}")
        self._redraw()

    def _toggle_snap(self):
        self.snap_enabled = not self.snap_enabled
        self._snap_btn.configure(
            text=f"Snap: {'ON' if self.snap_enabled else 'OFF'}",
            bg="#7722cc" if self.snap_enabled else "#442288"
        )

    # ── Element management ────────────────────────────────────────────────────

    def add_element(self, etype, elem=None):
        if elem is None:
            cx = snap(CANVAS_W//2 - 60, enabled=self.snap_enabled)
            cy = snap(CANVAS_H//2 - 30, enabled=self.snap_enabled)
            elem = GMElement(etype, cx, cy)

        self.elements.append(elem)
        self._push_undo(("delete", elem))
        self.selected = elem
        self._redraw()
        self._refresh_props()
        self._refresh_hier()

    def delete_selected(self):
        if not self.selected:
            return
        self._delete_elem(self.selected)

    def _delete_elem(self, elem):
        if elem not in self.elements:
            return
        idx = self.elements.index(elem)
        self.elements.remove(elem)
        self._push_undo(("restore", elem, idx))
        if self.selected == elem:
            self.selected = None
        self._redraw()
        self._refresh_props()
        self._refresh_hier()

    def duplicate_selected(self):
        if not self.selected:
            return
        s = self.selected
        new = GMElement(s.etype, s.x + 15, s.y + 15, s.w, s.h)
        new.bg          = s.bg
        new.text        = s.text
        new.text_color  = s.text_color
        new.text_size   = s.text_size
        new.transparency= s.transparency
        new.visible     = s.visible
        new.corner_r    = s.corner_r
        new.image_id    = s.image_id
        new.canvas_w    = s.canvas_w
        new.canvas_h    = s.canvas_h
        self.add_element(s.etype, new)

    def clear_all(self):
        if not self.elements:
            return
        snapshot = list(self.elements)
        self.elements = []
        self.selected = None
        self._push_undo(("restore_all", snapshot))
        self._redraw()
        self._refresh_props()
        self._refresh_hier()

    # ── Undo / Redo ───────────────────────────────────────────────────────────

    def _push_undo(self, action):
        self.undo_stack.append(action)
        self.redo_stack.clear()
        if len(self.undo_stack) > 60:
            self.undo_stack.pop(0)

    def undo(self):
        if not self.undo_stack:
            return
        action = self.undo_stack.pop()
        self._apply_inverse(action, self.redo_stack)
        self._redraw(); self._refresh_props(); self._refresh_hier()

    def redo(self):
        if not self.redo_stack:
            return
        action = self.redo_stack.pop()
        self._apply_inverse(action, self.undo_stack)
        self._redraw(); self._refresh_props(); self._refresh_hier()

    def _apply_inverse(self, action, other_stack):
        kind = action[0]
        if kind == "delete":
            elem = action[1]
            self.elements.append(elem)
            other_stack.append(("delete", elem))
        elif kind == "restore":
            elem, idx = action[1], action[2]
            if elem in self.elements:
                self.elements.remove(elem)
            other_stack.append(("restore", elem, idx))
        elif kind == "restore_all":
            snapshot = action[1]
            prev = list(self.elements)
            self.elements = list(snapshot)
            other_stack.append(("restore_all", prev))
        elif kind == "move":
            elem, ox, oy, nx, ny = action[1], action[2], action[3], action[4], action[5]
            elem.x, elem.y = ox, oy
            other_stack.append(("move", elem, nx, ny, ox, oy))
        elif kind == "resize":
            elem = action[1]
            ox, oy, ow, oh = action[2], action[3], action[4], action[5]
            nx, ny, nw, nh = elem.x, elem.y, elem.w, elem.h
            elem.x, elem.y, elem.w, elem.h = ox, oy, ow, oh
            other_stack.append(("resize", elem, nx, ny, nw, nh))
        elif kind == "prop":
            elem, prop, old_val, new_val = action[1], action[2], action[3], action[4]
            setattr(elem, prop, old_val)
            other_stack.append(("prop", elem, prop, new_val, old_val))
            if self.selected == elem:
                self._refresh_props()

    # ── Mouse interaction ─────────────────────────────────────────────────────

    def _canvas_xy(self, event):
        return event.x, event.y

    def _hit_handle(self, elem, mx, my):
        for name, (x1,y1,x2,y2) in elem.handle_rects().items():
            if x1 <= mx <= x2 and y1 <= my <= y2:
                return name
        return None

    def _on_press(self, event):
        mx, my = self._canvas_xy(event)

        # Check selected element handles first
        if self.selected:
            h = self._hit_handle(self.selected, mx, my)
            if h:
                self._drag_mode  = h
                self._drag_start = (mx, my,
                                    self.selected.x, self.selected.y,
                                    self.selected.w, self.selected.h)
                return

        # Hit test elements back-to-front (topmost first)
        hit = None
        for elem in reversed(self.elements):
            if elem.contains(mx, my):
                hit = elem
                break

        if hit:
            self.selected    = hit
            self._drag_mode  = "move"
            self._drag_start = (mx, my, hit.x, hit.y, hit.w, hit.h)
        else:
            self.selected   = None
            self._drag_mode = None

        self._redraw()
        self._refresh_props()
        self._refresh_hier()

    def _on_drag(self, event):
        if not self._drag_mode or not self._drag_start or not self.selected:
            return
        mx, my = self._canvas_xy(event)
        sx, sy, ox, oy, ow, oh = self._drag_start
        dx, dy = mx - sx, my - sy
        elem = self.selected

        if self._drag_mode == "move":
            elem.x = snap(max(0, min(ox + dx, CANVAS_W - elem.w)), enabled=self.snap_enabled)
            elem.y = snap(max(0, min(oy + dy, CANVAS_H - elem.h)), enabled=self.snap_enabled)

        else:
            h = self._drag_mode
            nx, ny, nw, nh = ox, oy, ow, oh
            if "E" in h: nw = max(20, ow + dx)
            if "S" in h: nh = max(20, oh + dy)
            if "W" in h:
                nw = max(20, ow - dx)
                nx = ox + (ow - nw)
            if "N" in h:
                nh = max(20, oh - dy)
                ny = oy + (oh - nh)
            elem.x = snap(nx, enabled=self.snap_enabled)
            elem.y = snap(ny, enabled=self.snap_enabled)
            elem.w = snap(nw, enabled=self.snap_enabled)
            elem.h = snap(nh, enabled=self.snap_enabled)

        self._redraw()
        # live-update pos/size fields
        self._live_update_props()

    def _on_release(self, event):
        if self._drag_mode and self._drag_start and self.selected:
            elem = self.selected
            sx, sy, ox, oy, ow, oh = self._drag_start
            if self._drag_mode == "move":
                if (ox, oy) != (elem.x, elem.y):
                    self._push_undo(("move", elem, ox, oy, elem.x, elem.y))
            else:
                if (ox,oy,ow,oh) != (elem.x,elem.y,elem.w,elem.h):
                    self._push_undo(("resize", elem, ox, oy, ow, oh))
        self._drag_mode  = None
        self._drag_start = None

    def _on_double(self, event):
        """Double-click to bring element forward in z-order."""
        if self.selected and self.selected in self.elements:
            idx = self.elements.index(self.selected)
            if idx < len(self.elements) - 1:
                self.elements.insert(idx + 1, self.elements.pop(idx))
                self.selected.zindex += 1
                self._redraw()
                self._refresh_hier()

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _redraw(self):
        c = self.canvas
        c.delete("all")

        # Grid
        if self.grid_enabled:
            for x in range(0, CANVAS_W, GRID):
                c.create_line(x, 0, x, CANVAS_H, fill="#3a3a50", width=1)
            for y in range(0, CANVAS_H, GRID):
                c.create_line(0, y, CANVAS_W, y, fill="#3a3a50", width=1)

        # Elements
        for elem in self.elements:
            if not elem.visible:
                continue
            x1, y1, x2, y2 = elem.rect()
            alpha_fill = self._hex_with_alpha(elem.bg, 1.0 - elem.transparency)

            c.create_rectangle(x1, y1, x2, y2,
                                fill=alpha_fill, outline="#888", width=1,
                                tags=("elem", elem.name))

            # label
            label = elem.text if elem.text else f"[{elem.etype}]"
            c.create_text(
                x1 + elem.w//2, y1 + elem.h//2,
                text=label, fill=elem.text_color,
                font=("Consolas", min(elem.text_size, 13)),
                width=elem.w - 6, tags=("elem_text", elem.name)
            )

            # name tag top-left
            c.create_text(x1 + 3, y1 + 3, text=elem.name,
                          fill="#aaaacc", font=("Consolas", 7),
                          anchor="nw", tags=("elem_name",))

            # logic badge — ⚡ top-right if element has wired logic
            if elem.logic:
                badge_colors = {"execCmd": CYAN, "toggle": YELLOW, "raw": "#ab54f7"}
                # use color of first rule type
                bc = badge_colors.get(elem.logic[0]["type"], CYAN)
                c.create_rectangle(x2-18, y1, x2, y1+13, fill=bc, outline="")
                c.create_text(x2-9, y1+6, text=f"⚡{len(elem.logic)}",
                              fill=BG, font=("Consolas", 7, "bold"), anchor="center")

        # Selection highlight + handles
        if self.selected and self.selected in self.elements:
            elem = self.selected
            x1, y1, x2, y2 = elem.rect()
            c.create_rectangle(x1-2, y1-2, x2+2, y2+2,
                                outline=CYAN, width=2, dash=(4,2))
            for hname, (hx1,hy1,hx2,hy2) in elem.handle_rects().items():
                c.create_rectangle(hx1, hy1, hx2, hy2,
                                   fill=CYAN, outline="#ffffff", width=1)

    def _hex_with_alpha(self, hex_color, alpha):
        """Blend hex color with dark bg for transparency simulation."""
        try:
            hex_color = hex_color.lstrip("#")
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            bg_r, bg_g, bg_b = 0x2e, 0x2e, 0x3a
            r = int(r * alpha + bg_r * (1 - alpha))
            g = int(g * alpha + bg_g * (1 - alpha))
            b = int(b * alpha + bg_b * (1 - alpha))
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return hex_color

    # ── Hierarchy ─────────────────────────────────────────────────────────────

    def _refresh_hier(self):
        self._hier_list.delete(0, "end")
        for i, elem in enumerate(reversed(self.elements)):
            marker = "▶ " if elem == self.selected else "   "
            vis    = "" if elem.visible else " [hidden]"
            logic  = f" ⚡{len(elem.logic)}" if elem.logic else ""
            self._hier_list.insert("end", f"{marker}[Z:{elem.zindex}] {elem.name}{vis}{logic}")

    def _hier_select(self, event):
        sel = self._hier_list.curselection()
        if not sel:
            return
        idx = len(self.elements) - 1 - sel[0]
        if 0 <= idx < len(self.elements):
            self.selected = self.elements[idx]
            self._redraw()
            self._refresh_props()

    # ── Properties Panel ──────────────────────────────────────────────────────

    def _refresh_props(self):
        for w in self._prop_frame.winfo_children():
            w.destroy()
        self._prop_widgets.clear()

        if not self.selected:
            tk.Label(self._prop_frame, text="No element selected",
                     font=FONT_SM, fg=SUBTEXT, bg=BG2).pack(pady=20)
            return

        elem = self.selected

        def prop_row(label, attr, conv=str, validate=None):
            row = tk.Frame(self._prop_frame, bg=BG2)
            row.pack(fill="x", pady=1, padx=4)
            tk.Label(row, text=label, font=FONT_SM, fg=SUBTEXT,
                     bg=BG2, width=12, anchor="w").pack(side="left")
            var = tk.StringVar(value=str(getattr(elem, attr)))
            e = tk.Entry(row, textvariable=var, font=FONT_SM,
                         bg=BG3, fg=TEXT, bd=0, insertbackground=CYAN, width=12)
            e.pack(side="left", fill="x", expand=True, ipady=3)
            self._prop_widgets[attr] = var

            def on_change(*_):
                try:
                    val = conv(var.get())
                    if validate and not validate(val):
                        return
                    old = getattr(elem, attr)
                    if old != val:
                        self._push_undo(("prop", elem, attr, old, val))
                        setattr(elem, attr, val)
                        self._redraw()
                        self._refresh_hier()
                except Exception:
                    pass
            var.trace_add("write", on_change)

        def color_row(label, attr):
            row = tk.Frame(self._prop_frame, bg=BG2)
            row.pack(fill="x", pady=1, padx=4)
            tk.Label(row, text=label, font=FONT_SM, fg=SUBTEXT,
                     bg=BG2, width=12, anchor="w").pack(side="left")
            preview = tk.Label(row, bg=getattr(elem, attr), width=3)
            preview.pack(side="left", padx=(0,4))
            var = tk.StringVar(value=getattr(elem, attr))
            e = tk.Entry(row, textvariable=var, font=FONT_SM,
                         bg=BG3, fg=TEXT, bd=0, insertbackground=CYAN, width=10)
            e.pack(side="left", fill="x", expand=True, ipady=3)
            self._prop_widgets[attr] = var

            def on_change(*_):
                val = var.get().strip()
                # accept #rrggbb or r,g,b
                if val.startswith("#") and len(val) == 7:
                    hex_val = val
                elif "," in val:
                    parts = val.split(",")
                    if len(parts) == 3:
                        try:
                            r,g,b = [max(0,min(255,int(x))) for x in parts]
                            hex_val = f"#{r:02x}{g:02x}{b:02x}"
                        except Exception:
                            return
                    else:
                        return
                else:
                    return
                old = getattr(elem, attr)
                if old != hex_val:
                    self._push_undo(("prop", elem, attr, old, hex_val))
                    setattr(elem, attr, hex_val)
                    preview.configure(bg=hex_val)
                    self._redraw()
            var.trace_add("write", on_change)

        def bool_row(label, attr):
            row = tk.Frame(self._prop_frame, bg=BG2)
            row.pack(fill="x", pady=1, padx=4)
            tk.Label(row, text=label, font=FONT_SM, fg=SUBTEXT,
                     bg=BG2, width=12, anchor="w").pack(side="left")
            var = tk.BooleanVar(value=getattr(elem, attr))
            cb = tk.Checkbutton(row, variable=var, bg=BG2,
                                selectcolor=BG3, activebackground=BG2,
                                fg=TEXT, activeforeground=TEXT,
                                highlightthickness=0, cursor="hand2")
            cb.pack(side="left")
            def on_change(*_):
                val = var.get()
                old = getattr(elem, attr)
                if old != val:
                    self._push_undo(("prop", elem, attr, old, val))
                    setattr(elem, attr, val)
                    self._redraw()
                    self._refresh_hier()
            var.trace_add("write", on_change)

        tk.Label(self._prop_frame, text=f"── {elem.etype} ──",
                 font=FONT_SM, fg=ACCENT, bg=BG2).pack(pady=(6,2))

        prop_row("Name",         "name",         str)
        prop_row("X",            "x",            int)
        prop_row("Y",            "y",            int)
        prop_row("Width",        "w",            int, lambda v: v >= 1)
        prop_row("Height",       "h",            int, lambda v: v >= 1)
        prop_row("ZIndex",       "zindex",       int)
        prop_row("CornerR",      "corner_r",     int)
        prop_row("AnchorX",      "anchor_x",     float)
        prop_row("AnchorY",      "anchor_y",     float)
        prop_row("Transparency", "transparency", float, lambda v: 0<=v<=1)
        bool_row("Visible",      "visible")
        color_row("BG Color",    "bg")

        has_text = elem.etype in ("TextLabel","TextButton","TextBox")
        if has_text:
            prop_row("Text",       "text",       str)
            prop_row("TextSize",   "text_size",  int)
            color_row("TextColor", "text_color")

        if elem.etype == "ImageLabel":
            prop_row("ImageID",  "image_id", str)

        if elem.etype == "ScrollingFrame":
            prop_row("CanvasW",  "canvas_w", int)
            prop_row("CanvasH",  "canvas_h", int)

        # Action buttons
        tk.Frame(self._prop_frame, bg=BORDER, height=1).pack(fill="x", pady=6, padx=4)

        btn_row = tk.Frame(self._prop_frame, bg=BG2)
        btn_row.pack(fill="x", padx=4, pady=2)
        tk.Button(btn_row, text="⚡ Logic", font=FONT_SM, bg="#2a2a50", fg=CYAN,
                  bd=0, padx=8, pady=4, cursor="hand2",
                  command=lambda: self._open_logic_list(elem)).pack(side="left", padx=(0,4))
        tk.Button(btn_row, text="⧉ Dup", font=FONT_SM, bg="#2a5aaa", fg=TEXT,
                  bd=0, padx=8, pady=4, cursor="hand2",
                  command=self.duplicate_selected).pack(side="left", padx=(0,4))
        tk.Button(btn_row, text="🗑 Del", font=FONT_SM, bg="#aa2222", fg=TEXT,
                  bd=0, padx=8, pady=4, cursor="hand2",
                  command=self.delete_selected).pack(side="left")

    def _live_update_props(self):
        """Update just x/y/w/h fields during drag without full rebuild."""
        if not self.selected:
            return
        elem = self.selected
        for attr in ("x", "y", "w", "h"):
            if attr in self._prop_widgets:
                try:
                    self._prop_widgets[attr].set(str(getattr(elem, attr)))
                except Exception:
                    pass

    # ── Right-click context menu ──────────────────────────────────────────────

    def _on_right_click(self, event):
        mx, my = event.x, event.y
        # hit-test
        hit = None
        for elem in reversed(self.elements):
            if elem.contains(mx, my):
                hit = elem
                break
        if not hit:
            return
        self.selected = hit
        self._redraw()
        self._refresh_props()
        self._refresh_hier()

        menu = tk.Menu(self.canvas, tearoff=0, bg=BG2, fg=TEXT,
                       activebackground=ACCENT, activeforeground=TEXT,
                       font=FONT_SM, bd=0, relief="flat")

        menu.add_command(label=f"  ⚡  Add Logic  [{hit.name}]",
                         state="disabled", font=(FONT_SM[0], FONT_SM[1], "bold"))
        menu.add_separator()
        menu.add_command(label="  🎯  execCmd  (run addcmd)",
                         command=lambda: self._open_logic_editor(hit, "execCmd"))
        menu.add_command(label="  🔀  Toggle command",
                         command=lambda: self._open_logic_editor(hit, "toggle"))
        menu.add_command(label="  📝  Raw Lua snippet",
                         command=lambda: self._open_logic_editor(hit, "raw"))

        if hit.logic:
            menu.add_separator()
            menu.add_command(label=f"  📋  View wired logic  ({len(hit.logic)} rule(s))",
                             command=lambda: self._open_logic_list(hit))
            menu.add_command(label="  🗑  Clear all logic",
                             command=lambda: self._clear_logic(hit))

        menu.add_separator()
        menu.add_command(label="  ⧉  Duplicate",  command=self.duplicate_selected)
        menu.add_command(label="  🗑  Delete",     command=self.delete_selected)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _open_logic_editor(self, elem, logic_type):
        EVENTS = ["MouseButton1Click", "MouseButton2Click", "MouseEnter", "MouseLeave", "MouseMoved"]
        TYPE_LABELS = {
            "execCmd": "execCmd  —  run an addcmd by name",
            "toggle":  "Toggle  —  toggle a command (bool state)",
            "raw":     "Raw Lua  —  arbitrary code block",
        }
        TYPE_COLORS = {"execCmd": CYAN, "toggle": YELLOW, "raw": "#ab54f7"}

        win = tk.Toplevel()
        win.title(f"Logic Editor — {elem.name}")
        win.configure(bg=BG)
        win.geometry("560x480")
        win.resizable(True, True)
        win.grab_set()

        # Header
        hdr = tk.Frame(win, bg=BG2)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"⚡ LOGIC EDITOR", font=FONT_TITLE, fg=ACCENT, bg=BG2).pack(side="left", padx=12, pady=8)
        tk.Label(hdr, text=TYPE_LABELS[logic_type], font=FONT_SM,
                 fg=TYPE_COLORS[logic_type], bg=BG2).pack(side="left", padx=4, pady=8)
        tk.Label(hdr, text=f"→ {elem.name}", font=FONT_SM, fg=SUBTEXT, bg=BG2).pack(side="right", padx=12, pady=8)

        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=10)

        # Event selector
        tk.Label(body, text="TRIGGER EVENT", font=FONT_SM, fg=ACCENT, bg=BG).pack(anchor="w")
        event_var = tk.StringVar(value="MouseButton1Click")
        event_frame = tk.Frame(body, bg=BG)
        event_frame.pack(fill="x", pady=(2,10))
        for ev in EVENTS:
            tk.Radiobutton(event_frame, text=ev, variable=event_var, value=ev,
                           font=FONT_SM, fg=TEXT, bg=BG, selectcolor=BG2,
                           activebackground=BG, activeforeground=ACCENT,
                           highlightthickness=0, cursor="hand2").pack(side="left", padx=(0,10))

        # Type-specific inputs
        if logic_type == "execCmd":
            tk.Label(body, text="COMMAND NAME  (without prefix)", font=FONT_SM, fg=ACCENT, bg=BG).pack(anchor="w")
            cmd_var = tk.StringVar()
            tk.Entry(body, textvariable=cmd_var, font=FONT_UI, bg=BG2, fg=CYAN,
                     insertbackground=CYAN, bd=0, highlightthickness=1,
                     highlightcolor=ACCENT, highlightbackground=BORDER).pack(fill="x", ipady=5, pady=(2,8))

            tk.Label(body, text="EXTRA ARGS  (optional, space separated)", font=FONT_SM, fg=ACCENT, bg=BG).pack(anchor="w")
            args_var = tk.StringVar()
            tk.Entry(body, textvariable=args_var, font=FONT_UI, bg=BG2, fg=TEXT,
                     insertbackground=CYAN, bd=0, highlightthickness=1,
                     highlightcolor=ACCENT, highlightbackground=BORDER).pack(fill="x", ipady=5, pady=(2,8))

            tk.Label(body, text="PREVIEW", font=FONT_SM, fg=SUBTEXT, bg=BG).pack(anchor="w")
            preview = tk.Label(body, font=("Consolas", 9), fg=CYAN, bg=BG3,
                               anchor="w", padx=8, pady=4, wraplength=500, justify="left")
            preview.pack(fill="x", pady=(2,0))

            def update_preview(*_):
                c = cmd_var.get().strip() or "commandname"
                a = args_var.get().strip()
                arg_str = (' "' + a + '"') if a else ""
                preview.configure(text=f'execCmd("{c}"{arg_str}, speaker)')
            cmd_var.trace_add("write", update_preview)
            args_var.trace_add("write", update_preview)
            update_preview()

            def do_save():
                c = cmd_var.get().strip()
                if not c:
                    messagebox.showwarning("Missing", "Enter a command name.", parent=win)
                    return
                a = args_var.get().strip()
                payload = c + ("|" + a if a else "")
                elem.logic.append({"event": event_var.get(), "type": "execCmd", "payload": payload})
                self._redraw()
                self._refresh_hier()
                win.destroy()

        elif logic_type == "toggle":
            tk.Label(body, text="COMMAND NAME  (the toggle command)", font=FONT_SM, fg=ACCENT, bg=BG).pack(anchor="w")
            cmd_var = tk.StringVar()
            tk.Entry(body, textvariable=cmd_var, font=FONT_UI, bg=BG2, fg=YELLOW,
                     insertbackground=CYAN, bd=0, highlightthickness=1,
                     highlightcolor=ACCENT, highlightbackground=BORDER).pack(fill="x", ipady=5, pady=(2,8))

            tk.Label(body, text="LABEL ON  /  LABEL OFF  (for button text swap, optional)",
                     font=FONT_SM, fg=ACCENT, bg=BG).pack(anchor="w")
            label_frame = tk.Frame(body, bg=BG)
            label_frame.pack(fill="x", pady=(2,8))
            on_var  = tk.StringVar(value="ON")
            off_var = tk.StringVar(value="OFF")
            tk.Label(label_frame, text="ON:", font=FONT_SM, fg=GREEN,  bg=BG).pack(side="left")
            tk.Entry(label_frame, textvariable=on_var,  font=FONT_UI, bg=BG2, fg=GREEN,
                     insertbackground=CYAN, bd=0, width=10,
                     highlightthickness=1, highlightcolor=ACCENT,
                     highlightbackground=BORDER).pack(side="left", ipady=4, padx=(4,14))
            tk.Label(label_frame, text="OFF:", font=FONT_SM, fg="#ff6666", bg=BG).pack(side="left")
            tk.Entry(label_frame, textvariable=off_var, font=FONT_UI, bg=BG2, fg="#ff6666",
                     insertbackground=CYAN, bd=0, width=10,
                     highlightthickness=1, highlightcolor=ACCENT,
                     highlightbackground=BORDER).pack(side="left", ipady=4, padx=(4,0))

            tk.Label(body, text="PREVIEW", font=FONT_SM, fg=SUBTEXT, bg=BG).pack(anchor="w")
            preview = tk.Label(body, font=("Consolas", 9), fg=YELLOW, bg=BG3,
                               anchor="w", padx=8, pady=4, wraplength=500, justify="left")
            preview.pack(fill="x", pady=(2,0))

            def update_preview(*_):
                c = cmd_var.get().strip() or "commandname"
                preview.configure(
                    text=f'local {c}On = false\n'
                         f'{elem.name}.MouseButton1Click:Connect(function()\n'
                         f'    {c}On = not {c}On\n'
                         f'    execCmd("{c}", speaker)\n'
                         f'    {elem.name}.Text = {c}On and "{on_var.get()}" or "{off_var.get()}"\n'
                         f'end)'
                )
            cmd_var.trace_add("write", update_preview)
            on_var.trace_add("write", update_preview)
            off_var.trace_add("write", update_preview)
            update_preview()

            def do_save():
                c = cmd_var.get().strip()
                if not c:
                    messagebox.showwarning("Missing", "Enter a command name.", parent=win)
                    return
                payload = f"{c}|{on_var.get()}|{off_var.get()}"
                elem.logic.append({"event": event_var.get(), "type": "toggle", "payload": payload})
                self._redraw()
                self._refresh_hier()
                win.destroy()

        else:  # raw
            tk.Label(body, text="LUA SNIPPET  (has access to speaker, args, element name as variable)",
                     font=FONT_SM, fg=ACCENT, bg=BG).pack(anchor="w")
            code_box = tk.Text(body, font=("Consolas", 10), bg=BG2, fg="#ab54f7",
                               insertbackground=CYAN, bd=0, height=12,
                               highlightthickness=1, highlightcolor=ACCENT,
                               highlightbackground=BORDER, padx=8, pady=6, wrap="none")
            code_box.pack(fill="both", expand=True, pady=(2,0))
            code_box.insert("1.0",
                f"-- Element: {elem.name}\n"
                f"-- Available: speaker, LocalPlayer, ScreenGui\n"
                f"DoNotif(\"{elem.name} clicked!\", 2)\n"
            )

            def do_save():
                code = code_box.get("1.0", "end-1c").strip()
                if not code:
                    messagebox.showwarning("Missing", "Write some Lua first.", parent=win)
                    return
                elem.logic.append({"event": event_var.get(), "type": "raw", "payload": code})
                self._redraw()
                self._refresh_hier()
                win.destroy()

        # Bottom buttons
        btn_bar = tk.Frame(win, bg=BG2)
        btn_bar.pack(fill="x", side="bottom")
        tk.Button(btn_bar, text="✅  SAVE LOGIC", font=FONT_SM, bg=ACCENT, fg=TEXT,
                  bd=0, padx=14, pady=7, cursor="hand2",
                  command=do_save).pack(side="left", padx=12, pady=8)
        tk.Button(btn_bar, text="✖  CANCEL", font=FONT_SM, bg=BG3, fg=TEXT,
                  bd=0, padx=14, pady=7, cursor="hand2",
                  command=win.destroy).pack(side="left")

    def _open_logic_list(self, elem):
        """View/delete existing logic rules on an element."""
        win = tk.Toplevel()
        win.title(f"Logic Rules — {elem.name}")
        win.configure(bg=BG)
        win.geometry("500x340")
        win.grab_set()

        TYPE_COLORS = {"execCmd": CYAN, "toggle": YELLOW, "raw": "#ab54f7"}

        tk.Label(win, text=f"Logic Rules on  {elem.name}", font=FONT_TITLE,
                 fg=ACCENT, bg=BG).pack(anchor="w", padx=12, pady=(10,4))

        frame = tk.Frame(win, bg=BG)
        frame.pack(fill="both", expand=True, padx=12)

        def refresh():
            for w in frame.winfo_children():
                w.destroy()
            if not elem.logic:
                tk.Label(frame, text="No logic rules.", font=FONT_SM,
                         fg=SUBTEXT, bg=BG).pack(pady=20)
                return
            for i, rule in enumerate(elem.logic):
                row = tk.Frame(frame, bg=BG2)
                row.pack(fill="x", pady=2)
                color = TYPE_COLORS.get(rule["type"], TEXT)
                tk.Label(row, text=f"[{rule['event']}]", font=FONT_SM,
                         fg=SUBTEXT, bg=BG2, width=22, anchor="w").pack(side="left", padx=(6,0))
                tk.Label(row, text=rule["type"], font=FONT_SM,
                         fg=color, bg=BG2, width=10, anchor="w").pack(side="left")
                payload_short = rule["payload"][:40] + ("…" if len(rule["payload"]) > 40 else "")
                tk.Label(row, text=payload_short, font=FONT_SM,
                         fg=TEXT, bg=BG2, anchor="w").pack(side="left", padx=4)
                idx = i
                tk.Button(row, text="🗑", font=FONT_SM, bg="#aa2222", fg=TEXT,
                          bd=0, padx=6, pady=2, cursor="hand2",
                          command=lambda i=idx: (elem.logic.pop(i), refresh(),
                                                 self._redraw(), self._refresh_hier())).pack(side="right", padx=4, pady=2)

        refresh()
        tk.Button(win, text="✖  Close", font=FONT_SM, bg=BG3, fg=TEXT,
                  bd=0, padx=12, pady=6, cursor="hand2",
                  command=win.destroy).pack(side="bottom", pady=8)

    def _clear_logic(self, elem):
        if messagebox.askyesno("Clear Logic", f"Remove all logic from {elem.name}?"):
            elem.logic.clear()
            self._redraw()
            self._refresh_hier()

    # ── Export ────────────────────────────────────────────────────────────────

    def export_lua(self):
        if not self.elements:
            messagebox.showinfo("Empty", "No elements to export.")
            return

        lines = []
        def w(s): lines.append(s)

        has_logic   = any(e.logic for e in self.elements)
        has_toggles = any(r["type"] == "toggle"
                          for e in self.elements for r in e.logic)

        w("-- ════════════════════════════════════════")
        w(f"-- Generated by Zuka Panel GUI Maker")
        w(f"-- Project: {self.proj_name}")
        w("-- ════════════════════════════════════════")
        w("local Players     = game:GetService('Players')")
        w("local LocalPlayer = Players.LocalPlayer")
        if has_logic:
            w("local speaker     = LocalPlayer  -- alias used by logic")
        w("")
        w("local ScreenGui = Instance.new('ScreenGui')")
        w(f"ScreenGui.Name           = '{self.proj_name}'")
        w("ScreenGui.ResetOnSpawn   = false")
        w("ScreenGui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling")
        w("ScreenGui.Parent         = LocalPlayer:WaitForChild('PlayerGui')")
        w("")

        # Emit toggle state variables up-front
        if has_toggles:
            w("-- Toggle states")
            seen_toggles = set()
            for elem in self.elements:
                for rule in elem.logic:
                    if rule["type"] == "toggle":
                        cmd = rule["payload"].split("|")[0]
                        var = f"_tog_{cmd.replace('-','_')}"
                        if var not in seen_toggles:
                            w(f"local {var} = false")
                            seen_toggles.add(var)
            w("")

        # Emit elements
        for elem in self.elements:
            n = elem.name
            w(f"-- {n}")
            w(f"local {n} = Instance.new('{elem.etype}')")
            w(f"{n}.Name                   = '{n}'")
            w(f"{n}.Size                   = UDim2.fromOffset({elem.w}, {elem.h})")
            w(f"{n}.Position               = UDim2.fromOffset({elem.x}, {elem.y})")
            w(f"{n}.AnchorPoint            = Vector2.new({elem.anchor_x}, {elem.anchor_y})")

            try:
                hx = elem.bg.lstrip("#")
                r,g,b = int(hx[0:2],16), int(hx[2:4],16), int(hx[4:6],16)
            except Exception:
                r,g,b = 100,100,180
            w(f"{n}.BackgroundColor3       = Color3.fromRGB({r}, {g}, {b})")
            w(f"{n}.BackgroundTransparency = {elem.transparency}")
            w(f"{n}.BorderSizePixel        = 0")
            w(f"{n}.ZIndex                 = {elem.zindex}")
            w(f"{n}.Visible                = {str(elem.visible).lower()}")

            if elem.etype in ("TextLabel","TextButton","TextBox"):
                safe = elem.text.replace("'", "\\'")
                try:
                    hx2 = elem.text_color.lstrip("#")
                    tr,tg,tb = int(hx2[0:2],16), int(hx2[2:4],16), int(hx2[4:6],16)
                except Exception:
                    tr,tg,tb = 255,255,255
                w(f"{n}.Text                   = '{safe}'")
                w(f"{n}.TextColor3             = Color3.fromRGB({tr}, {tg}, {tb})")
                w(f"{n}.TextSize               = {elem.text_size}")
                w(f"{n}.Font                   = Enum.Font.Gotham")
                w(f"{n}.TextXAlignment         = Enum.TextXAlignment.Left")
                if elem.etype == "TextBox":
                    w(f"{n}.PlaceholderText        = 'Enter text...'")
                    w(f"{n}.ClearTextOnFocus       = false")

            if elem.etype == "ImageLabel":
                img = elem.image_id or "rbxasset://textures/ui/GuiImagePlaceholder.png"
                w(f"{n}.Image     = '{img}'")
                w(f"{n}.ScaleType = Enum.ScaleType.Fit")

            if elem.etype == "ScrollingFrame":
                w(f"{n}.ScrollBarThickness = 6")
                w(f"{n}.CanvasSize         = UDim2.fromOffset({elem.canvas_w}, {elem.canvas_h})")
                w(f"{n}.ScrollingEnabled   = true")

            w(f"do local c = Instance.new('UICorner', {n}) ; c.CornerRadius = UDim.new(0, {elem.corner_r}) end")
            w(f"{n}.Parent = ScreenGui")

            # ── Emit logic connections ────────────────────────────────────────
            if elem.logic:
                w(f"-- Logic wiring for {n}")
                for rule in elem.logic:
                    event   = rule["event"]
                    ltype   = rule["type"]
                    payload = rule["payload"]

                    if ltype == "execCmd":
                        parts   = payload.split("|", 1)
                        cmd     = parts[0].strip()
                        extra   = parts[1].strip() if len(parts) > 1 else ""
                        arg_str = (f', "{extra}"') if extra else ""
                        w(f'{n}.{event}:Connect(function()')
                        w(f'    pcall(execCmd, "{cmd}"{arg_str}, speaker)')
                        w(f'end)')

                    elif ltype == "toggle":
                        parts   = payload.split("|")
                        cmd     = parts[0].strip()
                        on_lbl  = parts[1] if len(parts) > 1 else "ON"
                        off_lbl = parts[2] if len(parts) > 2 else "OFF"
                        var     = f"_tog_{cmd.replace('-','_')}"
                        w(f'{n}.{event}:Connect(function()')
                        w(f'    {var} = not {var}')
                        w(f'    pcall(execCmd, "{cmd}", speaker)')
                        if elem.etype in ("TextLabel","TextButton","TextBox"):
                            w(f'    {n}.Text = {var} and "{on_lbl}" or "{off_lbl}"')
                        w(f'end)')

                    else:  # raw
                        w(f'{n}.{event}:Connect(function()')
                        for line in payload.split("\n"):
                            w(f'    {line}')
                        w(f'end)')

            w("")

        code = "\n".join(lines)

        # Show in popup with copy button
        win = tk.Toplevel()
        win.title("Exported Lua")
        win.configure(bg=BG)
        win.geometry("700x540")

        tk.Label(win, text=f"Generated Lua — {self.proj_name}",
                 font=FONT_TITLE, fg=ACCENT, bg=BG).pack(pady=(10,4))

        out = tk.Text(win, font=("Consolas",10), bg=BG2, fg=TEXT,
                      insertbackground=CYAN, bd=0, wrap="none", padx=8, pady=6)
        out.pack(fill="both", expand=True, padx=10)
        out.insert("1.0", code)
        out.configure(state="disabled")

        btn_row = tk.Frame(win, bg=BG)
        btn_row.pack(fill="x", padx=10, pady=8)

        def do_copy():
            try:
                pyperclip.copy(code)
                messagebox.showinfo("Copied", "Lua code copied to clipboard!")
            except Exception:
                win.clipboard_clear()
                win.clipboard_append(code)
                messagebox.showinfo("Copied", "Copied via fallback.")

        def do_save():
            path = filedialog.asksaveasfilename(
                defaultextension=".lua",
                filetypes=[("Lua files","*.lua"),("All","*.*")],
                initialfile=f"{self.proj_name}.lua"
            )
            if path:
                with open(path,"w",encoding="utf-8") as f:
                    f.write(code)
                messagebox.showinfo("Saved", f"Saved:\n{path}")

        tk.Button(btn_row, text="📋 Copy", font=FONT_SM, bg=CYAN, fg=BG,
                  bd=0, padx=12, pady=5, cursor="hand2", command=do_copy).pack(side="left", padx=(0,8))
        tk.Button(btn_row, text="💾 Save .lua", font=FONT_SM, bg=BG3, fg=TEXT,
                  bd=0, padx=12, pady=5, cursor="hand2", command=do_save).pack(side="left")


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = ZukaCmdBuilder()
    app.mainloop()
