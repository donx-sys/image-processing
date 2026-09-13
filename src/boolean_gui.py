#!/usr/bin/env python3
"""
Boolean Operations on Images — Hands-On GUI
============================================

Load two images, choose a boolean operation, and see the per-pixel
result in a three-panel view.  A similarity report above the matrix
tells you how identical or different the two images actually are.

  ┌──────────┬──────────┬──────────┐
  │  IMAGE A │  IMAGE B │  RESULT  │
  └──────────┴──────────┴──────────┘
  ┌────────────────────────────────┐
  │  SIMILARITY REPORT             │
  ├────────────────────────────────┤
  │  PIXEL MATRIX  (A | B | OUT)   │
  └────────────────────────────────┘

The Result panel has three views:
  Binary result       — the mask produced by the selected operation
  Change overlay      — A dimmed, with pixels that changed in red
  Difference heatmap  — |A − B| rendered as a jet heatmap

Run:  python boolean_gui.py
"""

import csv
import os
import subprocess
import sys
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk

import numpy as np
from PIL import Image, ImageTk
from tabulate import tabulate

try:
    from scipy.ndimage import binary_dilation
    HAVE_SCIPY = True
except ImportError:
    HAVE_SCIPY = False


DEFAULT_REGION = 8
MAX_REGION = 32
DEFAULT_THRESHOLD = 128

OPS = ["AND", "OR", "XOR", "NOT A", "A - B"]
MODES = ["Binary", "Bitwise (8-bit)"]
RESULT_VIEWS = ["Binary result", "Change overlay", "Difference heatmap"]

FOCUS_COLOR = "#ff3860"
REGION_COLOR = "#00e0ff"


# ---------------------------------------------------------------------------
# Back to Menu
# ---------------------------------------------------------------------------

def install_back_button(root):
    if os.environ.get("DIP_LAUNCHED") != "1":
        return

    def go_back():
        main_py = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "main.py")
        if os.path.isfile(main_py):
            subprocess.Popen([sys.executable, main_py])
        root.destroy()

    menubar = tk.Menu(root)
    filemenu = tk.Menu(menubar, tearoff=0)
    filemenu.add_command(label="Back to Menu", command=go_back)
    menubar.add_cascade(label="File", menu=filemenu)
    root.config(menu=menubar)


# ==========================================================================
# Image loading + operations
# ==========================================================================

def load_grayscale_array(path):
    img = Image.open(path)
    img.load()
    return np.array(img.convert("L"), dtype=np.uint8), img.mode


def binarize(arr, threshold):
    return (arr >= threshold).astype(np.uint8)


def apply_binary_op(a, b, op):
    if op == "AND":
        return np.bitwise_and(a, b)
    if op == "OR":
        return np.bitwise_or(a, b)
    if op == "XOR":
        return np.bitwise_xor(a, b)
    if op == "NOT A":
        return (1 - a).astype(np.uint8)
    if op == "A - B":
        return np.bitwise_and(a, 1 - b).astype(np.uint8)
    raise ValueError(f"Unknown operation: {op}")


def apply_bitwise_op(a, b, op):
    if op == "AND":
        return np.bitwise_and(a, b)
    if op == "OR":
        return np.bitwise_or(a, b)
    if op == "XOR":
        return np.bitwise_xor(a, b)
    if op == "NOT A":
        return (255 - a).astype(np.uint8)
    if op == "A - B":
        return np.bitwise_and(a, 255 - b).astype(np.uint8)
    raise ValueError(f"Unknown operation: {op}")


