#!/usr/bin/env python3
"""
Image Contrast Enhancement — Hands-On GUI
==========================================

Load two images, pick a contrast-enhancement method for each one
independently, and compare each original with its enhanced version
side by side.  Histograms at the bottom show how the intensity
distribution changed.

Methods:
  Linear stretch          remap [p_low, p_high] of the range to [0, 255]
  Histogram equalization  flatten the histogram by CDF remapping
  Gamma correction        output = 255 * (input/255)^gamma
  Log transform           output = c * log(1 + input)

Layout:
  ┌──────────────┬──────────────┐
  │  A original  │  A enhanced  │
  ├──────────────┼──────────────┤
  │  B original  │  B enhanced  │
  ├──────────────┼──────────────┤
  │  HIST A      │  HIST B      │
  └──────────────┴──────────────┘

Run:  python contrast_gui.py
"""

import os
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
from PIL import Image, ImageTk


METHODS = [
    "Linear stretch",
    "Histogram equalization",
    "Gamma correction",
    "Log transform",
]

METHOD_BLURB = {
    "Linear stretch":
        "Remap the lowest / highest intensities to 0 / 255, or clip a "
        "fraction from each end before stretching.",
    "Histogram equalization":
        "Redistribute intensities via the cumulative distribution so the "
        "histogram is as flat as possible.  Global, monotonic.",
    "Gamma correction":
        "Nonlinear power law.  gamma < 1 brightens shadows, gamma > 1 "
        "darkens them.  Matches display / camera response curves.",
    "Log transform":
        "Compress bright regions, expand dark ones.  Common in "
        "Fourier-spectrum visualization.",
}


# ==========================================================================
# Enhancement functions  (pure numpy, no external deps beyond Pillow)
# ==========================================================================

def load_grayscale(path):
    img = Image.open(path)
    img.load()
    return np.array(img.convert("L"), dtype=np.uint8)


def linear_stretch(arr, low_pct=0, high_pct=100):
    """Remap the [low_pct, high_pct] percentile range to [0, 255]."""
    lo = np.percentile(arr, low_pct)
    hi = np.percentile(arr, high_pct)
    if hi <= lo:
        return arr.copy()
    scaled = (arr.astype(np.float32) - lo) * 255.0 / (hi - lo)
    return np.clip(scaled, 0, 255).astype(np.uint8)


def hist_equalize(arr):
    """Global histogram equalization via the CDF."""
    hist = np.bincount(arr.flatten(), minlength=256)
    cdf = hist.cumsum()
    nz = cdf[cdf > 0]
    if len(nz) == 0:
        return arr.copy()
    cdf_min = int(nz[0])
    total = arr.size
    denom = total - cdf_min
    if denom <= 0:
        return arr.copy()
    lut = np.round((cdf - cdf_min) * 255.0 / denom)
    lut = np.clip(lut, 0, 255).astype(np.uint8)
    return lut[arr]


def gamma_correct(arr, gamma):
    """output = 255 * (input/255)^gamma."""
    if gamma <= 0:
        gamma = 1e-3
    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(np.round((x ** gamma) * 255.0), 0, 255).astype(np.uint8)
    return lut[arr]


def log_transform(arr):
    """output = c * log(1 + input) with c = 255 / log(256)."""
    c = 255.0 / np.log(256.0)
    lut = np.clip(np.round(c * np.log1p(np.arange(256))),
                  0, 255).astype(np.uint8)
    return lut[arr]


def apply_method(arr, method, low_pct, high_pct, gamma):
    if method == "Linear stretch":
        return linear_stretch(arr, low_pct, high_pct)
    if method == "Histogram equalization":
        return hist_equalize(arr)
    if method == "Gamma correction":
        return gamma_correct(arr, gamma)
    if method == "Log transform":
        return log_transform(arr)
    raise ValueError(method)


# ==========================================================================
# Application
# ==========================================================================

class ContrastApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Contrast Enhancement — Hands-On")
        self.root.geometry("1300x920")
        self.root.minsize(1000, 720)

        # ---- state ----
        self.arr_a = None
        self.arr_b = None
        self.enh_a = None
        self.enh_b = None
        self.path_a = None
        self.path_b = None

        self._photos = {}          # keep PhotoImage refs alive

        # ---- option vars (one method per image) ----
        self.method_a_var = tk.StringVar(value=METHODS[1])
        self.method_b_var = tk.StringVar(value=METHODS[1])
        self.low_pct_var = tk.IntVar(value=0)
        self.high_pct_var = tk.IntVar(value=100)
        self.gamma_var = tk.DoubleVar(value=1.0)

        self.method_a_var.trace_add("write",
                                    lambda *_: self._on_method_change())
        self.method_b_var.trace_add("write",
                                    lambda *_: self._on_method_change())

        self._build_ui()
        self._on_method_change()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = self.root
        root.grid_rowconfigure(0, weight=0)   # control bar
        root.grid_rowconfigure(1, weight=1)   # main content
        root.grid_rowconfigure(2, weight=0)   # status bar
        root.grid_columnconfigure(0, weight=1)

        # ---------- control bar ----------
        bar = tk.Frame(root, bg="#f0f0f0")
        bar.grid(row=0, column=0, sticky="ew")

        tk.Button(bar, text="Load Image A", command=self.load_a
                  ).pack(side=tk.LEFT, padx=4, pady=6)
        tk.Button(bar, text="Load Image B", command=self.load_b
                  ).pack(side=tk.LEFT, padx=4, pady=6)

        tk.Label(bar, text="   Method A:").pack(side=tk.LEFT)
        ttk.Combobox(bar, textvariable=self.method_a_var, state="readonly",
                     width=20, values=METHODS
                     ).pack(side=tk.LEFT, padx=2)

        tk.Label(bar, text="  Method B:").pack(side=tk.LEFT)
        ttk.Combobox(bar, textvariable=self.method_b_var, state="readonly",
                     width=20, values=METHODS
                     ).pack(side=tk.LEFT, padx=2)

        # Parameter widgets live here, rebuilt on method change
        self.params_frame = tk.Frame(bar, bg="#f0f0f0")
        self.params_frame.pack(side=tk.LEFT, padx=8)

        tk.Button(bar, text="Save Enhanced B",
                  command=lambda: self.save("b")
                  ).pack(side=tk.RIGHT, padx=4, pady=6)
        tk.Button(bar, text="Save Enhanced A",
                  command=lambda: self.save("a")
                  ).pack(side=tk.RIGHT, padx=4, pady=6)

        # ---------- main content: 4 image panels + 2 histogram panels ----
        main = tk.Frame(root, bg="#0d0d0d")
        main.grid(row=1, column=0, sticky="nsew")
        main.grid_rowconfigure(0, weight=3)
        main.grid_rowconfigure(1, weight=3)
        main.grid_rowconfigure(2, weight=2)
        main.grid_columnconfigure(0, weight=1, uniform="col")
        main.grid_columnconfigure(1, weight=1, uniform="col")

        self.canvas_a_orig, self.label_a_orig = self._make_panel(
            main, 0, 0, "A — original")
        self.canvas_a_enh,  self.label_a_enh  = self._make_panel(
            main, 0, 1, "A — enhanced")
        self.canvas_b_orig, self.label_b_orig = self._make_panel(
            main, 1, 0, "B — original")
        self.canvas_b_enh,  self.label_b_enh  = self._make_panel(
            main, 1, 1, "B — enhanced")

        # histogram row
        hist_a_frame = tk.Frame(main, bg="#0a0a0a",
                                highlightbackground="#222",
                                highlightthickness=1)
        hist_a_frame.grid(row=2, column=0, sticky="nsew", padx=4, pady=4)
        hist_a_frame.grid_rowconfigure(0, weight=1)
        hist_a_frame.grid_columnconfigure(0, weight=1)
        self.canvas_hist_a = tk.Canvas(hist_a_frame, bg="#0a0a0a",
                                       highlightthickness=0)
        self.canvas_hist_a.grid(row=0, column=0, sticky="nsew")

        hist_b_frame = tk.Frame(main, bg="#0a0a0a",
                                highlightbackground="#222",
                                highlightthickness=1)
        hist_b_frame.grid(row=2, column=1, sticky="nsew", padx=4, pady=4)
        hist_b_frame.grid_rowconfigure(0, weight=1)
        hist_b_frame.grid_columnconfigure(0, weight=1)
        self.canvas_hist_b = tk.Canvas(hist_b_frame, bg="#0a0a0a",
                                       highlightthickness=0)
        self.canvas_hist_b.grid(row=0, column=0, sticky="nsew")

        # ---------- status bar ----------
        self.status = tk.Label(root, anchor="w", relief=tk.SUNKEN, bd=1,
                               padx=6, pady=4, justify=tk.LEFT,
                               text="Load an image to begin.")
        self.status.grid(row=2, column=0, sticky="ew")

        # ---------- redraw on resize ----------
        for c in (self.canvas_a_orig, self.canvas_a_enh,
                  self.canvas_b_orig, self.canvas_b_enh,
                  self.canvas_hist_a, self.canvas_hist_b):
            c.bind("<Configure>", lambda e: self._redraw())

        root.update_idletasks()

    def _make_panel(self, parent, row, col, title):
        frame = tk.Frame(parent, bg="#0d0d0d")
        frame.grid(row=row, column=col, sticky="nsew")
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        label = tk.Label(frame, text=f"{title}:  —",
                         fg="white", bg="#0d0d0d",
                         font=("TkDefaultFont", 11, "bold"))
        label.grid(row=0, column=0, pady=(6, 2))

        canvas = tk.Canvas(frame, bg="#050505", highlightthickness=0)
        canvas.grid(row=1, column=0, sticky="nsew")
        return canvas, label

    # ------------------------------------------------------------------
    # Dynamic parameter widgets
    # ------------------------------------------------------------------
    def _on_method_change(self):
        """Rebuild the parameter row based on which methods are selected.

        The clip percentages and gamma values are shared between A and B —
        if either dropdown needs a given parameter, the widget appears once
        and applies to both images."""
        for w in self.params_frame.winfo_children():
            w.destroy()

        ma = self.method_a_var.get()
        mb = self.method_b_var.get()
        selected = {ma, mb}

        if "Linear stretch" in selected:
            tk.Label(self.params_frame, text="Low %",
                     bg="#f0f0f0").pack(side=tk.LEFT)
            tk.Spinbox(self.params_frame, from_=0, to=49, width=4,
                       textvariable=self.low_pct_var,
                       command=self._recompute
                       ).pack(side=tk.LEFT, padx=2)
            tk.Label(self.params_frame, text="High %",
                     bg="#f0f0f0").pack(side=tk.LEFT, padx=(8, 0))
            tk.Spinbox(self.params_frame, from_=51, to=100, width=4,
                       textvariable=self.high_pct_var,
                       command=self._recompute
                       ).pack(side=tk.LEFT, padx=2)

        if "Gamma correction" in selected:
            tk.Label(self.params_frame, text="gamma",
                     bg="#f0f0f0").pack(side=tk.LEFT, padx=(8, 0))
            tk.Scale(self.params_frame, from_=0.1, to=5.0, resolution=0.05,
                     orient=tk.HORIZONTAL, variable=self.gamma_var,
                     length=160, showvalue=True,
                     command=lambda e: self._recompute()
                     ).pack(side=tk.LEFT, padx=2)

        self._recompute()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    def load_a(self):
        path = filedialog.askopenfilename(
            title="Choose image A",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff"),
                       ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self.arr_a = load_grayscale(path)
        except Exception as exc:
            messagebox.showerror("Error", f"Could not load image A:\n{exc}")
            return
        self.path_a = path
        self._recompute()

    def load_b(self):
        path = filedialog.askopenfilename(
            title="Choose image B",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff"),
                       ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self.arr_b = load_grayscale(path)
        except Exception as exc:
            messagebox.showerror("Error", f"Could not load image B:\n{exc}")
            return
        self.path_b = path
        self._recompute()

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    def _recompute(self):
        ma = self.method_a_var.get()
        mb = self.method_b_var.get()
        try:
            low = int(self.low_pct_var.get())
            high = int(self.high_pct_var.get())
        except (tk.TclError, ValueError):
            low, high = 0, 100
        try:
            gamma = float(self.gamma_var.get())
        except (tk.TclError, ValueError):
            gamma = 1.0

        try:
            if self.arr_a is not None:
                self.enh_a = apply_method(self.arr_a, ma,
                                          low, high, gamma)
            if self.arr_b is not None:
                self.enh_b = apply_method(self.arr_b, mb,
                                          low, high, gamma)
        except Exception:
            traceback.print_exc()

        self._redraw()
        self._update_status()

    def _update_status(self):
        ma = self.method_a_var.get()
        mb = self.method_b_var.get()

        parts = [f"A method = {ma}", f"B method = {mb}"]

        if "Linear stretch" in (ma, mb):
            parts.append(f"clip {self.low_pct_var.get()}%.."
                         f"{self.high_pct_var.get()}%")
        if "Gamma correction" in (ma, mb):
            try:
                g = float(self.gamma_var.get())
                parts.append(f"gamma = {g:.2f}")
            except (tk.TclError, ValueError):
                pass

        for tag, orig, enh, method in (
                ("A", self.arr_a, self.enh_a, ma),
                ("B", self.arr_b, self.enh_b, mb)):
            if orig is not None and enh is not None:
                parts.append(
                    f"{tag} [{method.split()[0]}]: "
                    f"mean {orig.mean():.1f}->{enh.mean():.1f}, "
                    f"std {orig.std():.1f}->{enh.std():.1f}"
                )

        self.status.config(text="  |  ".join(parts))

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def _draw_image(self, canvas, arr, ref_key):
        canvas.delete("all")
        cw = canvas.winfo_width()
        ch = canvas.winfo_height()
        if cw < 2 or ch < 2 or arr is None:
            return

        img = Image.fromarray(arr, mode="L")
        iw, ih = img.size
        scale = min(cw / iw, ch / ih, 1.0)
        dw = max(1, int(iw * scale))
        dh = max(1, int(ih * scale))
        x = (cw - dw) // 2
        y = (ch - dh) // 2
        disp = img.resize((dw, dh), Image.LANCZOS)
        photo = ImageTk.PhotoImage(disp)
        self._photos[ref_key] = photo
        canvas.create_image(x, y, anchor=tk.NW, image=photo)

    def _draw_histogram(self, canvas, orig, enh, title):
        canvas.delete("all")
        cw = canvas.winfo_width()
        ch = canvas.winfo_height()
        if cw < 20 or ch < 20:
            return

        margin_l, margin_r, margin_t, margin_b = 40, 24, 26, 26
        plot_w = cw - margin_l - margin_r
        plot_h = ch - margin_t - margin_b
        if plot_w < 20 or plot_h < 20:
            return

        canvas.create_text(cw // 2, 12, text=title, fill="#e0e0e0",
                           font=("TkDefaultFont", 10, "bold"))

        if orig is None:
            canvas.create_text(cw // 2, ch // 2, text="(no image)",
                               fill="#555", font=("TkDefaultFont", 10))
            return

        hist_orig = np.bincount(orig.flatten(), minlength=256).astype(np.float32)
        hist_enh = (np.bincount(enh.flatten(), minlength=256).astype(np.float32)
                    if enh is not None else None)

        mx = hist_orig.max()
        if hist_enh is not None:
            mx = max(mx, hist_enh.max())
        if mx <= 0:
            return

        # axes
        canvas.create_line(margin_l, margin_t,
                           margin_l, margin_t + plot_h, fill="#444")
        canvas.create_line(margin_l, margin_t + plot_h,
                           margin_l + plot_w, margin_t + plot_h, fill="#444")

        for v in (0, 64, 128, 192, 255):
            x = margin_l + v * plot_w / 255
            canvas.create_line(x, margin_t + plot_h,
                               x, margin_t + plot_h + 4, fill="#444")
            canvas.create_text(x, margin_t + plot_h + 14, text=str(v),
                               fill="#888", font=("TkDefaultFont", 8))

        def draw_line(hist, color, width):
            pts = []
            for i in range(256):
                x = margin_l + i * plot_w / 255
                y = margin_t + plot_h - (hist[i] / mx) * plot_h
                pts.extend([x, y])
            if len(pts) >= 4:
                canvas.create_line(*pts, fill=color, width=width)

        draw_line(hist_orig, "#cccccc", 1)
        if hist_enh is not None:
            draw_line(hist_enh, "#ff8a3d", 2)

        # legend
        lx = margin_l + plot_w - 130
        ly = margin_t + 4
        canvas.create_rectangle(lx, ly, lx + 12, ly + 8,
                                fill="#cccccc", outline="")
        canvas.create_text(lx + 16, ly + 4, text="original",
                           fill="#cccccc", anchor="w",
                           font=("TkDefaultFont", 8))
        canvas.create_rectangle(lx + 70, ly, lx + 82, ly + 8,
                                fill="#ff8a3d", outline="")
        canvas.create_text(lx + 86, ly + 4, text="enhanced",
                           fill="#ff8a3d", anchor="w",
                           font=("TkDefaultFont", 8))

    def _redraw(self):
        # A original
        if self.arr_a is not None:
            self._draw_image(self.canvas_a_orig, self.arr_a, "a_orig")
            h, w = self.arr_a.shape
            self.label_a_orig.config(text=f"A — original ({w}×{h})")
        else:
            self.canvas_a_orig.delete("all")
            self.label_a_orig.config(text="A — original:  —")

        # A enhanced
        if self.enh_a is not None:
            self._draw_image(self.canvas_a_enh, self.enh_a, "a_enh")
            h, w = self.enh_a.shape
            self.label_a_enh.config(
                text=f"A — enhanced [{self.method_a_var.get()}] ({w}×{h})")
        else:
            self.canvas_a_enh.delete("all")
            self.label_a_enh.config(text="A — enhanced:  —")

        # B original
        if self.arr_b is not None:
            self._draw_image(self.canvas_b_orig, self.arr_b, "b_orig")
            h, w = self.arr_b.shape
            self.label_b_orig.config(text=f"B — original ({w}×{h})")
        else:
            self.canvas_b_orig.delete("all")
            self.label_b_orig.config(text="B — original:  —")

        # B enhanced
        if self.enh_b is not None:
            self._draw_image(self.canvas_b_enh, self.enh_b, "b_enh")
            h, w = self.enh_b.shape
            self.label_b_enh.config(
                text=f"B — enhanced [{self.method_b_var.get()}] ({w}×{h})")
        else:
            self.canvas_b_enh.delete("all")
            self.label_b_enh.config(text="B — enhanced:  —")

        # histograms
        self._draw_histogram(self.canvas_hist_a, self.arr_a, self.enh_a,
                             "Histogram — A")
        self._draw_histogram(self.canvas_hist_b, self.arr_b, self.enh_b,
                             "Histogram — B")

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    def save(self, which):
        if which == "a":
            arr, path = self.enh_a, self.path_a
            method = self.method_a_var.get()
        else:
            arr, path = self.enh_b, self.path_b
            method = self.method_b_var.get()

        if arr is None:
            messagebox.showinfo("Nothing to save",
                                "Load the image and pick a method first.")
            return

        base = os.path.splitext(os.path.basename(path))[0]
        method_slug = method.replace(" ", "_").lower()
        out = os.path.join(os.getcwd(),
                           f"{base}_enhanced_{method_slug}.png")
        Image.fromarray(arr, mode="L").save(out)
        messagebox.showinfo("Saved", f"Enhanced image saved to:\n{out}")


def main():
    root = tk.Tk()
    try:
        ContrastApp(root)
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
