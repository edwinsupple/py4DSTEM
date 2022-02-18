# Functions for creating flowline maps from diffraction spots


import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.axes import Axes
from scipy.ndimage import gaussian_filter1d

from matplotlib.colors import hsv_to_rgb
from matplotlib.colors import rgb_to_hsv
from matplotlib.colors import ListedColormap

from ...io.datastructure import PointList, PointListArray
from ..utils import tqdmnd


def make_orientation_histogram(
    bragg_peaks,
    radial_ranges,
    upsample_factor=4.0,
    theta_step_deg=1.0,
    sigma_x = 1.0,
    sigma_y = 1.0,
    sigma_theta = 3.0,
    normalize_intensity_image: bool = False,
    normalize_intensity_stack: bool = True,
    progress_bar: bool = True,
    ):
    """
    Create an 3D or 4D orientation histogram from a braggpeaks PointListArray,
    from user-specified radial ranges.
    
    Args:
        bragg_peaks (PointListArray):       2D of pointlists containing centered peak locations.
        radial_ranges (np array):           Size (N x 2) array for N radial bins, or (2,) for a single bin.
        upsample_factor (float):            Upsample factor
        theta_step_deg (float):             Step size along annular direction in degrees
        sigma_x (float):                    Smoothing in x direction before upsample
        sigma_y (float):                    Smoothing in x direction before upsample
        sigma_theta (float):                Smoothing in annular direction (units of bins, periodic)
        normalize_intensity_image (bool):   Normalize to max peak intensity = 1, per image
        normalize_intensity_stack (bool):   Normalize to max peak intensity = 1, all images
        progress_bar (bool):                Enable progress bar

    Returns:
        orient_hist (array):                4D array containing Bragg peak intensity histogram 
                                            [radial_bin x_probe y_probe theta]
    """

    # Input bins
    radial_ranges = np.array(radial_ranges)
    if radial_ranges.ndim == 1:
        radial_ranges = radial_ranges[None,:]
    radial_ranges_2 = radial_ranges**2
    num_radii = radial_ranges.shape[0]
    
    # coordinates
    theta = np.arange(0,180,theta_step_deg) * np.pi / 180.0
    dtheta = theta[1] - theta[0]
    dtheta_deg = dtheta * 180 / np.pi
    num_theta_bins = np.size(theta)
    size_input = bragg_peaks.shape
    size_output = np.round(np.array(size_input).astype('float') * upsample_factor).astype('int')

    # output init
    orient_hist = np.zeros([
        num_radii,
        size_output[0],
        size_output[1],
        num_theta_bins])

    for a0 in range(num_radii):
        # Loop over all probe positions
        t = "Generating histogram " + str(a0)
        for rx, ry in tqdmnd(
                *bragg_peaks.shape, desc=t,unit=" probe positions", disable=not progress_bar
            ):
            x = (rx + 0.5)*upsample_factor - 0.5
            y = (ry + 0.5)*upsample_factor - 0.5
            x = np.clip(x,0,size_output[0]-2)
            y = np.clip(y,0,size_output[1]-2)

            xF = np.floor(x).astype('int')
            yF = np.floor(y).astype('int')
            dx = x - xF
            dy = y - yF

            p = bragg_peaks.get_pointlist(rx,ry)
            r2 = p.data['qx']**2 + p.data['qy']**2

            sub = np.logical_and(r2 >= radial_ranges_2[a0,0], r2 < radial_ranges_2[a0,1])

            if np.any(sub):
                intensity = p.data['intensity'][sub]
                t = np.arctan2(p.data['qy'][sub],p.data['qx'][sub]) / dtheta
                tF = np.floor(t).astype('int')
                dt = t - tF

                orient_hist[a0,xF  ,yF  ,:] = orient_hist[a0,xF  ,yF  ,:] + \
                    np.bincount(np.mod(tF  ,num_theta_bins),
                        weights=(1-dx)*(1-dy)*(1-dt)*intensity,minlength=num_theta_bins)
                orient_hist[a0,xF  ,yF  ,:] = orient_hist[a0,xF  ,yF  ,:] + \
                    np.bincount(np.mod(tF+1,num_theta_bins),
                        weights=(1-dx)*(1-dy)*(  dt)*intensity,minlength=num_theta_bins)

                orient_hist[a0,xF+1,yF  ,:] = orient_hist[a0,xF+1,yF  ,:] + \
                    np.bincount(np.mod(tF  ,num_theta_bins),
                        weights=(  dx)*(1-dy)*(1-dt)*intensity,minlength=num_theta_bins)
                orient_hist[a0,xF+1,yF  ,:] = orient_hist[a0,xF+1,yF  ,:] + \
                    np.bincount(np.mod(tF+1,num_theta_bins),
                        weights=(  dx)*(1-dy)*(  dt)*intensity,minlength=num_theta_bins)
 
                orient_hist[a0,xF  ,yF+1,:] = orient_hist[a0,xF  ,yF+1,:] + \
                    np.bincount(np.mod(tF  ,num_theta_bins),
                        weights=(1-dx)*(  dy)*(1-dt)*intensity,minlength=num_theta_bins)
                orient_hist[a0,xF  ,yF+1,:] = orient_hist[a0,xF  ,yF+1,:] + \
                    np.bincount(np.mod(tF+1,num_theta_bins),
                        weights=(1-dx)*(  dy)*(  dt)*intensity,minlength=num_theta_bins)

                orient_hist[a0,xF+1,yF+1,:] = orient_hist[a0,xF+1,yF+1,:] + \
                    np.bincount(np.mod(tF  ,num_theta_bins),
                        weights=(  dx)*(  dy)*(1-dt)*intensity,minlength=num_theta_bins)
                orient_hist[a0,xF+1,yF+1,:] = orient_hist[a0,xF+1,yF+1,:] + \
                    np.bincount(np.mod(tF+1,num_theta_bins),
                        weights=(  dx)*(  dy)*(  dt)*intensity,minlength=num_theta_bins)           

    # smoothing / interpolation
    if (sigma_x is not None) or (sigma_y is not None) or (sigma_theta is not None):
        if num_radii > 1:
            print('Interpolating orientation matrices ...', end='')
        else:
            print('Interpolating orientation matrix ...', end='')            
        if sigma_x is not None and sigma_x > 0:
            orient_hist = gaussian_filter1d(
                orient_hist,sigma_x*upsample_factor,
                mode='nearest',
                axis=1,
                truncate=3.0)
        if sigma_y is not None and sigma_y > 0:
            orient_hist = gaussian_filter1d(
                orient_hist,sigma_y*upsample_factor,
                mode='nearest',
                axis=2,
                truncate=3.0)
        if sigma_theta is not None and sigma_theta > 0:
            orient_hist = gaussian_filter1d(
                orient_hist,sigma_theta/dtheta_deg,
                mode='wrap',
                axis=3,
                truncate=2.0)
        print(' done.')

    # normalization
    if normalize_intensity_stack is True:
            orient_hist = orient_hist / np.max(orient_hist)
    elif normalize_intensity_image is True:
        for a0 in range(num_radii):
            orient_hist[:,:,a0,:] = orient_hist[:,:,a0,:] / np.max(orient_hist[:,:,a0,:])

    return orient_hist



