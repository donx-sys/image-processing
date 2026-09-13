#!/usr/bin/env python3
"""
Pixel Bit-Depth Matrix Visualizer — Hands-On GUI
=================================================

Load an image, choose grayscale or RGB, choose 3-bit or 8-bit, and see:

  ┌────────────────────────────┬────────────────────────────┐
  │  GRID OVERLAY              │  PIXEL MATRIX              │
  │  (N×N crop, upscaled,      │  (the numbers, scrollable, │
  │   darkened, grid lines)    │   zoomable via Matrix zoom)│
  └────────────────────────────┴────────────────────────────┘
  [ status bar ]

Each cell in the left grid corresponds to exactly one number on the
right.  The image is darkened so the grid lines are clearly visible.

The "Matrix zoom" spinbox (6–16) controls the font size of the matrix
panel.  Small values fit more of the matrix on screen; large values
make each number easier to read.  The table style also switches
automatically — heavy borders when zoomed in, no borders when zoomed
out — so more of the matrix fits at once.

Run:  python image_representation.py
"""

import csv
import os
import subprocess
import sys
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox

import numpy as np
from PIL import Image, ImageDraw, ImageTk
from tabulate import tabulate


MAX_REGION     = 32
DEFAULT_REGION = 8
GRID_DARKEN    = 0.55
GRID_LINE_RGB  = (170, 170, 170)

MIN_MATRIX_FONT = 6
MAX_MATRIX_FONT = 16
DEFAULT_MATRIX_FONT = 9


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
# Core operations
# ==========================================================================

def to_grayscale(img):
    return img.convert("L")


def to_rgb(img):
    return img.convert("RGB")


def quantize_to_3bit(arr):
    """value_3bit = value_8bit >> 5 — keep the top 3 bits, drop the low 5."""
    return arr >> 5


def crop_center(arr, n):
    h, w = arr.shape[:2]
    top = (h - n) // 2
    left = (w - n) // 2
    return arr[top:top + n, left:left + n], left, top


def pick_table_format(font_size):
    """Heavier borders when zoomed in, none when zoomed out."""
    if font_size >= 9:
        return "fancy_grid"
    if font_size >= 7:
        return "grid"
    return "plain"


def format_matrix_text(mat, mode, font_size):
    n = mat.shape[0]
    if mode == "gray":
        rows = [[int(v) for v in row] for row in mat]
    else:
        rows = [
            [f"({int(mat[r, c, 0])},{int(mat[r, c, 1])},"
             f"{int(mat[r, c, 2])})" for c in range(n)]
            for r in range(n)
        ]
    headers = [str(c) for c in range(n)]
    return tabulate(rows, headers=headers,
                    tablefmt=pick_table_format(font_size),
                    showindex=range(n))