def jet_colormap(t):
    """Map [0,1] floats to a jet-style RGB uint8 image."""
    t = np.clip(t, 0.0, 1.0)
    r = np.clip(1.5 - np.abs(4 * t - 3), 0, 1)
    g = np.clip(1.5 - np.abs(4 * t - 2), 0, 1)
    b = np.clip(1.5 - np.abs(4 * t - 1), 0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


# ==========================================================================
# Application
# ==========================================================================

class BooleanApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Boolean Operations on Images — Hands-On")
        self.root.geometry("1300x900")
        self.root.minsize(1000, 700)

        self.arr_a = None
        self.arr_b_raw = None
        self.arr_b = None
        self.path_a = None
        self.path_b = None
        self.mode_a = None
        self.mode_b = None

        self.bin_a = None
        self.bin_b = None
        self.result_arr = None
        self.result_view = None

        self._photo_a = None
        self._photo_b = None
        self._photo_r = None

        self._panel_layout = {"a": (1.0, 0, 0),
                              "b": (1.0, 0, 0),
                              "r": (1.0, 0, 0)}

        self.focus_px = (0, 0)

        # option vars
        self.mode_var = tk.StringVar(value=MODES[0])
        self.op_var = tk.StringVar(value=OPS[0])
        self.result_view_var = tk.StringVar(value=RESULT_VIEWS[0])
        self.threshold_var = tk.IntVar(value=DEFAULT_THRESHOLD)
        self.region_var = tk.IntVar(value=DEFAULT_REGION)
        self.show_bin_var = tk.BooleanVar(value=True)

        self.mode_var.trace_add("write", lambda *_: self._on_option_change())
        self.op_var.trace_add("write",   lambda *_: self._on_option_change())
        self.threshold_var.trace_add("write",
                                     lambda *_: self._on_option_change())
        self.result_view_var.trace_add("write",
                                       lambda *_: self._redraw())

        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = self.root
        root.grid_rowconfigure(0, weight=0)
        root.grid_rowconfigure(1, weight=1)
        root.grid_rowconfigure(2, weight=0)
        root.grid_columnconfigure(0, weight=1)

        # ---- control bar ----
        bar = tk.Frame(root, bg="#f0f0f0")
        bar.grid(row=0, column=0, sticky="ew")

        tk.Button(bar, text="Load Image A", command=self.load_a
                  ).pack(side=tk.LEFT, padx=4, pady=6)
        tk.Button(bar, text="Load Image B", command=self.load_b
                  ).pack(side=tk.LEFT, padx=4, pady=6)
        tk.Button(bar, text="Swap A ↔ B", command=self.swap
                  ).pack(side=tk.LEFT, padx=4, pady=6)

        tk.Label(bar, text="   Op:").pack(side=tk.LEFT)
        ttk.Combobox(bar, textvariable=self.op_var, state="readonly",
                     width=8, values=OPS
                     ).pack(side=tk.LEFT, padx=2)

        tk.Label(bar, text="   Mode:").pack(side=tk.LEFT)
        ttk.Combobox(bar, textvariable=self.mode_var, state="readonly",
                     width=14, values=MODES
                     ).pack(side=tk.LEFT, padx=2)

        tk.Label(bar, text="   Threshold:").pack(side=tk.LEFT)
        tk.Scale(bar, from_=0, to=255, orient=tk.HORIZONTAL,
                 variable=self.threshold_var, length=120, showvalue=True
                 ).pack(side=tk.LEFT, padx=2)

        tk.Checkbutton(bar, text="Show binarized",
                       variable=self.show_bin_var,
                       command=self._redraw
                       ).pack(side=tk.LEFT, padx=(8, 2))

        tk.Label(bar, text="   Result view:").pack(side=tk.LEFT, padx=(8, 2))
        ttk.Combobox(bar, textvariable=self.result_view_var,
                     state="readonly", width=18, values=RESULT_VIEWS
                     ).pack(side=tk.LEFT, padx=2)

        # second control row: region + save
        bar2 = tk.Frame(root, bg="#f0f0f0")
        bar2.grid(row=0, column=0, sticky="sew")

        tk.Label(bar, text="   Region N:").pack(side=tk.LEFT)
        tk.Spinbox(bar, from_=1, to=MAX_REGION, width=4,
                   textvariable=self.region_var,
                   command=self._update_matrix
                   ).pack(side=tk.LEFT, padx=2)

        tk.Button(bar, text="Save Result", command=self.save_result
                  ).pack(side=tk.LEFT, padx=(12, 4))
        tk.Button(bar, text="Save Matrix CSV", command=self.save_matrix
                  ).pack(side=tk.LEFT, padx=4)

        # ---- main content ----
        main = tk.Frame(root, bg="#0d0d0d")
        main.grid(row=1, column=0, sticky="nsew")
        main.grid_rowconfigure(0, weight=3)
        main.grid_rowconfigure(1, weight=2)
        main.grid_columnconfigure(0, weight=1)

        # top row: three panels
        top = tk.Frame(main, bg="#0d0d0d")
        top.grid(row=0, column=0, sticky="nsew")
        top.grid_rowconfigure(0, weight=1)
        top.grid_columnconfigure(0, weight=1, uniform="trip")
        top.grid_columnconfigure(1, weight=1, uniform="trip")
        top.grid_columnconfigure(2, weight=1, uniform="trip")

        self.canvas_a, self.label_a = self._make_panel(top, 0, "Image A")
        self.canvas_b, self.label_b = self._make_panel(top, 1, "Image B")
        self.canvas_r, self.label_r = self._make_panel(top, 2, "Result")

        # bottom: similarity + matrix
        bottom = tk.Frame(main, bg="#111")
        bottom.grid(row=1, column=0, sticky="nsew")
        bottom.grid_rowconfigure(1, weight=1)
        bottom.grid_columnconfigure(0, weight=1)

        self.similarity_label = tk.Label(
            bottom,
            text="Load both images to see the similarity report.",
            bg="#111", fg="#888",
            font=("Courier", 10),
            anchor="w", justify=tk.LEFT,
            padx=8, pady=6,
        )
        self.similarity_label.grid(row=0, column=0, columnspan=2,
                                   sticky="ew", padx=(8, 0), pady=(8, 4))

        self.matrix_text = tk.Text(
            bottom, bg="#111", fg="#e0e0e0",
            font=("Courier", 10), wrap="none",
            borderwidth=0, highlightthickness=0,
        )
        sb_v = tk.Scrollbar(bottom, orient="vertical",
                            command=self.matrix_text.yview)
        sb_h = tk.Scrollbar(bottom, orient="horizontal",
                            command=self.matrix_text.xview)
        self.matrix_text.configure(yscrollcommand=sb_v.set,
                                   xscrollcommand=sb_h.set)
        self.matrix_text.grid(row=1, column=0, sticky="nsew",
                              padx=(8, 0), pady=(0, 0))
        sb_v.grid(row=1, column=1, sticky="ns", pady=(0, 0))
        sb_h.grid(row=2, column=0, sticky="ew", padx=(8, 0), pady=(0, 8))

        # ---- status bar ----
        self.status = tk.Label(
            root, anchor="w", relief=tk.SUNKEN, bd=1, padx=6, pady=4,
            text="Step 1: Load image A and image B.",
        )
        self.status.grid(row=2, column=0, sticky="ew")

        for c in (self.canvas_a, self.canvas_b, self.canvas_r):
            c.bind("<Configure>", lambda e: self._redraw())
            c.bind("<Button-1>", self._on_canvas_click)

        root.update_idletasks()
        self._update_matrix()
        self._update_similarity()

    def _make_panel(self, parent, col, title):
        frame = tk.Frame(parent, bg="#0d0d0d")
        frame.grid(row=0, column=col, sticky="nsew")
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        label = tk.Label(frame, text=f"{title}:  —",
                         fg="white", bg="#0d0d0d",
                         font=("TkDefaultFont", 12, "bold"))
        label.grid(row=0, column=0, pady=(10, 4))

        canvas = tk.Canvas(frame, bg="#050505",
                           highlightthickness=0, cursor="tcross")
        canvas.grid(row=1, column=0, sticky="nsew")
        return canvas, label

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    def load_a(self):
        path = filedialog.askopenfilename(
            title="Choose image A",
            filetypes=[("Images",
                        "*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff"),
                       ("All files", "*.*")],
        )
        if not path:
            return
        try:
            arr, mode = load_grayscale_array(path)
        except Exception as exc:
            messagebox.showerror("Error", f"Could not load image A:\n{exc}")
            return
        self.arr_a = arr
        self.path_a = path
        self.mode_a = mode
        if self.arr_a is not None:
            self.focus_px = (self.arr_a.shape[1] // 2,
                             self.arr_a.shape[0] // 2)
        self._reset_b_to_match()
        self._after_load(f"A = {os.path.basename(path)}")

    def load_b(self):
        path = filedialog.askopenfilename(
            title="Choose image B",
            filetypes=[("Images",
                        "*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff"),
                       ("All files", "*.*")],
        )
        if not path:
            return
        try:
            arr, mode = load_grayscale_array(path)
        except Exception as exc:
            messagebox.showerror("Error", f"Could not load image B:\n{exc}")
            return
        self.arr_b_raw = arr
        self.path_b = path
        self.mode_b = mode
        self._reset_b_to_match()
        self._after_load(f"B = {os.path.basename(path)}")

    def swap(self):
        if self.arr_a is None and self.arr_b_raw is None:
            return
        self.arr_a, self.arr_b_raw = self.arr_b_raw, self.arr_a
        self.path_a, self.path_b = self.path_b, self.path_a
        self.mode_a, self.mode_b = self.mode_b, self.mode_a
        self._reset_b_to_match()
        self._after_load("Swapped A and B")

    def _reset_b_to_match(self):
        if self.arr_a is None or self.arr_b_raw is None:
            self.arr_b = None
            return
        if self.arr_a.shape == self.arr_b_raw.shape:
            self.arr_b = self.arr_b_raw
            return
        h, w = self.arr_a.shape
        pil_b = Image.fromarray(self.arr_b_raw, mode="L")
        pil_b = pil_b.resize((w, h), Image.LANCZOS)
        self.arr_b = np.array(pil_b, dtype=np.uint8)

    def _after_load(self, msg):
        self._recompute()
        self._update_matrix()
        self._redraw()
        self.status.config(text=msg + "  |  " + self._summary())

    def _summary(self):
        if self.arr_a is None:
            return "no A"
        if self.arr_b is None:
            return "load B to compute result"
        h, w = self.arr_a.shape
        note = ""
        if self.arr_b_raw is not None and self.arr_a.shape != self.arr_b_raw.shape:
            note = "  (B resized to match A)"
        return (f"A {w}×{h}, B {w}×{h}{note}  |  "
                f"mode={self.mode_var.get()}  op={self.op_var.get()}")

    # ------------------------------------------------------------------
    # Recompute
    # ------------------------------------------------------------------
    def _on_option_change(self):
        if self.arr_a is None or self.arr_b is None:
            self._update_similarity()
            return
        self._recompute()
        self._update_matrix()
        self._redraw()
        self.status.config(text=self._summary())

    def _recompute(self):
        if self.arr_a is None or self.arr_b is None:
            self.result_arr = None
            self.result_view = None
            self._update_similarity()
            return

        mode = self.mode_var.get()
        op = self.op_var.get()

        if mode == "Binary":
            thr = int(self.threshold_var.get())
            self.bin_a = binarize(self.arr_a, thr)
            self.bin_b = binarize(self.arr_b, thr)
            self.result_arr = apply_binary_op(self.bin_a, self.bin_b, op)
            self.result_view = Image.fromarray(
                (self.result_arr * 255).astype(np.uint8), mode="L"
            )
        else:
            self.bin_a = None
            self.bin_b = None
            self.result_arr = apply_bitwise_op(self.arr_a, self.arr_b, op)
            self.result_view = Image.fromarray(self.result_arr, mode="L")

        self._update_similarity()

    # ------------------------------------------------------------------
    # Similarity report
    # ------------------------------------------------------------------
    @staticmethod
    def _verdict(sim_pct):
        if sim_pct >= 100.0 - 1e-9:
            return "IDENTICAL — every pixel matches."
        if sim_pct >= 99.0:
            return "Nearly identical — only a tiny fraction of pixels differ."
        if sim_pct >= 95.0:
            return "Very similar — differences are small and localised."
        if sim_pct >= 80.0:
            return "Moderately similar — substantial differences exist."
        if sim_pct >= 50.0:
            return "Different — most pixels disagree."
        return "Very different — almost no pixels match."

    def _update_similarity(self):
        if not hasattr(self, "similarity_label"):
            return

        if self.arr_a is None or self.arr_b is None:
            self.similarity_label.config(
                text="Load both images to see the similarity report.",
                fg="#888")
            return

        mode = self.mode_var.get()
        N = self.arr_a.size

        if mode == "Binary":
            a = self.bin_a
            b = self.bin_b
            if a is None or b is None:
                self.similarity_label.config(
                    text="(binary masks not yet computed)", fg="#888")
                return

            same     = int(np.sum(a == b))
            diff     = int(np.sum(a != b))
            both_on  = int(np.sum((a == 1) & (b == 1)))
            both_off = int(np.sum((a == 0) & (b == 0)))
            only_a   = int(np.sum((a == 1) & (b == 0)))
            only_b   = int(np.sum((a == 0) & (b == 1)))

            sim_pct  = same / N * 100.0
            diff_pct = diff / N * 100.0
            thr = int(self.threshold_var.get())

            if diff == 0:
                banner = "  *** IDENTICAL ***   no pixels differ"
            else:
                banner = (f"  *** CHANGE DETECTED ***   "
                          f"{diff:,} pixels differ ({diff_pct:.3f} %)")

            lines = [
                banner,
                f"SIMILARITY REPORT  —  binary masks at threshold {thr}",
                f"  total pixels          : {N:>12,}",
                f"  pixels that MATCH     : {same:>12,}   ({sim_pct:7.3f} %)",
                f"  pixels that DIFFER    : {diff:>12,}   ({diff_pct:7.3f} %)",
                f"  both foreground  (1,1): {both_on:>12,}",
                f"  both background  (0,0): {both_off:>12,}",
                f"  only A is on     (1,0): {only_a:>12,}",
                f"  only B is on     (0,1): {only_b:>12,}",
                f"  -> {self._verdict(sim_pct)}",
            ]
        else:
            a = self.arr_a.astype(np.int32)
            b = self.arr_b.astype(np.int32)
            ad = np.abs(a - b)

            same     = int(np.sum(a == b))
            diff     = int(np.sum(a != b))
            mad      = float(ad.mean())
            maxd     = int(ad.max())
            mse      = float(((a - b) ** 2).mean())

            sim_pct  = same / N * 100.0
            diff_pct = diff / N * 100.0

            if diff == 0:
                banner = "  *** IDENTICAL ***   every byte matches"
            else:
                banner = (f"  *** DIFFERS ***   "
                          f"{diff:,} pixels differ ({diff_pct:.3f} %), "
                          f"mean |diff| = {mad:.2f}")

            lines = [
                banner,
                "SIMILARITY REPORT  —  8-bit grayscale",
                f"  total pixels          : {N:>12,}",
                f"  pixels that MATCH     : {same:>12,}   ({sim_pct:7.3f} %)",
                f"  pixels that DIFFER    : {diff:>12,}   ({diff_pct:7.3f} %)",
                f"  mean absolute diff    : {mad:>12.4f}",
                f"  max absolute diff     : {maxd:>12}",
                f"  mean squared error    : {mse:>12.4f}",
                f"  -> {self._verdict(sim_pct)}",
            ]

        self.similarity_label.config(text="\n".join(lines), fg="#e0e0e0")

    # ------------------------------------------------------------------
    # Alternative result views
    # ------------------------------------------------------------------
    def _build_change_overlay(self):
        """A dimmed, with pixels that changed between A and B in red."""
        if self.arr_a is None or self.arr_b is None:
            return None

        base = self.arr_a.astype(np.float32) * 0.35 + 20
        base = np.stack([base, base, base], axis=-1)

        mode = self.mode_var.get()
        if mode == "Binary":
            if self.bin_a is None or self.bin_b is None:
                return None
            changed = self.bin_a != self.bin_b
        else:
            diff = np.abs(self.arr_a.astype(np.int32) -
                          self.arr_b.astype(np.int32))
            changed = diff > 5

        if HAVE_SCIPY and changed.any():
            changed = binary_dilation(changed, iterations=1)

        base[changed] = [255, 40, 40]
        return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8),
                               mode="RGB")

    def _build_difference_heatmap(self):
        """|A − B| rendered as a jet heatmap (dark = no change, red = big change)."""
        if self.arr_a is None or self.arr_b is None:
            return None

        diff = np.abs(self.arr_a.astype(np.float32) -
                      self.arr_b.astype(np.float32))
        mx = float(diff.max()) if diff.max() > 0 else 1.0
        norm = diff / mx
        rgb = jet_colormap(norm)
        return Image.fromarray(rgb, mode="RGB")

    # ------------------------------------------------------------------
    # Matrix panel
    # ------------------------------------------------------------------
    def _clamp_region(self):
        if self.arr_a is None:
            return 1
        h, w = self.arr_a.shape
        try:
            n = int(self.region_var.get())
        except (tk.TclError, ValueError):
            n = DEFAULT_REGION
        return max(1, min(n, h, w))

    def _sample_bounds(self):
        n = self._clamp_region()
        h, w = self.arr_a.shape
        x, y = self.focus_px
        top = max(0, min(h - n, y - n // 2))
        left = max(0, min(w - n, x - n // 2))
        return top, left, n

    def _update_matrix(self):
        t = self.matrix_text
        t.delete("1.0", tk.END)

        if self.arr_a is None and self.arr_b is None:
            t.insert(tk.END, "Load image A and image B to begin.\n")
            return
        if self.arr_a is None:
            t.insert(tk.END, "Load image A to begin.\n")
            return
        if self.arr_b is None:
            t.insert(tk.END,
                     "Image A loaded.  Load image B to perform the "
                     "boolean operation.\n")
            return

        top, left, n = self._sample_bounds()

        a_patch = self.arr_a[top:top + n, left:left + n]
        b_patch = self.arr_b[top:top + n, left:left + n]
        r_patch = self.result_arr[top:top + n, left:left + n]

        mode = self.mode_var.get()
        op = self.op_var.get()
        thr = int(self.threshold_var.get())

        t.insert(tk.END,
                 f"Sample region: {n}×{n} centre crop  |  "
                 f"source position (left={left}, top={top})  |  "
                 f"mode={mode}  |  op={op}")
        if mode == "Binary":
            t.insert(tk.END, f"  |  threshold={thr}")
        t.insert(tk.END, "\n\n")

        if mode == "Binary":
            a_rows = [[int(v) for v in row]
                      for row in self.bin_a[top:top + n, left:left + n]]
            b_rows = [[int(v) for v in row]
                      for row in self.bin_b[top:top + n, left:left + n]]
            r_rows = [[int(v) for v in row] for row in r_patch]
            title_a = f"BINARIZED A  (threshold {thr})"
            title_b = f"BINARIZED B  (threshold {thr})"
            title_r = f"RESULT = {op}"
        else:
            a_rows = [[int(v) for v in row] for row in a_patch]
            b_rows = [[int(v) for v in row] for row in b_patch]
            r_rows = [[int(v) for v in row] for row in r_patch]
            title_a = "IMAGE A  (0-255)"
            title_b = "IMAGE B  (0-255)"
            title_r = f"RESULT = {op}"

        headers = [str(c) for c in range(n)]
        table_a = tabulate(a_rows, headers=headers,
                           tablefmt="fancy_grid", showindex=range(n))
        table_b = tabulate(b_rows, headers=headers,
                           tablefmt="fancy_grid", showindex=range(n))
        table_r = tabulate(r_rows, headers=headers,
                           tablefmt="fancy_grid", showindex=range(n))

        lines_a = table_a.split("\n")
        lines_b = table_b.split("\n")
        lines_r = table_r.split("\n")

        wa = max(len(l) for l in lines_a)
        wb = max(len(l) for l in lines_b)
        gap = 4

        title_line = (title_a.center(wa) + " " * gap +
                      title_b.center(wb) + " " * gap +
                      title_r)
        t.insert(tk.END, title_line + "\n\n")

        max_lines = max(len(lines_a), len(lines_b), len(lines_r))
        for i in range(max_lines):
            la = lines_a[i] if i < len(lines_a) else ""
            lb = lines_b[i] if i < len(lines_b) else ""
            lr = lines_r[i] if i < len(lines_r) else ""
            t.insert(tk.END,
                     la.ljust(wa + gap) + lb.ljust(wb + gap) + lr + "\n")

        if mode == "Binary":
            a_show = self.bin_a[top:top + n, left:left + n]
            b_show = self.bin_b[top:top + n, left:left + n]
            t.insert(tk.END, "\n" + "=" * 70 + "\n")
            t.insert(tk.END, f"Region summary  (op = {op})\n")
            t.insert(tk.END, "-" * 70 + "\n")
            t.insert(tk.END,
                     f"  A binarized:  {int(a_show.sum())} of {n*n} "
                     f"pixels are 1 (on)\n")
            t.insert(tk.END,
                     f"  B binarized:  {int(b_show.sum())} of {n*n} "
                     f"pixels are 1 (on)\n")
            t.insert(tk.END,
                     f"  A ≠ B:        "
                     f"{int((a_show.astype(int) - b_show.astype(int) != 0).sum())} "
                     f"pixels differ\n")
            t.insert(tk.END,
                     f"  Result:       {int(r_patch.sum())} of {n*n} "
                     f"pixels are 1 (on)\n")

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def _draw_in_panel(self, canvas, pil_img, key):
        canvas.delete("all")
        cw = canvas.winfo_width()
        ch = canvas.winfo_height()
        if cw < 2 or ch < 2 or pil_img is None:
            self._panel_layout[key] = (1.0, 0, 0)
            return

        iw, ih = pil_img.size
        scale = min(cw / iw, ch / ih, 1.0)
        dw = max(1, int(iw * scale))
        dh = max(1, int(ih * scale))
        x = (cw - dw) // 2
        y = (ch - dh) // 2

        disp = pil_img
        if disp.mode not in ("RGB", "L", "RGBA"):
            a = np.array(disp)
            a = np.clip(a, 0, 255).astype(np.uint8)
            disp = Image.fromarray(a, mode="L" if a.ndim == 2 else "RGB")

        disp = disp.resize((dw, dh), Image.LANCZOS)
        photo = ImageTk.PhotoImage(disp)
        setattr(self, f"_photo_{key}", photo)
        canvas.create_image(x, y, anchor=tk.NW, image=photo)

        self._panel_layout[key] = (scale, x, y)

        if self.arr_a is not None:
            fx, fy = self.focus_px
            mx = x + (fx + 0.5) * scale
            my = y + (fy + 0.5) * scale
            r = 5
            canvas.create_line(mx - r, my, mx + r, my,
                               fill=FOCUS_COLOR, width=2)
            canvas.create_line(mx, my - r, mx, my + r,
                               fill=FOCUS_COLOR, width=2)
            canvas.create_oval(mx - r - 1, my - r - 1,
                               mx + r + 1, my + r + 1,
                               outline=FOCUS_COLOR, width=1)

            top, left, n = self._sample_bounds()
            bx1 = x + left * scale
            by1 = y + top * scale
            bx2 = x + (left + n) * scale
            by2 = y + (top + n) * scale
            canvas.create_rectangle(bx1, by1, bx2, by2,
                                    outline=REGION_COLOR, width=2,
                                    dash=(4, 2))

    def _redraw(self):
        # A
        if self.arr_a is not None:
            if self.mode_var.get() == "Binary" and self.show_bin_var.get():
                thr = int(self.threshold_var.get())
                a_disp = Image.fromarray(
                    (binarize(self.arr_a, thr) * 255).astype(np.uint8),
                    mode="L"
                )
            else:
                a_disp = Image.fromarray(self.arr_a, mode="L")
            self._draw_in_panel(self.canvas_a, a_disp, "a")
            W, H = self.arr_a.shape[1], self.arr_a.shape[0]
            self.label_a.config(text=f"Image A:  {W} × {H} px")
        else:
            self.canvas_a.delete("all")
            self._panel_layout["a"] = (1.0, 0, 0)
            self.label_a.config(text="Image A:  —")

        # B
        if self.arr_b is not None:
            if self.mode_var.get() == "Binary" and self.show_bin_var.get():
                thr = int(self.threshold_var.get())
                b_disp = Image.fromarray(
                    (binarize(self.arr_b, thr) * 255).astype(np.uint8),
                    mode="L"
                )
            else:
                b_disp = Image.fromarray(self.arr_b, mode="L")
            self._draw_in_panel(self.canvas_b, b_disp, "b")
            W, H = self.arr_b.shape[1], self.arr_b.shape[0]
            self.label_b.config(text=f"Image B:  {W} × {H} px")
        else:
            self.canvas_b.delete("all")
            self._panel_layout["b"] = (1.0, 0, 0)
            self.label_b.config(text="Image B:  —")

        # Result
        if self.arr_a is not None and self.arr_b is not None:
            view = self.result_view_var.get()
            if view == "Change overlay":
                display = self._build_change_overlay()
                title = "Result — change overlay (red = changed)"
            elif view == "Difference heatmap":
                display = self._build_difference_heatmap()
                title = "Result — difference heatmap (|A − B|)"
            else:
                display = self.result_view
                op = self.op_var.get()
                mode = self.mode_var.get()
                title = f"Result [{op}]  ({mode})"

            if display is not None:
                self._draw_in_panel(self.canvas_r, display, "r")
                self.label_r.config(text=title)
            else:
                self.canvas_r.delete("all")
                self._panel_layout["r"] = (1.0, 0, 0)
                self.label_r.config(text="Result:  —")
        else:
            self.canvas_r.delete("all")
            self._panel_layout["r"] = (1.0, 0, 0)
            self.label_r.config(text="Result:  —")
            cw = self.canvas_r.winfo_width()
            ch = self.canvas_r.winfo_height()
            if cw > 2 and ch > 2:
                msg = ("Load image A and image B to see the result."
                       if self.arr_a is None or self.arr_b is None
                       else "(no result yet)")
                self.canvas_r.create_text(cw // 2, ch // 2,
                                          text=msg, fill="#666",
                                          font=("TkDefaultFont", 11))

    # ------------------------------------------------------------------
    # Click
    # ------------------------------------------------------------------
    def _on_canvas_click(self, event):
        if self.arr_a is None:
            return
        widget = event.widget
        key = None
        if widget is self.canvas_a:
            key = "a"
        elif widget is self.canvas_b:
            key = "b"
        elif widget is self.canvas_r:
            key = "r"
        if key is None:
            return

        scale, ox, oy = self._panel_layout[key]
        if scale <= 0:
            return
        ix = int((event.x - ox) / scale)
        iy = int((event.y - oy) / scale)
        h, w = self.arr_a.shape
        if 0 <= ix < w and 0 <= iy < h:
            self.focus_px = (ix, iy)
            self._update_matrix()
            self._redraw()

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    def save_result(self):
        if self.arr_a is None or self.arr_b is None:
            messagebox.showinfo("Nothing to save",
                                "Load both images first.")
            return

        view = self.result_view_var.get()
        if view == "Change overlay":
            img = self._build_change_overlay()
            slug = "change"
        elif view == "Difference heatmap":
            img = self._build_difference_heatmap()
            slug = "diffheat"
        else:
            if self.result_view is None:
                messagebox.showinfo("Nothing to save",
                                    "No result computed.")
                return
            img = self.result_view
            op_slug = self.op_var.get().replace(" ", "").replace("-", "minus")
            slug = op_slug + "_" + (
                "bin" if self.mode_var.get() == "Binary" else "bitwise")

        if img is None:
            messagebox.showinfo("Nothing to save", "No image to save.")
            return

        base_a = os.path.splitext(os.path.basename(self.path_a))[0]
        base_b = os.path.splitext(os.path.basename(self.path_b))[0]
        out = os.path.join(os.getcwd(), f"{base_a}_x_{base_b}_{slug}.png")
        img.save(out)
        messagebox.showinfo("Saved", f"Result saved to:\n{out}")

    def save_matrix(self):
        if self.arr_a is None or self.arr_b is None:
            messagebox.showinfo("Nothing to save",
                                "Load both images first.")
            return

        top, left, n = self._sample_bounds()
        a_patch = self.arr_a[top:top + n, left:left + n]
        b_patch = self.arr_b[top:top + n, left:left + n]
        r_patch = self.result_arr[top:top + n, left:left + n]

        mode = self.mode_var.get()
        op = self.op_var.get()

        if mode == "Binary":
            a_show = self.bin_a[top:top + n, left:left + n]
            b_show = self.bin_b[top:top + n, left:left + n]
        else:
            a_show = a_patch
            b_show = b_patch

        base = os.path.splitext(os.path.basename(self.path_a))[0]
        op_slug = op.replace(" ", "").replace("-", "minus")
        mode_slug = "bin" if mode == "Binary" else "bitwise"
        out = os.path.join(os.getcwd(),
                           f"matrix_{base}_{op_slug}_{mode_slug}.csv")

        with open(out, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["row", "col", "A", "B", "result"])
            for r in range(n):
                for c in range(n):
                    writer.writerow([
                        r, c,
                        int(a_show[r, c]),
                        int(b_show[r, c]),
                        int(r_patch[r, c]),
                    ])

        messagebox.showinfo(
            "Saved",
            f"Matrix ({n}×{n}, op={op}) saved to:\n{out}"
        )


def main():
    root = tk.Tk()
    install_back_button(root)
    try:
        BooleanApp(root)
    except Exception:
        traceback.print_exc()
        try:
            messagebox.showerror("Startup error", traceback.format_exc())
        except Exception:
            pass
        return
    root.mainloop()


if __name__ == "__main__":
    main()