def make_flowline_map(
    orient_hist,
    thresh_seed = 0.2,
    thresh_grow = 0.05,
    thresh_collision = 0.001,
    sep_seeds = None,
    sep_xy = 6.0,
    sep_theta = 5.0,
    sort_seeds = 'intensity',
    linewidth = 2.0,
    step_size = 0.5,
    min_steps = 4,
    max_steps = 1000,
    sigma_x = 1.0,
    sigma_y = 1.0,
    sigma_theta = 2.0,
    progress_bar: bool = True,
    ):
    """
    Create an 3D or 4D orientation flowline map - essentially a pixelated "stream map" which represents diffraction data.
    
    Args:
        orient_hist (array):        Histogram of all orientations with coordinates 
                                    [radial_bin x_probe y_probe theta]
                                    We assume theta bin ranges from 0 to 180 degrees and is periodic.
        thresh_seed (float):        Threshold for seed generation in histogram.
        thresh_grow (float):        Threshold for flowline growth in histogram.
        thresh_collision (float):   Threshold for termination of flowline growth in histogram.
        sep_seeds (float):          Initial seed separation in bins - set to None to use default value,
                                    which is equal to 0.5*sep_xy.
        sep_xy (float):             Search radius for flowline direction in x and y.
        sep_theta = (float):        Search radius for flowline direction in theta.
        sort_seeds (str):           How to sort the initial seeds for growth:
                                        None - no sorting
                                        'intensity' - sort by histogram intensity
                                        'random' - random order
        linewidth (float):          Thickness of the flowlines in pixels.
        step_size (float):          Step size for flowline growth in pixels.
        min_steps (int):            Minimum number of steps for a flowline to be drawn.
        max_steps (int):            Maximum number of steps for a flowline to be drawn.
        sigma_x (float):            Weighted sigma in x direction for direction update.
        sigma_y (float):            Weighted sigma in y direction for direction update.
        sigma_theta (float):        Weighted sigma in theta for direction update.
        progress_bar (bool):        Enable progress bar

    Returns:
        orient_flowlines (array):   4D array containing flowlines
                                    [radial_bin x_probe y_probe theta]
    """

    # Default seed separation
    if sep_seeds is None:
        sep_seeds = np.round(sep_xy / 2 + 0.5).astype('int')

    # number of radial bins
    num_radii = orient_hist.shape[0]
    
    # coordinates
    theta = np.linspace(0,np.pi,orient_hist.shape[3],endpoint=False)
    dtheta = theta[1] - theta[0]
    size_3D = np.array([
        orient_hist.shape[1],
        orient_hist.shape[2],
        orient_hist.shape[3],
    ])

    # initialize weighting array
    vx = np.arange(-np.ceil(2*sigma_x),np.ceil(2*sigma_x)+1)
    vy = np.arange(-np.ceil(2*sigma_y),np.ceil(2*sigma_y)+1)
    vt = np.arange(-np.ceil(2*sigma_theta),np.ceil(2*sigma_theta)+1)
    ay,ax,at = np.meshgrid(vy,vx,vt)
    k = np.exp(ax**2/(-2*sigma_x**2)) * \
        np.exp(ay**2/(-2*sigma_y**2)) * \
        np.exp(at**2/(-2*sigma_theta**2))
    k = k / np.sum(k)  
    vx = vx[:,None,None].astype('int')
    vy = vy[None,:,None].astype('int')
    vt = vt[None,None,:].astype('int')

    # initialize collision check array
    cr = np.arange(-np.ceil(sep_xy),np.ceil(sep_xy)+1)
    ct = np.arange(-np.ceil(sep_theta),np.ceil(sep_theta)+1)
    ay,ax,at = np.meshgrid(cr,cr,ct)
    c_mask = ((ax**2 + ay**2)/sep_xy**2 + at**2/sep_theta**2 <= (1 + 1/sep_xy)**2)[None,:,:,:]
    cx = cr[None,:,None,None].astype('int')
    cy = cr[None,None,:,None].astype('int')
    ct = ct[None,None,None,:].astype('int')

    # initalize flowline array
    orient_flowlines = np.zeros_like(orient_hist)

    # initialize output
    xy_t_int = np.zeros((max_steps+1,4))
    xy_t_int_rev = np.zeros((max_steps+1,4))

    # Loop over radial bins
    for a0 in range(num_radii):
        # Find all seed locations
        orient = orient_hist[a0,:,:,:] 
        sub_seeds = np.logical_and(np.logical_and(
            orient >= np.roll(orient,1,axis=2),
            orient >= np.roll(orient,-1,axis=2)),
            orient >= thresh_seed)

        # Separate seeds
        if sep_seeds > 0:
            for a1 in range(sep_seeds-1):
                sub_seeds[a1::sep_seeds,:,:] = False
                sub_seeds[:,a1::sep_seeds,:] = False

        # Index seeds
        x_inds,y_inds,t_inds = np.where(sub_seeds)
        if sort_seeds is not None:
            if sort_seeds == 'intensity':
                inds_sort = np.argsort(orient[sub_seeds])[::-1]  
            elif sort_seeds == 'random':
                inds_sort = np.random.permutation(np.count_nonzero(sub_seeds))
            x_inds = x_inds[inds_sort]
            y_inds = y_inds[inds_sort]
            t_inds = t_inds[inds_sort]  

        # for a1 in tqdmnd(range(0,40), desc="Drawing flowlines",unit=" seeds", disable=not progress_bar):
        t = "Drawing flowlines " + str(a0)
        for a1 in tqdmnd(range(0,x_inds.shape[0]), desc=t, unit=" seeds", disable=not progress_bar):
            # initial coordinate and intensity
            xy0 = np.array((x_inds[a1],y_inds[a1]))
            t0 = theta[t_inds[a1]]

            # init theta
            inds_theta = np.mod(np.round(t0/dtheta).astype('int')+vt,orient.shape[2])
            orient_crop = k * orient[
                np.clip(np.round(xy0[0]).astype('int')+vx,0,orient.shape[0]-1),
                np.clip(np.round(xy0[1]).astype('int')+vy,0,orient.shape[1]-1),
                inds_theta]
            theta_crop = theta[inds_theta]
            t0 = np.sum(orient_crop * theta_crop) / np.sum(orient_crop)

            # forward direction
            t = t0
            v0 = np.array((-np.sin(t),np.cos(t)))
            v = v0 * step_size
            xy = xy0
            int_val = get_intensity(orient,xy0[0],xy0[1],t0/dtheta)
            xy_t_int[0,0:2] = xy0
            xy_t_int[0,2] = t/dtheta
            xy_t_int[0,3] = int_val
            # main loop
            grow = True
            count = 0
            while grow is True:
                count += 1

                # update position and intensity
                xy = xy + v 
                int_val = get_intensity(orient,xy[0],xy[1],t/dtheta)

                # check for collision
                flow_crop = orient_flowlines[
                    a0,
                    np.clip(np.round(xy[0]).astype('int')+cx,0,orient.shape[0]-1),
                    np.clip(np.round(xy[1]).astype('int')+cy,0,orient.shape[1]-1),
                    np.mod(np.round(t/dtheta).astype('int')+ct,orient.shape[2])
                ]
                int_flow = np.max(flow_crop[c_mask])

                if  xy[0] < 0 or \
                    xy[1] < 0 or \
                    xy[0] > orient.shape[0] or \
                    xy[1] > orient.shape[1] or \
                    int_val < thresh_grow or \
                    int_flow > thresh_collision:
                    grow = False
                else:
                    # update direction
                    inds_theta = np.mod(np.round(t/dtheta).astype('int')+vt,orient.shape[2])
                    orient_crop = k * orient[
                        np.clip(np.round(xy[0]).astype('int')+vx,0,orient.shape[0]-1),
                        np.clip(np.round(xy[1]).astype('int')+vy,0,orient.shape[1]-1),
                        inds_theta]
                    theta_crop = theta[inds_theta]
                    t = np.sum(orient_crop * theta_crop) / np.sum(orient_crop)
                    v = np.array((-np.sin(t),np.cos(t))) * step_size

                    xy_t_int[count,0:2] = xy
                    xy_t_int[count,2] = t/dtheta
                    xy_t_int[count,3] = int_val

                    if count > max_steps-1:
                        grow=False

            # reverse direction
            t = t0 + np.pi
            v0 = np.array((-np.sin(t),np.cos(t)))
            v = v0 * step_size
            xy = xy0
            int_val = get_intensity(orient,xy0[0],xy0[1],t0/dtheta)
            xy_t_int_rev[0,0:2] = xy0
            xy_t_int_rev[0,2] = t/dtheta
            xy_t_int_rev[0,3] = int_val
            # main loop
            grow = True
            count_rev = 0
            while grow is True:
                count_rev += 1

                # update position and intensity
                xy = xy + v 
                int_val = get_intensity(orient,xy[0],xy[1],t/dtheta)

                # check for collision
                flow_crop = orient_flowlines[
                    a0,
                    np.clip(np.round(xy[0]).astype('int')+cx,0,orient.shape[0]-1),
                    np.clip(np.round(xy[1]).astype('int')+cy,0,orient.shape[1]-1),
                    np.mod(np.round(t/dtheta).astype('int')+ct,orient.shape[2])
                ]
                int_flow = np.max(flow_crop[c_mask])

                if  xy[0] < 0 or \
                    xy[1] < 0 or \
                    xy[0] > orient.shape[0] or \
                    xy[1] > orient.shape[1] or \
                    int_val < thresh_grow or \
                    int_flow > thresh_collision:
                    grow = False
                else:
                    # update direction
                    inds_theta = np.mod(np.round(t/dtheta).astype('int')+vt,orient.shape[2])
                    orient_crop = k * orient[
                        np.clip(np.round(xy[0]).astype('int')+vx,0,orient.shape[0]-1),
                        np.clip(np.round(xy[1]).astype('int')+vy,0,orient.shape[1]-1),
                        inds_theta]
                    theta_crop = theta[inds_theta]
                    t = np.sum(orient_crop * theta_crop) / np.sum(orient_crop) + np.pi
                    v = np.array((-np.sin(t),np.cos(t))) * step_size

                    xy_t_int_rev[count_rev,0:2] = xy
                    xy_t_int_rev[count_rev,2] = t/dtheta
                    xy_t_int_rev[count_rev,3] = int_val

                    if count_rev > max_steps-1:
                        grow=False

            # write into output array
            if count + count_rev > min_steps:
                if count > 0:
                    orient_flowlines[a0,:,:,:] = set_intensity(
                        orient_flowlines[a0,:,:,:],
                        xy_t_int[1:count,:])
                if count_rev > 1:
                    orient_flowlines[a0,:,:,:] = set_intensity(
                        orient_flowlines[a0,:,:,:],
                        xy_t_int_rev[1:count_rev,:])

    # normalize to step size
    orient_flowlines = orient_flowlines * step_size

    # linewidth
    if linewidth > 1.0:
        s = linewidth - 1.0
        
        orient_flowlines = gaussian_filter1d(
            orient_flowlines, 
            s, 
            axis=1,
            truncate=3.0)
        orient_flowlines = gaussian_filter1d(
            orient_flowlines, 
            s, 
            axis=2,
            truncate=3.0)
        orient_flowlines = orient_flowlines * (s**2)

    return orient_flowlines




