TITLE = "Preprocessing: Identifying Information-Rich Areas"

CONTENT = """\
PREPROCESSING: INFORMATION-RICH AREAS
======================================

THE CORE IDEA
-------------
Brightness is not information.  A clear sky is bright but carries almost
no information - you can predict every pixel without looking.  A dark
patch of foliage is dim but carries a lot of information, because the
values vary unpredictably from pixel to pixel.

Information, in the technical sense, is UNPREDICTABILITY.

This tool measures local unpredictability across the whole image and
renders it as a heatmap, so you can see WHERE the image is informative.

MEASURES
--------
Six ways to compute local information, all over a sliding W x W window:

Entropy         Shannon entropy of the local histogram:
                    H = -sum p_i * log2(p_i)
                Zero for a uniform patch; up to 8 for a patch that uses
                all 256 values equally.

Variance        Mean squared deviation from the window mean.

RMS contrast    sqrt(variance).  Same idea in pixel-value units.

Gradient        Local edge strength via the Sobel operator.  Responds
                to coherent directional change, not to noise.

Laplacian       Energy in the second derivative.  Local ROUGHNESS.
                Very sensitive to fine texture and noise.

Range           max - min in the window.  Simple and robust, but a
                single outlier can inflate it.

SLIDING WINDOW
--------------
The window size controls the scale at which "local" is defined.  A 3x3
window is essentially per-pixel activity; a 41x41 window captures
regional structure.  Both are correct - they answer different questions.

WHAT THIS TOOL DOES
-------------------
Load an image, pick a measure, pick a window size, and see a false-
colour map of information density.  The top-N regions are boxed on both
panels.  Click anywhere to inspect a location - the report shows the
local value and its rank among all windows.

WHAT TO LOOK FOR
----------------
- A photo with a large sky: the sky is dark blue on the map (low info)
  even though it is bright in the raw image.
- The top 5 regions are rarely the brightest part of the image.  In a
  portrait they tend to be the eyes, mouth, hair.
- Switch from Entropy to Gradient - the highlight regions move.  They
  answer different questions about "what is informative."
"""
