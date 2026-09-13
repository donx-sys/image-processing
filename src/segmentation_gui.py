#!/usr/bin/env python3
"""
Image Segmentation — Hands-On GUI
=================================

Load an image, choose a segmentation method, and see three views:

  ┌────────────┬──────────────┬──────────────────┐
  │  ORIGINAL  │ SEGMENTATION │  BOUNDARIES ON   │
  │            │  (mask or    │  ORIGINAL        │
  │            │   labels)    │                  │
  └────────────┴──────────────┴──────────────────┘
  ┌──────────────────────────────────────────────┐
  │  METHOD INFO + PARAMETERS + STATS            │
  └──────────────────────────────────────────────┘

Every parameter updates the segmentation live — there is no Apply /
Segment button.  Otsu in particular finds its threshold automatically,
so there is nothing to press: switching to it or loading a new image
recomputes the mask immediately.

Methods:
  Otsu threshold       automatic global threshold
  Fixed threshold      manual global threshold
  Adaptive mean        local threshold that follows illumination
  Gradient / edges     threshold on edge magnitude
  K-means              partition intensities into k clusters
  Region growing       click to seed, grow where intensity is similar

Run:  python segmentation_gui.py
"""

import os
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
from PIL import Image, ImageTk

try:
    from scipy.ndimage import uniform_filter, sobel, label as nd_label
    HAVE_SCIPY = True
except ImportError:
    HAVE_SCIPY = False


MAX_WORK = 700
DEFAULT_FIXED_THRESHOLD = 128
DEFAULT_ADAPTIVE_WINDOW = 31
DEFAULT_ADAPTIVE_C      = 5
DEFAULT_GRADIENT_THRESH = 40
DEFAULT_K               = 3
DEFAULT_TOLERANCE       = 20

SEED_COLOR = "#ff3860"

METHODS = [
    "Otsu threshold",
    "Fixed threshold",
    "Adaptive mean",
    "Gradient / edges",
    "K-means",
    "Region growing",
]

METHOD_INFO = {
    "Otsu threshold":
        "Automatically picks the threshold t that maximises the "
        "between-class variance between the two groups (background vs "
        "foreground).  Works well on bimodal histograms and is the "
        "standard first thing to try.",
    "Fixed threshold":
        "Every pixel above t becomes foreground; the rest is background.  "
        "Simple and fast, but fails when the two classes overlap in "
        "intensity or when illumination is uneven across the image.",
    "Adaptive mean":
        "Computes a local mean around each pixel and thresholds against it.  "
        "Handles uneven illumination because the threshold follows the "
        "background.  Classic choice for document binarisation.",
    "Gradient / edges":
        "Marks pixels where the intensity changes rapidly.  Produces a "
        "boundary map rather than a region map.  Usually the first stage "
        "of an edge-based segmentation pipeline.",
    "K-means":
        "Clusters pixel intensities into k groups by alternating "
        "assignment and centroid updates.  Produces a k-level quantised "
        "image where each level becomes one 'region'.  Ignores spatial "
        "information.",
    "Region growing":
        "Start from a seed pixel and grow outward while neighbours stay "
        "within tolerance of the seed's intensity.  Click on the original "
        "to move the seed.  Simple and intuitive, but very sensitive to "
        "where the seed is placed.",
}


# ==========================================================================
# Segmentation primitives
# ==========================================================================

def otsu_threshold(arr):
    hist = np.bincount(arr.flatten(), minlength=256).astype(np.float64)
    total = float(arr.size)
    sum_total = float(np.dot(np.arange(256), hist))
    sum_b = 0.0
    w_b = 0.0
    max_var = -1.0
    best_t = 0
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_total - sum_b) / w_f
        var_between = w_b * w_f * (m_b - m_f) ** 2
        if var_between > max_var:
            max_var = var_between
            best_t = t
    return best_t, arr > best_t


def fixed_threshold_mask(arr, t):
    return arr > t


def adaptive_mean_mask(arr, window, C):
    w = max(3, int(window))
    if w % 2 == 0:
        w += 1
    local_mean = uniform_filter(arr.astype(np.float32), size=w, mode="reflect")
    return arr.astype(np.float32) > (local_mean - C)


def gradient_magnitude(arr):
    a = arr.astype(np.float32)
    gx = sobel(a, axis=1, mode="reflect")
    gy = sobel(a, axis=0, mode="reflect")
    return np.sqrt(gx * gx + gy * gy)