def make_flowline_rainbow_image(
    orient_flowlines,
    int_range = [0,0.2],
    sym_rotation_order = 2,
    theta_offset = 0.0,
    greyscale = False,
    greyscale_max = True,
    white_background = False,
    power_scaling = 1.0,
    sum_radial_bins = False,
    plot_images = True,
    ):
    """
    Generate RGB output images from the flowline arrays.
    
    Args:
        orient_flowline (array):    Histogram of all orientations with coordinates [x y radial_bin theta]
                                    We assume theta bin ranges from 0 to 180 degrees and is periodic.
        int_range (float)           2 element array giving the intensity range
        sym_rotation_order (int):   rotational symmety for colouring
        theta_offset (float):       Offset the anglular coloring by this value in radians.
        greyscale (bool):           Set to False for color output, True for greyscale output.
        greyscale_max (bool):       If output is greyscale, use max instead of mean for overlapping flowlines.
        white_background (bool):    For either color or greyscale output, switch to white background (from black).
        power_scaling (float):      Power law scaling for flowline intensity output.
        sum_radial_bins (bool):     Sum all radial bins (alternative is to output separate images).
        plot_images (bool):         Plot the outputs for quick visualization.

    Returns:
        im_flowline (array):        3D or 4D array containing flowline images
    """

    # init array
    size_input = orient_flowlines.shape
    size_output = np.array([size_input[0],size_input[1],size_input[2],3])
    im_flowline = np.zeros(size_output)

    if greyscale is True:
        for a0 in range(size_input[0]):
            if greyscale_max is True:
                im = np.max(orient_flowlines[a0,:,:,:],axis=2)
            else:
                im = np.mean(orient_flowlines[a0,:,:,:],axis=2)

            sig = np.clip((im - int_range[0]) \
                / (int_range[1] - int_range[0]),0,1)

            if power_scaling != 1:
                sig = sig ** power_scaling

            if white_background is False:
                im_flowline[a0,:,:,:] = sig[:,:,None]
            else:
                im_flowline[a0,:,:,:] = 1-sig[:,:,None]

    else:
        # Color basis
        c0 = np.array([1.0, 0.0, 0.0])
        c1 = np.array([0.0, 0.7, 0.0])
        c2 = np.array([0.0, 0.3, 1.0])

        # angles
        theta = np.linspace(0,np.pi,size_input[3],endpoint=False)
        theta_color = theta * sym_rotation_order

        # color projections
        b0 =  np.maximum(1 - np.abs(np.mod(theta_offset + theta_color + np.pi, 2*np.pi) - np.pi)**2 / (np.pi*2/3)**2, 0)
        b1 =  np.maximum(1 - np.abs(np.mod(theta_offset + theta_color - np.pi*2/3 + np.pi, 2*np.pi) - np.pi)**2 / (np.pi*2/3)**2, 0)
        b2 =  np.maximum(1 - np.abs(np.mod(theta_offset + theta_color - np.pi*4/3 + np.pi, 2*np.pi) - np.pi)**2 / (np.pi*2/3)**2, 0)


        for a0 in range(size_input[0]):
            sig = np.clip(
                (orient_flowlines[a0,:,:,:] - int_range[0]) \
                / (int_range[1] - int_range[0]),0,1)
            if power_scaling != 1:
                sig = sig ** power_scaling

            im_flowline[a0,:,:,:] = \
                np.sum(sig * b0[None,None,:], axis=2)[:,:,None]*c0[None,None,:] + \
                np.sum(sig * b1[None,None,:], axis=2)[:,:,None]*c1[None,None,:] + \
                np.sum(sig * b2[None,None,:], axis=2)[:,:,None]*c2[None,None,:]
                
            # clip limits
            im_flowline[a0,:,:,:] = np.clip(im_flowline[a0,:,:,:],0,1)

            # contrast flip
            if white_background is True:
                im = rgb_to_hsv(im_flowline[a0])
                im_v = im[:,:,2]
                im[:,:,1] = im_v
                im[:,:,2] = 1
                im_flowline[a0] = hsv_to_rgb(im)

    if sum_radial_bins is True:
        if white_background is False:
            im_flowline = np.clip(np.sum(im_flowline,axis=0),0,1)[None,:,:,:]
        else:
            # im_flowline = np.clip(np.sum(im_flowline,axis=0)+1-im_flowline.shape[0],0,1)[None,:,:,:]
            im_flowline = np.min(im_flowline,axis=0)[None,:,:,:]


    if plot_images is True:
        fig,ax = plt.subplots(im_flowline.shape[0],1,figsize=(10,im_flowline.shape[0]*10))

        if im_flowline.shape[0] > 1:
            for a0 in range(im_flowline.shape[0]):
                ax[a0].imshow(im_flowline[a0])
                # ax[a0].axis('off')
            plt.subplots_adjust(wspace=0, hspace=0.02)
        else:
            ax.imshow(im_flowline[0])
            # ax.axis('off')
        plt.show()

    return im_flowline



