TITLE = "Preprocessing: Noise Removal"

CONTENT = """\
PREPROCESSING: NOISE REMOVAL
=============================

WHAT NOISE IS
-------------
Noise is unwanted random variation added to pixel values.  It comes
from the sensor, from low light, from compression, or from transmission
errors.  Noise has no structure — by definition it is unpredictable.

TYPES OF NOISE
--------------
Gaussian      additive, N(0, sigma).  Sensor noise.  Smooth, no outliers.
Salt & pepper a small percentage of pixels forced to 0 or 255.  Dust on
              a scanned photo, dead pixels.
Speckle       multiplicative: pixel * (1 + noise).  Radar and ultrasound.
              Noise is proportional to signal — bright areas noisier
              than dark ones.
Uniform       additive over [-a, +a].  Models quantization noise.
Poisson       signal-dependent.  Photon-counting statistics.

FILTERS
-------
All classical denoising works by averaging nearby pixels.  Noise is
random and cancels; signal is coherent and survives.  The tradeoff is
that edges also get blurred.

Mean (box)    uniform average over a k x k window.  Fast, blurs edges.
Gaussian      weighted average with a Gaussian kernel.  Smooth, no ringing.
Median        middle value of the window.  Rejects outliers.  Best for
              salt & pepper noise.
Bilateral     average weighted by both spatial distance AND intensity
              difference.  Edges survive; flat regions smooth.
Wiener        statistically optimal for Gaussian noise.

MATCHING FILTER TO NOISE
------------------------
No single filter is best for all noise:

    Gaussian noise     ->  Gaussian, Wiener
    Salt & pepper      ->  MEDIAN (by a wide margin)
    Speckle            ->  mean / Gaussian

The single most striking demonstration is applying a MEAN filter to a
salt & pepper image (produces grey smudge) and then MEDIAN to the same
image (produces a clean result).  The filter must match the noise.

METRICS
-------
MSE  = mean squared error.  Lower is better.
PSNR = 10 * log10(255^2 / MSE).  Higher is better, in decibels.

Rough guide: PSNR >= 30 dB is visually close to the reference; 20-30 dB
shows visible noise; below 20 dB is obviously degraded.

WHAT THIS TOOL DOES
-------------------
Load an image, switch between "Add Noise" (pick type and amount,
compare original vs noisy) and "Remove Noise" (pick filter and kernel,
compare noisy vs denoised).  A metrics panel reports MSE and PSNR at
every stage.
"""
