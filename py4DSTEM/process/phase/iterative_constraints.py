from py4DSTEM.process.phase.utils import (
    estimate_global_transformation_ransac,
    fft_shift,
)
from py4DSTEM.process.utils import get_CoM


def _object_threshold_constraint(self, current_object, pure_phase_object):
    """
    Ptychographic threshold constraint.
    Used for avoiding the scaling ambiguity between probe and object.

    Parameters
    --------
    current_object: np.ndarray
        Current object estimate
    pure_phase_object: bool
        If True, object amplitude is set to unity

    Returns
    --------
    constrained_object: np.ndarray
        Constrained object estimate
    """
    xp = self._xp
    phase = xp.exp(1.0j * xp.angle(current_object))
    if pure_phase_object:
        amplitude = 1.0
    else:
        amplitude = xp.minimum(xp.abs(current_object), 1.0)
    return amplitude * phase


def _object_denoise_tv_chambolle(
    self,
    current_object,
    weight,
    axis,
    pad_object,
    eps=2.0e-4,
    max_num_iter=200,
    scaling=None,
):
    """
    Perform total-variation denoising on n-dimensional images.

    Parameters
    ----------
    current_object: np.ndarray
        Current object estimate
    weight : float, optional
        Denoising weight. The greater `weight`, the more denoising (at
        the expense of fidelity to `input`).
    axis: int or tuple
        Axis for denoising, if None uses all axes
    pad_object: bool
        if True, pads object with zeros along axes of blurring
    eps : float, optional
        Relative difference of the value of the cost function that determines
        the stop criterion. The algorithm stops when:

            (E_(n-1) - E_n) < eps * E_0

    max_num_iter : int, optional
        Maximal number of iterations used for the optimization.
    scaling : tuple, optional
        Scale weight of tv denoise on different axes

    Returns
    -------
    constrained_object: np.ndarray
        Constrained object estimate

    Notes
    -----
    Rudin, Osher and Fatemi algorithm.
    Adapted skimage.restoration.denoise_tv_chambolle.
    """
    xp = self._xp

    if axis is None:
        ndim = xp.arange(current_object.ndim).tolist()
    elif type(axis) == tuple:
        ndim = list(axis)
    else:
        ndim = [axis]

    if pad_object:
        pad_width = ((0, 0),) * current_object.ndim
        pad_width = list(pad_width)
        for ax in range(len(ndim)):
            pad_width[ndim[ax]] = (1, 1)
        current_object = xp.pad(current_object, pad_width=pad_width, mode="constant")

    p = xp.zeros(
        (current_object.ndim,) + current_object.shape, dtype=current_object.dtype
    )
    g = xp.zeros_like(p)
    d = xp.zeros_like(current_object)

    i = 0
    while i < max_num_iter:
        if i > 0:
            # d will be the (negative) divergence of p
            d = -p.sum(0)
            slices_d = [
                slice(None),
            ] * current_object.ndim
            slices_p = [
                slice(None),
            ] * (current_object.ndim + 1)
            for ax in range(len(ndim)):
                slices_d[ndim[ax]] = slice(1, None)
                slices_p[ndim[ax] + 1] = slice(0, -1)
                slices_p[0] = ndim[ax]
                d[tuple(slices_d)] += p[tuple(slices_p)]
                slices_d[ndim[ax]] = slice(None)
                slices_p[ndim[ax] + 1] = slice(None)
            updated_object = current_object + d
        else:
            updated_object = current_object
        E = (d**2).sum()

        # g stores the gradients of updated_object along each axis
        # e.g. g[0] is the first order finite difference along axis 0
        slices_g = [
            slice(None),
        ] * (current_object.ndim + 1)
        for ax in range(len(ndim)):
            slices_g[ndim[ax] + 1] = slice(0, -1)
            slices_g[0] = ndim[ax]
            g[tuple(slices_g)] = xp.diff(updated_object, axis=ndim[ax])
            slices_g[ndim[ax] + 1] = slice(None)
        if scaling is not None:
            scaling /= xp.max(scaling)
            g *= xp.array(scaling)[:, xp.newaxis, xp.newaxis]
        norm = xp.sqrt((g**2).sum(axis=0))[xp.newaxis, ...]
        E += weight * norm.sum()
        tau = 1.0 / (2.0 * len(ndim))
        norm *= tau / weight
        norm += 1.0
        p -= tau * g
        p /= norm
        E /= float(current_object.size)
        if i == 0:
            E_init = E
            E_previous = E
        else:
            if xp.abs(E_previous - E) < eps * E_init:
                break
            else:
                E_previous = E
        i += 1

    from py4DSTEM.process.phase.utils import array_slice

    if pad_object:
        for ax in range(len(ndim)):
            slices = array_slice(ndim[ax], current_object.ndim, 1, -1)
            updated_object = updated_object[slices]

    return updated_object / xp.sum(updated_object) * xp.sum(current_object)


