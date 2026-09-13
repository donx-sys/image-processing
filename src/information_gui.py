#!/usr/bin/env python3
"""
Information-Rich Regions — Hands-On GUI
========================================

Load an image, pick an information measure and a window size, and see
a false-colour map showing WHERE the image carries the most information.

The lesson: "bright" ≠ "informative".  A plain white sky is bright but
carries almost no information.  A dark textured patch carries a lot.
Information lives in VARIATION, not in absolute intensity.

Measures:
  Entropy        local Shannon entropy of the pixel values (bits/pixel)
  Variance       local spread of intensities around their mean
  RMS contrast   sqrt(variance), in the same units as pixel values
  Gradient       local edge strength (Sobel magnitude)
  Laplacian      local roughness (second-derivative energy)
  Range          brightest − darkest pixel in the window

Layout:
  ┌──────────────────────────┬──────────────────────────┐
  │  ORIGINAL                │  INFORMATION MAP         │
  │  (top-N regions boxed,   │  (jet false colour)      │
  │   click to inspect)      │                          │
  ├──────────────────────────┴──────────────────────────┤
  │  STATISTICS + TOP-N LIST                            │
  └─────────────────────────────────────────────────────┘

Run:  python information_gui.py
"""

import os
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
from PIL import Image, ImageTk

try:
    from scipy.ndimage import (uniform_filter, maximum_filter,
                               minimum_filter, sobel, laplace)
    HAVE_SCIPY = True
except ImportError:
    HAVE_SCIPY = False


MAX_WORK       = 700        # cap working image's longest side (px)
DEFAULT_WINDOW = 15
DEFAULT_TOPN   = 5

TOP_COLOR   = "#ffd400"
FOCUS_COLOR = "#ff3860"


# ==========================================================================
# Information measures  (each returns a float32 map, same shape as input)
# ==========================================================================

def map_entropy(arr, w):
    """Local Shannon entropy in a w×w window.

    Implementation trick: for each distinct intensity value present, build
    a 0/1 mask, then run a box filter over the mask to get the local
    probability p of that value.  Sum −p·log₂(p) across all values.
    """
    vals = np.unique(arr)
    total = np.zeros(arr.shape, dtype=np.float32)
    for v in vals:
        mask = (arr == v).astype(np.float32)
        p = uniform_filter(mask, size=w, mode="reflect")
        p = np.maximum(p, 1e-12)
        total -= p * np.log2(p)
    return total


def map_variance(arr, w):
    a = arr.astype(np.float32)
    mean = uniform_filter(a, size=w, mode="reflect")
    mean_sq = uniform_filter(a * a, size=w, mode="reflect")
    return np.maximum(mean_sq - mean * mean, 0.0)


def map_rms_contrast(arr, w):
    return np.sqrt(map_variance(arr, w))


def map_gradient(arr, w):
    a = arr.astype(np.float32)
    gx = sobel(a, axis=1, mode="reflect")
    gy = sobel(a, axis=0, mode="reflect")
    mag = np.sqrt(gx * gx + gy * gy)
    return uniform_filter(mag, size=w, mode="reflect")


def map_laplacian(arr, w):
    a = arr.astype(np.float32)
    lap = laplace(a, mode="reflect")
    return uniform_filter(lap * lap, size=w, mode="reflect")


def map_range(arr, w):
    mx = maximum_filter(arr, size=w, mode="reflect").astype(np.float32)
    mn = minimum_filter(arr, size=w, mode="reflect").astype(np.float32)
    return mx - mn


MEASURE_INFO = {
    "Entropy": {
        "fn": map_entropy,
        "unit": "bits/pixel",
        "blurb":
            "Shannon entropy of the local histogram: how unpredictable the "
            "pixel values are within the window.  A perfectly flat region "
            "with one value scores 0; a region that uses all 256 values "
            "with equal probability scores 8.",
    },
    "Variance": {
        "fn": map_variance,
        "unit": "intensity²",
        "blurb":
            "How spread out the values are around their mean.  High variance "
            "means big swings between dark and bright inside the window.  A "
            "noisy patch scores high even if it has no structure.",
    },
    "RMS contrast": {
        "fn": map_rms_contrast,
        "unit": "intensity",
        "blurb":
            "Square root of variance — the same idea, but expressed in the "
            "same units as the pixel values (0–255).  Easier to reason "
            "about than variance.",
    },
    "Gradient": {
        "fn": map_gradient,
        "unit": "Sobel magnitude",
        "blurb":
            "Local edge strength: how fast the intensity changes from one "
            "pixel to the next.  Edges and texture give high values; flat "
            "regions give near zero.  This is the standard edge detector "
            "energy map.",
    },
    "Laplacian": {
        "fn": map_laplacian,
        "unit": "second-deriv energy",
        "blurb":
            "Energy in the second derivative — a measure of local "
            "roughness.  Extremely sensitive to fine detail, high-frequency "
            "texture, and noise.  Very high on text, foliage, and fabric.",
    },
    "Range": {
        "fn": map_range,
        "unit": "max − min",
        "blurb":
            "The difference between the brightest and the darkest pixel in "
            "the window.  Simple and robust.  Its weakness: a single outlier "
            "pixel can push the score up even when the rest of the window "
            "is flat.",
    },
}