def make_flowline_rainbow_legend(
    im_size=np.array([256,256]),
    sym_rotation_order = 2,
    theta_offset = 0.0,
    white_background = False,
    return_image=False,
    radial_range=np.array([0.45,0.9]),
    plot_legend=True,
    figsize=(4,4),
    ):
    """
    This function generates a legend for a the rainbow colored flowline maps, and returns it as an RGB image.
    
    Args:
        im_size (np.array):         Size of legend image in pixels.
        sym_rotation_order (int):   rotational symmety for colouring
        theta_offset (float):       Offset the anglular coloring by this value in radians.
        white_background (bool):    For either color or greyscale output, switch to white background (from black).
        return_image (bool):        Return the image array.
        radial_range (np.array):    Inner and outer radius for the legend ring.
        plot_legend (bool):         Plot the generated legend.
        figsize (tuple or list):    Size of the plotted legend.     

    Returns:
        im_legend (array):          Image array for the legend.
    """



    # Color basis
    c0 = np.array([1.0, 0.0, 0.0])
    c1 = np.array([0.0, 0.7, 0.0])
    c2 = np.array([0.0, 0.3, 1.0])

    # Coordinates
    x = np.linspace(-1,1,im_size[0])
    y = np.linspace(-1,1,im_size[1])
    ya,xa = np.meshgrid(-y,x)
    ra = np.sqrt(xa**2 + ya**2)
    ta = np.arctan2(ya,xa)
    ta_sym = ta*sym_rotation_order

    # mask
    dr = xa[1,0] - xa[0,0]
    mask = np.clip((radial_range[1] - ra)/dr + 0.5,0,1) \
        * np.clip((ra - radial_range[0])/dr + 0.5,0,1)

    # rgb image
    b0 =  np.maximum(1 - np.abs(np.mod(theta_offset + ta_sym + np.pi, 2*np.pi) - np.pi)**2 / (np.pi*2/3)**2, 0)
    b1 =  np.maximum(1 - np.abs(np.mod(theta_offset + ta_sym - np.pi*2/3 + np.pi, 2*np.pi) - np.pi)**2 / (np.pi*2/3)**2, 0)
    b2 =  np.maximum(1 - np.abs(np.mod(theta_offset + ta_sym - np.pi*4/3 + np.pi, 2*np.pi) - np.pi)**2 / (np.pi*2/3)**2, 0)
    im_legend = \
        b0[:,:,None]*c0[None,None,:] + \
        b1[:,:,None]*c1[None,None,:] + \
        b2[:,:,None]*c2[None,None,:]
    im_legend = im_legend * mask[:,:,None]

    if white_background is True:
        im_legend = rgb_to_hsv(im_legend)
        im_v = im_legend[:,:,2]
        im_legend[:,:,1] = im_v
        im_legend[:,:,2] = 1
        im_legend = hsv_to_rgb(im_legend)

    # plotting
    if plot_legend:
        fig,ax = plt.subplots(1,1,figsize=figsize)
        ax.imshow(im_legend)
        ax.invert_yaxis()
        # ax.set_axis_off()
        ax.axis('off')



    # # angles
    # theta = np.linspace(0,np.pi,num_angle_bins,endpoint=False)
    # theta_color = theta * sym_rotation_order

    # # color projections
    # b0 =  np.maximum(1 - np.abs(np.mod(theta_color + np.pi, 2*np.pi) - np.pi)**2 / (np.pi*2/3)**2, 0)
    # b1 =  np.maximum(1 - np.abs(np.mod(theta_color - np.pi*2/3 + np.pi, 2*np.pi) - np.pi)**2 / (np.pi*2/3)**2, 0)
    # b2 =  np.maximum(1 - np.abs(np.mod(theta_color - np.pi*4/3 + np.pi, 2*np.pi) - np.pi)**2 / (np.pi*2/3)**2, 0)

    # print(b0.shape)
    if return_image:
        return im_legend