def _object_positivity_constraint(self, current_object, shrinkage_rad):
    """
    Ptychographic positivity constraint.
    Used to ensure electrostatic potential is positive.

    Parameters
    --------
    current_object: np.ndarray
        Current object estimate
    shrinkage_rad: float
        Phase shift in radians to be subtracted from the potential at each iteration

    Returns
    --------
    constrained_object: np.ndarray
        Constrained object estimate
    """
    xp = self._xp

    if shrinkage_rad is not None:
        current_object -= shrinkage_rad

    return xp.maximum(current_object, 0.0)


def _object_gaussian_constraint(
    self, current_object, gaussian_filter_sigma, pure_phase_object
):
    """
    Ptychographic smoothness constraint.
    Used for blurring object.

    Parameters
    --------
    current_object: np.ndarray
        Current object estimate
    gaussian_filter_sigma: float
        Standard deviation of gaussian kernel
    pure_phase_object: bool
        If True, gaussian blur performed on phase only

    Returns
    --------
    constrained_object: np.ndarray
        Constrained object estimate
    """
    xp = self._xp
    gaussian_filter = self._gaussian_filter

    if pure_phase_object:
        phase = xp.angle(current_object)
        phase = gaussian_filter(phase, gaussian_filter_sigma)
        current_object = xp.exp(1.0j * phase)
    else:
        current_object = gaussian_filter(current_object, gaussian_filter_sigma)

    return current_object


def _object_butterworth_constraint(self, current_object, q_lowpass, q_highpass):
    """
    Butterworth filter

    Parameters
    --------
    current_object: np.ndarray
        Current object estimate
    q_lowpass: float
        Cut-off frequency in A^-1 for low-pass butterworth filter
    q_highpass: float
        Cut-off frequency in A^-1 for high-pass butterworth filter

    Returns
    --------
    constrained_object: np.ndarray
        Constrained object estimate
    """
    xp = self._xp
    qx = xp.fft.fftfreq(current_object.shape[0], self.sampling[0])
    qy = xp.fft.fftfreq(current_object.shape[1], self.sampling[1])

    qya, qxa = xp.meshgrid(qy, qx)
    qra = xp.sqrt(qxa**2 + qya**2)

    env = xp.ones_like(qra)
    if q_highpass:
        env *= 1 - 1 / (1 + (qra / q_highpass) ** 4)
    if q_lowpass:
        env *= 1 / (1 + (qra / q_lowpass) ** 4)

    current_object = xp.fft.ifft2(xp.fft.fft2(current_object) * env)

    if self._object_type == "potential":
        current_object = xp.real(current_object)

    return current_object


