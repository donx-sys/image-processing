TITLE = "Preprocessing: Contrast Enhancement"

CONTENT = """\
PREPROCESSING: CONTRAST ENHANCEMENT
=====================================

WHAT CONTRAST IS
----------------
Contrast is the SPREAD of pixel intensities.  A low-contrast image has
all its values huddled in a narrow range - it looks flat, hazy, dull.
A high-contrast image uses the full 0-255 range and looks punchy.

The HISTOGRAM (bar chart of how many pixels have each intensity) is the
diagnostic.  A low-contrast image has a tall, narrow histogram.  A well
-exposed one has a broad histogram spanning most of the range.

THE FOUR CLASSIC METHODS
------------------------
Linear stretch
    Find the minimum and maximum intensities actually present, rescale
    so they map to 0 and 255.  Preserves the SHAPE of the histogram.

Histogram equalization
    Use the cumulative distribution (CDF) as a remap table.  The output
    histogram is as flat as possible.  Powerful but can over-amplify
    noise in flat regions.

Gamma correction
    output = 255 * (input/255) ^ gamma.  Non-linear.  gamma < 1
    brightens shadows; gamma > 1 darkens them.

Log transform
    output = c * log(1 + input).  Compresses bright regions, expands
    dark ones.  Used for Fourier-spectrum visualization.

ALL FOUR ARE POINTWISE
----------------------
Every output pixel depends only on the corresponding input pixel.  No
neighbourhood, no interpolation.  Each can be implemented as a single
256-entry lookup table applied to the whole image.

THE HISTOGRAM TELLS THE STORY
-----------------------------
    stretch         narrow bell -> wide bell (same shape)
    equalization    any shape   -> flat plateau
    gamma           shape slides left or right
    log             values push away from zero

WHAT THIS TOOL DOES
-------------------
Load an image.  Pick a method for image A and a (possibly different)
method for image B.  Four image panels show A-original, A-enhanced,
B-original, B-enhanced.  Two histograms below show the before (grey)
and after (orange) distributions overlaid.  Every parameter updates
live.
"""
