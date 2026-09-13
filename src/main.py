#!/usr/bin/env python3
"""
Hands-On Learning — Digital Image Processing
...
"""

import importlib
import os
import shutil
import subprocess
import sys
import tkinter as tk
import traceback
from tkinter import messagebox


SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DOCS_DIR     = os.path.join(PROJECT_ROOT, "docs")

for path in (SCRIPT_DIR, PROJECT_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)


# ---------------------------------------------------------------------------
# Colour palette and typography
# ---------------------------------------------------------------------------

PAGE   = "#fafafa"
CARD   = "#ffffff"
HOVER  = "#f1f1f2"
RULE   = "#e4e4e7"
TEXT   = "#18181b"
MUTED  = "#71717a"
LINK   = "#2563eb"

FONT_TITLE    = ("TkDefaultFont", 22, "bold")
FONT_SUB      = ("TkDefaultFont", 13)
FONT_HINT     = ("TkDefaultFont", 10)
FONT_SECTION  = ("TkDefaultFont", 13, "bold")
FONT_SUBSECT  = ("TkDefaultFont", 11, "bold")
FONT_ROW      = ("TkDefaultFont", 11)
FONT_ROW_SUB  = ("TkDefaultFont", 9)
FONT_BADGE    = ("Courier", 11, "bold")
FONT_LINK     = ("TkDefaultFont", 10)
FONT_FOOTER   = ("TkDefaultFont", 9)


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------

MENU = [
    ("section", 0, "1. Introduction"),
    ("tool",    1, "1.1", "Understanding Matrix Representation",
                     "An image is a grid of numbers.  See it.",
                     "image_representation.py", "matrix"),

    ("section", 0, "2. Resolutions"),
    ("section", 1, "2.1  Spatial Resolution"),
    ("tool",    2, "2.1.1", "Resize",
                     "Change the number of pixels that cover a scene.",
                     "image_resizer.py", "spatial_resize"),
    ("tool",    2, "2.1.2", "Cropping",
                     "Extract a rectangular region, exactly.",
                     "cropping_gui.py", "spatial_crop"),
    ("section", 1, "2.2  Intensity Resolution"),
    ("tool",    2, "2.2.1", "Intensity Quantization",
                     "Reduce bit depth and watch banding appear.",
                     "intensity_gui.py", "intensity"),

    ("section", 0, "3. Preprocessing"),
    ("tool",    1, "3.1", "Noise Removal",
                     "Add noise, then remove it.  Match filter to noise.",
                     "noise_gui.py", "noise"),
    ("tool",    1, "3.2", "Contrast Enhancement",
                     "Widen the histogram.  Four classic methods.",
                     "contrast_gui.py", "contrast"),
    ("tool",    1, "3.3", "Identifying Information-Rich Areas",
                     "Measure local unpredictability as a heatmap.",
                     "information_gui.py", "information"),

    ("section", 0, "4. Segmentation"),
    ("tool",    1, "4.1", "Segmentation Methods",
                     "Six ways to assign a label to every pixel.",
                     "segmentation_gui.py", "segmentation"),
    ("tool",    1, "4.2", "Boolean Operations on Images",
                     "AND, OR, XOR, and change detection between images.",
                     "boolean_gui.py", "boolean"),
]

CLI_SCRIPTS = set()


# ---------------------------------------------------------------------------
# Launching and docs (unchanged behaviour)
# ---------------------------------------------------------------------------

def launch(script_name):
    path = os.path.join(SCRIPT_DIR, script_name)
    if not os.path.isfile(path):
        messagebox.showerror("Missing file",
                             "Could not find:\n" + path)
        return
    env = os.environ.copy()
    env["DIP_LAUNCHED"] = "1"
    try:
        if script_name in CLI_SCRIPTS:
            _launch_in_terminal(path, env)
        else:
            subprocess.Popen([sys.executable, path],
                             cwd=PROJECT_ROOT, env=env)
    except Exception as exc:
        messagebox.showerror("Launch failed", str(exc))


