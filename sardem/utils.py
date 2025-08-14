"""utils.py: extra helper functions"""

from __future__ import division, print_function

import logging
import os
import subprocess
import sys
from math import floor

from sardem import loading
from sardem.constants import DEFAULT_RES


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


def shift_integer_bbox(bbox):
    """Shift the integer bounds of a bbox by 1/2 pixel to select a whole tile"""
    left, bottom, right, top = bbox
    hp = 0.5 * DEFAULT_RES  # half pixel
    # Tile names refer to the center of the bottom-left corner of the tile
    return left - hp, bottom + hp, right - hp, top + hp


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
            "X_FIRST": round(x_first - 0.5 * x_step, 9),
            "Y_FIRST": round(y_first - 0.5 * y_step, 9),
        }
    else:
        # Move down+right half a pixel to represent the *center* of top left pixel
        new_first = {
            "X_FIRST": round(x_first + 0.5 * x_step, 9),
            "Y_FIRST": round(y_first + 0.5 * y_step, 9),
        }
    rsc_dict.update(new_first)

    # return to lowercase if necessary
    if is_lowercase:
        rsc_dict = {k.lower(): v for k, v in rsc_dict.items()}
    return rsc_dict


def get_output_size(bounds, xrate, yrate):
    """Calculate the output size of a raster given the bounds and rates"""
    default_spacing = 0.0002777777777777778
    left, bottom, right, top = bounds
    width = right - left
    height = top - bottom
    rows = int(round(width / default_spacing * xrate))
    cols = int(round(height / default_spacing * yrate))
    return rows, cols


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


def gdal2isce_xml(fname, keep_egm=False):
    """
    Generate ISCE xml file from gdal supported file

    Example: import isce
             from applications.gdal2isce_xml import gdal2isce_xml
             xml_file = gdal2isce_xml(fname+'.vrt')
    """
    _gdal_installed_correctly()
    import rasterio

    try:
        import isce  # noqa
        import isceobj
    except ImportError:
        logger.error("isce2 not installed. Cannot generate xml file.")
        raise

    # open the rasterio file and get typical data information
    RASTERIO2ISCE_DATATYPE = {
        "uint8": "BYTE",
        "uint16": "uint16",
        "int16": "SHORT",
        "uint32": "uint32",
        "int32": "INT",
        "float32": "FLOAT",
        "float64": "DOUBLE",
        "complex64": "CFLOAT",
        "complex128": "complex128",
    }

    # check if the input file is a vrt
    fbase, fext = os.path.splitext(fname)
    if fext == ".vrt":
        outname = fbase
    else:
        outname = fname
    logger.info("Writing to %s", outname)

    # open the rasterio file and get typical dataset information
    with rasterio.open(fname) as ds:
        width = ds.width
        length = ds.height
        bands = ds.count
        logger.info("width:       " + "\t" + str(width))
        logger.info("length:      " + "\t" + str(length))
        logger.info("num of bands:" + "\t" + str(bands))

        # getting the datatype information
        dataType = RASTERIO2ISCE_DATATYPE.get(str(ds.dtypes[0]), str(ds.dtypes[0]))
        logger.info("dataType: " + "\t" + str(dataType))

        # transformation contains gridcorners (lines/pixels or lonlat and the spacing 1/-1 or deltalon/deltalat)
        transform = ds.transform
    # if a complex data type, then create complex image
    # if a real data type, then create a regular image

    img = isceobj.createImage()
    img.setFilename(os.path.abspath(outname))
    img.setWidth(width)
    img.setLength(length)
    img.setAccessMode("READ")
    img.bands = bands
    img.dataType = dataType

    # interleave
    if bands < 2:
        logger.info("Single band, using BIP")
        img.scheme = "BIP"
    else:
        logger.info("Multi-band, using BSQ")
        img.scheme = "BSQ"

    first_lon = transform.c
    first_lat = transform.f
    delta_lat = transform.e
    delta_lon = transform.a
    # We are using rasterio conventions of the edges of the image for the bbox
    # We need to shift the `first________` values to the middle of the top left pixel
    first_lon += 0.5 * delta_lon
    first_lat += 0.5 * delta_lat

    img.firstLongitude = round(first_lon, 9)  # rounding to avoid precision issues
    img.firstLatitude = round(first_lat, 9)
    img.deltaLongitude = delta_lon
    img.deltaLatitude = delta_lat

    xml_file = outname + ".xml"
    img.dump(xml_file)

    _add_reference_datum(xml_file, keep_egm=keep_egm)

    return xml_file


def _add_reference_datum(xml_file, keep_egm=False):
    """
    Example of modifying an existing XML file
    """

    import xml.etree.ElementTree as ET
    from xml.dom import minidom

    logger.info(
        "add <reference> info to xml file: {}".format(os.path.basename(xml_file))
    )

    # get property element for reference
    ref = ET.Element("property", attrib={"name": "reference"})

    val = ET.SubElement(ref, "value")
    if keep_egm:
        val.text = "EGM2008"
    else:
        val.text = "WGS84"

    doc = ET.SubElement(ref, "doc")
    doc.text = "Geodetic datum"

    # pretty xml
    ref_str = minidom.parseString(ET.tostring(ref)).toprettyxml(indent="    ")
    ref = ET.fromstring(ref_str)

    # write back to xml file
    tree = ET.parse(xml_file)
    root = tree.getroot()
    root.append(ref)
    tree.write(xml_file)
    return xml_file
