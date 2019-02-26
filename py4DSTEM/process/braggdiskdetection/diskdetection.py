# Functions for finding Bragg disks.
#
# Using a vacuum probe as a template - i.e. a convolution kernel - a cross correlation (or phase or
# hybrid correlation) is taken between each DP and the template, and the positions and intensities
# of all local correlation maxima are used to identify the Bragg disks. Erroneous peaks are filtered
# out with several types of threshold. Detected Bragg disks are generally stored in PointLists (when
# run on only selected DPs) or PointListArrays (when run on a full DataCube).

import numpy as np
from scipy.ndimage.filters import gaussian_filter
from time import time

from ..datastructure import PointList, PointListArray
from ..utils import get_cross_correlation_fk, get_maximal_points

def find_Bragg_disks_single_DP_FK(DP, probe_kernel_FT,
                                  corrPower = 1,
                                  sigma = 2,
                                  edgeBoundary = 20,
                                  minRelativeIntensity = 0.005,
                                  minPeakSpacing = 60,
                                  maxNumPeaks = 70,
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
                             the intensity of the brightest peak
        minPeakSpacing       (float) the minimum acceptable spacing between detected peaks
        maxNumPeaks          (int) the maximum number of peaks to return
        peaks                (PointList) For internal use.
                             If peaks is None, the PointList of peak positions is created here.
                             If peaks is not None, it is the PointList that detected peaks are added
                             to, and must have the appropriate coords ('qx','qy','intensity').

    Returns:
        peaks                (PointList) the Bragg peak positions and correlation intensities
    """
    # Get cross correlation
    cc = get_cross_correlation_fk(DP, probe_kernel_FT, corrPower)
    cc = np.maximum(cc,0)
    cc = gaussian_filter(cc, sigma)

    # Get maximal points
    max_points = get_maximal_points(cc)

    # Remove points at edges
    max_points[:edgeBoundary,:]=False
    max_points[-edgeBoundary:,:]=False
    max_points[:,:edgeBoundary]=False
    max_points[:,-edgeBoundary:]=False

    # Make peaks PointList
    if peaks is None:
        coords = [('qx',float),('qy',float),('intensity',float)]
        peaks = PointList(coordinates=coords)
    else:
        assert(isinstance(peaks,PointList))

    # Populate peaks PointList
    max_point_indices_x, max_point_indices_y = np.nonzero(max_points)
    point_intensities = cc[max_point_indices_x,max_point_indices_y]
    for i in range(len(point_intensities)):
        new_point = (max_point_indices_x[i], max_point_indices_y[i], point_intensities[i])
        peaks.add_point(new_point)

    # Arrange peaks by intensity
    peaks.sort(coordinate='intensity',order='descending')

    # Remove peaks below minRelativeIntensity
    deletemask = peaks.data['intensity']/max(peaks.data['intensity']) < minRelativeIntensity
    peaks.remove_points(deletemask)

    # Remove peaks closer together than minPeakSpacing
    deletemask = np.zeros(peaks.length,dtype=bool)
    for i in range(peaks.length):
        if deletemask[i] == False:
            tooClose = ( (peaks.data['qx']-peaks.data['qx'][i])**2 + \
                         (peaks.data['qy']-peaks.data['qy'][i])**2 ) < minPeakSpacing**2
            tooClose[:i+1] = False
            deletemask[tooClose] = True
    peaks.remove_points(deletemask)

    # Remove peaks in excess of maxNumPeaks
    if peaks.length > maxNumPeaks:
        deletemask = np.zeros(peaks.length,dtype=bool)
        deletemask[maxNumPeaks:] = True
        peaks.remove_points(deletemask)

    return peaks


def find_Bragg_disks_single_DP(DP, probe_kernel,
                               corrPower = 1,
                               sigma = 2,
                               edgeBoundary = 20,
                               minRelativeIntensity = 0.005,
                               minPeakSpacing = 60,
                               maxNumPeaks = 70):
    """
    Identical to find_Bragg_disks_single_DP_FK, accept that this function accepts a probe_kernel in
    real space, rather than Fourier space. For more info, see the find_Bragg_disks_single_DP_FK
    documentation.

    Accepts:
        DP                   (ndarray) a diffraction pattern
        probe_kernel         (ndarray) the vacuum probe template, in real space.
        corrPower            (float between 0 and 1, inclusive) the cross correlation power. A
                             value of 1 corresponds to a cross correaltion, and 0 corresponds to a
                             phase correlation, with intermediate values giving various hybrids.
        sigma                (float) the standard deviation for the gaussian smoothing applied to
                             the cross correlation
        edgeBoundary         (int) minimum acceptable distance from the DP edge, in pixels
        minRelativeIntensity (float) the minimum acceptable correlation peak intensity, relative to
                             the intensity of the brightest peak
        minPeakSpacing       (float) the minimum acceptable spacing between detected peaks
        maxNumPeaks          (int) the maximum number of peaks to return

    Returns:
        peaks                (PointList) the Bragg peak positions and correlation intensities

    """
    probe_kernel_FT = np.conj(np.fft.fft2(probe_kernel))
    return find_Bragg_disks_single_DP_FK(DP, probe_kernel_FT,
                                         corrPower = corrPower,
                                         sigma = sigma,
                                         edgeBoundary = edgeBoundary,
                                         minRelativeIntensity = minRelativeIntensity,
                                         minPeakSpacing = minPeakSpacing,
                                         maxNumPeaks = maxNumPeaks)


def find_Bragg_disks_selected(datacube, probe, Rx, Ry,
                              corrPower = 1,
                              sigma = 2,
                              edgeBoundary = 20,
                              minRelativeIntensity = 0.005,
                              minPeakSpacing = 60,
                              maxNumPeaks = 70):
    """
    Finds the Bragg disks in the diffraction patterns of datacube at scan positions (Rx,Ry) by
    cross, hybrid, or phase correlation with probe.

    Accepts:
        DP                   (ndarray) a diffraction pattern
        probe                (ndarray) the vacuum probe template, in real space.
        Rx                   (int or tuple/list of ints) scan position x-coords of DPs of interest
        Ry                   (int or tuple/list of ints) scan position y-coords of DPs of interest
        corrPower            (float between 0 and 1, inclusive) the cross correlation power. A
                             value of 1 corresponds to a cross correaltion, and 0 corresponds to a
                             phase correlation, with intermediate values giving various hybrids.
        sigma                (float) the standard deviation for the gaussian smoothing applied to
                             the cross correlation
        edgeBoundary         (int) minimum acceptable distance from the DP edge, in pixels
        minRelativeIntensity (float) the minimum acceptable correlation peak intensity, relative to
                             the intensity of the brightest peak
        minPeakSpacing       (float) the minimum acceptable spacing between detected peaks
        maxNumPeaks          (int) the maximum number of peaks to return

    Returns:
        peaks                (n-tuple of PointLists, n=len(Rx)) the Bragg peak positions and
                             correlation intensities at each scan position (Rx,Ry)
    """
    assert(len(Rx)==len(Ry))
    peaks = []

    # Get probe kernel in Fourier space
    probe_kernel_FT = np.conj(np.fft.fft2(probe))

    # Loop over selected diffraction patterns
    t0 = time()
    for i in range(len(Rx)):
        DP = datacube.data4D[Rx[i],Ry[i],:,:]
        peaks.append(find_Bragg_disks_single_DP_FK(DP, probe_kernel_FT,
                                                   corrPower = corrPower,
                                                   sigma = sigma,
                                                   edgeBoundary = edgeBoundary,
                                                   minRelativeIntensity = minRelativeIntensity,
                                                   minPeakSpacing = minPeakSpacing,
                                                   maxNumPeaks = maxNumPeaks))
    t = time()-t0
    print("Analyzed {} diffraction patterns in {}h {}m {}s".format(len(Rx), int(t/3600),
                                                                   int(t/60), int(t%60)))

    return tuple(peaks)


def find_Bragg_disks(datacube, probe,
                     corrPower = 1,
                     sigma = 2,
                     edgeBoundary = 20,
                     minRelativeIntensity = 0.005,
                     minPeakSpacing = 60,
                     maxNumPeaks = 70,
                     verbose = False):
    """
    Finds the Bragg disks in all diffraction patterns of datacube by cross, hybrid, or phase
    correlation with probe.

    Accepts:
        DP                   (ndarray) a diffraction pattern
        probe                (ndarray) the vacuum probe template, in real space.
        corrPower            (float between 0 and 1, inclusive) the cross correlation power. A
                             value of 1 corresponds to a cross correaltion, and 0 corresponds to a
                             phase correlation, with intermediate values giving various hybrids.
        sigma                (float) the standard deviation for the gaussian smoothing applied to
                             the cross correlation
        edgeBoundary         (int) minimum acceptable distance from the DP edge, in pixels
        minRelativeIntensity (float) the minimum acceptable correlation peak intensity, relative to
                             the intensity of the brightest peak
        minPeakSpacing       (float) the minimum acceptable spacing between detected peaks
        maxNumPeaks          (int) the maximum number of peaks to return
        verbose              (bool) if True, prints completion updates

    Returns:
        peaks                (PointListArray) the Bragg peak positions and correlation intensities
    """
    # Make the peaks PointListArray
    coords = [('qx',float),('qy',float),('intensity',float)]
    peaks = PointListArray(coordinates=coords, shape=(datacube.R_Nx, datacube.R_Ny))

    # Get the probe kernel FT
    probe_kernel_FT = np.conj(np.fft.fft2(probe))

    # Loop over all diffraction patterns
    t0 = time()
    for Rx in range(datacube.R_Nx):
        for Ry in range(datacube.R_Ny):
            if verbose:
                print("Analyzing scan position {}, {}...".format(Rx,Ry))
            DP = datacube.data4D[Rx,Ry,:,:]
            find_Bragg_disks_single_DP_FK(DP, probe_kernel_FT,
                                          corrPower = corrPower,
                                          sigma = sigma,
                                          edgeBoundary = edgeBoundary,
                                          minRelativeIntensity = minRelativeIntensity,
                                          minPeakSpacing = minPeakSpacing,
                                          maxNumPeaks = maxNumPeaks,
                                          peaks = peaks.get_pointlist(Rx,Ry))
    t = time()-t0
    print("Analyzed {} diffraction patterns in {}h {}m {}s".format(datacube.R_N, int(t/3600),
                                                                   int(t/60), int(t%60)))

    return peaks