def _launch_in_terminal(path, env):
    for term, args in [
        ("x-terminal-emulator", ["-e"]),
        ("gnome-terminal", ["--"]),
        ("konsole", ["-e"]),
        ("xfce4-terminal", ["-e"]),
        ("mate-terminal", ["-e"]),
        ("tilix", ["-e"]),
        ("xterm", ["-e"]),
    ]:
        if shutil.which(term):
            subprocess.Popen([term] + args + [sys.executable, path],
                             cwd=PROJECT_ROOT, env=env)
            return
    messagebox.showinfo("Terminal required",
                        os.path.basename(path) + " is a command-line tool.")


def load_doc(docs_key):
    if not docs_key:
        return None, None
    if not os.path.isdir(DOCS_DIR):
        return docs_key, "Documentation folder not found:\n" + DOCS_DIR
    init_py = os.path.join(DOCS_DIR, "__init__.py")
    if not os.path.isfile(init_py):
        return docs_key, "docs/__init__.py is missing."
    target = os.path.join(DOCS_DIR, docs_key + ".py")
    if not os.path.isfile(target):
        try:
            present = sorted(f[:-3] for f in os.listdir(DOCS_DIR)
                             if f.endswith(".py") and f != "__init__.py")
        except Exception:
            present = []
        return docs_key, ("Missing doc file:\n" + target + "\n\nPresent: "
                          + ", ".join(present))
    try:
        mod_name = "docs." + docs_key
        sys.modules.pop(mod_name, None)
        mod = importlib.import_module(mod_name)
        return (getattr(mod, "TITLE", docs_key),
                getattr(mod, "CONTENT", "(no content)"))
    except Exception:
        return docs_key, "Could not import " + target + "\n\n" + traceback.format_exc()


def show_man_page(parent, topic_title, docs_key):
    title, content = load_doc(docs_key)
    if content is None:
        messagebox.showinfo("No docs", "No manual page for this topic.")
        return

    win = tk.Toplevel(parent)
    win.title("Manual — " + (title or topic_title))
    win.geometry("860x720")
    win.minsize(620, 440)
    win.configure(bg=PAGE)

    head = tk.Frame(win, bg=PAGE)
    head.pack(fill=tk.X, padx=28, pady=(22, 8))
    tk.Label(head, text=(title or topic_title),
             fg=TEXT, bg=PAGE, anchor="w",
             font=("TkDefaultFont", 15, "bold")).pack(fill=tk.X)

    tk.Frame(win, height=1, bg=RULE).pack(fill=tk.X, padx=28)

    body_frame = tk.Frame(win, bg=PAGE)
    body_frame.pack(fill=tk.BOTH, expand=True, padx=28, pady=16)

    text = tk.Text(body_frame, wrap="word", borderwidth=0,
                   highlightthickness=0, bg=CARD, fg=TEXT,
                   font=("Courier New", 10),
                   padx=16, pady=16, spacing1=0, spacing2=2)
    sb = tk.Scrollbar(body_frame, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=sb.set)
    text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    sb.pack(side=tk.RIGHT, fill=tk.Y)
    text.insert("1.0", content)
    text.config(state=tk.DISABLED)

    footer = tk.Frame(win, bg=PAGE)
    footer.pack(fill=tk.X, padx=28, pady=(0, 18))
    tk.Button(footer, text="Close", width=10, command=win.destroy,
              relief=tk.FLAT, bg="#e4e4e7", activebackground="#d4d4d8",
              bd=0, highlightthickness=0, padx=12, pady=6
              ).pack(side=tk.RIGHT)

    win.bind("<Escape>", lambda e: win.destroy())
    win.transient(parent)
    win.focus_set()


# ---------------------------------------------------------------------------
# Launcher
# ---------------------------------------------------------------------------

