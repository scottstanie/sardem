"""utils.py: extra helper functions"""
from __future__ import division, print_function
import os
import sys
from math import floor, ceil
import logging
from sardem import loading


def set_logger_handler(logger, level='INFO'):
    logger.setLevel(level)
    h = logging.StreamHandler()
    h.setLevel(level)
    format_ = '[%(asctime)s] [%(levelname)s %(filename)s] %(message)s'
    fmt = logging.Formatter(format_, datefmt='%m/%d %H:%M:%S')
    h.setFormatter(fmt)
    logger.addHandler(h)


def get_cache_dir():
    """Find location of directory to store .hgt downloads

    Assuming linux, uses ~/.cache/sardem/

    """
    path = os.getenv('XDG_CACHE_HOME', os.path.expanduser('~/.cache'))
    path = os.path.join(path, 'sardem')  # Make subfolder for our downloads
    if not os.path.exists(path):
        os.makedirs(path)
    return path


def up_size(cur_size, rate):
    """Calculates the number of points to be computed in the upsampling

    Example: 3 points at x = (0, 1, 2), rate = 2 becomes 5 points:
        x = (0, .5, 1, 1.5, 2)
        >>> up_size(3, 2)
        5
    """
    return int(floor(1 + (cur_size - 1) * rate))


def floor_float(num, ndigits):
    """Like rounding to ndigits, but flooring

    Used for .dem.rsc creation, because rounding to 12 sigfigs
    causes the fortran routines to overstep the matrix and fail,
    since 0.000277777778*3600 = 1.00000000079.. , but
    0.000277777777*3600 = 0.99999999719

    Example:
        >>> floor_float(1/3600, 12)
        0.000277777777
    """
    return floor((10**ndigits) * num) / (10**ndigits)


def is_file(f):
    """python 2/3 compatible check for file object"""
    return isinstance(f, file) if sys.version_info[0] == 2 else hasattr(f, 'read')


def corner_coords(lon, lat, dlon, dlat):
    """Take the width/height, convert to 4 points of box corners"""
    dlat = abs(dlat)  # Since we start at top and go down
    return [
        [lon, lat],
        [lon + dlon, lat],
        [lon + dlon, lat - dlat],
        [lon, lat - dlat],
    ]


def bounding_box(left_lon=None, top_lat=None, dlon=None, dlat=None):
    """From a corner/dlat/dlon, compute bounding lon/lats

    Args:
        left_lon (float): Left (western) most longitude of DEM box
            in degrees (west=negative)
        top_lat (float): Top (northern) most latitude of DEM box (deg)
        dlon (float): width of bounding box (if top_corner given)
        dlat (float): height of bounding box (if top_corner given)

    Returns:
        tuple[float]: the left,bottom,right,top coords of bounding box
    """

    coordinates = corner_coords(left_lon, top_lat, dlon, dlat)

    left = min(float(lon) for (lon, lat) in coordinates)
    right = max(float(lon) for (lon, lat) in coordinates)

    top = max(float(lat) for (lon, lat) in coordinates)
    bottom = min(float(lat) for (lon, lat) in coordinates)
    return left, bottom, right, top


def find_bounding_idxs(bounds, x_step, y_step, x_first, y_first):
    """Finds the indices of stitched dem to crop bounding box

    Also finds the new x_start and y_start after cropping.

    Note: x_start, y_start could be different from bounds
    if steps didnt exactly match, but should be further up and left

    Takes the desired bounds, .rsc data from stitched dem,
    Examples:
        >>> bounds = (-155.49, 19.0, -154.5, 19.51)
        >>> x_step = 0.1
        >>> y_step = -0.1
        >>> x_first = -156
        >>> y_first = 20.0
        >>> print(find_bounding_idxs(bounds, x_step, y_step, x_first, y_first))
        ((5, 10, 15, 4), (-155.5, 19.6))
    """

    left, bot, right, top = bounds
    left_idx = int(floor((left - x_first) / x_step))
    right_idx = int(ceil((right - x_first) / x_step))
    # Note: y_step will be negative for these
    top_idx = int(floor((top - y_first) / y_step))
    bot_idx = int(ceil((bot - y_first) / y_step))
    new_x_first = x_first + x_step * left_idx
    new_y_first = y_first + y_step * top_idx  # Again: y_step negative
    return (left_idx, bot_idx, right_idx, top_idx), (new_x_first, new_y_first)


def upsample_dem_rsc(rate=None, rsc_dict=None, rsc_filepath=None):
    """Creates a new .dem.rsc file for upsampled version

    Adjusts the FILE_LENGTH, WIDTH, X_STEP, Y_STEP for new rate

    Args:
        rate (int): rate by which to upsample the DEM
        rsc_dict (str): Optional, the rsc data from Stitcher.create_dem_rsc()
        filepath (str): Optional, location of .dem.rsc file

    Note: Must supply only one of rsc_dict or rsc_filepath

    Returns:
        str: file same as original with upsample adjusted numbers

    Raises:
        TypeError: if neither (or both) rsc_filepath and rsc_dict are given

    """
    if rsc_dict and rsc_filepath:
        raise TypeError("Can only give one of rsc_dict or rsc_filepath")
    elif not rsc_dict and not rsc_filepath:
        raise TypeError("Must give at least one of rsc_dict or rsc_filepath")
    elif not rate:
        raise TypeError("Must supply rate for upsampling")

    if rsc_filepath:
        rsc_dict = loading.load_dem_rsc(rsc_filepath)

    outstring = ""
    for field, value in rsc_dict.items():
        # Files seemed to be left justified with 13 spaces? Not sure why 13
        # TODO: its 14- but fix this and previous formatting to be DRY
        if field.lower() in ('width', 'file_length'):
            new_size = up_size(value, rate)
            outstring += "{field:<14s}{val}\n".format(field=field.upper(), val=new_size)
        elif field.lower() in ('x_step', 'y_step'):
            # New is 1 + (size - 1) * rate, old is size, old rate is 1/(size-1)
            value /= rate
            # Also give step floats proper sig figs to not output scientific notation
            outstring += "{field:<14s}{val:0.12f}\n".format(field=field.upper(), val=value)
        else:
            outstring += "{field:<14s}{val}\n".format(field=field.upper(), val=value)

    return outstring
