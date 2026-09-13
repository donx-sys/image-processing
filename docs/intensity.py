TITLE = "Intensity Resolution"

CONTENT = """\
INTENSITY RESOLUTION
=====================

WHAT IT IS
----------
Intensity resolution is the number of distinct values a single pixel
can take.  It is determined by the BIT DEPTH of each channel.

    bits   levels     typical use
    ----   ------     -----------
     1       2        faxes, line art
     2       4        retro palettes
     3       8        old 8-colour displays
     4      16        EGA graphics
     8     256        standard JPEG / PNG
    12    4096        RAW photo
    16   65536        medical, scientific

levels = 2 ^ bits.

Intensity resolution is a separate axis from spatial resolution.  A
4K image can be 1-bit (pure black and white).  A 100 x 100 image can
be 16-bit.  One tells you how many pixels there are; the other tells
you how many shades each one can hold.

QUANTIZATION
------------
Reducing the bit depth is called QUANTIZATION.  The standard method is
bit truncation: keep the top b bits, discard the rest.

    value_target = value_source >> (source_bits - target_bits)

Examples on an 8-bit value 200 = 1 1 0 0 1 0 0 0:

    4-bit  =  1 1 0 0          =  12       (>> 4)
    3-bit  =  1 1 0            =   6       (>> 5)
    1-bit  =  1                =   1       (>> 7)

This is NOT the same as round(x * target / source).  The shift is
bit-aligned - it literally chooses which bit planes survive.  That is
the standard definition in a DIP course.

WHAT IT LOOKS LIKE
------------------
Quantization turns smooth gradients into flat bands with hard edges
between them.  Those hard edges are FALSE CONTOURS - an artefact of
the coarse staircase transfer function, not real structure.

At 3-bit (8 levels) banding is very visible.  At 6-bit (64 levels) it
is subtle.  At 8-bit (256 levels) it is invisible under normal viewing.

QUANTIZATION ERROR
------------------
The error for any pixel is |output - input|.  For truncation the error
is in [0, step-1]; for rounding it is in [-step/2, +step/2].  For
8-bit -> 4-bit, step = 16, so worst-case error is 15 (truncation) or
8 (rounding).

WHAT THIS TOOL DOES
-------------------
Load an image, analyse the per-channel intensity usage, choose a target
bit depth (1-16), and see the result side by side with the original.
The pixel matrix shows original 0-255 values next to quantized values,
so you can verify the collapse numerically.
"""
