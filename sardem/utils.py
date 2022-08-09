"""utils.py: extra helper functions"""
from __future__ import division, print_function

import logging
import os
import subprocess
import sys
from math import ceil, floor

from sardem import loading


def set_logger_handler(logger, level="INFO"):
    logger.setLevel(level)
    if logger.hasHandlers():
        # logger.handlers.clear()
        return
    h = logging.StreamHandler()
    h.setLevel(level)
    format_ = "[%(asctime)s] [%(levelname)s %(filename)s] %(message)s"
    fmt = logging.Formatter(format_, datefmt="%m/%d %H:%M:%S")
    h.setFormatter(fmt)
    logger.addHandler(h)


logger = logging.getLogger("sardem")
# set_logger_handler(logger)


def get_cache_dir():
    """Find location of directory to store .hgt downloads

    Assuming linux, uses ~/.cache/sardem/

    """
    path = os.getenv("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
    path = os.path.join(path, "sardem")  # Make subfolder for our downloads
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
    return floor((10 ** ndigits) * num) / (10 ** ndigits)


def is_file(f):
    """python 2/3 compatible check for file object"""
    return isinstance(f, file) if sys.version_info[0] == 2 else hasattr(f, "read")


def corner_coords(lon, lat, dlon, dlat):
    """Take the width/height, convert to 4 points of box corners"""
    dlat = abs(dlat)  # Since we start at top and go down
    return [
        [lon, lat],
        [lon + dlon, lat],
        [lon + dlon, lat - dlat],
        [lon, lat - dlat],
    ]


def bounding_box(left_lon=None, top_lat=None, dlon=None, dlat=None, geojson=None):
    """From a top left/dlat/dlon, compute bounding lon/lats

    Args:
        left_lon (float): Left (western) most longitude of DEM box
            in degrees (west=negative)
        top_lat (float): Top (northern) most latitude of DEM box (deg)
        dlon (float): width of bounding box
        dlat (float): height of bounding box
        geojson (dict): alternative to other args, geojson object for area

    Returns:
        tuple[float]: the left,bottom,right,top coords of bounding box
    """

    if all(arg is not None for arg in (left_lon, top_lat, dlon, dlat)):
        coordinates = corner_coords(left_lon, top_lat, dlon, dlat)
    elif geojson:
        coordinates = coords(geojson)
    else:
        raise ValueError("Must provide geojson, or top_corner, dlon, and dlat")

    left = min(float(lon) for (lon, lat) in coordinates)
    right = max(float(lon) for (lon, lat) in coordinates)

    top = max(float(lat) for (lon, lat) in coordinates)
    bottom = min(float(lat) for (lon, lat) in coordinates)
    return left, bottom, right, top


def coords(geojson):
    """Finds the coordinates of a geojson polygon
    Note: we are assuming one simple polygon with no holes

    Args:
        geojson (dict): loaded geojson dict

    Returns:
        list: coordinates of polygon in the geojson

    Raises:
        ValueError: if invalid geojson type (no 'geometry' in the json)
    """
    # First, if given a deeper object (e.g. from geojson.io), extract just polygon
    try:
        if geojson.get("type") == "FeatureCollection":
            geojson = geojson["features"][0]["geometry"]
        elif geojson.get("type") == "Feature":
            geojson = geojson["geometry"]
    except KeyError:
        raise ValueError("Invalid geojson")
    return geojson["coordinates"][0]


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


def _load_rsc_dict(rsc_dict=None, rsc_filename=None):
    if rsc_dict and rsc_filename:
        raise ValueError("Can only give one of rsc_dict or rsc_filename")
    elif not rsc_dict and not rsc_filename:
        raise ValueError("Must give at least one of rsc_dict or rsc_filename")

    if rsc_filename:
        rsc_dict = loading.load_dem_rsc(rsc_filename)
    return rsc_dict


def upsample_dem_rsc(xrate=None, yrate=None, rsc_dict=None, rsc_filename=None):
    """Creates a new .dem.rsc file for upsampled version

    Adjusts the FILE_LENGTH, WIDTH, X_STEP, Y_STEP for new rate

    Args:
        xrate (int): rate in x direcion to upsample the DEM
        yrate (int): rate in y direcion to upsample the DEM
        rsc_dict (str): Optional, the rsc data from Stitcher.create_dem_rsc()
        filepath (str): Optional, location of .dem.rsc file

    Note: Must supply only one of rsc_dict or rsc_filename

    Returns:
        str: file same as original with upsample adjusted numbers

    Raises:
        TypeError: if neither (or both) rsc_filename and rsc_dict are given

    """
    if not xrate and not yrate:
        raise ValueError("Must supply either xrate or yrate for upsampling")

    rsc_dict = _load_rsc_dict(rsc_dict=rsc_dict, rsc_filename=rsc_filename)

    xrate = xrate or 1
    yrate = yrate or 1
    outstring = ""
    for field, value in rsc_dict.items():
        # Files seemed to be left justified with 13 spaces? Not sure why 13
        # TODO: its 14- but fix this and previous formatting to be DRY
        if field.lower() == "width":
            new_size = up_size(value, xrate)
            outstring += "{field:<14s}{val}\n".format(field=field.upper(), val=new_size)
        elif field.lower() == "file_length":
            new_size = up_size(value, yrate)
            outstring += "{field:<14s}{val}\n".format(field=field.upper(), val=new_size)
        elif field.lower() == "x_step":
            # New is 1 + (size - 1) * rate, old is size, old rate is 1/(size-1)
            value /= xrate
            # Also give step floats proper sig figs to not output scientific notation
            outstring += "{field:<14s}{val:0.12f}\n".format(
                field=field.upper(), val=value
            )
        elif field.lower() == "y_step":
            value /= yrate
            outstring += "{field:<14s}{val:0.12f}\n".format(
                field=field.upper(), val=value
            )
        else:
            outstring += "{field:<14s}{val}\n".format(field=field.upper(), val=value)

    return outstring


def get_wkt_bbox(fname):
    try:
        from shapely import wkt
    except ImportError:
        logger.error("Need shapely installed to load from .wkt file")
        raise

    return wkt.load(fname).bounds
    # with open(fname) as f:
        # return wkt.load(f).bounds


def shift_rsc_file(rsc_filename=None, outname=None, to_gdal=True):
    """Shift the top-left of a .rsc file by half pixel

    The SRTM tiles are named such that the number represents the 
    lon/lat of the lower left corner *center* of the tile, so a shift
    is needed to create a .rsc file in GDAL convention.
    
    See here for geotransform info
    https://gdal.org/user/raster_data_model.html#affine-geotransform
    GDAL standard is to reference a raster by its top left edges,
    while some SAR processors use the middle of a pixel.

    `to_gdal`=True means it moves the X_FIRST, Y_FIRST up and left half a pixel.
    `to_gdal`=False does the reverse, back to the middle of the top left pixel
    """
    msg = "Shifting %s for GDAL conversion by half pixel "
    msg += "to edges" if to_gdal else "back to center"
    logger.info(msg, rsc_filename)
    if outname is None:
        outname = rsc_filename
    rsc_dict = loading.load_dem_rsc(rsc_filename)

    rsc_dict = shift_rsc_dict(rsc_dict, to_gdal=to_gdal)
    with open(outname, "w") as f:
        f.write(loading.format_dem_rsc(rsc_dict))


def shift_rsc_dict(rsc_dict, to_gdal=True):
    """Shift the top-left of the rsc data dictionary  by half pixel

    The SRTM tiles are named such that the number represents the 
    lon/lat of the lower left corner *center* of the tile, so a shift
    is needed to create a .rsc file in GDAL convention.
    
    See here for geotransform info
    https://gdal.org/user/raster_data_model.html#affine-geotransform
    GDAL standard is to reference a raster by its top left edges,
    while some SAR processors use the middle of a pixel.

    `to_gdal`=True means it moves the X_FIRST, Y_FIRST up and left half a pixel.
    `to_gdal`=False does the reverse, back to the middle of the top left pixel
    """
    is_lowercase = "x_first" in rsc_dict
    if is_lowercase:
        rsc_dict = {k.upper(): v for k, v in rsc_dict.items()}

    x_first, y_first = rsc_dict["X_FIRST"], rsc_dict["Y_FIRST"]
    x_step, y_step = rsc_dict["X_STEP"], rsc_dict["Y_STEP"]
    if to_gdal:
        # Move up+left half a pixel to represent the top left *edge* of the image
        new_first = {
            "X_FIRST": x_first - 0.5 * x_step,
            "Y_FIRST": y_first - 0.5 * y_step,
        }
    else:
        # Move down+right half a pixel to represent the *center* of top left pixel
        new_first = {
            "X_FIRST": x_first + 0.5 * x_step,
            "Y_FIRST": y_first + 0.5 * y_step,
        }
    rsc_dict.update(new_first)

    # return to lowercase if necessary
    if is_lowercase:
        rsc_dict = {k.lower(): v for k, v in rsc_dict.items()}
    return rsc_dict


def _gdal_installed_correctly():
    cmd = "gdalinfo --help-general"
    # cmd = "gdalinfo -h"
    try:
        subprocess.check_output(cmd, shell=True)
        return True
    except subprocess.CalledProcessError:
        logger.error("GDAL command failed to run.", exc_info=True)
        logger.error("Check GDAL installation.")
        return False