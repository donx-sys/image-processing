TITLE = "Segmentation Methods"

CONTENT = """\
SEGMENTATION
=============

WHAT SEGMENTATION IS
--------------------
Segmentation assigns a LABEL to every pixel.  The simplest case is
binary: every pixel is either "foreground" (1) or "background" (0).
More generally, each pixel gets a class index, and pixels with the same
label form a REGION.

Segmentation is the step between "a picture" and "an object".  Every
vision pipeline that reasons about objects starts by partitioning the
image.

METHODS IN THIS TOOL
--------------------
Otsu threshold
    Automatic global threshold.  Otsu tries every possible t (0-255),
    computes between-class variance for each, and picks the t that
    maximises it.  Works well on bimodal histograms.

Fixed threshold
    Manual global threshold.  Simple, fast, fails on uneven lighting.

Adaptive mean
    Local threshold.  For each pixel, compute the mean of a W x W
    neighbourhood and threshold against (mean - C).  Handles uneven
    illumination.  Classic choice for document binarization.

Gradient / edges
    Threshold the gradient magnitude (Sobel).  Produces a BOUNDARY map
    rather than a region map.

K-means
    Cluster pixel intensities into k groups.  Ignores spatial info -
    two pixels with the same intensity but far apart get the same label.

Region growing
    Start from a seed pixel.  Grow outward while neighbours stay within
    tolerance of the seed's intensity.  Sensitive to seed placement.

WHAT TO LOOK AT
---------------
The tool displays three views:
    Original
    Segmentation (binary mask or label map)
    Boundaries on original

The boundaries panel is the honest view.  It draws label edges as red
pixels on the raw image, so you can see whether the segmentation
matches the real edges of the objects you care about.

EVALUATION
----------
There is no universal "correct" segmentation.  Different tasks need
different regions.  A segmentation that isolates a face is not the same
as one that isolates a tumour.  What matters is whether the regions are
useful for the downstream task.
"""
