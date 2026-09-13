#!/usr/bin/env python3
"""
Intensity Resolution — Hands-On GUI (with Pixel Matrix)
=======================================================

Load an image, see how many bits each colour channel actually uses,
quantize it down to a target bit depth (1-16), and inspect the result
both as an image AND as an explicit numeric matrix.

Layout
------
  [ control bar: Load / target bits / Quantize / Save / Reset ]
  ┌─────────────────────┬─────────────────────┐
  │  ORIGINAL           │  QUANTIZED          │
  │  (with zoom slider) │  (with zoom slider) │
  ├─────────────────────┴─────────────────────┤
  │  [ Analysis ]  [ Pixel Matrix ]   <- tabs │
  │  (scrollable text in each tab)             │
  └────────────────────────────────────────────┘
  [ status bar ]

The Pixel Matrix tab shows an NxN centre crop of the CURRENT state
(quantized if Quantize has been run, source otherwise) and offers:
  * Save Matrix CSV      -- values in 0..2^b-1, Excel/Sheets friendly
  * Save Crop PNG        -- the NxN patch, NEAREST-upscaled, blocky

Run:  python intensity_gui.py
"""

import csv
import os
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
from PIL import Image, ImageTk
from tabulate import tabulate


MAX_BITS       = 16
DEFAULT_TARGET = 4
DEFAULT_REGION = 8
DEFAULT_CROP_SIZE = 400
NEAREST_SCALE  = 8        # block size for the saved crop


# ==========================================================================
# Analysis
# ==========================================================================

def natural_bits(arr):
    """Bit depth implied by the array's dtype."""
    if arr.dtype == np.uint8:
        return 8
    if arr.dtype == np.uint16:
        return 16
    return max(1, int(arr.max()).bit_length())


def analyse(arr):
    """Per-channel analysis of an image array.

    Returns {channel_name: {'min','max','distinct','bits'}}
    """
    if arr.ndim == 2:
        channels = {"Gray": arr}
    else:
        names = ["R", "G", "B", "A"][:arr.shape[2]]
        channels = {name: arr[..., i] for i, name in enumerate(names)}

    report = {}
    for name, chan in channels.items():
        mx = int(chan.max())
        report[name] = {
            "min": int(chan.min()),
            "max": mx,
            "distinct": int(np.unique(chan).size),
            "bits": max(1, mx.bit_length()),
        }
    return report


# ==========================================================================
# Quantization + display helpers
# ==========================================================================

def quantize_array(arr, src_bits, dst_bits):
    """Bit-truncation from src_bits to dst_bits."""
    if dst_bits >= src_bits:
        return arr.copy()
    shift = src_bits - dst_bits
    return (arr >> shift).astype(arr.dtype)


def stretch_to_8bit(arr):
    """Rescale any integer array to 0..255 for display only."""
    if arr.dtype == np.uint8:
        return arr
    mn, mx = int(arr.min()), int(arr.max())
    if mx == mn:
        return np.zeros_like(arr, dtype=np.uint8)
    scaled = (arr.astype(np.float32) - mn) * 255.0 / (mx - mn)
    return scaled.astype(np.uint8)


def quantized_to_view(arr, dst_bits):
    """Map quantized values 0..2^b-1 back to 0..255 for display only."""
    max_val = (1 << dst_bits) - 1
    if max_val == 0:
        return np.zeros_like(arr, dtype=np.uint8)
    scaled = (arr.astype(np.uint32) * 255) // max_val
    return scaled.astype(np.uint8)


def crop_center(arr, n):
    """NxN centre crop."""
    h, w = arr.shape[:2]
    n = max(1, min(n, h, w))
    top = (h - n) // 2
    left = (w - n) // 2
    return arr[top:top + n, left:left + n], top, left


# ==========================================================================
# The application
# ==========================================================================

class IntensityApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Intensity Resolution — Hands-On (with Matrix)")
        self.root.geometry("1280x900")
        self.root.minsize(1000, 700)

        # ---- source & state ----
        self.img = None
        self.src_path = None
        self.src_arr = None
        self.src_bits = 8
        self.analysis = None

        self.quantized_arr = None
        self.quantized_view = None
        self.target = None

        # ---- Tk refs ----
        self._photo_orig = None
        self._photo_res = None

        # ---- zoom ----
        self.zoom = tk.IntVar(value=1)

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = self.root
        root.grid_rowconfigure(0, weight=0)   # control bar
        root.grid_rowconfigure(1, weight=1)   # main content
        root.grid_rowconfigure(2, weight=0)   # status bar
        root.grid_columnconfigure(0, weight=1)

        # ------------------------------------------------- control bar
        bar = tk.Frame(root, bg="#f0f0f0")
        bar.grid(row=0, column=0, sticky="ew")

        tk.Button(bar, text="Load Image", command=self.load_image
                  ).pack(side=tk.LEFT, padx=4, pady=6)

        tk.Label(bar, text="  Target bits (1–16):").pack(side=tk.LEFT)
        self.target_var = tk.IntVar(value=DEFAULT_TARGET)
        tk.Spinbox(bar, from_=1, to=MAX_BITS, width=4,
                   textvariable=self.target_var).pack(side=tk.LEFT, padx=2)

        tk.Button(bar, text="Quantize", command=self.quantize
                  ).pack(side=tk.LEFT, padx=8)
        tk.Button(bar, text="Save Quantized", command=self.save_image
                  ).pack(side=tk.LEFT, padx=4)
        tk.Button(bar, text="Reset", command=self.reset
                  ).pack(side=tk.LEFT, padx=4)

        tk.Label(bar, text="   Region N:").pack(side=tk.LEFT)
        self.region_var = tk.IntVar(value=DEFAULT_REGION)
        tk.Spinbox(bar, from_=1, to=64, width=4, textvariable=self.region_var,
                   command=self._update_matrix).pack(side=tk.LEFT, padx=2)

        tk.Label(bar, text="   Zoom:").pack(side=tk.LEFT, padx=(10, 2))
        tk.Scale(bar, from_=1, to=16, orient=tk.HORIZONTAL,
                 variable=self.zoom, length=140,
                 command=lambda e: self._redraw()).pack(side=tk.LEFT)

        # ------------------------------------------------- main content
        main = tk.Frame(root, bg="#0d0d0d")
        main.grid(row=1, column=0, sticky="nsew")
        main.grid_rowconfigure(0, weight=3)   # image pair
        main.grid_rowconfigure(1, weight=2)   # notebook
        main.grid_columnconfigure(0, weight=1)

        # ---- top row: two image panels ----
        top_pair = tk.Frame(main, bg="#0d0d0d")
        top_pair.grid(row=0, column=0, sticky="nsew")
        top_pair.grid_rowconfigure(0, weight=1)
        top_pair.grid_columnconfigure(0, weight=1, uniform="pair")
        top_pair.grid_columnconfigure(1, weight=1, uniform="pair")

        # Left
        left = tk.Frame(top_pair, bg="#0d0d0d")
        left.grid(row=0, column=0, sticky="nsew")
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        self.orig_label = tk.Label(left, text="Original:  —",
                                   fg="white", bg="#0d0d0d",
                                   font=("TkDefaultFont", 12, "bold"))
        self.orig_label.grid(row=0, column=0, pady=(10, 4))

        self.orig_canvas = tk.Canvas(left, bg="#050505",
                                     highlightthickness=0)
        self.orig_canvas.grid(row=1, column=0, sticky="nsew")

        # Right
        right = tk.Frame(top_pair, bg="#0d0d0d")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self.res_label = tk.Label(right, text="Quantized:  —",
                                  fg="white", bg="#0d0d0d",
                                  font=("TkDefaultFont", 12, "bold"))
        self.res_label.grid(row=0, column=0, pady=(10, 4))

        self.res_canvas = tk.Canvas(right, bg="#050505",
                                    highlightthickness=0)
        self.res_canvas.grid(row=1, column=0, sticky="nsew")

        # ---- bottom: tabbed (Analysis | Pixel Matrix) ----
        nb = ttk.Notebook(main)
        nb.grid(row=1, column=0, sticky="nsew")

        # Tab 1: Analysis
        tab_analysis = tk.Frame(nb, bg="#111")
        tab_analysis.grid_rowconfigure(0, weight=1)
        tab_analysis.grid_columnconfigure(0, weight=1)
        nb.add(tab_analysis, text="Analysis")

        self.analysis_text = tk.Text(
            tab_analysis, bg="#111", fg="#e0e0e0",
            font=("Courier", 10), wrap="none",
            borderwidth=0, highlightthickness=0,
        )
        sb1 = tk.Scrollbar(tab_analysis, orient="vertical",
                           command=self.analysis_text.yview)
        self.analysis_text.configure(yscrollcommand=sb1.set)
        self.analysis_text.grid(row=0, column=0, sticky="nsew",
                                padx=(8, 0), pady=8)
        sb1.grid(row=0, column=1, sticky="ns", pady=8)

        # Tab 2: Pixel Matrix
        tab_matrix = tk.Frame(nb, bg="#111")
        tab_matrix.grid_rowconfigure(0, weight=1)
        tab_matrix.grid_columnconfigure(0, weight=1)
        nb.add(tab_matrix, text="Pixel Matrix")

        # toolbar for the matrix tab
        matbar = tk.Frame(tab_matrix, bg="#1a1a1a")
        matbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        tk.Button(matbar, text="Save Matrix CSV",
                  command=self.save_matrix_csv
                  ).pack(side=tk.LEFT, padx=4, pady=4)
        tk.Button(matbar, text="Save Crop PNG (NEAREST ×%d)" % NEAREST_SCALE,
                  command=self.save_crop_png
                  ).pack(side=tk.LEFT, padx=4, pady=4)
        tk.Button(matbar, text="Refresh",
                  command=self._update_matrix
                  ).pack(side=tk.LEFT, padx=4, pady=4)
        self.matrix_state = tk.Label(
            matbar, text="(no image)", fg="#888", bg="#1a1a1a",
            font=("TkDefaultFont", 9, "italic"),
        )
        self.matrix_state.pack(side=tk.LEFT, padx=12)

        self.matrix_text = tk.Text(
            tab_matrix, bg="#111", fg="#e0e0e0",
            font=("Courier", 10), wrap="none",
            borderwidth=0, highlightthickness=0,
        )
        sb2 = tk.Scrollbar(tab_matrix, orient="vertical",
                           command=self.matrix_text.yview)
        sbh = tk.Scrollbar(tab_matrix, orient="horizontal",
                           command=self.matrix_text.xview)
        self.matrix_text.configure(yscrollcommand=sb2.set,
                                   xscrollcommand=sbh.set)
        self.matrix_text.grid(row=1, column=0, sticky="nsew",
                              padx=(8, 0), pady=(0, 8))
        sb2.grid(row=1, column=1, sticky="ns", pady=(0, 8))
        sbh.grid(row=2, column=0, sticky="ew", padx=(8, 0), pady=(0, 8))

        # ------------------------------------------------- status bar
        self.status = tk.Label(
            root, anchor="w", relief=tk.SUNKEN, bd=1, padx=6, pady=4,
            text="Step 1: Load an image.",
        )
        self.status.grid(row=2, column=0, sticky="ew")

        # Canvas resize hooks
        self.orig_canvas.bind("<Configure>", lambda e: self._redraw())
        self.res_canvas.bind("<Configure>",  lambda e: self._redraw())

        root.update_idletasks()
        self._show_analysis()
        self._update_matrix()

    # ------------------------------------------------------------------
    # Image loading
    # ------------------------------------------------------------------
    def load_image(self):
        path = filedialog.askopenfilename(
            title="Choose an image",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        try:
            img = Image.open(path)
            img.load()
        except Exception as exc:
            messagebox.showerror("Error", f"Could not open image:\n{exc}")
            return

        try:
            arr = np.array(img)
            if arr.dtype == np.uint8 and arr.ndim in (2, 3):
                self.img = img if img.mode in ("L", "RGB") else img.convert("RGB")
            else:
                self.img = img.convert("RGB")
            self.src_arr = np.array(self.img)
        except Exception as exc:
            messagebox.showerror("Error", f"Could not process image:\n{exc}")
            return

        self.src_bits = natural_bits(self.src_arr)
        self.src_path = path
        self.quantized_arr = None
        self.quantized_view = None
        self.target = None
        self.analysis = analyse(self.src_arr)

        W, H = self.img.size
        self.orig_label.config(
            text=f"Original:  {W} × {H} px   [{self.src_bits}-bit]"
        )
        self.res_label.config(text="Quantized:  —")
        self.status.config(
            text=f"Loaded {os.path.basename(path)}.  "
                 f"Analyse below, then pick a target bit depth."
        )

        self._show_analysis()
        self._update_matrix()
        self._redraw()

    # ------------------------------------------------------------------
    # Analysis tab
    # ------------------------------------------------------------------
    def _show_analysis(self):
        t = self.analysis_text
        t.delete("1.0", tk.END)
        if self.analysis is None:
            return

        W, H = self.img.size
        t.insert(tk.END,
                 f"Image     : {os.path.basename(self.src_path)}\n"
                 f"Size      : {W} × {H} px\n"
                 f"Container : {self.src_arr.dtype}  "
                 f"({self.src_bits}-bit per channel)\n\n")

        t.insert(tk.END, "Bits required per channel (based on max value):\n")
        t.insert(tk.END, "-" * 62 + "\n")
        t.insert(tk.END,
                 f"  {'channel':<8}{'min':>8}{'max':>8}"
                 f"{'distinct':>12}{'bits':>10}\n")
        t.insert(tk.END,
                 f"  {'-'*8}{'-'*8:>8}{'-'*8:>8}{'-'*12:>12}{'-'*10:>10}\n")

        for name, info in self.analysis.items():
            t.insert(tk.END,
                     f"  {name:<8}{info['min']:>8}{info['max']:>8}"
                     f"{info['distinct']:>12}{info['bits']:>10}\n")

        highest = max(i["bits"] for i in self.analysis.values())
        t.insert(tk.END, "\n")
        t.insert(tk.END,
                 f"Highest intensity resolution across channels: "
                 f"{highest} bits\n")
        t.insert(tk.END, "-" * 62 + "\n\n")
        t.insert(tk.END,
                 f"Enter a target bit depth (1-{MAX_BITS}) above, then "
                 f"click Quantize.\n"
                 f"Quantization keeps only the top `target` bits of every "
                 f"pixel and discards the rest.\n")

    def _show_quantization_report(self, target):
        t = self.analysis_text
        t.delete("1.0", tk.END)

        src_bits = self.src_bits
        step = 1 << max(0, src_bits - target)
        max_out = (1 << target) - 1
        max_err = step // 2 if step > 1 else 0

        t.insert(tk.END,
                 f"Quantization:  {src_bits}-bit -> {target}-bit\n")
        t.insert(tk.END, "-" * 62 + "\n\n")
        t.insert(tk.END, f"  Source value range  :  0 - {2**src_bits - 1}\n")
        t.insert(tk.END, f"  Output value range  :  0 - {max_out}\n")
        t.insert(tk.END, f"  Output levels       :  {2 ** target}\n")
        t.insert(tk.END,
                 f"  Step size (source)  :  {step} stored values "
                 f"collapse to 1 output value\n")
        t.insert(tk.END,
                 f"  Max quantization err:  +/-{max_err} source levels\n\n")

        if target < src_bits:
            t.insert(tk.END, "Per-channel effect on the maximum value:\n")
            t.insert(tk.END, "-" * 62 + "\n")
            t.insert(tk.END,
                     f"  {'channel':<8}{'src max':>12}"
                     f"{'>> shift':>12}{'out max':>12}\n")
            for name, info in self.analysis.items():
                out_max = info["max"] >> (src_bits - target)
                t.insert(tk.END,
                         f"  {name:<8}{info['max']:>12}"
                         f"{'>>' + str(src_bits - target):>12}"
                         f"{out_max:>12}\n")
        else:
            t.insert(tk.END,
                     "Target >= source bit depth - image passes through "
                     "unchanged.\n")

        t.insert(tk.END, "\n")
        t.insert(tk.END,
                 "Note: the right-hand preview has been contrast-stretched "
                 "back to 0-255 for viewing.\n"
                 f"The in-memory array holds the true quantized values "
                 f"(0-{max_out}).\n")

    # ------------------------------------------------------------------
    # Pixel Matrix tab
    # ------------------------------------------------------------------
    def _update_matrix(self):
        """Refresh the matrix tab with the current NxN sample AND the
        original (source) values side by side, so the collapse is visible."""
        t = self.matrix_text
        if t is None:
            return
        t.delete("1.0", tk.END)

        if self.src_arr is None:
            t.insert(tk.END, "Load an image first.\n")
            if hasattr(self, "matrix_state"):
                self.matrix_state.config(text="(no image)")
            return

        # ---- region size ----
        h, w = self.src_arr.shape[:2]
        try:
            n = int(self.region_var.get())
        except (tk.TclError, ValueError):
            n = DEFAULT_REGION
        n = max(1, min(n, h, w))

        # ---- source patch ----
        src_patch, top, left = crop_center(self.src_arr, n)
        src_depth = self.src_bits
        src_max = (1 << src_depth) - 1

        # ---- quantized patch (same region) ----
        if self.quantized_arr is not None:
            q_patch, _, _ = crop_center(self.quantized_arr, n)
            q_depth = self.target
            q_max = (1 << q_depth) - 1
        else:
            q_patch = None
            q_depth = None
            q_max = None

        # ---- header ----
        t.insert(tk.END,
                 f"NxN = {n}x{n} centre crop  |  source position "
                 f"(left={left}, top={top})\n\n")

        # ---- build both tables ----
        src_rows = self._array_to_rows(src_patch)
        headers = [str(c) for c in range(n)]
        src_table = tabulate(src_rows, headers=headers,
                             tablefmt="fancy_grid", showindex=range(n))

        if q_patch is not None:
            q_rows = self._array_to_rows(q_patch)
            q_table = tabulate(q_rows, headers=headers,
                               tablefmt="fancy_grid", showindex=range(n))

            src_lines = src_table.split("\n")
            q_lines = q_table.split("\n")
            src_block_w = max(len(line) for line in src_lines)

            # Column titles above each table
            left_title  = f"SOURCE  ({src_depth}-bit)   values 0-{src_max}"
            right_title = f"QUANTIZED  ({q_depth}-bit)   values 0-{q_max}"
            t.insert(tk.END, left_title.ljust(src_block_w + 4)
                            + right_title + "\n")
            t.insert(tk.END, "\n")

            # Zip the two tables line by line
            for i in range(max(len(src_lines), len(q_lines))):
                s = src_lines[i] if i < len(src_lines) else ""
                q = q_lines[i] if i < len(q_lines) else ""
                t.insert(tk.END, s.ljust(src_block_w + 4) + q + "\n")

            # ---- difference statistics ----
            diff = src_patch.astype(np.int32) - q_patch.astype(np.int32)
            absd = np.abs(diff)

            src_distinct = int(np.unique(src_patch).size)
            q_distinct   = int(np.unique(q_patch).size)
            collapse     = src_distinct / q_distinct if q_distinct else 0.0

            t.insert(tk.END, "\n" + "=" * 70 + "\n")
            t.insert(tk.END, "Difference  (source − quantized)\n")
            t.insert(tk.END, "-" * 70 + "\n")
            t.insert(tk.END, f"  max  |error|       : {int(absd.max())}\n")
            t.insert(tk.END, f"  mean |error|       : {float(absd.mean()):.2f}\n")
            t.insert(tk.END, f"  distinct source    : {src_distinct}\n")
            t.insert(tk.END, f"  distinct quantized : {q_distinct}\n")
            t.insert(tk.END,
                     f"  collapse           : {collapse:.2f} source values "
                     f"per output value\n")

            if hasattr(self, "matrix_state"):
                self.matrix_state.config(
                    text=f"source {src_depth}-bit  |  quantized {q_depth}-bit  "
                         f"|  {n}×{n}"
                )
        else:
            # No quantization yet — just show the source
            t.insert(tk.END,
                     f"SOURCE  ({src_depth}-bit)   values 0-{src_max}\n\n")
            t.insert(tk.END, src_table)
            t.insert(tk.END,
                     "\n\nQuantize the image to see it side by side with "
                     "the original values here.\n")

            if hasattr(self, "matrix_state"):
                self.matrix_state.config(
                    text=f"source {src_depth}-bit  |  {n}×{n}   "
                         f"(quantize to compare)"
                )

    def _array_to_rows(self, patch):
        """Convert an NxN patch into rows of cells suitable for tabulate."""
        n = patch.shape[0]
        if patch.ndim == 2:
            # Grayscale — one integer per cell
            return [[int(v) for v in row] for row in patch]
        # RGB — one "(R,G,B)" string per cell
        return [
            [f"({int(patch[r, c, 0])},{int(patch[r, c, 1])},"
             f"{int(patch[r, c, 2])})"
             for c in range(n)]
            for r in range(n)
        ]
    # ------------------------------------------------------------------
    # Quantization
    # ------------------------------------------------------------------
    def quantize(self):
        if self.src_arr is None:
            messagebox.showinfo("No image", "Load an image first.")
            return

        try:
            target = int(self.target_var.get())
        except (tk.TclError, ValueError):
            messagebox.showerror("Bad target", "Target bits must be an integer.")
            return
        if target < 1 or target > MAX_BITS:
            messagebox.showerror(
                "Bad target",
                f"Target must be between 1 and {MAX_BITS} bits."
            )
            return

        src_bits = self.src_bits
        if target >= src_bits:
            if not messagebox.askyesno(
                "No reduction",
                f"Source is {src_bits}-bit, target is {target}-bit.\n"
                f"Nothing will change.  Continue anyway?"
            ):
                return

        try:
            q = quantize_array(self.src_arr, src_bits, target)
            self.quantized_arr = q
            self.target = target
            view = quantized_to_view(q, target)
            mode = "L" if q.ndim == 2 else "RGB"
            self.quantized_view = Image.fromarray(view, mode=mode)
        except Exception as exc:
            messagebox.showerror("Quantize failed", str(exc))
            return

        W, H = self.img.size
        self.res_label.config(
            text=f"Quantized:  {W} × {H} px   [{target}-bit]"
        )
        self.status.config(
            text=f"Quantized {src_bits}-bit -> {target}-bit.  "
                 f"Step = 2^{src_bits - target} = "
                 f"{1 << max(0, src_bits - target)} stored levels "
                 f"per output level.  Output range 0-{(1 << target) - 1}."
        )
        self._show_quantization_report(target)
        self._update_matrix()
        self._redraw()

    def reset(self):
        if self.src_arr is None:
            return
        self.quantized_arr = None
        self.quantized_view = None
        self.target = None
        self.res_label.config(text="Quantized:  —")
        self.status.config(text="Reset.  Original restored.")
        self._show_analysis()
        self._update_matrix()
        self._redraw()

    # ------------------------------------------------------------------
    # Saving
    # ------------------------------------------------------------------
    def save_image(self):
        if self.quantized_view is None:
            messagebox.showinfo("Nothing to save", "Click Quantize first.")
            return
        base = os.path.splitext(os.path.basename(self.src_path))[0]
        target = self.target
        out = os.path.join(os.getcwd(), f"{base}_quantized_{target}bit.png")
        self.quantized_view.save(out)
        messagebox.showinfo(
            "Saved",
            f"Saved:\n{out}\n\n"
            f"Note: the file stores the contrast-stretched view (0-255) "
            f"so it opens correctly.\n"
            f"The true quantized values (0-{(1 << target) - 1}) are in "
            f"the in-memory array and in the matrix tab."
        )

    def save_matrix_csv(self):
        if self.src_arr is None:
            messagebox.showinfo("No image", "Load an image first.")
            return

        # Determine what to sample
        if self.quantized_arr is not None:
            arr = self.quantized_arr
            tag = f"quantized_{self.target}bit"
        else:
            arr = self.src_arr
            tag = f"source_{self.src_bits}bit"

        h, w = arr.shape[:2]
        try:
            n = int(self.region_var.get())
        except (tk.TclError, ValueError):
            n = DEFAULT_REGION
        n = max(1, min(n, h, w))
        patch, _, _ = crop_center(arr, n)

        base = os.path.splitext(os.path.basename(self.src_path))[0]
        out = os.path.join(os.getcwd(), f"matrix_{base}_{tag}.csv")

        try:
            with open(out, "w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                if patch.ndim == 2:
                    for row in patch:
                        writer.writerow(int(v) for v in row)
                else:
                    writer.writerow(["row", "col", "R", "G", "B"])
                    for r in range(n):
                        for c in range(n):
                            R, G, B = (int(v) for v in patch[r, c, :3])
                            writer.writerow([r, c, R, G, B])
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))
            return

        messagebox.showinfo(
            "Saved",
            f"Matrix ({n}×{n}) saved to:\n{out}\n\n"
            f"Grayscale: rows × columns.\n"
            f"RGB: long format — row, col, R, G, B."
        )

    def save_crop_png(self):
        if self.src_arr is None:
            messagebox.showinfo("No image", "Load an image first.")
            return

        if self.quantized_arr is not None:
            arr = self.quantized_arr
            tag = f"quantized_{self.target}bit"
            depth = self.target
        else:
            arr = self.src_arr
            tag = f"source_{self.src_bits}bit"
            depth = self.src_bits

        h, w = arr.shape[:2]
        try:
            n = int(self.region_var.get())
        except (tk.TclError, ValueError):
            n = DEFAULT_REGION
        n = max(1, min(n, h, w))
        patch, _, _ = crop_center(arr, n)

        # Stretch quantized values to 0-255 for viewing, then upscale
        # with NEAREST so every pixel is a solid block.
        max_out = (1 << depth) - 1
        if max_out == 255:
            display = patch.astype(np.uint8)
        else:
            display = ((patch.astype(np.uint32) * 255) // max_out).astype(np.uint8)

        mode = "L" if display.ndim == 2 else "RGB"
        img = Image.fromarray(display, mode=mode)
        target_size = (n * NEAREST_SCALE, n * NEAREST_SCALE)
        img = img.resize(target_size, Image.NEAREST)

        base = os.path.splitext(os.path.basename(self.src_path))[0]
        out = os.path.join(os.getcwd(), f"crop_{base}_{tag}.png")
        img.save(out)

        messagebox.showinfo(
            "Saved",
            f"Crop saved to:\n{out}\n\n"
            f"Size: {n}×{n} source pixels, upscaled ×{NEAREST_SCALE} "
            f"with NEAREST so each pixel is a solid block.\n"
            f"Values shown: 0-{max_out}  (contrast-stretched to 0-255 "
            f"for display only)."
        )

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def _draw_fitted(self, canvas, pil_img, ref_name):
        canvas.delete("all")
        cw = canvas.winfo_width()
        ch = canvas.winfo_height()
        if cw < 2 or ch < 2 or pil_img is None:
            return

        iw, ih = pil_img.size
        # Base fit so it always shows the whole image; then zoom multiplies
        base = min(cw / iw, ch / ih, 1.0)
        try:
            z = max(1, int(self.zoom.get()))
        except (tk.TclError, ValueError):
            z = 1

        # Only apply zoom when the base fit is already large enough that
        # the zoomed image won't blow past the canvas; simple clamp.
        scale = base
        if base * z * iw <= cw * 4 and base * z * ih <= ch * 4:
            # allow zoom up to a point, but clip to canvas
            scale = min(base * z, cw / iw, ch / ih)
        dw = max(1, int(iw * scale))
        dh = max(1, int(ih * scale))
        x = (cw - dw) // 2
        y = (ch - dh) // 2

        disp = pil_img
        if disp.mode not in ("RGB", "L", "RGBA"):
            a = np.array(disp)
            a = np.clip(a, 0, 255).astype(np.uint8)
            disp = Image.fromarray(a, mode="L" if a.ndim == 2 else "RGB")

        # Use NEAREST when zooming past 1× so students see individual pixels
        resample = Image.NEAREST if z > 1 else Image.LANCZOS
        disp = disp.resize((dw, dh), resample)
        photo = ImageTk.PhotoImage(disp)
        setattr(self, ref_name, photo)
        canvas.create_image(x, y, anchor=tk.NW, image=photo)

    def _redraw(self):
        if self.src_arr is not None:
            try:
                orig_view = Image.fromarray(
                    stretch_to_8bit(self.src_arr),
                    mode="L" if self.src_arr.ndim == 2 else "RGB",
                )
                self._draw_fitted(self.orig_canvas, orig_view, "_photo_orig")
            except Exception:
                traceback.print_exc()

        self._draw_fitted(self.res_canvas, self.quantized_view, "_photo_res")

        if self.quantized_view is None:
            cw = self.res_canvas.winfo_width()
            ch = self.res_canvas.winfo_height()
            if cw > 2 and ch > 2:
                self.res_canvas.create_text(
                    cw // 2, ch // 2,
                    text="(not quantized yet)",
                    fill="#666", font=("TkDefaultFont", 11),
                )


def main():
    root = tk.Tk()
    try:
        IntensityApp(root)
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
