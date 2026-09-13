TITLE = "Spatial Resolution: Resizing"

CONTENT = """\
SPATIAL RESOLUTION: RESIZING
=============================

WHAT RESIZING IS
----------------
Resizing changes the number of pixels that cover a scene.  Upscaling
adds pixels; downscaling removes them.  Because the new grid rarely
lines up with the old one, every output pixel must be COMPUTED from
nearby input pixels - this is INTERPOLATION.

INTERPOLATION METHODS
---------------------
Nearest neighbour   copy the closest input pixel.  Fast, blocky, only
                    produces values that already exist in the input.
Bilinear            weighted average of the 2x2 nearest inputs.
Bicubic             weighted average of a 4x4 neighbourhood.  Sharper
                    than bilinear; can slightly overshoot on edges.
Lanczos             weighted average of a 6x6 neighbourhood using the
                    Lanczos kernel.  Sharpest of the standard methods.
Box                 simple average of all overlapping inputs.  Best for
                    large downscaling ratios.

UPSCALING VS DOWNSCALING
------------------------
Upscaling invents no new information.  Every output pixel is a weighted
combination of existing inputs.  The output LOOKS higher resolution but
contains nothing the input did not already have.

Downscaling destroys information.  When a 1000-pixel-wide image becomes
100 pixels wide, ten source pixels collapse into one output pixel.  The
differences between them are lost forever.  Downscale-then-upscale does
not recover the original.

WHAT THIS TOOL DOES
-------------------
Load an image, enter a new width and height (or lock aspect ratio), pick
an interpolation method, and see the result.  Three panels show the
original, the resized result, and a per-pixel explainer at a focus point.

WHAT TO LOOK FOR
----------------
- Zoom into the resized image with NEAREST vs BICUBIC.  NEAREST produces
  hard blocks; BICUBIC produces smooth gradients.
- Downscale a checkerboard by 4x with NEAREST - you get Moire patterns.
  With BOX you get uniform grey, because the average is correct.
- Downscale to 25% and back to 100%.  Compare with the original - they
  are not the same image.
"""
