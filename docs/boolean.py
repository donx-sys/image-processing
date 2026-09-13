TITLE = "Boolean Operations on Images"

CONTENT = """\
BOOLEAN OPERATIONS ON IMAGES
=============================

THE IDEA
--------
Two images of the same size can be combined with boolean logic, one
pixel at a time.  The output is a new image, same size as the inputs,
whose pixels are the per-pixel boolean results.

Boolean operations are POINTWISE and EXACT.  No neighbourhood, no
interpolation, no invented values.

BINARY MODE
-----------
Each image is first reduced to a binary mask (pixel > threshold -> 1,
else 0).  Then:

    AND     output 1 only where BOTH inputs are 1
    OR      output 1 where EITHER input is 1
    XOR     output 1 where EXACTLY ONE input is 1
    NOT A   invert A
    A - B   A AND (NOT B): in A but not in B

These are the operations of set theory applied to pixel coordinates.

BITWISE MODE (8-BIT)
--------------------
Each pixel is a byte - eight bits.  The boolean operation runs
INDEPENDENTLY on each of the eight bit positions, and the eight results
pack back into a byte.

For A = 200 = 1 1 0 0 1 0 0 0
    B = 180 = 1 0 1 1 0 1 0 0

    A AND B = 1 0 0 0 0 0 0 0 = 128   bit kept if BOTH had it
    A OR  B = 1 1 1 1 1 1 0 0 = 252   bit kept if EITHER had it
    A XOR B = 0 1 1 1 1 1 0 0 = 124   bit kept if they DIFFER
    NOT A   = 0 0 1 1 0 1 1 1 =  55   all bits flipped
    A - B   = A AND NOT B     =  72

USES
----
Masking             image AND mask -> keep only the masked region
Selections          maskA OR maskB -> union of two selections
Change detection    frameA XOR frameB -> where the two frames differ
Bit-plane slicing   (image >> k) AND 1 -> extract bit plane k
Steganography       overwrite the LSB of a cover image with secret data
Watermarking        OR a visible mark, AND NOT to remove it

CHANGE DETECTION
----------------
XOR is the standard way to answer "what changed between these two
images."  If the two images are aligned, the XOR result is nonzero
exactly at the pixels that changed.

This tool offers two views:
Change overlay      original A dimmed, changed pixels tinted red.
Difference heatmap  |A - B| rendered as a jet heatmap.  Dark blue where
                    images agree, deep red where they differ most.

SIMILARITY
----------
The report compares the two images pixel by pixel and reports how many
match, how many differ, and (in Bitwise mode) the mean absolute
difference and MSE.

WARNING ABOUT BINARY SIMILARITY
Two unrelated photos often show 80-95% similarity in Binary mode
because most of both is background.  The four-cell breakdown
(both 1, both 0, only A, only B) is the honest version.  In Bitwise
mode similarity is strict: two different JPEGs of the same scene
score near zero because compression shifts every byte.
"""