def make_flowline_combined_image(
    orient_flowlines,
    int_range = [0,0.2],
    cvals = np.array([
        [0.0,0.7,0.0],
        [1.0,0.0,0.0],
        [0.0,0.7,1.0],
        ]),
    white_background = False,
    power_scaling = 1.0,
    sum_radial_bins = True,
    plot_images = True,
    ):
    """
    Generate RGB output images from the flowline arrays.

    Args:
        orient_flowline (array):    Histogram of all orientations with coordinates [x y radial_bin theta]
                                    We assume theta bin ranges from 0 to 180 degrees and is periodic.
        int_range (float)           2 element array giving the intensity range
        cvals (array):              Nx3 size array containing RGB colors for different radial ibns.
        white_background (bool):    For either color or greyscale output, switch to white background (from black).
        power_scaling (float):      Power law scaling for flowline intensities.
        sum_radial_bins (bool):     Sum outputs over radial bins.
        plot_images (bool):         Plot the output images for quick visualization.

    Returns:
        im_flowline (array):        flowline images
    """

    # init array
    size_input = orient_flowlines.shape
    size_output = np.array([size_input[0],size_input[1],size_input[2],3])
    im_flowline = np.zeros(size_output)

    # Generate all color images
    for a0 in range(size_input[0]):
        sig = np.clip(
            (np.sum(orient_flowlines[a0,:,:,:],axis=2) - int_range[0]) \
            / (int_range[1] - int_range[0]),0,1)
        if power_scaling != 1:
            sig = sig ** power_scaling

        im_flowline[a0,:,:,:] = sig[:,:,None]*cvals[a0,:][None,None,:]

        # contrast flip
        if white_background is True:
            im = rgb_to_hsv(im_flowline[a0,:,:,:])
            # im_s = im[:,:,1]
            im_v = im[:,:,2]
            im[:,:,1] = im_v
            im[:,:,2] = 1
            im_flowline[a0,:,:,:] = hsv_to_rgb(im)

    if sum_radial_bins is True:
        im_flowline = np.clip(np.sum(im_flowline,axis=0),0,1)[None,:,:,:]

    if plot_images is True:
        fig,ax = plt.subplots(im_flowline.shape[0],1,figsize=(10,im_flowline.shape[0]*10))

        if im_flowline.shape[0] > 1:
            for a0 in range(im_flowline.shape[0]):
                ax[a0].imshow(im_flowline[a0])
                ax[a0].axis('off')
            plt.subplots_adjust(wspace=0, hspace=0.02)
        else:
            ax.imshow(im_flowline[0])
            ax.axis('off')
        plt.show()

    return im_flowline