def gradient_mask(arr, threshold):
    mag = gradient_magnitude(arr)
    return mag > threshold, mag


def kmeans_1d(arr, k, max_iter=50):
    data = arr.flatten().astype(np.float32)
    qs = np.linspace(0, 100, k + 2)[1:-1]
    centers = np.percentile(data, qs).astype(np.float32)
    labels = np.zeros_like(data, dtype=np.int32)
    for _ in range(max_iter):
        dists = np.abs(data[:, None] - centers[None, :])
        new_labels = np.argmin(dists, axis=1).astype(np.int32)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for i in range(k):
            sel = labels == i
            if sel.any():
                centers[i] = float(data[sel].mean())
    order = np.argsort(centers)
    remap = np.zeros(k, dtype=np.int32)
    remap[order] = np.arange(k)
    return remap[labels].reshape(arr.shape), centers[order]


def region_growing(arr, seed, tolerance):
    h, w = arr.shape
    sx = max(0, min(w - 1, int(seed[0])))
    sy = max(0, min(h - 1, int(seed[1])))
    seed_val = float(arr[sy, sx])
    candidate = np.abs(arr.astype(np.float32) - seed_val) <= tolerance
    if not HAVE_SCIPY:
        return candidate, seed_val
    labeled, _ = nd_label(candidate)
    lab = labeled[sy, sx]
    if lab == 0:
        return np.zeros_like(candidate), seed_val
    return labeled == lab, seed_val


def find_boundaries(labels):
    b = np.zeros(labels.shape, dtype=bool)
    b[:-1, :] |= labels[:-1, :] != labels[1:, :]
    b[1:, :]  |= labels[:-1, :] != labels[1:, :]
    b[:, :-1] |= labels[:, :-1] != labels[:, 1:]
    b[:, 1:]  |= labels[:, :-1] != labels[:, 1:]
    return b


PALETTE = np.array([
    [230, 25, 75],   [60, 180, 75],   [255, 225, 25],
    [0, 130, 200],   [245, 130, 48],  [145, 30, 180],
    [70, 240, 240],  [240, 50, 230],  [210, 245, 60],
], dtype=np.uint8)


def label_to_color(labels):
    return PALETTE[np.mod(labels, len(PALETTE))]


# ==========================================================================
# Application
# ==========================================================================

class SegmentApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Segmentation — Hands-On")
        self.root.geometry("1400x900")
        self.root.minsize(1100, 700)

        self.arr = None
        self.path = None
        self.mask = None
        self.is_label_map = False
        self.boundary_mask = None
        self.info_text_cache = ""

        self._photos = {}
        self._layout = {"orig": (1.0, 0, 0)}

        self.seed = (0, 0)

        # ---- option vars ----
        self.method_var    = tk.StringVar(value="Otsu threshold")
        self.fixed_t_var   = tk.IntVar(value=DEFAULT_FIXED_THRESHOLD)
        self.adapt_w_var   = tk.IntVar(value=DEFAULT_ADAPTIVE_WINDOW)
        self.adapt_c_var   = tk.IntVar(value=DEFAULT_ADAPTIVE_C)
        self.grad_t_var    = tk.IntVar(value=DEFAULT_GRADIENT_THRESH)
        self.k_var         = tk.IntVar(value=DEFAULT_K)
        self.tol_var       = tk.IntVar(value=DEFAULT_TOLERANCE)

        # every parameter updates the result live
        self.method_var.trace_add("write", lambda *_: self._on_method_change())
        for var in (self.fixed_t_var, self.adapt_w_var, self.adapt_c_var,
                    self.grad_t_var, self.k_var, self.tol_var):
            var.trace_add("write", lambda *_: self._recompute())

        self._build_ui()
        self._on_method_change()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = self.root
        root.grid_rowconfigure(0, weight=0)   # control bar
        root.grid_rowconfigure(1, weight=5)   # image row
        root.grid_rowconfigure(2, weight=2)   # info
        root.grid_rowconfigure(3, weight=0)   # status bar
        root.grid_columnconfigure(0, weight=1)

        # ---------- control bar ----------
        bar = tk.Frame(root, bg="#f0f0f0")
        bar.grid(row=0, column=0, sticky="ew")

        tk.Button(bar, text="Load Image", command=self.load_image
                  ).pack(side=tk.LEFT, padx=4, pady=6)

        tk.Label(bar, text="   Method:").pack(side=tk.LEFT)
        ttk.Combobox(bar, textvariable=self.method_var, state="readonly",
                     width=18, values=METHODS
                     ).pack(side=tk.LEFT, padx=2)

        self.params_frame = tk.Frame(bar, bg="#f0f0f0")
        self.params_frame.pack(side=tk.LEFT, padx=10)

        tk.Button(bar, text="Save Mask",
                  command=lambda: self.save("mask")
                  ).pack(side=tk.RIGHT, padx=4, pady=6)
        tk.Button(bar, text="Save Overlay",
                  command=lambda: self.save("overlay")
                  ).pack(side=tk.RIGHT, padx=4, pady=6)

        # ---------- image row: three panels ----------
        img_row = tk.Frame(root, bg="#0d0d0d")
        img_row.grid(row=1, column=0, sticky="nsew")
        img_row.grid_rowconfigure(0, weight=1)
        for c in range(3):
            img_row.grid_columnconfigure(c, weight=1, uniform="imgcol")

        self.canvas_orig, self.label_orig = self._make_panel(
            img_row, 0, "Original")
        self.canvas_mask, self.label_mask = self._make_panel(
            img_row, 1, "Segmentation")
        self.canvas_over, self.label_over = self._make_panel(
            img_row, 2, "Boundaries on original")

        # ---------- info panel ----------
        info_frame = tk.Frame(root, bg="#111")
        info_frame.grid(row=2, column=0, sticky="nsew", padx=6, pady=6)
        info_frame.grid_rowconfigure(0, weight=1)
        info_frame.grid_columnconfigure(0, weight=1)

        self.info = tk.Text(
            info_frame, bg="#111", fg="#e0e0e0",
            font=("Courier", 10), wrap="word",
            borderwidth=0, highlightthickness=0,
        )
        sb = tk.Scrollbar(info_frame, orient="vertical",
                          command=self.info.yview)
        self.info.configure(yscrollcommand=sb.set)
        self.info.grid(row=0, column=0, sticky="nsew",
                       padx=(8, 0), pady=6)
        sb.grid(row=0, column=1, sticky="ns", pady=6)

        # ---------- status bar ----------
        self.status = tk.Label(root, anchor="w", relief=tk.SUNKEN, bd=1,
                               padx=6, pady=4,
                               text="Load an image to begin.")
        self.status.grid(row=3, column=0, sticky="ew")

        # ---------- bindings ----------
        self.canvas_orig.bind("<Button-1>", self._on_click)
        for c in (self.canvas_orig, self.canvas_mask, self.canvas_over):
            c.bind("<Configure>", lambda e: self._redraw())

        root.update_idletasks()
        self._update_info()

    def _make_panel(self, parent, col, title):
        frame = tk.Frame(parent, bg="#0d0d0d")
        frame.grid(row=0, column=col, sticky="nsew", padx=2, pady=2)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        label = tk.Label(frame, text=title, fg="white", bg="#0d0d0d",
                         font=("TkDefaultFont", 11, "bold"))
        label.grid(row=0, column=0, pady=(6, 2))

        canvas = tk.Canvas(frame, bg="#050505",
                           highlightthickness=0, cursor="tcross")
        canvas.grid(row=1, column=0, sticky="nsew")
        return canvas, label

    # ------------------------------------------------------------------
    # Method-specific parameter widgets
    # ------------------------------------------------------------------
    def _on_method_change(self):
        for w in self.params_frame.winfo_children():
            w.destroy()

        m = self.method_var.get()

        if m == "Otsu threshold":
            tk.Label(self.params_frame,
                     text="(threshold found automatically — no settings)",
                     bg="#f0f0f0", fg="#666",
                     font=("TkDefaultFont", 9, "italic")
                     ).pack(side=tk.LEFT)

        elif m == "Fixed threshold":
            tk.Label(self.params_frame, text="Threshold:",
                     bg="#f0f0f0").pack(side=tk.LEFT)
            tk.Scale(self.params_frame, from_=0, to=255, orient=tk.HORIZONTAL,
                     variable=self.fixed_t_var,
                     length=260, showvalue=True
                     ).pack(side=tk.LEFT, padx=2)

        elif m == "Adaptive mean":
            tk.Label(self.params_frame, text="Window:",
                     bg="#f0f0f0").pack(side=tk.LEFT)
            tk.Spinbox(self.params_frame, from_=3, to=101, increment=2,
                       width=4, textvariable=self.adapt_w_var
                       ).pack(side=tk.LEFT, padx=2)
            tk.Label(self.params_frame, text="  C:",
                     bg="#f0f0f0").pack(side=tk.LEFT)
            tk.Scale(self.params_frame, from_=-20, to=30, orient=tk.HORIZONTAL,
                     variable=self.adapt_c_var,
                     length=180, showvalue=True
                     ).pack(side=tk.LEFT, padx=2)

        elif m == "Gradient / edges":
            tk.Label(self.params_frame, text="Threshold:",
                     bg="#f0f0f0").pack(side=tk.LEFT)
            tk.Scale(self.params_frame, from_=0, to=300, orient=tk.HORIZONTAL,
                     variable=self.grad_t_var,
                     length=260, showvalue=True
                     ).pack(side=tk.LEFT, padx=2)

        elif m == "K-means":
            tk.Label(self.params_frame, text="k clusters:",
                     bg="#f0f0f0").pack(side=tk.LEFT)
            tk.Spinbox(self.params_frame, from_=2, to=8, width=3,
                       textvariable=self.k_var
                       ).pack(side=tk.LEFT, padx=2)

        elif m == "Region growing":
            tk.Label(self.params_frame, text="Tolerance:",
                     bg="#f0f0f0").pack(side=tk.LEFT)
            tk.Scale(self.params_frame, from_=1, to=80, orient=tk.HORIZONTAL,
                     variable=self.tol_var,
                     length=220, showvalue=True
                     ).pack(side=tk.LEFT, padx=2)
            tk.Button(self.params_frame, text="Reset seed to centre",
                      command=self._reset_seed
                      ).pack(side=tk.LEFT, padx=8)

        self._recompute()

    def _reset_seed(self):
        if self.arr is None:
            return
        h, w = self.arr.shape
        self.seed = (w // 2, h // 2)
        self._recompute()

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
            img = Image.open(path).convert("L")
            img.load()
        except Exception as exc:
            messagebox.showerror("Error", f"Could not load image:\n{exc}")
            return

        w, h = img.size
        scale = min(1.0, MAX_WORK / max(w, h))
        if scale < 1.0:
            img = img.resize((max(1, int(w * scale)),
                              max(1, int(h * scale))),
                             Image.LANCZOS)

        self.arr = np.array(img, dtype=np.uint8)
        self.path = path
        self.seed = (self.arr.shape[1] // 2, self.arr.shape[0] // 2)
        self.mask = None
        self.boundary_mask = None

        if not HAVE_SCIPY:
            messagebox.showwarning(
                "scipy missing",
                "Adaptive mean, gradient, and region growing need "
                "scipy.ndimage.\nInstall with:\n\n    pip install scipy"
            )

        self._recompute()
        self.status.config(
            text=f"Loaded {os.path.basename(path)}  "
                 f"({self.arr.shape[1]}×{self.arr.shape[0]} working size)."
        )

    # ------------------------------------------------------------------
    # Compute — runs on every parameter change
    # ------------------------------------------------------------------
    def _recompute(self):
        if self.arr is None:
            self._redraw()
            self._update_info()
            return

        needs_scipy = self.method_var.get() in (
            "Adaptive mean", "Gradient / edges", "Region growing")
        if not HAVE_SCIPY and needs_scipy:
            self.mask = None
            self.boundary_mask = None
            self.info_text_cache = "This method needs scipy.ndimage.\n"
            self._redraw()
            self._update_info()
            return

        m = self.method_var.get()
        self.is_label_map = False
        self.info_text_cache = ""

        try:
            if m == "Otsu threshold":
                t, self.mask = otsu_threshold(self.arr)
                self.info_text_cache = (
                    f"Otsu found threshold  t = {t}\n"
                    f"Foreground = {self.mask.mean() * 100:.1f}% of pixels.\n"
                )

            elif m == "Fixed threshold":
                t = int(self.fixed_t_var.get())
                self.mask = fixed_threshold_mask(self.arr, t)
                self.info_text_cache = (
                    f"Fixed threshold t = {t}\n"
                    f"Foreground = {self.mask.mean() * 100:.1f}% of pixels.\n"
                )

            elif m == "Adaptive mean":
                w = int(self.adapt_w_var.get())
                C = int(self.adapt_c_var.get())
                self.mask = adaptive_mean_mask(self.arr, w, C)
                self.info_text_cache = (
                    f"Adaptive mean, window {w}×{w}, C = {C}\n"
                    f"Foreground = {self.mask.mean() * 100:.1f}% of pixels.\n"
                )

            elif m == "Gradient / edges":
                t = int(self.grad_t_var.get())
                self.mask, mag = gradient_mask(self.arr, t)
                self.info_text_cache = (
                    f"Gradient threshold = {t}\n"
                    f"Edge pixels = {self.mask.mean() * 100:.1f}% of image.\n"
                    f"Gradient magnitude range: 0 … {mag.max():.1f}\n"
                )

            elif m == "K-means":
                k = max(2, min(8, int(self.k_var.get())))
                labels, centers = kmeans_1d(self.arr, k)
                self.mask = labels.astype(np.int32)
                self.is_label_map = True
                lines = [f"K-means, k = {k}"]
                for i, c in enumerate(centers):
                    frac = float((labels == i).mean()) * 100
                    lines.append(
                        f"  cluster {i}:  centre = {c:6.1f}   "
                        f"({frac:5.1f}% of pixels)")
                self.info_text_cache = "\n".join(lines) + "\n"

            elif m == "Region growing":
                tol = int(self.tol_var.get())
                self.mask, seed_val = region_growing(self.arr,
                                                     self.seed, tol)
                self.info_text_cache = (
                    f"Region growing from seed {self.seed} "
                    f"(intensity {seed_val:.0f}), tolerance {tol}\n"
                    f"Region size = {self.mask.mean() * 100:.1f}% of image.\n"
                )

        except Exception:
            traceback.print_exc()
            self.mask = None
            self.boundary_mask = None
            self._redraw()
            self._update_info()
            return

        if self.mask is not None:
            self.boundary_mask = find_boundaries(self.mask.astype(np.int32))

        self._redraw()
        self._update_info()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def _draw_pil_into(self, canvas, pil_img, key):
        canvas.delete("all")
        cw = canvas.winfo_width()
        ch = canvas.winfo_height()
        if cw < 2 or ch < 2 or pil_img is None:
            self._layout[key] = (1.0, 0, 0)
            return
        iw, ih = pil_img.size
        scale = min(cw / iw, ch / ih, 1.0)
        dw = max(1, int(iw * scale))
        dh = max(1, int(ih * scale))
        x = (cw - dw) // 2
        y = (ch - dh) // 2
        resample = Image.LANCZOS if dw < iw else Image.NEAREST
        disp = pil_img.resize((dw, dh), resample)
        photo = ImageTk.PhotoImage(disp)
        self._photos[key] = photo
        canvas.create_image(x, y, anchor=tk.NW, image=photo)
        self._layout[key] = (scale, x, y)

    def _redraw(self):
        # ---- original ----
        if self.arr is not None:
            orig_rgb = Image.fromarray(self.arr, mode="L").convert("RGB")
            self._draw_pil_into(self.canvas_orig, orig_rgb, "orig")
            h, w = self.arr.shape
            self.label_orig.config(text=f"Original  ({w}×{h})")

            if self.method_var.get() == "Region growing":
                scale, ox, oy = self._layout["orig"]
                if scale > 0:
                    sx, sy = self.seed
                    mx = ox + (sx + 0.5) * scale
                    my = oy + (sy + 0.5) * scale
                    r = 6
                    self.canvas_orig.create_line(
                        mx - r, my, mx + r, my, fill=SEED_COLOR, width=2)
                    self.canvas_orig.create_line(
                        mx, my - r, mx, my + r, fill=SEED_COLOR, width=2)
        else:
            self.canvas_orig.delete("all")
            self.label_orig.config(text="Original:  —")

        # ---- segmentation ----
        if self.mask is not None:
            if self.is_label_map:
                rgb = label_to_color(self.mask.astype(np.int32))
                seg_pil = Image.fromarray(rgb, mode="RGB")
                h, w = self.mask.shape
                self.label_mask.config(
                    text=f"Segmentation — {int(self.mask.max()) + 1} labels  "
                         f"({w}×{h})")
            else:
                seg_pil = Image.fromarray(
                    (self.mask.astype(np.uint8) * 255), mode="L"
                ).convert("RGB")
                h, w = self.mask.shape
                self.label_mask.config(
                    text=f"Segmentation — binary mask  ({w}×{h})")
            self._draw_pil_into(self.canvas_mask, seg_pil, "mask")
        else:
            self.canvas_mask.delete("all")
            self.label_mask.config(text="Segmentation:  —")

        # ---- boundaries on original ----
        if self.arr is not None and self.boundary_mask is not None:
            base = np.stack([self.arr, self.arr, self.arr],
                            axis=-1).astype(np.uint8)
            base[self.boundary_mask] = [255, 60, 60]
            over_pil = Image.fromarray(base, mode="RGB")
            self._draw_pil_into(self.canvas_over, over_pil, "over")
            self.label_over.config(text="Boundaries on original")
        else:
            self.canvas_over.delete("all")
            self.label_over.config(text="Boundaries on original:  —")

    # ------------------------------------------------------------------
    # Click handling — move the region-growing seed
    # ------------------------------------------------------------------
    def _on_click(self, event):
        if self.arr is None:
            return
        if self.method_var.get() != "Region growing":
            return
        scale, ox, oy = self._layout.get("orig", (1.0, 0, 0))
        if scale <= 0:
            return
        ix = int((event.x - ox) / scale)
        iy = int((event.y - oy) / scale)
        h, w = self.arr.shape
        if 0 <= ix < w and 0 <= iy < h:
            self.seed = (ix, iy)
            self._recompute()

    # ------------------------------------------------------------------
    # Info panel
    # ------------------------------------------------------------------
    def _update_info(self):
        t = self.info
        t.delete("1.0", tk.END)

        if self.arr is None:
            t.insert(tk.END, "Load an image to begin.\n")
            return

        h, w = self.arr.shape
        m = self.method_var.get()

        t.insert(tk.END,
                 f"Image  : {os.path.basename(self.path)}  ({w} × {h})\n"
                 f"Method : {m}\n\n")
        t.insert(tk.END, METHOD_INFO.get(m, "") + "\n\n")
        t.insert(tk.END, "-" * 62 + "\n")

        if self.info_text_cache:
            t.insert(tk.END, self.info_text_cache + "\n")

        if self.mask is None:
            t.insert(tk.END, "(No segmentation computed.)\n")
            return

        if self.boundary_mask is not None:
            n_b = int(self.boundary_mask.sum())
            t.insert(tk.END,
                     f"Boundary pixels: {n_b}  "
                     f"({n_b / self.boundary_mask.size * 100:.2f}% of image)\n")

        if not self.is_label_map and HAVE_SCIPY:
            _, n_regions = nd_label(self.mask)
            t.insert(tk.END,
                     f"Connected regions in the mask: {n_regions}\n")

        if m == "Region growing":
            t.insert(tk.END,
                     "\nClick anywhere on the original to move the seed.\n")

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    def save(self, which):
        if self.arr is None or self.mask is None:
            messagebox.showinfo("Nothing to save",
                                "Run the segmentation first.")
            return

        base = os.path.splitext(os.path.basename(self.path))[0]
        method_slug = (self.method_var.get().replace(" ", "_")
                       .replace("/", "").lower())

        if which == "mask":
            if self.is_label_map:
                rgb = label_to_color(self.mask.astype(np.int32))
                out_img = Image.fromarray(rgb, mode="RGB")
            else:
                out_img = Image.fromarray(
                    (self.mask.astype(np.uint8) * 255), mode="L")
            out = os.path.join(
                os.getcwd(),
                f"{base}_segmentation_{method_slug}.png")
        else:
            if self.boundary_mask is None:
                messagebox.showinfo("Nothing to save",
                                    "No boundaries computed.")
                return
            base_rgb = np.stack([self.arr, self.arr, self.arr],
                                axis=-1).astype(np.uint8)
            base_rgb[self.boundary_mask] = [255, 60, 60]
            out_img = Image.fromarray(base_rgb, mode="RGB")
            out = os.path.join(
                os.getcwd(),
                f"{base}_boundaries_{method_slug}.png")

        out_img.save(out)
        messagebox.showinfo("Saved", f"Saved to:\n{out}")


def main():
    root = tk.Tk()
    try:
        SegmentApp(root)
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
