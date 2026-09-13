#!/usr/bin/env python3
"""
Noise Removal — Hands-On GUI
=============================

Load a clean image.  Use the Mode dropdown to switch between:

  Add Noise     — shows original (input) vs noisy (output)
  Remove Noise  — shows noisy (input) vs denoised (output)

The two panels always show the input of the current operation on the
left and its output on the right, so the pipeline is left → right.

Layout:
  ┌──────────────────────┬──────────────────────┐
  │  INPUT               │  OUTPUT              │
  │  (clean / noisy)     │  (noisy / denoised)  │
  └──────────────────────┴──────────────────────┘
  ┌──────────────────────────────────────────────┐
  │  METRICS  (MSE / PSNR vs the clean truth)    │
  └──────────────────────────────────────────────┘

Noise types:  Gaussian, Salt & Pepper, Speckle, Uniform, Poisson
Filters:      Mean (box), Gaussian, Median, Bilateral, Wiener

Run:  python noise_gui.py
"""

import os
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk

import numpy as np
from PIL import Image, ImageFilter, ImageTk

try:
    from scipy.signal import wiener as scipy_wiener
    HAVE_SCIPY = True
except ImportError:
    HAVE_SCIPY = False


NOISE_TYPES = ["Gaussian", "Salt & Pepper", "Speckle", "Uniform", "Poisson"]
FILTER_TYPES = ["Mean (box)", "Gaussian", "Median", "Bilateral", "Wiener"]
MODES = ["Add Noise", "Remove Noise"]


# ==========================================================================
# Noise generators
# ==========================================================================

def add_gaussian_noise(arr, sigma):
    noise = np.random.normal(0, sigma, arr.shape).astype(np.float32)
    return np.clip(arr.astype(np.float32) + noise, 0, 255).astype(np.uint8)


def add_salt_pepper_noise(arr, amount):
    out = arr.copy()
    h, w = arr.shape
    n = int(arr.size * (amount / 100.0))
    if n <= 0:
        return out
    ys = np.random.randint(0, h, n)
    xs = np.random.randint(0, w, n)
    half = n // 2
    out[ys[:half], xs[:half]] = 0
    out[ys[half:], xs[half:]] = 255
    return out


def add_speckle_noise(arr, amount):
    scale = amount / 100.0
    noise = np.random.normal(0, scale, arr.shape).astype(np.float32)
    return np.clip(arr.astype(np.float32) * (1 + noise), 0, 255).astype(np.uint8)


def add_uniform_noise(arr, amount):
    noise = np.random.uniform(-amount, amount, arr.shape).astype(np.float32)
    return np.clip(arr.astype(np.float32) + noise, 0, 255).astype(np.uint8)


def add_poisson_noise(arr, amount):
    scale = max(1.0, amount)
    vals = np.random.poisson(arr.astype(np.float32) * scale) / scale
    return np.clip(vals, 0, 255).astype(np.uint8)


def generate_noise(clean, kind, amount):
    if kind == "Gaussian":
        return add_gaussian_noise(clean, amount)
    if kind == "Salt & Pepper":
        return add_salt_pepper_noise(clean, min(amount, 40) / 2.0)
    if kind == "Speckle":
        return add_speckle_noise(clean, amount)
    if kind == "Uniform":
        return add_uniform_noise(clean, amount)
    if kind == "Poisson":
        return add_poisson_noise(clean, max(1.0, amount))
    raise ValueError(kind)


# ==========================================================================
# Filters
# ==========================================================================

def _to_pil(arr):
    return Image.fromarray(arr, mode="L")