def orientation_correlation(
    orient_hist,
    radius_max=None,    
    ):
    """
    Take in the 4D orientation histogram, and compute the distance-angle (auto)correlations
    
    Args:
        orient_hist (array):    3D or 4D histogram of all orientations with coordinates [x y radial_bin theta]
        radius_max (float):     Maximum radial distance for correlogram calculation. If set to None, the maximum 
                                radius will be set to min(orient_hist.shape[0],orient_hist.shape[1])/2.

    Returns:
        orient_corr (array):          3D or 4D array containing correlation images as function of (dr,dtheta)
    """

    # Array sizes
    size_input = np.array(orient_hist.shape)
    if radius_max is None:
        radius_max = np.ceil(np.min(orient_hist.shape[1:2])/2).astype('int')
    size_corr = np.array([
        np.maximum(size_input[1],2*radius_max),
        np.maximum(size_input[2],2*radius_max)])

    # Pad and initialize orientation histogram
    x_inds = np.concatenate((
        np.arange(np.ceil(size_input[1]/2)),
        np.arange(-np.floor(size_input[1]/2),0) + size_corr[0]
        )).astype('int')
    y_inds = np.concatenate((
        np.arange(np.ceil(size_input[2]/2)),
        np.arange(-np.floor(size_input[2]/2),0) + size_corr[1]
        )).astype('int')
    orient_hist_pad = np.zeros((
        size_input[0],
        size_corr[0],
        size_corr[1],
        size_input[3],        
        ),dtype='complex')
    orient_norm_pad = np.zeros((
        size_input[0],
        size_corr[0],
        size_corr[1],
        ),dtype='complex')
    orient_hist_pad[:,x_inds[:,None],y_inds[None,:],:] = \
        np.fft.fftn(orient_hist,axes=(1,2,3))
    orient_norm_pad[:,x_inds[:,None],y_inds[None,:]]   = \
        np.fft.fftn(np.sum(orient_hist,axis=3),axes=(1,2)) / np.sqrt(size_input[3])

    # Radial coordinates for integration
    x = np.mod(np.arange(size_corr[0])+size_corr[0]/2,size_corr[0])-size_corr[0]/2
    y = np.mod(np.arange(size_corr[1])+size_corr[1]/2,size_corr[1])-size_corr[1]/2
    ya,xa = np.meshgrid(y,x)
    ra = np.sqrt(xa**2 + ya**2)

    # coordinate subset
    sub0 = ra <= radius_max
    sub1 = ra <= radius_max-1
    rF0 = np.floor(ra[sub0]).astype('int')
    rF1 = np.floor(ra[sub1]).astype('int')
    dr0 = ra[sub0] - rF0
    dr1 = ra[sub1] - rF1
    inds = np.concatenate((rF0,rF1+1))
    weights = np.concatenate((1-dr0,dr1))

    # init output
    num_corr = (0.5*size_input[0]*(size_input[0]+1)).astype('int')
    orient_corr = np.zeros((
        num_corr,
        (size_input[3]/2+1).astype('int'),
        radius_max+1,
        ))

    # Main correlation calculation
    ind_output = 0
    for a0 in range(size_input[0]):
        for a1 in range(size_input[0]):
            if a0 <= a1:
                # Correlation
                c = np.real(np.fft.ifftn(
                    orient_hist_pad[a0,:,:,:] * \
                    np.conj(orient_hist_pad[a1,:,:,:]),
                    axes=(0,1,2)))

                # Loop over all angles from 0 to pi/2  (half of indices)
                for a2 in range((size_input[3]/2+1).astype('int')):
                    orient_corr[ind_output,a2,:] = \
                        np.bincount(
                            inds,
                            weights=weights*np.concatenate((c[:,:,a2][sub0],c[:,:,a2][sub1])),
                            minlength=radius_max,
                            )
                    
                # normalize
                c_norm = np.real(np.fft.ifftn(
                    orient_norm_pad[a0,:,:] * \
                    np.conj(orient_norm_pad[a1,:,:]),
                    axes=(0,1)))
                sig_norm = np.bincount(
                    inds,
                    weights=weights*np.concatenate((c_norm[sub0],c_norm[sub1])),
                    minlength=radius_max,
                    )
                orient_corr[ind_output,:,:] /= sig_norm[None,:]
    
                # increment output index
                ind_output += 1

    return orient_corr