def _probe_center_of_mass_constraint(self, current_probe):
    """
    Ptychographic threshold constraint.
    Used for avoiding the scaling ambiguity between probe and object.

    Parameters
    --------
    current_probe: np.ndarray
        Current probe estimate

    Returns
    --------
    constrained_probe: np.ndarray
        Constrained probe estimate
    """
    xp = self._xp
    asnumpy = self._asnumpy

    probe_center = xp.array(self._region_of_interest_shape) / 2
    probe_intensity = asnumpy(xp.abs(current_probe) ** 2)

    probe_x0, probe_y0 = get_CoM(probe_intensity)
    shifted_probe = fft_shift(
        current_probe, probe_center - xp.array([probe_x0, probe_y0]), xp
    )

    return shifted_probe


def _probe_fourier_amplitude_constraint(self, current_probe, threshold):
    """
    Ptychographic probe fourier amplitude constraint

    Parameters
    ----------
    current_probe: np.ndarray
        Current positions estimate
    threshold: np.ndarray
        Threshold value for current probe fourier mask. Value should
        be between 0 and 1, where higher values provide the most masking.

    Returns
    --------
    constrained_probe: np.ndarray
        Constrained probe estimate
    """
    xp = self._xp
    erf = self._erf

    curent_probe_sum = xp.sum(xp.abs(current_probe) ** 2)
    current_probe_fft_amp = xp.abs(xp.fft.fft2(current_probe))

    threshold_px = xp.argmax(
        current_probe_fft_amp < xp.max(current_probe_fft_amp) * threshold
    )

    qx = xp.abs(xp.fft.fftfreq(current_probe.shape[0], 1))
    qy = xp.abs(xp.fft.fftfreq(current_probe.shape[1], 1))
    qya, qxa = xp.meshgrid(qy, qx)
    qra = xp.sqrt(qxa**2 + qya**2) - threshold_px / current_probe.shape[0]

    width = 5
    tophat_mask = 0.5 * (1 - erf(width * qra / (1 - qra**2)))

    updated_probe = xp.fft.ifft2(xp.fft.fft2(current_probe) * tophat_mask)
    updated_probe_sum = xp.sum(xp.abs(updated_probe) ** 2)

    return updated_probe / updated_probe_sum * curent_probe_sum


def _probe_finite_support_constraint(self, current_probe):
    """
    Ptychographic probe support constraint.
    Used for penalizing focused probes to replicate sample periodicity.

    Parameters
    --------
    current_probe: np.ndarray
        Current probe estimate

    Returns
    --------
    constrained_probe: np.ndarray
        Finite-support constrained probe estimate
    """

    return current_probe * self._probe_support_mask


def _positions_center_of_mass_constraint(self, current_positions):
    """
    Ptychographic position center of mass constraint.
    Additionally updates vectorized indices used in _overlap_projection.

    Parameters
    ----------
    current_positions: np.ndarray
        Current positions estimate

    Returns
    --------
    constrained_positions: np.ndarray
        CoM constrained positions estimate
    """
    xp = self._xp

    current_positions -= xp.mean(current_positions, axis=0) - self._positions_px_com
    self._positions_px_fractional = current_positions - xp.round(current_positions)

    (
        self._vectorized_patch_indices_row,
        self._vectorized_patch_indices_col,
    ) = self._extract_vectorized_patch_indices()

    return current_positions


def _positions_affine_transformation_constraint(
    self, initial_positions, current_positions
):
    """
    Constrains the updated positions to be an affine transformation of the initial scan positions,
    composing of two scale factors, a shear, and a rotation angle.

    Uses RANSAC to estimate the global transformation robustly.
    Stores the AffineTransformation in self._tf.

    Parameters
    ----------
    initial_positions: np.ndarray
        Initial scan positions
    current_positions: np.ndarray
        Current positions estimate

    Returns
    -------
    constrained_positions: np.ndarray
        Affine-transform constrained positions estimate
    """

    xp = self._xp

    tf, _ = estimate_global_transformation_ransac(
        positions0=initial_positions,
        positions1=current_positions,
        origin=self._positions_px_com,
        translation_allowed=True,
        min_sample=self._num_diffraction_patterns // 10,
        xp=xp,
    )

    self._tf = tf
    current_positions = tf(initial_positions, origin=self._positions_px_com, xp=xp)

    return current_positions
