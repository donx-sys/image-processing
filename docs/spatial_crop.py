TITLE = "Spatial Resolution: Cropping"

CONTENT = """\
SPATIAL RESOLUTION: CROPPING
=============================

WHAT CROPPING IS
----------------
Cropping extracts a rectangular sub-region of the image and produces a
smaller image containing exactly those pixels.  No new values are
invented.  No values are modified.  The remaining pixels are exactly
the original bytes, sitting in a smaller array.

Cropping changes the FIELD OF VIEW, not the pixel values.

THE BOUNDING BOX
----------------
PIL and this tool use:

    box = (left, upper, right, lower)

with right and lower EXCLUSIVE.  The crop contains pixels whose column
index x satisfies left <= x < right, and whose row index y satisfies
upper <= y < lower.

    width  = right - left
    height = lower - upper

Passing (0, 0, 100, 100) gives a 100-wide, 100-tall patch - not 101,
not 99.  This off-by-one bites everyone once.

AN EXAMPLE
----------
A 20 x 20 image, cropped with box (5, 5, 15, 15):

    left=5, upper=5, right=15, lower=15
    width  = 10, height = 10

The result is a 10 x 10 image containing the pixels at rows 5..14 and
columns 5..14 of the original.

WHAT THIS TOOL DOES
-------------------
The GUI shows the whole image.  You drag a rectangle on it (or type
coordinates directly), and the tool records the region.  It displays
the cropped piece, draws the boundaries on the original so you can see
which pixels were taken, and lets you save either view.

WHY IT MATTERS
--------------
Cropping is the simplest spatial operation - the one that does nothing
to the pixel values.  It is the baseline against which resizing is
understood: resizing also changes the array's shape, but in the process
it invents new pixel values.  Cropping shows that you can change the
size of an image without touching a single byte.
"""