def filter_mean(arr, ksize):
    radius = max(1, (ksize - 1) // 2)
    return np.array(_to_pil(arr).filter(ImageFilter.BoxBlur(radius)),
                    dtype=np.uint8)


def filter_gaussian(arr, ksize):
    radius = max(1, (ksize - 1) // 2)
    return np.array(_to_pil(arr).filter(ImageFilter.GaussianBlur(radius)),
                    dtype=np.uint8)


def filter_median(arr, ksize):
    size = ksize if ksize % 2 == 1 else ksize + 1
    size = max(3, size)
    return np.array(_to_pil(arr).filter(ImageFilter.MedianFilter(size)),
                    dtype=np.uint8)


def filter_bilateral(arr, ksize, sigma_color=25.0, sigma_space=5.0):
    d = ksize if ksize % 2 == 1 else ksize + 1
    d = max(3, min(d, 11))
    r = d // 2

    arr_f = arr.astype(np.float32)
    h, w = arr_f.shape
    pad = np.pad(arr_f, r, mode="reflect")

    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    spatial = np.exp(-(xx ** 2 + yy ** 2) / (2 * sigma_space ** 2))

    output = np.zeros_like(arr_f)
    weight_total = np.zeros_like(arr_f)

    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            shifted = pad[r + dy:r + dy + h, r + dx:r + dx + w]
            color_diff = shifted - arr_f
            w_color = np.exp(-(color_diff ** 2) / (2 * sigma_color ** 2))
            w_total = spatial[dy + r, dx + r] * w_color
            output += w_total * shifted
            weight_total += w_total

    output /= np.maximum(weight_total, 1e-6)
    return np.clip(output, 0, 255).astype(np.uint8)


def filter_wiener(arr, ksize):
    if not HAVE_SCIPY:
        raise RuntimeError(
            "Wiener filter needs scipy.  Install it with:\n"
            "    pip install scipy"
        )
    size = max(3, ksize if ksize % 2 == 1 else ksize + 1)
    out = scipy_wiener(arr.astype(np.float32), mysize=(size, size))
    return np.clip(out, 0, 255).astype(np.uint8)


def apply_filter(arr, name, ksize):
    if name == "Mean (box)":
        return filter_mean(arr, ksize)
    if name == "Gaussian":
        return filter_gaussian(arr, ksize)
    if name == "Median":
        return filter_median(arr, ksize)
    if name == "Bilateral":
        return filter_bilateral(arr, ksize)
    if name == "Wiener":
        return filter_wiener(arr, ksize)
    raise ValueError(name)


# ==========================================================================
# Metrics
# ==========================================================================

def mse(a, b):
    diff = a.astype(np.float32) - b.astype(np.float32)
    return float(np.mean(diff * diff))


def psnr(a, b):
    m = mse(a, b)
    if m <= 1e-12:
        return float("inf")
    return 10.0 * np.log10((255.0 ** 2) / m)


# ==========================================================================
# Application
# ==========================================================================

class NoiseApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Noise Removal — Hands-On")
        self.root.geometry("1200x900")
        self.root.minsize(950, 700)

        # ---- state ----
        self.clean = None       # the original loaded image
        self.noisy = None       # clean + noise (produced in Add Noise mode)
        self.denoised = None    # noisy + filter (produced in Remove Noise mode)
        self.path = None

        self._photos = {}

        # ---- option vars ----
        self.mode_var = tk.StringVar(value=MODES[0])
        self.noise_type = tk.StringVar(value="Gaussian")
        self.noise_amount = tk.DoubleVar(value=20.0)
        self.filter_type = tk.StringVar(value="Gaussian")
        self.filter_size = tk.IntVar(value=5)

        self.mode_var.trace_add("write", lambda *_: self._on_mode_change())
        self.noise_type.trace_add("write",
                                  lambda *_: self._on_noise_param_change())
        self.noise_amount.trace_add("write",
                                    lambda *_: self._on_noise_param_change())

        self._build_ui()
        self._on_mode_change()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = self.root
        root.grid_rowconfigure(0, weight=0)     # control bar
        root.grid_rowconfigure(1, weight=3)     # 2 image panels
        root.grid_rowconfigure(2, weight=1)     # metrics
        root.grid_rowconfigure(3, weight=0)     # status bar
        root.grid_columnconfigure(0, weight=1)

        # ---------- control bar ----------
        bar = tk.Frame(root, bg="#f0f0f0")
        bar.grid(row=0, column=0, sticky="ew")

        tk.Button(bar, text="Load Image", command=self.load_image
                  ).pack(side=tk.LEFT, padx=4, pady=6)

        tk.Label(bar, text="   Mode:").pack(side=tk.LEFT)
        ttk.Combobox(bar, textvariable=self.mode_var, state="readonly",
                     width=14, values=MODES
                     ).pack(side=tk.LEFT, padx=2)

        # ---- mode-specific parameter frame ----
        self.params_frame = tk.Frame(bar, bg="#f0f0f0")
        self.params_frame.pack(side=tk.LEFT, padx=10)

        # ---- the single Apply button (its action depends on mode) ----
        self.apply_btn = tk.Button(bar, text="Apply", command=self._apply)
        self.apply_btn.pack(side=tk.LEFT, padx=8)

        tk.Button(bar, text="Save Output", command=self.save_output
                  ).pack(side=tk.RIGHT, padx=4, pady=6)

        # ---------- 2 image panels ----------
        img_row = tk.Frame(root, bg="#0d0d0d")
        img_row.grid(row=1, column=0, sticky="nsew")
        img_row.grid_columnconfigure(0, weight=1, uniform="imgcol")
        img_row.grid_columnconfigure(1, weight=1, uniform="imgcol")

        self.canvas_left, self.label_left = self._make_panel(
            img_row, 0, "INPUT")
        self.canvas_right, self.label_right = self._make_panel(
            img_row, 1, "OUTPUT")

        # ---------- metrics ----------
        metrics_frame = tk.Frame(root, bg="#111")
        metrics_frame.grid(row=2, column=0, sticky="nsew",
                           padx=6, pady=6)
        metrics_frame.grid_rowconfigure(0, weight=1)
        metrics_frame.grid_columnconfigure(0, weight=1)

        self.metrics_text = tk.Text(
            metrics_frame, bg="#111", fg="#e0e0e0",
            font=("Courier", 10), wrap="word",
            borderwidth=0, highlightthickness=0, height=8,
        )
        sb = tk.Scrollbar(metrics_frame, orient="vertical",
                          command=self.metrics_text.yview)
        self.metrics_text.configure(yscrollcommand=sb.set)
        self.metrics_text.grid(row=0, column=0, sticky="nsew",
                               padx=(8, 0), pady=6)
        sb.grid(row=0, column=1, sticky="ns", pady=6)

        # ---------- status bar ----------
        self.status = tk.Label(root, anchor="w", relief=tk.SUNKEN, bd=1,
                               padx=6, pady=4,
                               text="Load an image to begin.")
        self.status.grid(row=3, column=0, sticky="ew")

        for c in (self.canvas_left, self.canvas_right):
            c.bind("<Configure>", lambda e: self._redraw())

        root.update_idletasks()
        self._show_metrics()

    def _make_panel(self, parent, col, title):
        frame = tk.Frame(parent, bg="#0d0d0d")
        frame.grid(row=0, column=col, sticky="nsew", padx=2, pady=2)
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
    # Mode switching
    # ------------------------------------------------------------------
    def _on_mode_change(self):
        # rebuild the parameter widgets
        for w in self.params_frame.winfo_children():
            w.destroy()

        mode = self.mode_var.get()

        if mode == "Add Noise":
            tk.Label(self.params_frame, text="Noise:",
                     bg="#f0f0f0").pack(side=tk.LEFT)
            ttk.Combobox(self.params_frame, textvariable=self.noise_type,
                         state="readonly", width=14, values=NOISE_TYPES
                         ).pack(side=tk.LEFT, padx=2)
            tk.Label(self.params_frame, text="Amount:",
                     bg="#f0f0f0").pack(side=tk.LEFT, padx=(8, 0))
            tk.Scale(self.params_frame, from_=1, to=80,
                     orient=tk.HORIZONTAL, variable=self.noise_amount,
                     length=180, showvalue=True
                     ).pack(side=tk.LEFT, padx=2)
            self.apply_btn.config(text="Regenerate Noise")

        else:  # Remove Noise
            tk.Label(self.params_frame, text="Filter:",
                     bg="#f0f0f0").pack(side=tk.LEFT)
            ttk.Combobox(self.params_frame, textvariable=self.filter_type,
                         state="readonly", width=13, values=FILTER_TYPES
                         ).pack(side=tk.LEFT, padx=2)
            tk.Label(self.params_frame, text="Kernel:",
                     bg="#f0f0f0").pack(side=tk.LEFT, padx=(8, 0))
            tk.Spinbox(self.params_frame, from_=3, to=15, width=4,
                       textvariable=self.filter_size
                       ).pack(side=tk.LEFT, padx=2)
            self.apply_btn.config(text="Apply Filter")

        self._redraw()
        self._show_metrics()
        self.status.config(text=self._mode_status())

    def _mode_status(self):
        mode = self.mode_var.get()
        if mode == "Add Noise":
            return ("Add Noise mode — the left panel is the clean original, "
                    "the right panel is the noisy version.")
        else:
            return ("Remove Noise mode — the left panel is the noisy input, "
                    "the right panel is the filter output.")

    # ------------------------------------------------------------------
    # Noise parameter changes — auto-regenerate noise
    # ------------------------------------------------------------------
    def _on_noise_param_change(self):
        if self.mode_var.get() != "Add Noise" or self.clean is None:
            return
        self._generate_noise()
        self._redraw()
        self._show_metrics()

    def _generate_noise(self):
        if self.clean is None:
            return
        try:
            amount = float(self.noise_amount.get())
        except (tk.TclError, ValueError):
            amount = 20.0
        kind = self.noise_type.get()
        try:
            self.noisy = generate_noise(self.clean, kind, amount)
        except Exception:
            traceback.print_exc()
            return
        # any noise change invalidates the previous denoise result
        self.denoised = None

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
            arr = np.array(img.convert("L"), dtype=np.uint8)
        except Exception as exc:
            messagebox.showerror("Error", f"Could not load image:\n{exc}")
            return

        self.clean = arr
        self.path = path
        self.noisy = None
        self.denoised = None

        # Auto-generate the noise if we're already in Add Noise mode
        if self.mode_var.get() == "Add Noise":
            self._generate_noise()

        self._redraw()
        self._show_metrics()
        self.status.config(
            text=f"Loaded {os.path.basename(path)}  ({arr.shape[1]}×"
                 f"{arr.shape[0]}).  " + self._mode_status()
        )

    # ------------------------------------------------------------------
    # Apply button — action depends on mode
    # ------------------------------------------------------------------
    def _apply(self):
        if self.clean is None:
            messagebox.showinfo("No image", "Load an image first.")
            return

        mode = self.mode_var.get()

        if mode == "Add Noise":
            self._generate_noise()
            self._redraw()
            self._show_metrics()
            self.status.config(
                text=f"{self.noise_type.get()} noise regenerated "
                     f"(amount {self.noise_amount.get():.0f})."
            )
            return

        # ---- Remove Noise ----
        if self.noisy is None:
            # No noise was added — treat the clean image as the input
            inp = self.clean
            note = "(no noise was added — filtering the clean image)"
        else:
            inp = self.noisy
            note = ""

        try:
            ksize = int(self.filter_size.get())
        except (tk.TclError, ValueError):
            ksize = 5
        name = self.filter_type.get()

        try:
            self.denoised = apply_filter(inp, name, ksize)
        except RuntimeError as exc:
            messagebox.showerror("Missing dependency", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Filter failed", str(exc))
            traceback.print_exc()
            return

        self._redraw()
        self._show_metrics()
        self.status.config(
            text=f"Applied {name} (kernel {ksize}) to the noisy input.  "
                 f"{note}".strip()
        )

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------
    def _show_metrics(self):
        t = self.metrics_text
        t.delete("1.0", tk.END)

        if self.clean is None:
            t.insert(tk.END, "Load an image to begin.\n")
            return

        h, w = self.clean.shape
        mode = self.mode_var.get()

        t.insert(tk.END,
                 f"Image : {os.path.basename(self.path)}  ({w} × {h})\n")
        t.insert(tk.END, f"Mode  : {mode}\n\n")

        if mode == "Add Noise":
            t.insert(tk.END,
                     f"Noise : {self.noise_type.get()}   "
                     f"amount = {self.noise_amount.get():.0f}\n\n")
            if self.noisy is not None:
                m = mse(self.clean, self.noisy)
                p = psnr(self.clean, self.noisy)
                t.insert(tk.END,
                         f"  Noisy vs Original   MSE = {m:>10.2f}   "
                         f"PSNR = {p:>6.2f} dB\n\n")
                t.insert(tk.END,
                         "  Lower PSNR means more damage.  Switch to "
                         "\"Remove Noise\" and apply a filter to see how "
                         "much can be recovered.\n")
        else:
            t.insert(tk.END,
                     f"Filter : {self.filter_type.get()}   "
                     f"kernel = {self.filter_size.get()}\n\n")

            inp = self.noisy if self.noisy is not None else self.clean

            if self.denoised is None:
                t.insert(tk.END,
                         "  No filter applied yet.  Click \"Apply Filter\".\n")
                return

            def row(label, a, b):
                m = mse(a, b)
                p = psnr(a, b)
                ps = "inf" if np.isinf(p) else f"{p:>6.2f}"
                t.insert(tk.END,
                         f"  {label:<28} MSE = {m:>10.2f}   "
                         f"PSNR = {ps} dB\n")

            t.insert(tk.END, "  Comparisons:\n")
            row("Denoised vs Input",
                self.denoised, inp)
            if self.noisy is not None:
                row("Denoised vs Original (clean)",
                    self.denoised, self.clean)
                row("Input vs Original (clean)",
                    self.noisy, self.clean)
            else:
                row("Denoised vs Original", self.denoised, self.clean)

            t.insert(tk.END, "\n")

            if self.noisy is not None:
                imp = psnr(self.denoised, self.clean) - \
                      psnr(self.noisy, self.clean)
                t.insert(tk.END,
                         f"  PSNR improvement over noisy input: "
                         f"{imp:+.2f} dB\n")
                if imp <= 0.5:
                    t.insert(tk.END,
                             "    → Almost no improvement.  Try a "
                             "different filter or larger kernel.\n")
                elif imp < 3.0:
                    t.insert(tk.END,
                             "    → Modest improvement.  Filter is helping "
                             "but noise is still visible.\n")
                else:
                    t.insert(tk.END,
                             "    → Strong improvement.  This filter "
                             "handles this noise well.\n")

            t.insert(tk.END, "\n")
            t.insert(tk.END,
                     "  PSNR ≥ 30 dB → visually close to original\n")
            t.insert(tk.END,
                     "  PSNR 20–30 dB → noise visible on close inspection\n")
            t.insert(tk.END,
                     "  PSNR < 20 dB → obvious degradation\n")

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

    def _redraw(self):
        if self.clean is None:
            self.canvas_left.delete("all")
            self.canvas_right.delete("all")
            self.label_left.config(text="INPUT:  —")
            self.label_right.config(text="OUTPUT:  —")
            return

        mode = self.mode_var.get()
        h, w = self.clean.shape

        # ---- left panel ----
        if mode == "Add Noise":
            left_arr = self.clean
            left_title = f"INPUT — Original (clean)  ({w}×{h})"
        else:
            if self.noisy is not None:
                left_arr = self.noisy
                left_title = (f"INPUT — Noisy "
                              f"[{self.noise_type.get()}]  ({w}×{h})")
            else:
                left_arr = self.clean
                left_title = (f"INPUT — Original "
                              f"(no noise added yet)  ({w}×{h})")

        self._draw_image(self.canvas_left, left_arr, "left")
        self.label_left.config(text=left_title)

        # ---- right panel ----
        if mode == "Add Noise":
            if self.noisy is not None:
                self._draw_image(self.canvas_right, self.noisy, "right")
                self.label_right.config(
                    text=f"OUTPUT — Noisy [{self.noise_type.get()}]  "
                         f"({w}×{h})")
            else:
                self.canvas_right.delete("all")
                self.label_right.config(text="OUTPUT:  —")
        else:
            if self.denoised is not None:
                self._draw_image(self.canvas_right, self.denoised, "right")
                self.label_right.config(
                    text=f"OUTPUT — Denoised [{self.filter_type.get()}]  "
                         f"({w}×{h})")
            else:
                self.canvas_right.delete("all")
                self.label_right.config(text="OUTPUT — Denoised:  —")
                cw = self.canvas_right.winfo_width()
                ch = self.canvas_right.winfo_height()
                if cw > 2 and ch > 2:
                    self.canvas_right.create_text(
                        cw // 2, ch // 2,
                        text="(click Apply Filter)",
                        fill="#666", font=("TkDefaultFont", 10),
                    )

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    def save_output(self):
        mode = self.mode_var.get()
        arr = self.noisy if mode == "Add Noise" else self.denoised

        if arr is None:
            messagebox.showinfo("Nothing to save",
                                "Nothing has been produced yet.")
            return

        base = os.path.splitext(os.path.basename(self.path))[0]
        if mode == "Add Noise":
            kind_slug = (self.noise_type.get().replace(" ", "")
                         .replace("&", ""))
            out = os.path.join(os.getcwd(),
                               f"{base}_noisy_{kind_slug}.png")
        else:
            filter_slug = self.filter_type.get().split()[0].lower()
            out = os.path.join(
                os.getcwd(),
                f"{base}_denoised_{filter_slug}_"
                f"{self.filter_size.get()}.png"
            )

        Image.fromarray(arr, mode="L").save(out)
        messagebox.showinfo("Saved", f"Saved to:\n{out}")


def main():
    root = tk.Tk()
    try:
        NoiseApp(root)
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