def plot_orientation_correlation(
    orient_corr,
    prob_range=[0.1, 10.0],
    inds_plot=None,
    pixel_size=None,
    pixel_units=None,
    size_fig=[8,6],
    return_fig=False,
    ):

    """
    Plot the distance-angle (auto)correlations in orient_corr.
    
    Args:
        orient_corr (array):    3D or 4D array containing correlation images as function of (dr,dtheta)
                                1st index represents each pair of rings.
        prob_range (array):     Plotting range in units of "multiples of random distribution".
        inds_plot (float):      Which indices to plot for orient_corr.  Set to "None" to plot all pairs.
        pixel_size (float):     Pixel size for x axis.
        pixel_units (str):      units of pixels.
        size_fig (array):       Size of the figure panels.
        return_fig (bool):      Whether to return figure axes.

    Returns:
        fig, ax                 Figure and axes handles (optional).
        
    """

    # Make sure range is an numpy array
    prob_range = np.array(prob_range)

    if pixel_units is None:
        pixel_units = 'pixels'

    # Get the pair indices
    size_input = orient_corr.shape
    num_corr = (np.sqrt(8*size_input[0]+1)/2-1/2).astype('int')
    ya,xa = np.meshgrid(np.arange(num_corr),np.arange(num_corr))
    keep = ya >= xa
    # row 0 is the first diff ring, row 1 is the second diff ring
    pair_inds = np.vstack((xa[keep],ya[keep]))

    if inds_plot is None:
        inds_plot = np.arange(size_input[0])
    elif np.ndim(inds_plot) == 0:
        inds_plot = np.atleast_1d(inds_plot)
    else:
        inds_plot = np.array(inds_plot)

    # Custom divergent colormap:
    # dark blue
    # light blue
    # white
    # red
    # dark red
    N = 256
    cvals = np.zeros((N, 4))
    cvals[:,3] = 1
    c = np.linspace(0.0,1.0,int(N/4))

    cvals[0:int(N/4),1] = c*0.4+0.3
    cvals[0:int(N/4),2] = 1
    
    cvals[int(N/4):int(N/2),0] = c
    cvals[int(N/4):int(N/2),1] = c*0.3+0.7
    cvals[int(N/4):int(N/2),2] = 1

    cvals[int(N/2):int(N*3/4),0] = 1
    cvals[int(N/2):int(N*3/4),1] = 1-c
    cvals[int(N/2):int(N*3/4),2] = 1-c

    cvals[int(N*3/4):N,0] = 1-0.5*c
    new_cmap = ListedColormap(cvals)

    # plotting
    num_plot = inds_plot.shape[0]
    fig,ax = plt.subplots(
        num_plot,
        1,
        figsize=(size_fig[0],num_plot*size_fig[1]))

    # loop over indices
    for count,ind in enumerate(inds_plot):
        if num_plot > 1:
            p = ax[count].imshow(
                np.log10(orient_corr[ind,:,:]),
                vmin=np.log10(prob_range[0]), 
                vmax=np.log10(prob_range[1]),
                aspect='auto',
                cmap=new_cmap
                )
            ax_handle = ax[count]
        else:
            p = ax.imshow(
                np.log10(orient_corr[ind,:,:]),
                vmin=np.log10(prob_range[0]), 
                vmax=np.log10(prob_range[1]),
                aspect='auto',
                cmap=new_cmap
                )
            ax_handle = ax

        cbar = fig.colorbar(p, ax=ax_handle)
        t = cbar.get_ticks()
        t_lab = []
        for a1 in range(t.shape[0]):
            t_lab.append(f"{10**t[a1]:.2g}")

        cbar.set_ticks(t)
        cbar.ax.set_yticklabels(t_lab)
        cbar.ax.set_ylabel(
            'Probability [mult. of rand. dist.]',
            fontsize=12)


        ind_0 = pair_inds[0,ind]
        ind_1 = pair_inds[1,ind]

        if ind_0 != ind_1:
            ax_handle.set_title(
                'Correlation of Rings ' + str(ind_0)  + ' and ' + str(ind_1),
                fontsize=16)
        else:
            ax_handle.set_title(
                'Autocorrelation of Ring ' + str(ind_0),
                fontsize=16)


        ax_handle.invert_yaxis()
        ax_handle.set_xlabel(
            'Radial Distance [' + pixel_units + ']',
            fontsize=12)
        ax_handle.set_ylabel(
            'Relative Grain Orientation [degrees]',
            fontsize=12)
        ax_handle.set_yticks(
            [0,10,20,30,40,50,60,70,80,90])
        ax_handle.set_yticklabels(
            ['0','','','30','','','60','','','90'])


    plt.show()

    if return_fig is True:
        return fig, ax


