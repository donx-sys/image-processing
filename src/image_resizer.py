#!/usr/bin/env python3
"""
Image Resizer — Hands-On GUI (3-Panel Teaching Layout)
======================================================

Layout:
  ┌───────────────────────┬───────────────────────┐
  │  ORIGINAL             │  RESIZED              │
  │  W × H                │  W' × H'              │
  ├───────────────────────┴───────────────────────┤
  │  HOW PIXELS GET RESIZED (concept + example)   │
  │  (scrollable)                                 │
  └───────────────────────────────────────────────┘

The bottom panel samples a small 5×5 block of SOURCE pixels around a
focus point (default = image centre, click on the original to move it)
and shows the block of DESTINATION pixels they produce — with the
mapping between them highlighted so students see exactly which output
pixels a given input pixel feeds into (upscale) or vice versa (downscale).

Run:  python resizer_gui.py
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
from PIL import Image, ImageTk


INTERPOLATIONS = [
    ("Nearest Neighbour", Image.NEAREST),
    ("Box (average)",     Image.BOX),
    ("Bilinear",          Image.BILINEAR),
    ("Hamming",           Image.HAMMING),
    ("Bicubic",           Image.BICUBIC),
    ("Lanczos (best)",    Image.LANCZOS),
]

ALGO_EXPLAIN = {
    "Nearest Neighbour": [
        "For each destination pixel, pick the CLOSEST source pixel and copy its value as-is.",
        "Weighting: 1 sample, weight = 1.  No averaging, no new numbers produced.",
        "Upscaling duplicates pixels (blocky).  Downscaling drops source pixels it doesn't land on.",
    ],
    "Box (average)": [
        "Each destination pixel is the AREA-WEIGHTED AVERAGE of every source pixel its cell overlaps.",
        "Weighting: samples contribute in proportion to how much area they cover.",
        "Behaves like a simple low-pass filter.  Fast and predictable, no ringing.",
    ],
    "Bilinear": [
        "Each destination pixel is a weighted average of its 2×2 nearest source pixels.",
        "Weighting: linear falloff with distance — the closest source pixel contributes most.",
        "Reach: 4 samples.  Cheap and smooth, but soft on hard edges.",
    ],
    "Hamming": [
        "Like bilinear in reach (2×2), but the weights follow a HAMMING WINDOW instead of a linear ramp.",
        "Weighting: cosine-shaped taper — near-centre samples dominate, edge samples fade gently.",
        "Similar look to bilinear, often preferred when anti-aliasing matters more than sharpness.",
    ],
    "Bicubic": [
        "Each destination pixel is a weighted average of its 4×4 nearest source pixels.",
        "Weighting: cubic polynomial (Catmull-Rom style) — smooth falloff with small negative lobes.",
        "Reach: 16 samples.  Sharper than bilinear; can slightly overshoot (ring) near hard edges.",
    ],
    "Lanczos (best)": [
        "Each destination pixel is a weighted average of its 6×6 nearest source pixels.",
        "Weighting: the Lanczos window — a sinc (ideal low-pass) tapered by a wider sinc.",
        "Reach: 36 samples.  Sharpest and most faithful; slight ringing on very hard edges is expected.",
    ],
}

SAMPLE_N       = 5      # source pixels per side in the explainer sample
MAX_DST_CELLS  = 12     # cap on destination grid size (visual)
CELL_PX        = 34     # on-screen size of each sample cell
HIGHLIGHT      = "#ffd400"
MARKER         = "#ff3860"


class ResizerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Resizer — Hands-On (3-Panel)")
        self.root.geometry("1280x900")
        self.root.minsize(1000, 720)

        self.src = None
        self.src_path = None
        self.resized = None

        self._photo_orig = None
        self._photo_res = None

        self._lock = False
        self.focus_px = None

        self._orig_scale = 1.0
        self._orig_x = 0
        self._orig_y = 0

        self._build_ui()

    # ----------------------------------------------------------------- UI --
    def _build_ui(self):
        # ---------- control bar ------------------------------------------
        bar = tk.Frame(self.root, bg="#f0f0f0")
        bar.pack(side=tk.TOP, fill=tk.X)

        tk.Button(bar, text="Load Image", command=self.load_image
                  ).pack(side=tk.LEFT, padx=4, pady=6)

        tk.Label(bar, text="  Width:").pack(side=tk.LEFT)
        self.w_var = tk.StringVar()
        e = tk.Entry(bar, width=7, textvariable=self.w_var)
        e.pack(side=tk.LEFT, padx=2)
        self.w_var.trace_add("write", self._on_w_change)

        tk.Label(bar, text="Height:").pack(side=tk.LEFT, padx=(10, 2))
        self.h_var = tk.StringVar()
        e2 = tk.Entry(bar, width=7, textvariable=self.h_var)
        e2.pack(side=tk.LEFT, padx=2)
        self.h_var.trace_add("write", self._on_h_change)

        self.lock_var = tk.BooleanVar(value=True)
        tk.Checkbutton(bar, text="Lock aspect", variable=self.lock_var
                       ).pack(side=tk.LEFT, padx=(8, 4))

        tk.Label(bar, text="  Method:").pack(side=tk.LEFT, padx=(10, 2))
        self.interp_var = tk.StringVar(value=INTERPOLATIONS[-1][0])
        ttk.Combobox(
            bar, textvariable=self.interp_var, state="readonly", width=18,
            values=[name for name, _ in INTERPOLATIONS],
        ).pack(side=tk.LEFT, padx=2)

        tk.Button(bar, text="Resize", command=self.do_resize
                  ).pack(side=tk.LEFT, padx=8)
        tk.Button(bar, text="Save Resized", command=self.save_resized
                  ).pack(side=tk.LEFT, padx=4)
        tk.Button(bar, text="Reset Size", command=self.reset_size
                  ).pack(side=tk.LEFT, padx=4)
        tk.Button(bar, text="Recentre Focus", command=self.recentre_focus
                  ).pack(side=tk.LEFT, padx=4)

        # ---------- status bar -------------------------------------------
        self.status = tk.Label(
            self.root, anchor="w", relief=tk.SUNKEN, bd=1, padx=6, pady=4,
            text="Step 1: Load an image.",
        )
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

        # ---------- main: 3-panel grid ------------------------------------
        main = tk.Frame(self.root, bg="#0d0d0d")
        main.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        main.grid_rowconfigure(0, weight=3)
        main.grid_rowconfigure(1, weight=2)
        main.grid_columnconfigure(0, weight=1)

        # ----- top row: two equal panels side by side -----
        top = tk.Frame(main, bg="#0d0d0d")
        top.grid(row=0, column=0, sticky="nsew")
        top.grid_rowconfigure(0, weight=1)
        top.grid_columnconfigure(0, weight=1, uniform="toppair")
        top.grid_columnconfigure(1, weight=1, uniform="toppair")

        left = tk.Frame(top, bg="#0d0d0d")
        left.grid(row=0, column=0, sticky="nsew")
        self.orig_label = tk.Label(
            left, text="Original:  —",
            fg="white", bg="#0d0d0d",
            font=("TkDefaultFont", 12, "bold"),
        )
        self.orig_label.pack(side=tk.TOP, pady=(10, 4))
        self.orig_canvas = tk.Canvas(left, bg="#050505", highlightthickness=0,
                                     cursor="tcross")
        self.orig_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.orig_canvas.bind("<Button-1>", self._on_orig_click)

        tk.Frame(top, bg="#333", width=2).grid(row=0, column=0, sticky="nse")

        right = tk.Frame(top, bg="#0d0d0d")
        right.grid(row=0, column=1, sticky="nsew")
        self.res_label = tk.Label(
            right, text="Resized:  —",
            fg="white", bg="#0d0d0d",
            font=("TkDefaultFont", 12, "bold"),
        )
        self.res_label.pack(side=tk.TOP, pady=(10, 4))
        self.res_canvas = tk.Canvas(right, bg="#050505", highlightthickness=0)
        self.res_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # ----- bottom row: explainer panel with vertical scrollbar -----
        bottom = tk.Frame(main, bg="#111")
        bottom.grid(row=1, column=0, sticky="nsew")
        bottom.grid_rowconfigure(0, weight=1)
        bottom.grid_columnconfigure(0, weight=1)

        self.explain_canvas = tk.Canvas(bottom, bg="#111",
                                        highlightthickness=0)
        self.explain_scrollbar = tk.Scrollbar(
            bottom, orient="vertical", command=self.explain_canvas.yview
        )
        self.explain_canvas.configure(yscrollcommand=self.explain_scrollbar.set)

        self.explain_canvas.grid(row=0, column=0, sticky="nsew")
        self.explain_scrollbar.grid(row=0, column=1, sticky="ns")

        # Mouse-wheel scrolling over the explainer canvas
        self.explain_canvas.bind("<MouseWheel>", self._on_wheel)   # Win/macOS
        self.explain_canvas.bind("<Button-4>",   self._on_wheel)   # Linux up
        self.explain_canvas.bind("<Button-5>",   self._on_wheel)   # Linux down

        # redraw on resize
        self.orig_canvas.bind("<Configure>",    lambda e: self._redraw_all())
        self.res_canvas.bind("<Configure>",     lambda e: self._redraw_all())
        self.explain_canvas.bind("<Configure>", lambda e: self._redraw_all())

    # -------------------------------------------------- aspect lock -------
    def _on_w_change(self, *_):
        if self._lock or self.src is None or not self.lock_var.get():
            return
        try:
            w = int(self.w_var.get())
            if w < 1:
                return
        except ValueError:
            return
        W, H = self.src.size
        self._lock = True
        self.h_var.set(str(max(1, round(w * H / W))))
        self._lock = False

    def _on_h_change(self, *_):
        if self._lock or self.src is None or not self.lock_var.get():
            return
        try:
            h = int(self.h_var.get())
            if h < 1:
                return
        except ValueError:
            return
        W, H = self.src.size
        self._lock = True
        self.w_var.set(str(max(1, round(h * W / H))))
        self._lock = False

    # --------------------------------------------------- mouse wheel ------
    def _on_wheel(self, event):
        if event.num == 4:
            self.explain_canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.explain_canvas.yview_scroll(1, "units")
        else:
            self.explain_canvas.yview_scroll(
                -1 if event.delta > 0 else 1, "units"
            )

    # ---------------------------------------------------- image loading ---
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

        self.src = img.convert("RGB")
        self.src_path = path
        self.resized = None
        W, H = self.src.size
        self.focus_px = (W // 2, H // 2)

        self._lock = True
        self.w_var.set(str(W))
        self.h_var.set(str(H))
        self._lock = False

        self.orig_label.config(text=f"Original:  {W} × {H} px")
        self.res_label.config(text="Resized:  —")
        self.status.config(
            text=f"Loaded {os.path.basename(path)}  ({W} × {H}).  "
                 f"Click anywhere on the original to sample that pixel in "
                 f"the explainer below."
        )
        # Reset the explainer scroll to the top for the new image
        self.explain_canvas.yview_moveto(0)
        self._redraw_all()

    def recentre_focus(self):
        if self.src is None:
            return
        W, H = self.src.size
        self.focus_px = (W // 2, H // 2)
        self._redraw_all()

    def reset_size(self):
        if self.src is None:
            return
        W, H = self.src.size
        self._lock = True
        self.w_var.set(str(W))
        self.h_var.set(str(H))
        self._lock = False
        self.resized = None
        self.res_label.config(text="Resized:  —")
        self.status.config(text=f"Size reset to original {W} × {H}.")
        self._redraw_all()

    # ---------------------------------------------------- the resize ------
    def do_resize(self):
        if self.src is None:
            messagebox.showinfo("No image", "Load an image first.")
            return
        try:
            new_w = int(self.w_var.get())
            new_h = int(self.h_var.get())
        except ValueError:
            messagebox.showerror("Bad size",
                                 "Width and height must be integers.")
            return
        if new_w < 1 or new_h < 1:
            messagebox.showerror("Bad size", "Width and height must be ≥ 1.")
            return
        if new_w > 20000 or new_h > 20000:
            messagebox.showerror("Too big", "Cap is 20000 × 20000.")
            return

        method = self._current_interpolation()
        try:
            self.resized = self.src.resize((new_w, new_h), method)
        except Exception as exc:
            messagebox.showerror("Resize failed", str(exc))
            return

        W, H = self.src.size
        self.res_label.config(text=f"Resized:  {new_w} × {new_h} px")
        self.status.config(
            text=f"Resized {W} × {H}  →  {new_w} × {new_h}   "
                 f"(×{new_w/W:.3f} horizontal, ×{new_h/H:.3f} vertical)   "
                 f"using {self.interp_var.get()}."
        )
        self._redraw_all()

    def _current_interpolation(self):
        for name, m in INTERPOLATIONS:
            if name == self.interp_var.get():
                return m
        return Image.LANCZOS

    # ----------------------------------------------------- click handler --
    def _on_orig_click(self, event):
        if self.src is None or self._orig_scale <= 0:
            return
        x = int((event.x - self._orig_x) / self._orig_scale)
        y = int((event.y - self._orig_y) / self._orig_scale)
        W, H = self.src.size
        if 0 <= x < W and 0 <= y < H:
            self.focus_px = (x, y)
            self._redraw_all()

    # ------------------------------------------------------- preview draw --
    def _draw_fitted(self, canvas, img, ref_name, overlay_marker=False):
        canvas.delete("all")
        cw = canvas.winfo_width()
        ch = canvas.winfo_height()
        if cw < 2 or ch < 2 or img is None:
            return None

        iw, ih = img.size
        scale = min(cw / iw, ch / ih, 1.0)
        dw = max(1, int(iw * scale))
        dh = max(1, int(ih * scale))
        x = (cw - dw) // 2
        y = (ch - dh) // 2

        disp = img.resize((dw, dh), Image.LANCZOS)
        photo = ImageTk.PhotoImage(disp)
        setattr(self, ref_name, photo)
        canvas.create_image(x, y, anchor=tk.NW, image=photo)

        if overlay_marker and self.focus_px is not None:
            fx, fy = self.focus_px
            mx = x + (fx + 0.5) * scale
            my = y + (fy + 0.5) * scale
            r = 6
            canvas.create_line(mx - r, my, mx + r, my, fill=MARKER, width=2)
            canvas.create_line(mx, my - r, mx, my + r, fill=MARKER, width=2)
            canvas.create_oval(mx - r - 1, my - r - 1, mx + r + 1, my + r + 1,
                               outline=MARKER, width=1)

        return (scale, x, y)

    def _redraw_all(self):
        # ---- top-left: original ----
        layout = self._draw_fitted(self.orig_canvas, self.src,
                                   "_photo_orig", overlay_marker=True)
        if layout is not None:
            self._orig_scale, self._orig_x, self._orig_y = layout

        # ---- top-right: resized ----
        self._draw_fitted(self.res_canvas, self.resized, "_photo_res")
        if self.resized is None:
            cw = self.res_canvas.winfo_width()
            ch = self.res_canvas.winfo_height()
            if cw > 2 and ch > 2:
                self.res_canvas.create_text(
                    cw // 2, ch // 2,
                    text="(not resized yet — pick a size and click Resize)",
                    fill="#666", font=("TkDefaultFont", 11),
                )

        # ---- bottom: explainer ----
        self._draw_explainer()

    # --------------------------------------------------- explainer panel --
    def _draw_explainer(self):
        c = self.explain_canvas
        c.delete("all")

        cw = c.winfo_width()
        ch = c.winfo_height()
        if cw < 2 or ch < 2:
            return

        if self.src is None:
            c.create_text(cw // 2, ch // 2,
                          text="Load an image to see how pixels are resized.",
                          fill="#888", font=("TkDefaultFont", 12))
            c.configure(scrollregion=(0, 0, cw, ch))
            return

        W, H = self.src.size
        if self.focus_px is None:
            self.focus_px = (W // 2, H // 2)
        fx, fy = self.focus_px

        # ---- header ----
        c.create_text(cw // 2, 16,
                      text="HOW PIXELS ARE RESIZED",
                      fill="white", font=("TkDefaultFont", 12, "bold"))

        if self.resized is None:
            c.create_text(cw // 2, ch // 2,
                          text="Resize the image to see the pixel mapping.",
                          fill="#888", font=("TkDefaultFont", 11))
            c.configure(scrollregion=(0, 0, cw, ch))
            return

        W2, H2 = self.resized.size
        sx = W2 / W
        sy = H2 / H

        # ---- sample regions ----
        n = min(SAMPLE_N, W, H)
        sx0 = max(0, min(W - n, fx - n // 2))
        sy0 = max(0, min(H - n, fy - n // 2))

        dx0 = int(sx0 * sx)
        dy0 = int(sy0 * sy)
        dx1 = max(dx0 + 1, int(round((sx0 + n) * sx)))
        dy1 = max(dy0 + 1, int(round((sy0 + n) * sy)))
        dst_w = min(MAX_DST_CELLS, dx1 - dx0)
        dst_h = min(MAX_DST_CELLS, dy1 - dy0)

        src_arr = np.asarray(self.src)
        res_arr = np.asarray(self.resized)

        # ---- layout ----
        gap = 56
        src_grid_w = n * CELL_PX
        dst_grid_w = dst_w * CELL_PX
        total_w = src_grid_w + gap + dst_grid_w
        start_x = max(10, (cw - total_w) // 2)
        grid_y = 44
        src_origin = (start_x, grid_y)
        dst_origin = (start_x + src_grid_w + gap, grid_y)

        # ---- labels above grids ----
        c.create_text(src_origin[0] + src_grid_w // 2, grid_y - 16,
                      text=f"SOURCE  {n}×{n}  around ({fx},{fy})",
                      fill=HIGHLIGHT, font=("TkDefaultFont", 9, "bold"))
        c.create_text(dst_origin[0] + dst_grid_w // 2, grid_y - 16,
                      text=f"DESTINATION  {dst_w}×{dst_h}",
                      fill=HIGHLIGHT, font=("TkDefaultFont", 9, "bold"))

        # ---- source grid ----
        center_col = n // 2
        center_row = n // 2
        for r in range(n):
            for col in range(n):
                gx = sx0 + col
                gy = sy0 + r
                if gx >= W or gy >= H:
                    continue
                px = src_arr[gy, gx]
                color = f"#{px[0]:02x}{px[1]:02x}{px[2]:02x}"
                is_center = (col == center_col and r == center_row)
                x1 = src_origin[0] + col * CELL_PX
                y1 = src_origin[1] + r * CELL_PX
                c.create_rectangle(
                    x1, y1, x1 + CELL_PX, y1 + CELL_PX,
                    fill=color,
                    outline=HIGHLIGHT if is_center else "#333",
                    width=3 if is_center else 1,
                )

        # ---- destination grid ----
        center_sx = sx0 + center_col
        center_sy = sy0 + center_row
        csx_lo = center_sx * sx
        csx_hi = (center_sx + 1) * sx
        csy_lo = center_sy * sy
        csy_hi = (center_sy + 1) * sy

        for r in range(dst_h):
            for col in range(dst_w):
                gx = dx0 + col
                gy = dy0 + r
                if gx >= W2 or gy >= H2:
                    continue
                px = res_arr[gy, gx]
                color = f"#{px[0]:02x}{px[1]:02x}{px[2]:02x}"
                overlap_x = (gx < csx_hi) and (gx + 1 > csx_lo)
                overlap_y = (gy < csy_hi) and (gy + 1 > csy_lo)
                contributes = overlap_x and overlap_y
                x1 = dst_origin[0] + col * CELL_PX
                y1 = dst_origin[1] + r * CELL_PX
                c.create_rectangle(
                    x1, y1, x1 + CELL_PX, y1 + CELL_PX,
                    fill=color,
                    outline=HIGHLIGHT if contributes else "#333",
                    width=3 if contributes else 1,
                )

        # ---- arrow between grids ----
        ax1 = src_origin[0] + src_grid_w + 12
        ax2 = dst_origin[0] - 12
        ay = src_origin[1] + n * CELL_PX // 2
        c.create_line(ax1, ay, ax2, ay,
                      fill="#00e0ff", width=3,
                      arrow=tk.LAST, arrowshape=(12, 14, 4))

        # ---- text section below the grids ----
        text_y = grid_y + max(n, dst_h) * CELL_PX + 20

        if abs(sx - 1.0) < 1e-9 and abs(sy - 1.0) < 1e-9:
            mode = "IDENTITY   (no resize)"
            scale_line = "Every source pixel maps to exactly one destination pixel."
        elif sx < 1.0 or sy < 1.0:
            mode = (f"DOWNSCALING   ×{sx:.3f} horizontal,   "
                    f"×{sy:.3f} vertical")
            scale_line = (f"Average coverage:  1 output pixel  ←  "
                          f"{(1/sx)*(1/sy):.2f} source pixels.")
        else:
            mode = (f"UPSCALING   ×{sx:.3f} horizontal,   "
                    f"×{sy:.3f} vertical")
            scale_line = (f"Average coverage:  1 source pixel  →  "
                          f"{sx*sy:.2f} output pixels.")

        c.create_text(cw // 2, text_y, text=mode,
                      fill=HIGHLIGHT, font=("TkDefaultFont", 11, "bold"))
        c.create_text(cw // 2, text_y + 22, text=scale_line,
                      fill="white", font=("TkDefaultFont", 10))

        # ---- algorithm explanation ----
        algo_lines = ALGO_EXPLAIN.get(self.interp_var.get(), [])
        if algo_lines:
            algo_y = text_y + 52
            c.create_text(cw // 2, algo_y,
                          text=f"— {self.interp_var.get().upper()} —",
                          fill=HIGHLIGHT, font=("TkDefaultFont", 11, "bold"))
            for i, line in enumerate(algo_lines):
                c.create_text(
                    cw // 2, algo_y + 22 + i * 18, text=line,
                    fill="#e0e0e0" if i == 0 else "#aaa",
                    font=("TkDefaultFont", 9),
                )

        # ---- footer hint ----
        hint_y = text_y + 52 + 22 + len(algo_lines) * 18 + 8
        c.create_text(
            cw // 2, hint_y,
            text="Yellow outline = footprint of the centre source pixel "
                 "in the destination grid.",
            fill="#666", font=("TkDefaultFont", 8),
        )

        # ---- fit the scroll region to whatever was actually drawn --------
        bbox = c.bbox("all")
        content_h = (bbox[3] + 20) if bbox else ch
        c.configure(scrollregion=(0, 0, cw, content_h))

    # -------------------------------------------------------------- save --
    def save_resized(self):
        if self.resized is None:
            messagebox.showinfo("Nothing to save",
                                "Click Resize first, then save.")
            return
        base = os.path.splitext(os.path.basename(self.src_path))[0]
        W, H = self.resized.size
        out = os.path.join(os.getcwd(), f"{base}_resized_{W}x{H}.png")
        self.resized.save(out)
        messagebox.showinfo("Saved",
                            f"Saved resized image ({W} × {H}) to:\n{out}")


def main():
    root = tk.Tk()
    ResizerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
