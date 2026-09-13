#!/usr/bin/env python3
"""
Image Cropper — Hands-On GUI (Draggable Explosion)
==================================================

Load an image, drag a rectangle to select what to crop, and click
"Crop & Explode". The program:

  1. Crops the selected region out of the image.
  2. Extracts the 8 pieces that surrounded it.
  3. Lays them on a larger canvas: the 8 outer pieces are pushed
     radially outward by `explode` pixels, leaving a void GAP of
     exactly `explode` px between the inner crop and every outer piece.
  4. Makes the cropped region DRAGGABLE — click and drag it around.
     A cyan dashed outline keeps it highlighted at all times.

Buttons:
  Load Image          — pick the source image
  Enter Coords…       — type the crop box instead of dragging
  Crop & Explode      — run the explosion
  Clear Outer Pieces  — wipe the 8 outer pieces (leaves void + crop)
  Undo                — step back through every action
  Save Cropped Image  — save ONLY the cropped region as PNG
  Reset               — throw away all state

Void colour defaults to BLACK. Change it any time via the Void button.

Run:  python cropping_gui.py
"""

import os
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, simpledialog

from PIL import Image, ImageTk


DEFAULT_EXPLODE = 80                 # px the outer pieces fly outward
DEFAULT_VOID    = "#000000"          # black
HIGHLIGHT_COLOR = "#00e0ff"          # cyan
MAX_HISTORY     = 60


class CropperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Cropper — Draggable Explosion")
        self.root.geometry("1180x820")

        # ---- source image -------------------------------------------------
        self.src = None
        self.src_path = None

        # ---- pre-explode selection ---------------------------------------
        self.selection = None
        self.drag_start = None
        self._drag_rect_id = None

        # ---- post-explode state ------------------------------------------
        self.base_layer = None          # void + the 8 outer pieces
        self.inner_piece = None         # the draggable crop
        self.inner_pos = (0.0, 0.0)     # top-left in canvas coords

        # ---- drag state --------------------------------------------------
        self.dragging = False
        self.drag_offset = (0.0, 0.0)

        # ---- preview layout ----------------------------------------------
        self.scale = 1.0
        self.img_x = 0
        self.img_y = 0
        self.disp_w = 0
        self.disp_h = 0

        # ---- Tk item references ------------------------------------------
        self._photo_base = None
        self._photo_inner = None
        self._inner_item_id = None
        self._highlight_id = None

        # ---- history for Undo --------------------------------------------
        self.history = []

        self.void_color = DEFAULT_VOID

        self._build_ui()

    # ----------------------------------------------------------------- UI --
    def _build_ui(self):
        bar = tk.Frame(self.root, bg="#f0f0f0")
        bar.pack(side=tk.TOP, fill=tk.X)

        tk.Button(bar, text="Load Image", command=self.load_image
                  ).pack(side=tk.LEFT, padx=3, pady=6)
        tk.Button(bar, text="Enter Coords…", command=self.enter_coords
                  ).pack(side=tk.LEFT, padx=3, pady=6)
        tk.Button(bar, text="Crop & Explode", command=self.explode
                  ).pack(side=tk.LEFT, padx=3, pady=6)
        tk.Button(bar, text="Clear Outer Pieces", command=self.clear_outer
                  ).pack(side=tk.LEFT, padx=3, pady=6)
        tk.Button(bar, text="Undo", command=self.undo
                  ).pack(side=tk.LEFT, padx=3, pady=6)
        tk.Button(bar, text="Reset", command=self.reset
                  ).pack(side=tk.LEFT, padx=3, pady=6)
        tk.Button(bar, text="Save Cropped Image", command=self.save_cropped
                  ).pack(side=tk.LEFT, padx=3, pady=6)

        tk.Label(bar, text="   Explode (px):").pack(side=tk.LEFT)
        self.explode_var = tk.IntVar(value=DEFAULT_EXPLODE)
        tk.Spinbox(bar, from_=0, to=2000, width=6, textvariable=self.explode_var,
                   command=self._re_explode
                   ).pack(side=tk.LEFT, padx=2)

        tk.Label(bar, text="  Void:").pack(side=tk.LEFT, padx=(10, 2))
        self.void_btn = tk.Button(
            bar, text="  ", bg=self.void_color, width=3,
            command=self.pick_void_color, relief=tk.RIDGE,
        )
        self.void_btn.pack(side=tk.LEFT, padx=2)

        self.status = tk.Label(
            self.root, anchor="w", relief=tk.SUNKEN, bd=1, padx=6, pady=4,
            justify=tk.LEFT,
            text="Step 1: Load an image, then drag a rectangle on it.",
        )
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

        self.canvas = tk.Canvas(self.root, bg="#1a1a1a", highlightthickness=0,
                                cursor="crosshair")
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.canvas.bind("<Button-1>",        self.on_press)
        self.canvas.bind("<B1-Motion>",       self.on_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Configure>",       lambda e: self.redraw())

    # -------------------------------------------------------- UI callbacks --
    def _re_explode(self):
        if self.base_layer is not None and self.selection is not None:
            self.explode()

    def pick_void_color(self):
        _, hx = colorchooser.askcolor(color=self.void_color, title="Pick void colour")
        if hx:
            self._push_history()
            self.void_color = hx
            self.void_btn.config(bg=hx)
            if self.base_layer is not None and self.selection is not None:
                self.explode()

    # ------------------------------------------------------------- history --
    def _push_history(self):
        """Store the current state so Undo can come back to it."""
        snap = {
            "base_layer":  self.base_layer,          # PIL images are treated as immutable
            "inner_piece": self.inner_piece,
            "inner_pos":   self.inner_pos,
            "selection":   self.selection,
        }
        self.history.append(snap)
        if len(self.history) > MAX_HISTORY:
            self.history.pop(0)

    def undo(self):
        if not self.history:
            self.status.config(text="Nothing to undo.")
            return
        snap = self.history.pop()
        self.base_layer  = snap["base_layer"]
        self.inner_piece = snap["inner_piece"]
        self.inner_pos   = snap["inner_pos"]
        self.selection   = snap["selection"]
        self.dragging = False
        self.status.config(text="Undo.  " + self._mode_hint())
        self.redraw()

    def _mode_hint(self):
        if self.base_layer is None:
            return "Drag a rectangle on the image to choose what to crop."
        return "Inner crop is draggable.  Click and drag it anywhere."

    # ------------------------------------------------------- image loading --
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

        self._push_history()
        self.src = img.convert("RGB")
        self.src_path = path
        self.selection = None
        self.base_layer = None
        self.inner_piece = None
        self.inner_pos = (0.0, 0.0)
        self.dragging = False
        w, h = self.src.size
        self.status.config(
            text=f"Loaded {os.path.basename(path)}  ({w} × {h}).  "
                 f"Drag a rectangle on the image to choose what to crop."
        )
        self.redraw()

    # ------------------------------------------------ coordinate helpers --
    def _screen_to_img(self, sx, sy):
        if self.scale <= 0:
            return None
        return (sx - self.img_x) / self.scale, (sy - self.img_y) / self.scale

    def _clamp_orig(self, x, y):
        W, H = self.src.size
        return max(0, min(W, x)), max(0, min(H, y))

    # ------------------------------------------------------ mouse handlers --
    def on_press(self, event):
        if self.src is None:
            return

        # ----- post-explode: pick up the inner piece if clicked on it ----
        if self.base_layer is not None and self.inner_piece is not None:
            pt = self._screen_to_img(event.x, event.y)
            if pt is None:
                return
            ix, iy = pt
            px, py = self.inner_pos
            pw, ph = self.inner_piece.size
            if px <= ix <= px + pw and py <= iy <= py + ph:
                self._push_history()          # snapshot before the drag
                self.dragging = True
                self.drag_offset = (ix - px, iy - py)
                self.canvas.config(cursor="fleur")
            return

        # ----- pre-explode: start a new crop selection -------------------
        pt = self._screen_to_img(event.x, event.y)
        if pt is None:
            return
        self.drag_start = self._clamp_orig(*pt)
        self.selection = None
        if self._drag_rect_id is not None:
            self.canvas.delete(self._drag_rect_id)
            self._drag_rect_id = None

    def on_motion(self, event):
        # ----- dragging the inner piece ----------------------------------
        if self.dragging and self.inner_piece is not None:
            pt = self._screen_to_img(event.x, event.y)
            if pt is None:
                return
            ix, iy = pt
            self.inner_pos = (ix - self.drag_offset[0], iy - self.drag_offset[1])
            self._update_inner_display()
            return

        # ----- drawing a crop selection ----------------------------------
        if self.drag_start is None or self.src is None or self.base_layer is not None:
            return
        pt = self._screen_to_img(event.x, event.y)
        if pt is None:
            return
        x1, y1 = self.drag_start
        x2, y2 = self._clamp_orig(*pt)

        cx1 = self.img_x + x1 * self.scale
        cy1 = self.img_y + y1 * self.scale
        cx2 = self.img_x + x2 * self.scale
        cy2 = self.img_y + y2 * self.scale

        if self._drag_rect_id is None:
            self._drag_rect_id = self.canvas.create_rectangle(
                cx1, cy1, cx2, cy2,
                outline="#ffd400", width=3, dash=(8, 4),
            )
        else:
            self.canvas.coords(self._drag_rect_id, cx1, cy1, cx2, cy2)

    def on_release(self, event):
        # ----- end of an inner-piece drag ---------------------------------
        if self.dragging:
            self.dragging = False
            self.canvas.config(cursor="crosshair")
            self.status.config(
                text=f"Inner crop moved to (x={int(self.inner_pos[0])}, "
                     f"y={int(self.inner_pos[1])}).  "
                     f"Undo to step back, or Save to export the crop."
            )
            return

        # ----- end of a crop-selection drag -------------------------------
        if self.drag_start is None or self.src is None or self.base_layer is not None:
            return
        x1, y1 = self.drag_start
        pt = self._screen_to_img(event.x, event.y)
        self.drag_start = None
        if pt is None:
            return
        x2, y2 = self._clamp_orig(*pt)

        left   = int(min(x1, x2))
        top    = int(min(y1, y2))
        right  = int(max(x1, x2))
        bottom = int(max(y1, y2))

        W, H = self.src.size
        left   = min(left, W)
        right  = min(right, W)
        top    = min(top, H)
        bottom = min(bottom, H)

        if right - left < 2 or bottom - top < 2:
            if self._drag_rect_id is not None:
                self.canvas.delete(self._drag_rect_id)
                self._drag_rect_id = None
            self.selection = None
            self.status.config(text="Selection too small — drag a bigger rectangle.")
            return

        self.selection = (left, top, right, bottom)
        cw, ch = right - left, bottom - top
        self.status.config(
            text=f"Selected box (left={left}, top={top}, right={right}, "
                 f"bottom={bottom})  →  crop {cw} × {ch} px.  "
                 f"Click 'Crop & Explode'."
        )

    # ------------------------------------------------------ other actions --
    def reset(self):
        self._push_history()
        self.selection = None
        self.base_layer = None
        self.inner_piece = None
        self.inner_pos = (0.0, 0.0)
        self.dragging = False
        if self._drag_rect_id is not None:
            self.canvas.delete(self._drag_rect_id)
            self._drag_rect_id = None
        self.status.config(
            text="Reset.  Drag a rectangle on the image to choose a crop."
        )
        self.redraw()

    def enter_coords(self):
        if self.src is None:
            messagebox.showinfo("No image", "Load an image first.")
            return
        W, H = self.src.size

        if self.selection:
            l, t, r, b = self.selection
        else:
            l, t, r, b = W // 4, H // 4, 3 * W // 4, 3 * H // 4

        raw = simpledialog.askstring(
            "Enter crop box",
            f"Image is {W} × {H}.\n\n"
            f"Enter four integers:  left  top  right  bottom\n"
            f"(right and bottom are EXCLUSIVE, i.e. one past the last pixel)",
            initialvalue=f"{l} {t} {r} {b}",
        )
        if not raw:
            return
        parts = raw.replace(",", " ").split()
        if len(parts) != 4:
            messagebox.showerror("Bad input", "Need exactly four numbers.")
            return
        try:
            l, t, r, b = (int(x) for x in parts)
        except ValueError:
            messagebox.showerror("Bad input", "All four must be integers.")
            return

        l = max(0, min(l, W)); r = max(0, min(r, W))
        t = max(0, min(t, H)); b = max(0, min(b, H))
        if r - l < 2 or b - t < 2:
            messagebox.showerror("Bad box", "Box must be at least 2 × 2 px.")
            return

        self._push_history()
        self.selection = (l, t, r, b)
        self.base_layer = None
        self.inner_piece = None
        cw, ch = r - l, b - t
        self.status.config(
            text=f"Selected box (left={l}, top={t}, right={r}, bottom={b})  "
                 f"→  crop {cw} × {ch} px.  Click 'Crop & Explode'."
        )
        self.redraw()

    # ------------------------------------------------------ the explosion --
    def explode(self):
        if self.src is None:
            messagebox.showinfo("No image", "Load an image first.")
            return
        if self.selection is None:
            messagebox.showinfo(
                "No selection",
                "Drag a rectangle on the image (or use 'Enter Coords…') first."
            )
            return

        self._push_history()

        W, H = self.src.size
        L, T, R, B = self.selection
        d = max(0, self.explode_var.get())

        # ---- extract every piece at ORIGINAL resolution ------------------
        inner  = self.src.crop((L, T, R, B))
        top    = self.src.crop((L, 0, R, T))
        bottom = self.src.crop((L, B, R, H))
        left   = self.src.crop((0, T, L, B))
        right  = self.src.crop((R, T, W, B))
        tl     = self.src.crop((0, 0, L, T))
        tr     = self.src.crop((R, 0, W, T))
        bl     = self.src.crop((0, B, L, H))
        br     = self.src.crop((R, B, W, H))

        # ---- canvas sized to hold everything after displacement ----------
        canvas_w = W + 2 * d
        canvas_h = H + 2 * d

        # ---- build the STATIC base layer: void + the 8 outer pieces ------
        base = Image.new("RGB", (canvas_w, canvas_h), self._void_rgb())

        def put(piece, x, y):
            if piece.size[0] > 0 and piece.size[1] > 0:
                base.paste(piece, (int(x), int(y)))

        # Each outer piece keeps its ORIGINAL relative position but is
        # pushed outward by `d` along every axis it faces — this is what
        # creates a GAP of exactly `d` px of void between the inner crop
        # and each outer piece.
        put(tl,     0,          0)
        put(top,    L + d,      0)
        put(tr,     R + 2 * d,  0)

        put(left,   0,          T + d)
        put(right,  R + 2 * d,  T + d)

        put(bl,     0,          B + 2 * d)
        put(bottom, L + d,      B + 2 * d)
        put(br,     R + 2 * d,  B + 2 * d)

        self.base_layer  = base
        self.inner_piece = inner
        self.inner_pos   = (float(L + d), float(T + d))   # original spot
        self.dragging = False

        self.status.config(
            text=f"Exploded.  Void GAP of {d}px around the crop.  "
                 f"Inner crop ({R-L}×{B-T}) is DRAGGABLE — click and drag it."
        )
        self.redraw()

    def _void_rgb(self):
        hx = self.void_color.lstrip("#")
        return tuple(int(hx[i:i + 2], 16) for i in (0, 2, 4))

    # --------------------------------------------------- clear outer pieces --
    def clear_outer(self):
        if self.base_layer is None:
            messagebox.showinfo(
                "Nothing to clear",
                "Explode the image first — there are no outer pieces yet."
            )
            return
        self._push_history()
        W, H = self.base_layer.size
        self.base_layer = Image.new("RGB", (W, H), self._void_rgb())
        self.status.config(
            text="Outer pieces cleared.  Undo brings them back."
        )
        self.redraw()

    # ---------------------------------------------------- inner dragging --
    def _update_inner_display(self):
        if self._inner_item_id is None or self._highlight_id is None:
            return
        ix = self.img_x + self.inner_pos[0] * self.scale
        iy = self.img_y + self.inner_pos[1] * self.scale
        pw_disp = max(1, int(self.inner_piece.size[0] * self.scale))
        ph_disp = max(1, int(self.inner_piece.size[1] * self.scale))
        self.canvas.coords(self._inner_item_id, ix, iy)
        self.canvas.coords(self._highlight_id,
                           ix, iy, ix + pw_disp, iy + ph_disp)

    # ------------------------------------------------------------- drawing --
    def redraw(self):
        self.canvas.delete("all")
        self._inner_item_id = None
        self._highlight_id = None
        self._drag_rect_id = None

        if self.src is None:
            return

        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 2 or ch < 2:
            return

        layout_img = self.base_layer if self.base_layer is not None else self.src
        iw, ih = layout_img.size

        self.scale = min(cw / iw, ch / ih, 1.0)
        self.disp_w = max(1, int(iw * self.scale))
        self.disp_h = max(1, int(ih * self.scale))
        self.img_x = (cw - self.disp_w) // 2
        self.img_y = (ch - self.disp_h) // 2

        base_disp = layout_img.resize((self.disp_w, self.disp_h), Image.LANCZOS)
        self._photo_base = ImageTk.PhotoImage(base_disp)
        self.canvas.create_image(self.img_x, self.img_y,
                                 anchor=tk.NW, image=self._photo_base)

        if self.base_layer is None:
            # ---- pre-explode: draw the selection outline -----------------
            if self.selection is not None:
                L, T, R, B = self.selection
                x1 = self.img_x + L * self.scale
                y1 = self.img_y + T * self.scale
                x2 = self.img_x + R * self.scale
                y2 = self.img_y + B * self.scale
                self._drag_rect_id = self.canvas.create_rectangle(
                    x1, y1, x2, y2,
                    outline="#ffd400", width=3, dash=(8, 4),
                )
        else:
            # ---- post-explode: inner piece + cyan highlight --------------
            pw_disp = max(1, int(self.inner_piece.size[0] * self.scale))
            ph_disp = max(1, int(self.inner_piece.size[1] * self.scale))
            inner_disp = self.inner_piece.resize((pw_disp, ph_disp), Image.LANCZOS)
            self._photo_inner = ImageTk.PhotoImage(inner_disp)

            ix = self.img_x + self.inner_pos[0] * self.scale
            iy = self.img_y + self.inner_pos[1] * self.scale

            self._inner_item_id = self.canvas.create_image(
                ix, iy, anchor=tk.NW, image=self._photo_inner
            )
            self._highlight_id = self.canvas.create_rectangle(
                ix, iy, ix + pw_disp, iy + ph_disp,
                outline=HIGHLIGHT_COLOR, width=3, dash=(8, 4),
            )

    # -------------------------------------------------------------- save --
    def save_cropped(self):
        """Save ONLY the cropped region — not the exploded composite."""
        if self.inner_piece is None:
            # If we never exploded but a selection exists, honour it
            if self.src is not None and self.selection is not None:
                L, T, R, B = self.selection
                piece = self.src.crop((L, T, R, B))
            else:
                messagebox.showinfo(
                    "Nothing to save",
                    "Select a region (and optionally explode) first."
                )
                return
        else:
            piece = self.inner_piece

        base = os.path.splitext(os.path.basename(self.src_path))[0]
        out = os.path.join(os.getcwd(), f"{base}_cropped.png")
        piece.save(out)
        w, h = piece.size
        messagebox.showinfo(
            "Saved",
            f"Cropped image ({w} × {h}) saved to:\n{out}"
        )


def main():
    root = tk.Tk()
    CropperApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()