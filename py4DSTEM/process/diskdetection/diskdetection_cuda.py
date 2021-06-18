''' 

Functions for finding Braggdisks using cupy



'''
__all__ = ['_find_Bragg_disks_single_DP_FK_CUDA']

import numpy as np
import cupy as cp
from scipy.ndimage.filters import gaussian_filter

from ...io.datastructure import PointList, PointListArray
from ..utils import tqdmnd
from .kernels import kernels

def _find_Bragg_disks_single_DP_FK_CUDA(DP, probe_kernel_FT,
                                  corrPower = 1,
                                  sigma = 2,
                                  edgeBoundary = 20,
                                  minRelativeIntensity = 0.005,
                                  relativeToPeak = 0,
                                  minPeakSpacing = 60,
                                  maxNumPeaks = 70,
                                  subpixel = 'multicorr',
                                  upsample_factor = 16,
                                  filter_function = None,
                                  return_cc = False,
                                  peaks = None):
    """
     Finds the Bragg disks in DP by cross, hybrid, or phase correlation with probe_kernel_FT.

     After taking the cross/hybrid/phase correlation, a gaussian smoothing is applied
     with standard deviation sigma, and all local maxima are found. Detected peaks within
     edgeBoundary pixels of the diffraction plane edges are then discarded. Next, peaks with
     intensities less than minRelativeIntensity of the brightest peak in the correaltion are
     discarded. Then peaks which are within a distance of minPeakSpacing of their nearest neighbor
     peak are found, and in each such pair the peak with the lesser correlation intensities is
     removed. Finally, if the number of peaks remaining exceeds maxNumPeaks, only the maxNumPeaks
     peaks with the highest correlation intensity are retained.

     IMPORTANT NOTE: the argument probe_kernel_FT is related to the probe kernels generated by
     functions like get_probe_kernel() by:

             probe_kernel_FT = np.conj(np.fft.fft2(probe_kernel))

     if this function is simply passed a probe kernel, the results will not be meaningful! To run
     on a single DP while passing the real space probe kernel as an argument, use
     find_Bragg_disks_single_DP().

     Accepts:
         DP                   (ndarray) a diffraction pattern
         probe_kernel_FT      (ndarray) the vacuum probe template, in Fourier space. Related to the
                              real space probe kernel by probe_kernel_FT = F(probe_kernel)*, where F
                              indicates a Fourier Transform and * indicates complex conjugation.
         corrPower            (float between 0 and 1, inclusive) the cross correlation power. A
                              value of 1 corresponds to a cross correaltion, and 0 corresponds to a
                              phase correlation, with intermediate values giving various hybrids.
         sigma                (float) the standard deviation for the gaussian smoothing applied to
                              the cross correlation
         edgeBoundary         (int) minimum acceptable distance from the DP edge, in pixels
         minRelativeIntensity (float) the minimum acceptable correlation peak intensity, relative to
                              the intensity of the relativeToPeak'th peak
         relativeToPeak       (int) specifies the peak against which the minimum relative intensity
                              is measured -- 0=brightest maximum. 1=next brightest, etc.
         minPeakSpacing       (float) the minimum acceptable spacing between detected peaks
         maxNumPeaks          (int) the maximum number of peaks to return
         subpixel             (str)          'none': no subpixel fitting
                                   (default) 'poly': polynomial interpolation of correlogram peaks
                                                     (fairly fast but not very accurate)
                                             'multicorr': uses the multicorr algorithm with
                                                         DFT upsampling
         upsample_factor      (int) upsampling factor for subpixel fitting (only used when subpixel='multicorr')
         filter_function      (callable) filtering function to apply to each diffraction pattern before peakfinding.
                              Must be a function of only one argument (the diffraction pattern) and return
                              the filtered diffraction pattern.
                              The shape of the returned DP must match the shape of the probe kernel (but does
                              not need to match the shape of the input diffraction pattern, e.g. the filter
                              can be used to bin the diffraction pattern). If using distributed disk detection,
                              the function must be able to be pickled with by dill.
         return_cc            (bool) if True, return the cross correlation
         peaks                (PointList) For internal use.
                              If peaks is None, the PointList of peak positions is created here.
                              If peaks is not None, it is the PointList that detected peaks are added
                              to, and must have the appropriate coords ('qx','qy','intensity').

     Returns:
         peaks                (PointList) the Bragg peak positions and correlation intensities
     """
    assert subpixel in [ 'none', 'poly', 'multicorr' ], "Unrecognized subpixel option {}, subpixel must be 'none', 'poly', or 'multicorr'".format(subpixel)

    # Perform any prefiltering
    DP = cp.array(DP if filter_function is None else filter_function(DP))

    # Get the cross correlation
    if subpixel in ('none','poly'):
        cc = get_cross_correlation_fk(DP, probe_kernel_FT, corrPower)
        ccc = None
    # for multicorr subpixel fitting, we need both the real and complex cross correlation
    else:
        ccc = get_cross_correlation_fk(DP, probe_kernel_FT, corrPower, returnval='fourier')
        cc = np.maximum(np.real(np.fft.ifft2(ccc)),0)

    # Find the maxima
    maxima_x,maxima_y,maxima_int = get_maxima_2D(cc, sigma=sigma,
                                                 edgeBoundary=edgeBoundary,
                                                 minRelativeIntensity=minRelativeIntensity,
                                                 relativeToPeak=relativeToPeak,
                                                 minSpacing=minPeakSpacing,
                                                 maxNumPeaks=maxNumPeaks,
                                                 subpixel=subpixel,
                                                 ar_FT = ccc,
                                                 upsample_factor = upsample_factor)

    # Make peaks PointList
    if peaks is None:
        coords = [('qx',float),('qy',float),('intensity',float)]
        peaks = PointList(coordinates=coords)
    else:
        assert(isinstance(peaks,PointList))
    peaks.add_tuple_of_nparrays((maxima_x,maxima_y,maxima_int))

    if return_cc:
        return peaks, gaussian_filter(cc,sigma)
    else:
        return peaks


