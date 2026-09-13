TITLE = "Understanding Matrix Representation of the Image"

CONTENT = """\
MATRIX REPRESENTATION OF AN IMAGE
=================================

WHAT AN IMAGE IS
----------------
An image is a matrix of numbers.  Each element of that matrix is one
pixel.  The matrix's dimensions correspond to the image's height and
width:

    shape = (H, W)          grayscale  (one value per pixel)
    shape = (H, W, 3)       RGB        (three values per pixel)
    shape = (H, W, 4)       RGBA       (four values per pixel)

The number stored at a pixel is its INTENSITY.  For an 8-bit grayscale
image the range is 0-255.  For RGB, three 8-bit values, one each for
red, green and blue.  For a 3-bit grayscale image the range is 0-7.

INDEXING ORDER
--------------
Two conventions exist and they disagree:

    (x, y)   what you say when talking about a pixel position.
             x = column, y = row.  Origin top-left.

    [y, x]   how the array is indexed.  arr[row, col].
             Index 0 is the first row (top).

So pixel (x=100, y=50) lives at arr[50, 100].  Mixing these up is the
single most common mistake in image-processing code.

WHAT THIS TOOL DOES
-------------------
Load an image, convert to grayscale or RGB, optionally reduce the bit
depth to 3 bits, extract an NxN centre crop, and print the numeric
matrix to the console.  It also saves the patch as a PNG (upscaled
with NEAREST so pixels stay blocky) and the raw values as a CSV.

WHY IT MATTERS
--------------
Every other tool in this set operates on this matrix.  Cropping selects
a sub-rectangle of it.  Resizing produces a new one with different
dimensions.  Quantization replaces every element with a coarser value.
"An image is just a grid of numbers" is the mental model that unlocks
everything else.

WHAT TO LOOK FOR
----------------
- A pixel near a smooth sky region: 220, 221, 222, 223 ... nearly the
  same numbers.
- A pixel near an edge: 40, 180 — a big jump between adjacent cells.
- Load a small patch at 3-bit and compare: 220, 221, 222 all become 6.
"""