# ==========================================================================
# Visualisation helpers
# ==========================================================================

def colorize(norm):
    """Map a float array in [0,1] to a jet-style RGB uint8 image."""
    t = np.clip(norm, 0.0, 1.0)
    r = np.clip(1.5 - np.abs(4 * t - 3), 0, 1)
    g = np.clip(1.5 - np.abs(4 * t - 2), 0, 1)
    b = np.clip(1.5 - np.abs(4 * t - 1), 0, 1)
    rgb = np.stack([r, g, b], axis=-1)
    return (rgb * 255).astype(np.uint8)


def find_top_regions(score_map, n, sep):
    """Find top-N local maxima with at least `sep` pixels between them."""
    scores = score_map.astype(np.float32).copy()
    h, w = scores.shape
    regions = []
    for _ in range(max(0, n)):
        idx = int(np.argmax(scores))
        y, x = np.unravel_index(idx, scores.shape)
        score = float(scores[y, x])
        if score <= 0:
            break
        regions.append((score, int(y), int(x)))
        y0 = max(0, y - sep); y1 = min(h, y + sep + 1)
        x0 = max(0, x - sep); x1 = min(w, x + sep + 1)
        scores[y0:y1, x0:x1] = 0
    return regions


# ==========================================================================
# Application
# ==========================================================================

class InfoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Information-Rich Regions — Hands-On")
        self.root.geometry("1300x900")
        self.root.minsize(1050, 720)

        # ---- state ----
        self.arr = None          # working grayscale image (uint8)
        self.path = None
        self.score_map = None    # float32
        self.score_norm = None   # float32 in [0,1]
        self.heat_rgb = None     # uint8 (H,W,3)
        self.map_pil = None      # PIL image for right panel
        self.top_regions = []    # [(score, y, x)]
        self.focus = None        # (x, y) in working coords

        self._photos = {}
        self._layout = {"orig": (1.0, 0, 0), "map": (1.0, 0, 0)}

        # ---- option vars ----
        self.measure_var = tk.StringVar(value="Entropy")
        self.window_var = tk.IntVar(value=DEFAULT_WINDOW)
        self.topn_var = tk.IntVar(value=DEFAULT_TOPN)
        self.overlay_var = tk.BooleanVar(value=False)

        self.measure_var.trace_add("write", lambda *_: self._recompute())

        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = self.root
        root.grid_rowconfigure(0, weight=0)    # control bar
        root.grid_rowconfigure(1, weight=5)    # image row
        root.grid_rowconfigure(2, weight=2)    # info
        root.grid_rowconfigure(3, weight=0)    # status bar
        root.grid_columnconfigure(0, weight=1)

        # ---------- control bar ----------
        bar = tk.Frame(root, bg="#f0f0f0")
        bar.grid(row=0, column=0, sticky="ew")

        tk.Button(bar, text="Load Image", command=self.load_image
                  ).pack(side=tk.LEFT, padx=4, pady=6)

        tk.Label(bar, text="   Measure:").pack(side=tk.LEFT)
        ttk.Combobox(bar, textvariable=self.measure_var, state="readonly",
                     width=13, values=list(MEASURE_INFO.keys())
                     ).pack(side=tk.LEFT, padx=2)

        tk.Label(bar, text="  Window:").pack(side=tk.LEFT, padx=(10, 2))
        tk.Spinbox(bar, from_=3, to=41, increment=2, width=4,
                   textvariable=self.window_var
                   ).pack(side=tk.LEFT, padx=2)

        tk.Label(bar, text="  Top N:").pack(side=tk.LEFT, padx=(10, 2))
        tk.Spinbox(bar, from_=1, to=12, width=3,
                   textvariable=self.topn_var
                   ).pack(side=tk.LEFT, padx=2)

        tk.Button(bar, text="Recompute", command=self._recompute
                  ).pack(side=tk.LEFT, padx=10)

        tk.Checkbutton(bar, text="Overlay map on original",
                       variable=self.overlay_var,
                       command=self._redraw_map_panel
                       ).pack(side=tk.LEFT, padx=(12, 4))

        tk.Button(bar, text="Save Map",
                  command=self.save_map
                  ).pack(side=tk.RIGHT, padx=4, pady=6)

        # ---------- image row ----------
        img_row = tk.Frame(root, bg="#0d0d0d")
        img_row.grid(row=1, column=0, sticky="nsew")
        img_row.grid_rowconfigure(0, weight=1)
        img_row.grid_columnconfigure(0, weight=1, uniform="imgcol")
        img_row.grid_columnconfigure(1, weight=1, uniform="imgcol")

        self.canvas_orig, self.label_orig = self._make_panel(
            img_row, 0, "ORIGINAL — click to inspect")
        self.canvas_map, self.label_map = self._make_panel(
            img_row, 1, "INFORMATION MAP")

        # ---------- info panel ----------
        info_frame = tk.Frame(root, bg="#111")
        info_frame.grid(row=2, column=0, sticky="nsew", padx=6, pady=6)
        info_frame.grid_rowconfigure(0, weight=1)
        info_frame.grid_columnconfigure(0, weight=1)

        self.info_text = tk.Text(
            info_frame, bg="#111", fg="#e0e0e0",
            font=("Courier", 10), wrap="word",
            borderwidth=0, highlightthickness=0,
        )
        sb = tk.Scrollbar(info_frame, orient="vertical",
                          command=self.info_text.yview)
        self.info_text.configure(yscrollcommand=sb.set)
        self.info_text.grid(row=0, column=0, sticky="nsew",
                            padx=(8, 0), pady=6)
        sb.grid(row=0, column=1, sticky="ns", pady=6)

        # ---------- status bar ----------
        self.status = tk.Label(root, anchor="w", relief=tk.SUNKEN, bd=1,
                               padx=6, pady=4,
                               text="Load an image to begin.  Then click "
                                    "anywhere on the original to inspect "
                                    "that location.")
        self.status.grid(row=3, column=0, sticky="ew")

        # ---------- interaction ----------
        self.canvas_orig.bind("<Button-1>", self._on_click)
        self.canvas_map.bind("<Button-1>", self._on_click)
        for c in (self.canvas_orig, self.canvas_map):
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

        canvas = tk.Canvas(frame, bg="#050505", highlightthickness=0,
                           cursor="tcross")
        canvas.grid(row=1, column=0, sticky="nsew")
        return canvas, label

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

        # Cap the working resolution so all the filter computations stay fast
        w, h = img.size
        scale = min(1.0, MAX_WORK / max(w, h))
        if scale < 1.0:
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            img = img.resize((new_w, new_h), Image.LANCZOS)

        self.arr = np.array(img, dtype=np.uint8)
        self.path = path
        self.focus = None
        self.top_regions = []

        if not HAVE_SCIPY:
            messagebox.showwarning(
                "scipy missing",
                "The information measures use scipy.ndimage.\n"
                "Install it with:\n\n    pip install scipy\n\n"
                "The program will open, but no map will be computed."
            )

        self._recompute()
        self.status.config(
            text=f"Loaded {os.path.basename(path)}  "
                 f"({self.arr.shape[1]}×{self.arr.shape[0]} working size).  "
                 f"Click anywhere to inspect a location."
        )

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    def _recompute(self):
        if self.arr is None:
            self._redraw()
            self._update_info()
            return
        if not HAVE_SCIPY:
            self._redraw()
            self._update_info()
            return

        try:
            w = int(self.window_var.get())
            w = max(3, w)
            if w % 2 == 0:
                w += 1
        except (tk.TclError, ValueError):
            w = DEFAULT_WINDOW
            self.window_var.set(w)

        measure = self.measure_var.get()
        fn = MEASURE_INFO[measure]["fn"]

        try:
            self.score_map = fn(self.arr, w)
        except Exception:
            traceback.print_exc()
            self.score_map = None
            return

        mn = float(self.score_map.min())
        mx = float(self.score_map.max())
        if mx - mn < 1e-9:
            self.score_norm = np.zeros_like(self.score_map, dtype=np.float32)
        else:
            self.score_norm = ((self.score_map - mn) / (mx - mn)).astype(np.float32)

        self.heat_rgb = colorize(self.score_norm)

        # Top-N regions with non-maximum suppression
        try:
            n = int(self.topn_var.get())
            n = max(1, min(12, n))
        except (tk.TclError, ValueError):
            n = DEFAULT_TOPN
        sep = max(w // 2 + 4, 8)
        self.top_regions = find_top_regions(self.score_map, n, sep)

        self._redraw()
        self._update_info()
        self.status.config(
            text=f"{measure} map computed.  Window {w}×{w}.  "
                 f"Range: {mn:.3f} … {mx:.3f}  {MEASURE_INFO[measure]['unit']}."
        )

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

        if dw < iw:
            resample = Image.LANCZOS
        else:
            resample = Image.NEAREST
        disp = pil_img.resize((dw, dh), resample)
        photo = ImageTk.PhotoImage(disp)
        self._photos[key] = photo
        canvas.create_image(x, y, anchor=tk.NW, image=photo)
        self._layout[key] = (scale, x, y)

    def _redraw_orig_panel(self):
        cv = self.canvas_orig
        cv.delete("all")
        if self.arr is None:
            self._layout["orig"] = (1.0, 0, 0)
            return

        pil = Image.fromarray(self.arr, mode="L").convert("RGB")
        self._draw_pil_into(cv, pil, "orig")

        scale, ox, oy = self._layout["orig"]
        if scale <= 0:
            return

        w = int(self.window_var.get())
        half = w // 2

        # Top-N boxes
        for i, (score, y, x) in enumerate(self.top_regions, 1):
            x1 = ox + (x - half) * scale
            y1 = oy + (y - half) * scale
            x2 = ox + (x - half + w) * scale
            y2 = oy + (y - half + w) * scale
            cv.create_rectangle(x1, y1, x2, y2,
                                outline=TOP_COLOR, width=2, dash=(5, 3))
            cv.create_text(x1 + 3, y1 + 3, text=f"#{i}",
                           fill=TOP_COLOR, anchor="nw",
                           font=("TkDefaultFont", 9, "bold"))

        # Focus marker
        if self.focus is not None:
            fx, fy = self.focus
            mx = ox + (fx + 0.5) * scale
            my = oy + (fy + 0.5) * scale
            r = 7
            cv.create_line(mx - r, my, mx + r, my, fill=FOCUS_COLOR, width=2)
            cv.create_line(mx, my - r, mx, my + r, fill=FOCUS_COLOR, width=2)
            cv.create_oval(mx - r - 1, my - r - 1, mx + r + 1, my + r + 1,
                           outline=FOCUS_COLOR, width=1)

    def _build_map_image(self):
        if self.heat_rgb is None or self.arr is None:
            return None
        if self.overlay_var.get():
            g = np.stack([self.arr, self.arr, self.arr],
                         axis=-1).astype(np.float32)
            mixed = 0.55 * g + 0.45 * self.heat_rgb.astype(np.float32)
            return Image.fromarray(mixed.astype(np.uint8), mode="RGB")
        return Image.fromarray(self.heat_rgb, mode="RGB")

    def _redraw_map_panel(self):
        cv = self.canvas_map
        cv.delete("all")

        self.map_pil = self._build_map_image()
        if self.map_pil is None:
            self._layout["map"] = (1.0, 0, 0)
            cw = cv.winfo_width(); ch = cv.winfo_height()
            if cw > 2 and ch > 2:
                cv.create_text(cw // 2, ch // 2,
                               text="(no map yet)",
                               fill="#555", font=("TkDefaultFont", 10))
            return

        self._draw_pil_into(cv, self.map_pil, "map")

        scale, ox, oy = self._layout["map"]
        if scale <= 0:
            return

        # Same top-N boxes so both views correlate
        w = int(self.window_var.get())
        half = w // 2
        for i, (score, y, x) in enumerate(self.top_regions, 1):
            x1 = ox + (x - half) * scale
            y1 = oy + (y - half) * scale
            x2 = ox + (x - half + w) * scale
            y2 = oy + (y - half + w) * scale
            cv.create_rectangle(x1, y1, x2, y2,
                                outline=TOP_COLOR, width=2, dash=(5, 3))
            cv.create_text(x1 + 3, y1 + 3, text=f"#{i}",
                           fill=TOP_COLOR, anchor="nw",
                           font=("TkDefaultFont", 9, "bold"))

        if self.focus is not None:
            fx, fy = self.focus
            mx = ox + (fx + 0.5) * scale
            my = oy + (fy + 0.5) * scale
            r = 7
            cv.create_line(mx - r, my, mx + r, my,
                           fill=FOCUS_COLOR, width=2)
            cv.create_line(mx, my - r, mx, my + r,
                           fill=FOCUS_COLOR, width=2)

    def _redraw(self):
        self._redraw_orig_panel()
        self._redraw_map_panel()

    # ------------------------------------------------------------------
    # Click handling
    # ------------------------------------------------------------------
    def _on_click(self, event):
        if self.arr is None:
            return
        widget = event.widget
        key = "orig" if widget is self.canvas_orig else "map"
        scale, ox, oy = self._layout.get(key, (1.0, 0, 0))
        if scale <= 0:
            return

        ix = int((event.x - ox) / scale)
        iy = int((event.y - oy) / scale)
        h, w = self.arr.shape
        if 0 <= ix < w and 0 <= iy < h:
            self.focus = (ix, iy)
            self._redraw()
            self._update_info()

    # ------------------------------------------------------------------
    # Info panel
    # ------------------------------------------------------------------
    def _update_info(self):
        t = self.info_text
        t.delete("1.0", tk.END)

        if self.arr is None:
            t.insert(tk.END, "Load an image to begin.\n")
            return

        h, w = self.arr.shape
        measure = self.measure_var.get()
        info = MEASURE_INFO[measure]

        t.insert(tk.END,
                 f"Image   : {os.path.basename(self.path)}  ({w} × {h})\n")
        t.insert(tk.END, f"Measure : {measure}   "
                         f"[{info['unit']}]\n")
        try:
            win = int(self.window_var.get())
        except (tk.TclError, ValueError):
            win = DEFAULT_WINDOW
        t.insert(tk.END, f"Window  : {win} × {win} pixels\n\n")

        t.insert(tk.END, info["blurb"] + "\n\n")

        if self.score_map is None:
            t.insert(tk.END,
                     "(No map yet — install scipy or press Recompute.)\n")
            return

        # ---- clicked location ----
        if self.focus is not None:
            fx, fy = self.focus
            hh, ww = self.score_map.shape
            if 0 <= fx < ww and 0 <= fy < hh:
                val = float(self.score_map[fy, fx])
                mn = float(self.score_map.min())
                mx = float(self.score_map.max())
                flat = self.score_map.reshape(-1)
                rank = int(np.sum(flat > val)) + 1
                total = flat.size
                pct = 100.0 * rank / total

                t.insert(tk.END, "── CLICKED LOCATION ──\n")
                t.insert(tk.END, f"  Position       : ({fx}, {fy})\n")
                t.insert(tk.END,
                         f"  Local value    : {val:.4f}  {info['unit']}\n")
                t.insert(tk.END,
                         f"  Map range      : {mn:.4f}  …  {mx:.4f}\n")
                t.insert(tk.END,
                         f"  Rank           : #{rank} of {total} "
                         f"(top {pct:.2f}%)\n")
                t.insert(tk.END, "\n")
        else:
            t.insert(tk.END,
                     "Click anywhere on the image to inspect a location.\n\n")

        # ---- top-N regions ----
        if self.top_regions:
            t.insert(tk.END,
                     f"── TOP {len(self.top_regions)} "
                     f"INFORMATION-RICH REGIONS ──\n")
            t.insert(tk.END,
                     f"  {'rank':<5}{'score':>12}   "
                     f"{'position':>14}   {'window':>10}\n")
            t.insert(tk.END, "  " + "-" * 48 + "\n")
            for i, (score, y, x) in enumerate(self.top_regions, 1):
                t.insert(tk.END,
                         f"  #{i:<4}{score:>12.4f}   "
                         f"{'(' + str(x) + ', ' + str(y) + ')':>14}   "
                         f"{str(win) + '×' + str(win):>10}\n")
            t.insert(tk.END, "\n")
            t.insert(tk.END,
                     "The boxes on both panels show where these regions "
                     "sit.  Note how they are rarely the brightest part "
                     "of the image.\n")

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    def save_map(self):
        if self.map_pil is None:
            messagebox.showinfo("Nothing to save",
                                "Load an image and compute a map first.")
            return
        base = os.path.splitext(os.path.basename(self.path))[0]
        measure_slug = self.measure_var.get().replace(" ", "_").lower()
        win = int(self.window_var.get())
        out = os.path.join(
            os.getcwd(),
            f"{base}_information_{measure_slug}_w{win}.png"
        )
        self.map_pil.save(out)
        messagebox.showinfo("Saved", f"Map saved to:\n{out}")


def main():
    root = tk.Tk()
    try:
        InfoApp(root)
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