class Launcher:
    def __init__(self, root):
        self.root = root
        self.root.title("Hands-On Learning — Digital Image Processing")
        self.root.geometry("900x700")
        self.root.minsize(720, 520)
        self.root.configure(bg=PAGE)

        self._build()

    # ---------------------------------------------------------------
    def _build(self):
        # ---- header ----
        header = tk.Frame(self.root, bg=PAGE)
        header.pack(fill=tk.X, padx=36, pady=(32, 0))

        tk.Label(header, text="Hands-On Learning",
                 fg=TEXT, bg=PAGE, anchor="w",
                 font=("TkDefaultFont", 24, "bold")).pack(fill=tk.X)

        tk.Label(header, text="Digital Image Processing",
                 fg=MUTED, bg=PAGE, anchor="w",
                 font=("TkDefaultFont", 14)).pack(fill=tk.X, pady=(2, 0))

        tk.Label(header,
                 text="Click a topic to open it.  Click Docs for the manual.",
                 fg=MUTED, bg=PAGE, anchor="w",
                 font=("TkDefaultFont", 10)).pack(fill=tk.X, pady=(16, 0))

        tk.Frame(self.root, height=1, bg=RULE).pack(
            fill=tk.X, padx=36, pady=(16, 0))

        # ---- scrollable body ----
        outer = tk.Frame(self.root, bg=PAGE)
        outer.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(outer, borderwidth=0, highlightthickness=0,
                           bg=PAGE)
        scrollbar = tk.Scrollbar(outer, orient="vertical",
                                 command=canvas.yview)
        inner = tk.Frame(canvas, bg=PAGE)

        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _fit_width(event):
            canvas.itemconfigure(window_id, width=event.width)
        canvas.bind("<Configure>", _fit_width)

        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def on_wheel(event):
            if event.num == 4:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                canvas.yview_scroll(1, "units")
            else:
                canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

        # bind to the whole launcher so wheel works anywhere
        for widget in (canvas, inner, self.root):
            widget.bind("<MouseWheel>", on_wheel, add="+")
            widget.bind("<Button-4>", on_wheel, add="+")
            widget.bind("<Button-5>", on_wheel, add="+")

        # ---- render the menu ----
        for entry in MENU:
            if entry[0] == "section":
                self._add_section(inner, entry[2], entry[1])
            else:
                _, level, badge, title, subtitle, script, docs_key = entry
                self._add_tool(inner, level, badge, title, subtitle,
                               script, docs_key)

        # small bottom spacer
        tk.Frame(inner, bg=PAGE, height=24).pack(fill=tk.X)

        # ---- footer ----
        footer = tk.Frame(self.root, bg=PAGE)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Frame(footer, height=1, bg=RULE).pack(fill=tk.X, padx=36)
        tk.Label(footer,
                 text="Close a tool window to return to this menu.",
                 fg=MUTED, bg=PAGE, anchor="w",
                 font=("TkDefaultFont", 9)
                 ).pack(fill=tk.X, padx=36, pady=10)

    # ---------------------------------------------------------------
    def _add_section(self, parent, title, level):
        if level == 0:
            f = tk.Frame(parent, bg=PAGE)
            f.pack(fill=tk.X, padx=36, pady=(28, 8))
            tk.Label(f, text=title, fg=TEXT, bg=PAGE, anchor="w",
                     font=FONT_SECTION).pack(fill=tk.X)
            tk.Frame(f, height=1, bg=RULE).pack(fill=tk.X, pady=(8, 0))
        else:
            f = tk.Frame(parent, bg=PAGE)
            f.pack(fill=tk.X, padx=(52, 36), pady=(16, 6))
            tk.Label(f, text=title, fg=MUTED, bg=PAGE, anchor="w",
                     font=FONT_SUBSECT).pack(fill=tk.X)

    def _add_tool(self, parent, level, badge, title, subtitle,
                  script, docs_key):
        indent = 40 if level == 1 else 56
        right  = 40

        row = tk.Frame(parent, bg=CARD,
                       highlightbackground=RULE, highlightthickness=1,
                       cursor="hand2")
        row.pack(fill=tk.X, padx=(indent, right), pady=3)
        row.grid_columnconfigure(1, weight=1)

        # ---- badge ----
        badge_lbl = tk.Label(row, text=badge,
                             fg=MUTED, bg=CARD,
                             font=("Courier", 10, "bold"),
                             width=6, anchor="e", cursor="hand2")
        badge_lbl.grid(row=0, column=0, rowspan=2,
                       padx=(16, 12), pady=12, sticky="nw")

        # ---- title ----
        title_lbl = tk.Label(row, text=title,
                             fg=TEXT, bg=CARD,
                             font=("TkDefaultFont", 11),
                             anchor="w", cursor="hand2")
        title_lbl.grid(row=0, column=1, sticky="ew", pady=(12, 0))

        # ---- subtitle ----
        sub_lbl = tk.Label(row, text=subtitle,
                           fg=MUTED, bg=CARD,
                           font=("TkDefaultFont", 9),
                           anchor="w", cursor="hand2")
        sub_lbl.grid(row=1, column=1, sticky="ew", pady=(2, 12))

        # ---- docs: a small outlined button ----
        docs_btn = tk.Label(
            row, text="Docs",
            fg=LINK, bg=CARD,
            font=("TkDefaultFont", 9),
            padx=14, pady=5,
            highlightthickness=1,
            highlightbackground="#d4d4d8",
            highlightcolor="#d4d4d8",
            cursor="hand2",
        )
        docs_btn.grid(row=0, column=2, rowspan=2,
                      padx=(16, 18), pady=12, sticky="e")

        # ---- hover state ----
        state = {"card": False, "docs": False}

        def refresh():
            card_bg = HOVER if state["card"] else CARD
            for w in (row, badge_lbl, title_lbl, sub_lbl):
                w.configure(bg=card_bg)
            if state["docs"]:
                docs_btn.configure(bg="#eef2ff",
                                   highlightbackground=LINK)
            else:
                docs_btn.configure(bg=card_bg,
                                   highlightbackground="#d4d4d8")

        def is_descendant(widget, ancestor):
            w = widget
            while w is not None:
                if w is ancestor:
                    return True
                w = getattr(w, "master", None)
            return False

        # ---- card hover ----
        def on_card_enter(_e):
            state["card"] = True
            refresh()

        def on_card_leave(event):
            x, y = event.x_root, event.y_root
            under = event.widget.winfo_containing(x, y)
            if not is_descendant(under, row):
                state["card"] = False
                state["docs"] = False
                refresh()

        for w in (row, badge_lbl, title_lbl, sub_lbl):
            w.bind("<Enter>", on_card_enter)
            w.bind("<Leave>", on_card_leave)

        # ---- docs button hover ----
        def on_docs_enter(_e):
            # entering the button should also keep the card lit
            state["card"] = True
            state["docs"] = True
            refresh()

        def on_docs_leave(event):
            x, y = event.x_root, event.y_root
            under = event.widget.winfo_containing(x, y)
            if not is_descendant(under, docs_btn):
                state["docs"] = False
                refresh()

        docs_btn.bind("<Enter>", on_docs_enter)
        docs_btn.bind("<Leave>", on_docs_leave)

        # ---- clicks ----
        def open_tool(_e=None):
            launch(script)

        def open_docs(_e=None):
            show_man_page(self.root, title, docs_key)
            return "break"

        for w in (row, badge_lbl, title_lbl, sub_lbl):
            w.bind("<Button-1>", open_tool)

        docs_btn.bind("<Button-1>", open_docs)


# ---------------------------------------------------------------------------

def _startup_diagnostic():
    print("main.py running from :", os.path.abspath(__file__))
    print("project root         :", PROJECT_ROOT)
    print("docs folder          :", DOCS_DIR)
    print("docs folder exists   :", os.path.isdir(DOCS_DIR))
    if os.path.isdir(DOCS_DIR):
        present = sorted(f for f in os.listdir(DOCS_DIR) if f.endswith(".py"))
        print("files in docs/       :", present or "(none)")
    print()


def main():
    _startup_diagnostic()

    root = tk.Tk()

    def on_error(exc_type, exc_value, exc_tb):
        msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        print(msg, file=sys.stderr)
        try:
            messagebox.showerror("Unhandled error", msg)
        except Exception:
            pass

    root.report_callback_exception = on_error
    Launcher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