def get_intensity(orient,x,y,t):
    # utility function to get histogram intensites

    x = np.clip(x,0,orient.shape[0]-2)
    y = np.clip(y,0,orient.shape[1]-2)

    xF = np.floor(x).astype('int')
    yF = np.floor(y).astype('int')
    tF = np.floor(t).astype('int')
    dx = x - xF
    dy = y - yF
    dt = t - tF
    t1 = np.mod(tF  ,orient.shape[2])
    t2 = np.mod(tF+1,orient.shape[2])

    int_vals = \
        orient[xF  ,yF  ,t1]*((1-dx)*(1-dy)*(1-dt)) + \
        orient[xF  ,yF  ,t2]*((1-dx)*(1-dy)*(  dt)) + \
        orient[xF  ,yF+1,t1]*((1-dx)*(  dy)*(1-dt)) + \
        orient[xF  ,yF+1,t2]*((1-dx)*(  dy)*(  dt)) + \
        orient[xF+1,yF  ,t1]*((  dx)*(1-dy)*(1-dt)) + \
        orient[xF+1,yF  ,t2]*((  dx)*(1-dy)*(  dt)) + \
        orient[xF+1,yF+1,t1]*((  dx)*(  dy)*(1-dt)) + \
        orient[xF+1,yF+1,t2]*((  dx)*(  dy)*(  dt))

    return int_vals


def set_intensity(orient,xy_t_int):
    # utility function to set flowline intensites

    xF = np.floor(xy_t_int[:,0]).astype('int')
    yF = np.floor(xy_t_int[:,1]).astype('int')
    tF = np.floor(xy_t_int[:,2]).astype('int')
    dx = xy_t_int[:,0] - xF
    dy = xy_t_int[:,1] - yF
    dt = xy_t_int[:,2] - tF

    inds_1D = np.ravel_multi_index(
        [xF  ,yF  ,tF  ], 
        orient.shape[0:3], 
        mode=['clip','clip','wrap'])
    orient.ravel()[inds_1D] = orient.ravel()[inds_1D] + xy_t_int[:,3]*(1-dx)*(1-dy)*(1-dt)
    inds_1D = np.ravel_multi_index(
        [xF  ,yF  ,tF+1], 
        orient.shape[0:3], 
        mode=['clip','clip','wrap'])
    orient.ravel()[inds_1D] = orient.ravel()[inds_1D] + xy_t_int[:,3]*(1-dx)*(1-dy)*(  dt)
    inds_1D = np.ravel_multi_index(
        [xF  ,yF+1,tF  ], 
        orient.shape[0:3], 
        mode=['clip','clip','wrap'])
    orient.ravel()[inds_1D] = orient.ravel()[inds_1D] + xy_t_int[:,3]*(1-dx)*(  dy)*(1-dt)
    inds_1D = np.ravel_multi_index(
        [xF  ,yF+1,tF+1], 
        orient.shape[0:3], 
        mode=['clip','clip','wrap'])
    orient.ravel()[inds_1D] = orient.ravel()[inds_1D] + xy_t_int[:,3]*(1-dx)*(  dy)*(  dt)
    inds_1D = np.ravel_multi_index(
        [xF+1,yF  ,tF  ], 
        orient.shape[0:3], 
        mode=['clip','clip','wrap'])
    orient.ravel()[inds_1D] = orient.ravel()[inds_1D] + xy_t_int[:,3]*(  dx)*(1-dy)*(1-dt)
    inds_1D = np.ravel_multi_index(
        [xF+1,yF  ,tF+1], 
        orient.shape[0:3], 
        mode=['clip','clip','wrap'])
    orient.ravel()[inds_1D] = orient.ravel()[inds_1D] + xy_t_int[:,3]*(  dx)*(1-dy)*(  dt)
    inds_1D = np.ravel_multi_index(
        [xF+1,yF+1,tF  ], 
        orient.shape[0:3], 
        mode=['clip','clip','wrap'])
    orient.ravel()[inds_1D] = orient.ravel()[inds_1D] + xy_t_int[:,3]*(  dx)*(  dy)*(1-dt)
    inds_1D = np.ravel_multi_index(
        [xF+1,yF+1,tF+1], 
        orient.shape[0:3], 
        mode=['clip','clip','wrap'])
    orient.ravel()[inds_1D] = orient.ravel()[inds_1D] + xy_t_int[:,3]*(  dx)*(  dy)*(  dt)

    return orient