def build_grid_image(patch, mode, bit_depth, cell_px):
    n = patch.shape[0]

    if bit_depth == 3:
        display = ((patch.astype(np.uint16) * 255) // 7).astype(np.uint8)
    else:
        display = patch.astype(np.uint8)

    display = (display.astype(np.float32) * GRID_DARKEN).astype(np.uint8)

    if mode == "gray":
        rgb = np.stack([display, display, display], axis=-1)
    else:
        rgb = display

    pil = Image.fromarray(rgb, mode="RGB")
    big = pil.resize((n * cell_px, n * cell_px), Image.NEAREST)

    draw = ImageDraw.Draw(big)
    for i in range(n + 1):
        x = i * cell_px
        draw.line([(x, 0), (x, n * cell_px)], fill=GRID_LINE_RGB, width=1)
        draw.line([(0, x), (n * cell_px, x)], fill=GRID_LINE_RGB, width=1)

    return big


# ==========================================================================
# Application
# ==========================================================================

class MatrixApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Pixel Bit-Depth Matrix Visualizer")
        self.root.geometry("1400x820")
        self.root.minsize(1000, 600)

        self.img = None
        self.path = None
        self.arr = None
        self.patch = None
        self.patch_left = 0
        self.patch_top = 0
        self.patch_n = 0
        self.bit_depth = 8

        self._photos = {}

        self.mode_var        = tk.StringVar(value="gray")
        self.bit_var         = tk.StringVar(value="8")
        self.region_var      = tk.IntVar(value=DEFAULT_REGION)
        self.matrix_zoom_var = tk.IntVar(value=DEFAULT_MATRIX_FONT)

        self._build_ui()

        # register traces AFTER widgets exist
        self.mode_var.trace_add("write",        lambda *_: self._recompute())
        self.bit_var.trace_add("write",         lambda *_: self._recompute())
        self.region_var.trace_add("write",      lambda *_: self._recompute())
        self.matrix_zoom_var.trace_add("write", lambda *_: self._draw_matrix())

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = self.root
        root.grid_rowconfigure(0, weight=0)    # control bar
        root.grid_rowconfigure(1, weight=1)    # two panels
        root.grid_rowconfigure(2, weight=0)    # status bar
        root.grid_columnconfigure(0, weight=1)

        # ---------- control bar ----------
        bar = tk.Frame(root, bg="#f0f0f0")
        bar.grid(row=0, column=0, sticky="ew")

        tk.Button(bar, text="Load Image", command=self.load_image
                  ).pack(side=tk.LEFT, padx=4, pady=6)

        tk.Label(bar, text="   Mode:").pack(side=tk.LEFT)
        tk.Radiobutton(bar, text="Grayscale", variable=self.mode_var,
                       value="gray").pack(side=tk.LEFT, padx=2)
        tk.Radiobutton(bar, text="RGB", variable=self.mode_var,
                       value="rgb").pack(side=tk.LEFT, padx=2)

        tk.Label(bar, text="   Bit depth:").pack(side=tk.LEFT, padx=(12, 2))
        tk.Radiobutton(bar, text="3-bit (0-7)", variable=self.bit_var,
                       value="3").pack(side=tk.LEFT, padx=2)
        tk.Radiobutton(bar, text="8-bit (0-255)", variable=self.bit_var,
                       value="8").pack(side=tk.LEFT, padx=2)

        tk.Label(bar, text="   Region N:").pack(side=tk.LEFT, padx=(12, 2))
        tk.Spinbox(bar, from_=1, to=MAX_REGION, width=4,
                   textvariable=self.region_var
                   ).pack(side=tk.LEFT, padx=2)

        tk.Label(bar, text="   Matrix zoom:").pack(side=tk.LEFT, padx=(12, 2))
        tk.Spinbox(bar, from_=MIN_MATRIX_FONT, to=MAX_MATRIX_FONT, width=4,
                   textvariable=self.matrix_zoom_var
                   ).pack(side=tk.LEFT, padx=2)
        tk.Button(bar, text="–", width=2,
                  command=self._matrix_zoom_out
                  ).pack(side=tk.LEFT, padx=(2, 0))
        tk.Button(bar, text="+", width=2,
                  command=self._matrix_zoom_in
                  ).pack(side=tk.LEFT, padx=(2, 4))

        tk.Button(bar, text="Save Crop PNG",
                  command=self.save_png
                  ).pack(side=tk.RIGHT, padx=4, pady=6)
        tk.Button(bar, text="Save Matrix CSV",
                  command=self.save_csv
                  ).pack(side=tk.RIGHT, padx=4, pady=6)

        # ---------- two panels ----------
        panels = tk.Frame(root, bg="#0d0d0d")
        panels.grid(row=1, column=0, sticky="nsew")
        panels.grid_rowconfigure(0, weight=1)
        panels.grid_columnconfigure(0, weight=1, uniform="p")
        panels.grid_columnconfigure(1, weight=1, uniform="p")

        # -- left: grid overlay --
        left = tk.Frame(panels, bg="#0d0d0d")
        left.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        self.label_grid = tk.Label(
            left, text="Grid Overlay:  —",
            fg="white", bg="#0d0d0d",
            font=("TkDefaultFont", 11, "bold"))
        self.label_grid.grid(row=0, column=0, pady=(6, 2))

        self.canvas_grid = tk.Canvas(left, bg="#050505",
                                     highlightthickness=0)
        self.canvas_grid.grid(row=1, column=0, sticky="nsew")

        # -- right: pixel matrix text --
        right = tk.Frame(panels, bg="#0d0d0d")
        right.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self.label_matrix = tk.Label(
            right, text="Pixel Matrix:  —",
            fg="white", bg="#0d0d0d",
            font=("TkDefaultFont", 11, "bold"))
        self.label_matrix.grid(row=0, column=0, pady=(6, 2))

        text_frame = tk.Frame(right, bg="#111")
        text_frame.grid(row=1, column=0, sticky="nsew")
        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(0, weight=1)

        self.matrix_text = tk.Text(
            text_frame, bg="#111", fg="#e0e0e0",
            font=("Courier", DEFAULT_MATRIX_FONT), wrap="none",
            borderwidth=0, highlightthickness=0,
            padx=6, pady=6)
        sb_v = tk.Scrollbar(text_frame, orient="vertical",
                            command=self.matrix_text.yview)
        sb_h = tk.Scrollbar(text_frame, orient="horizontal",
                            command=self.matrix_text.xview)
        self.matrix_text.configure(yscrollcommand=sb_v.set,
                                   xscrollcommand=sb_h.set)
        self.matrix_text.grid(row=0, column=0, sticky="nsew")
        sb_v.grid(row=0, column=1, sticky="ns")
        sb_h.grid(row=1, column=0, sticky="ew")

        # keyboard scrolling
        for seq, delta in (("<Up>", -1), ("<Down>", 1)):
            self.matrix_text.bind(
                seq, lambda e, d=delta: self.matrix_text.yview_scroll(d, "units"))
        for seq, delta in (("<Left>", -1), ("<Right>", 1)):
            self.matrix_text.bind(
                seq, lambda e, d=delta: self.matrix_text.xview_scroll(d, "units"))
        self.matrix_text.bind("<Prior>",
                              lambda e: self.matrix_text.yview_scroll(-10, "units"))
        self.matrix_text.bind("<Next>",
                              lambda e: self.matrix_text.yview_scroll(10, "units"))
        self.matrix_text.bind("<Home>",
                              lambda e: self.matrix_text.yview_moveto(0.0))
        self.matrix_text.bind("<End>",
                              lambda e: self.matrix_text.yview_moveto(1.0))

        # Ctrl+wheel zooms the matrix font
        self.matrix_text.bind("<Control-MouseWheel>", self._on_ctrl_wheel)
        self.matrix_text.bind("<Control-Button-4>",   self._on_ctrl_wheel)
        self.matrix_text.bind("<Control-Button-5>",   self._on_ctrl_wheel)

        # ---------- status bar ----------
        self.status = tk.Label(root, anchor="w", relief=tk.SUNKEN, bd=1,
                               padx=6, pady=4,
                               text="Load an image to begin.")
        self.status.grid(row=2, column=0, sticky="ew")

        self.canvas_grid.bind("<Configure>",
                              lambda e: self._redraw_grid())

        root.update_idletasks()

    # ------------------------------------------------------------------
    # Matrix zoom helpers
    # ------------------------------------------------------------------
    def _matrix_zoom_in(self):
        v = self.matrix_zoom_var.get()
        if v < MAX_MATRIX_FONT:
            self.matrix_zoom_var.set(v + 1)

    def _matrix_zoom_out(self):
        v = self.matrix_zoom_var.get()
        if v > MIN_MATRIX_FONT:
            self.matrix_zoom_var.set(v - 1)

    def _on_ctrl_wheel(self, event):
        if event.num == 4 or getattr(event, "delta", 0) > 0:
            self._matrix_zoom_in()
        elif event.num == 5 or getattr(event, "delta", 0) < 0:
            self._matrix_zoom_out()
        return "break"

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    def load_image(self):
        path = filedialog.askopenfilename(
            title="Choose an image",
            filetypes=[("Images",
                        "*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff"),
                       ("All files", "*.*")],
        )
        if not path:
            return
        try:
            img = Image.open(path)
            img.load()
        except Exception as exc:
            messagebox.showerror("Error", f"Could not load image:\n{exc}")
            return

        self.img = img
        self.path = path
        self._recompute()

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    def _recompute(self):
        if not hasattr(self, "matrix_text"):
            return

        if self.img is None:
            self.arr = None
            self.patch = None
            self._draw_matrix()
            self._redraw_grid()
            return

        if self.mode_var.get() == "gray":
            arr = np.array(to_grayscale(self.img), dtype=np.uint8)
        else:
            arr = np.array(to_rgb(self.img), dtype=np.uint8)

        self.bit_depth = 3 if self.bit_var.get() == "3" else 8
        if self.bit_depth == 3:
            arr = quantize_to_3bit(arr)

        self.arr = arr

        h, w = arr.shape[:2]
        try:
            n = int(self.region_var.get())
        except (tk.TclError, ValueError):
            n = DEFAULT_REGION
        n = max(1, min(n, h, w))
        self.patch_n = n

        self.patch, self.patch_left, self.patch_top = crop_center(arr, n)

        self._draw_matrix()
        self._redraw_grid()

        max_val = 7 if self.bit_depth == 3 else 255
        self.status.config(
            text=f"{os.path.basename(self.path)}  ({w}×{h})  |  "
                 f"{self.mode_var.get()}  {self.bit_depth}-bit  "
                 f"range 0-{max_val}  |  "
                 f"{n}×{n} crop at "
                 f"(left={self.patch_left}, top={self.patch_top})  |  "
                 f"distinct values in patch: "
                 f"{int(np.unique(self.patch).size)}"
        )

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def _draw_matrix(self):
        if not hasattr(self, "matrix_text"):
            return
        t = self.matrix_text

        # apply current font size
        try:
            size = int(self.matrix_zoom_var.get())
        except (tk.TclError, ValueError):
            size = DEFAULT_MATRIX_FONT
        size = max(MIN_MATRIX_FONT, min(MAX_MATRIX_FONT, size))
        t.config(font=("Courier", size))

        # remember scroll position so a font change doesn't jump around
        yfrac = t.yview()[0]
        xfrac = t.xview()[0]

        t.config(state=tk.NORMAL)
        t.delete("1.0", tk.END)

        if self.patch is None:
            t.insert(tk.END, "Load an image to see the pixel matrix.\n")
            t.config(state=tk.DISABLED)
            self.label_matrix.config(text="Pixel Matrix:  —")
            return

        n = self.patch.shape[0]
        mode = self.mode_var.get()
        txt = format_matrix_text(self.patch, mode, size)
        t.insert(tk.END, txt + "\n")
        t.config(state=tk.DISABLED)

        max_val = 7 if self.bit_depth == 3 else 255
        ch = ("single value 0-%d" % max_val if mode == "gray"
              else "(R,G,B) 0-%d each" % max_val)
        self.label_matrix.config(
            text=f"Pixel Matrix  —  {n}×{n}, {ch}, font {size}")

        t.yview_moveto(yfrac)
        t.xview_moveto(xfrac)

    def _redraw_grid(self):
        cv = self.canvas_grid
        cv.delete("all")

        if self.patch is None:
            self.label_grid.config(text="Grid Overlay:  —")
            return

        cw = cv.winfo_width()
        ch = cv.winfo_height()
        if cw < 2 or ch < 2:
            return

        n = self.patch.shape[0]
        margin = 8
        avail_w = max(1, cw - margin)
        avail_h = max(1, ch - margin)
        cell = max(1, min(avail_w // n, avail_h // n))

        big = build_grid_image(self.patch, self.mode_var.get(),
                               self.bit_depth, cell)

        dw, dh = big.size
        x = (cw - dw) // 2
        y = (ch - dh) // 2

        photo = ImageTk.PhotoImage(big)
        self._photos["grid"] = photo
        cv.create_image(x, y, anchor=tk.NW, image=photo)

        self.label_grid.config(
            text=f"Grid Overlay  —  {n}×{n}, "
                 f"one cell = one number ({cell} px per cell)")

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    def save_csv(self):
        if self.patch is None:
            messagebox.showinfo("Nothing to save", "Load an image first.")
            return

        mode = self.mode_var.get()
        n = self.patch.shape[0]
        base = os.path.splitext(os.path.basename(self.path))[0]
        out = os.path.join(
            os.getcwd(),
            f"matrix_{base}_{mode}_{self.bit_depth}bit.csv"
        )

        with open(out, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            if mode == "gray":
                for row in self.patch:
                    writer.writerow(int(v) for v in row)
            else:
                writer.writerow(["row", "col", "R", "G", "B"])
                for r in range(n):
                    for c in range(n):
                        R, G, B = (int(v) for v in self.patch[r, c, :3])
                        writer.writerow([r, c, R, G, B])

        messagebox.showinfo(
            "Saved",
            f"Matrix saved to:\n{out}\n\n"
            f"Values are the true {self.bit_depth}-bit numbers."
        )

    def save_png(self):
        if self.patch is None:
            messagebox.showinfo("Nothing to save", "Load an image first.")
            return

        big = build_grid_image(self.patch, self.mode_var.get(),
                               self.bit_depth, 24)

        base = os.path.splitext(os.path.basename(self.path))[0]
        out = os.path.join(
            os.getcwd(),
            f"crop_{base}_{self.mode_var.get()}_{self.bit_depth}bit.png"
        )
        big.save(out)

        note = ""
        if self.bit_depth == 3:
            note = ("\n\n3-bit values 0-7 have been stretched to 0-255 "
                    "for display only.")
        messagebox.showinfo("Saved", f"Crop saved to:\n{out}{note}")


def main():
    root = tk.Tk()
    try:
        MatrixApp(root)
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