def get_cross_correlation_fk(ar, fourierkernel, corrPower=1, returnval='cc'):
    """
    Calculates the cross correlation of ar with fourierkernel.
    Here, fourierkernel = np.conj(np.fft.fft2(kernel)); speeds up computation when the same
    kernel is to be used for multiple cross correlations.
    corrPower specifies the correlation type, where 1 is a cross correlation, 0 is a phase
    correlation, and values in between are hybrids.

    The return value depends on the argument `returnval`:
        if return=='cc' (default), returns the real part of the cross correlation in real
        space.
        if return=='fourier', returns the output in Fourier space, before taking the
        inverse transform.
    """
    assert(returnval in ('cc','fourier'))
    m = cp.fft.fft2(ar) * fourierkernel
    ccc = cp.abs(m)**(corrPower) * cp.exp(1j*cp.angle(m))
    if returnval=='fourier':
        return ccc
    else:
        return cp.real(cp.fft.ifft2(ccc))


def get_maxima_2D(ar, sigma=0, edgeBoundary=0, minSpacing=0, minRelativeIntensity=0,
                  relativeToPeak=0, maxNumPeaks=0, subpixel='poly', ar_FT=None, upsample_factor=16):
    """
    Finds the indices where the 2D array ar is a local maximum.
    Optional parameters allow blurring of the array and filtering of the output;
    setting each of these to 0 (default) turns off these functions.

    Accepts:
        ar                      (ndarray) a 2D array
        sigma                   (float) guassian blur std to applyu to ar before finding the maxima
        edgeBoundary            (int) ignore maxima within edgeBoundary of the array edge
        minSpacing              (float) if two maxima are found within minSpacing, the dimmer one
                                is removed
        minRelativeIntensity    (float) maxima dimmer than minRelativeIntensity compared to the
                                relativeToPeak'th brightest maximum are removed
        relativeToPeak          (int) 0=brightest maximum. 1=next brightest, etc.
        maxNumPeaks             (int) return only the first maxNumPeaks maxima
        subpixel                (str)          'none': no subpixel fitting
                                     (default) 'poly': polynomial interpolation of correlogram peaks
                                                    (fairly fast but not very accurate)
                                               'multicorr': uses the multicorr algorithm with
                                                        DFT upsampling
        ar_FT                   (None or complex array) if subpixel=='multicorr' the
                                fourier transform of the image is required.  It may be
                                passed here as a complex array.  Otherwise, if ar_FT is None,
                                it is computed
        upsample_factor         (int) required iff subpixel=='multicorr'

    Returns
        maxima_x                (ndarray) x-coords of the local maximum, sorted by intensity.
        maxima_y                (ndarray) y-coords of the local maximum, sorted by intensity.
        maxima_intensity        (ndarray) intensity of the local maxima
    """
    assert subpixel in [ 'none', 'poly', 'multicorr' ], "Unrecognized subpixel option {}, subpixel must be 'none', 'poly', or 'multicorr'".format(subpixel)

    # Get maxima
    ar = gaussian_filter(ar, sigma)
    maxima_bool = get_maximal_points(ar)

    # Remove edges
    if edgeBoundary > 0:
        assert isinstance(edgeBoundary, (int, np.integer))
        maxima_bool[:edgeBoundary, :] = False
        maxima_bool[-edgeBoundary:, :] = False
        maxima_bool[:, :edgeBoundary] = False
        maxima_bool[:, -edgeBoundary:] = False
    elif subpixel is True:
        maxima_bool[:1, :] = False
        maxima_bool[-1:, :] = False
        maxima_bool[:, :1] = False
        maxima_bool[:, -1:] = False

    # Get indices, sorted by intensity
    maxima_x, maxima_y = np.nonzero(maxima_bool)
    dtype = np.dtype([('x', float), ('y', float), ('intensity', float)])
    maxima = np.zeros(len(maxima_x), dtype=dtype)
    maxima['x'] = maxima_x
    maxima['y'] = maxima_y
    maxima['intensity'] = ar[maxima_x, maxima_y]
    maxima = np.sort(maxima, order='intensity')[::-1]

    if len(maxima) > 0:
        # Remove maxima which are too close
        if minSpacing > 0:
            deletemask = np.zeros(len(maxima), dtype=bool)
            for i in range(len(maxima)):
                if deletemask[i] == False:
                    tooClose = ((maxima['x'] - maxima['x'][i]) ** 2 + \
                                (maxima['y'] - maxima['y'][i]) ** 2) < minSpacing ** 2
                    tooClose[:i + 1] = False
                    deletemask[tooClose] = True
            maxima = np.delete(maxima, np.nonzero(deletemask)[0])

        # Remove maxima which are too dim
        if (minRelativeIntensity > 0) & (len(maxima) > relativeToPeak):
            assert isinstance(relativeToPeak, (int, np.integer))
            deletemask = maxima['intensity'] / maxima['intensity'][relativeToPeak] < minRelativeIntensity
            maxima = np.delete(maxima, np.nonzero(deletemask)[0])

        # Remove maxima in excess of maxNumPeaks
        if maxNumPeaks > 0:
            assert isinstance(maxNumPeaks, (int, np.integer))
            if len(maxima) > maxNumPeaks:
                maxima = maxima[:maxNumPeaks]

        # Subpixel fitting 
        # For all subpixel fitting, first fit 1D parabolas in x and y to 3 points (maximum, +/- 1 pixel)
        if subpixel != 'none':
            for i in range(len(maxima)):
                Ix1_ = ar[int(maxima['x'][i]) - 1, int(maxima['y'][i])]
                Ix0 = ar[int(maxima['x'][i]), int(maxima['y'][i])]
                Ix1 = ar[int(maxima['x'][i]) + 1, int(maxima['y'][i])]
                Iy1_ = ar[int(maxima['x'][i]), int(maxima['y'][i]) - 1]
                Iy0 = ar[int(maxima['x'][i]), int(maxima['y'][i])]
                Iy1 = ar[int(maxima['x'][i]), int(maxima['y'][i]) + 1]
                deltax = (Ix1 - Ix1_) / (4 * Ix0 - 2 * Ix1 - 2 * Ix1_)
                deltay = (Iy1 - Iy1_) / (4 * Iy0 - 2 * Iy1 - 2 * Iy1_)
                maxima['x'][i] += deltax
                maxima['y'][i] += deltay
                maxima['intensity'][i] = linear_interpolation_2D(ar, maxima['x'][i], maxima['y'][i])
        # Further refinement with fourier upsampling
        if subpixel == 'multicorr':
            if ar_FT is None:
                ar_FT = np.fft.fft2(ar)
            for ipeak in range(len(maxima['x'])):
                xyShift = np.array((maxima['x'][ipeak],maxima['y'][ipeak]))
                # we actually have to lose some precision and go down to half-pixel
                # accuracy. this could also be done by a single upsampling at factor 2
                # instead of get_maxima_2D.
                xyShift[0] = np.round(xyShift[0] * 2) / 2
                xyShift[1] = np.round(xyShift[1] * 2) / 2

                subShift = upsampled_correlation(ar_FT,upsample_factor,xyShift)
                maxima['x'][ipeak]=subShift[0]
                maxima['y'][ipeak]=subShift[1]

    return maxima['x'], maxima['y'], maxima['intensity']

def get_maximal_points_kernel(dtype):
    """
    For 2D cupy array cpar, returns an array of bools of the same shape which is True for all entries with
    values larger than all 8 of their nearest neighbors. Writes into outarr if passed, else returns a
    numpy boolean array. Input array must be float32 or float64 type.
    """
    if dtype == 'float64':
        maxkernel = kernels['maximal_pts_float64']
    elif dtype == 'float32':
        maxkernel = kernels['maximal_pts_float32']
    else:
        raise TypeError("Maximal kernel only valid for float32 and float64 types...")

    return cp.RawKernel(maxkernel,'maximal_pts')
