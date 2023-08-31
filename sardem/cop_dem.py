import logging
from copy import deepcopy

import requests

from sardem import conversions, utils
from sardem.constants import DEFAULT_RES
from shapely import geometry, affinity, ops


TILE_LIST_URL = "https://copernicus-dem-30m.s3.amazonaws.com/tileList.txt"
URL_TEMPLATE = "https://copernicus-dem-30m.s3.amazonaws.com/{t}/{t}.tif"

logger = logging.getLogger("sardem")
utils.set_logger_handler(logger)


def download_and_stitch(
    output_name,
    bbox,
    keep_egm=False,
    xrate=1,
    yrate=1,
    vrt_filename=None,
    output_format="ENVI",
    output_type="int16",
):
    """Download the COP DEM from AWS.

    Data comes as heights above EGM2008 ellipsoid, so a conversion
    step is necessary for WGS84 heights for InsAR.

    References:
        https://spacedata.copernicus.eu/web/cscda/dataset-details?articleId=394198
        https://copernicus-dem-30m.s3.amazonaws.com/readme.html
    """
    from osgeo import gdal

    gdal.UseExceptions()
    # TODO: does downloading make it run any faster?
    # if download_vrt:
    #     cache_dir = utils.get_cache_dir()
    #     vrt_filename = os.path.join(cache_dir, "cop_global.vrt")
    #     if not os.path.exists(vrt_filename):
    #         make_cop_vrt(vrt_filename)
    # else:
    if vrt_filename is None:
        vrt_filename = "/vsicurl/https://raw.githubusercontent.com/scottstanie/sardem/master/sardem/data/cop_global.vrt"  # noqa

    if keep_egm:
        t_srs = s_srs = None
    else:
        code = conversions.EPSG_CODES["egm08"]
        s_srs = "epsg:4326+{}".format(code)
        t_srs = "epsg:4326"
    xres = DEFAULT_RES / xrate
    yres = DEFAULT_RES / yrate
    resamp = "bilinear" if (xrate > 1 or yrate > 1) else "nearest"

    # access_mode = "overwrite" if overwrite else None
    option_dict = dict(
        format=output_format,
        outputBounds=bbox,
        dstSRS=t_srs,
        srcSRS=s_srs,
        xRes=xres,
        yRes=yres,
        outputType=gdal.GetDataTypeByName(output_type.title()),
        resampleAlg=resamp,
        multithread=True,
        warpMemoryLimit=5000,
        warpOptions=["NUM_THREADS=4"],
    )

    # Used the __RETURN_OPTION_LIST__ to get the list of options for debugging
    logger.info("Creating {}".format(output_name))
    logger.info("Fetching remote tiles...")
    try:
        cmd = _gdal_cmd_from_options(vrt_filename, output_name, option_dict)
        logger.info("Running GDAL command:")
        logger.info(cmd)
    except Exception:
        # Can't form the cli version due to `deepcopy` Pickle error, just skip
        logger.info("Running gdal.Warp with options:")
        logger.info(option_dict)
        pass
    # Now convert to something GDAL can actually use
    option_dict["callback"] = gdal.TermProgress
    gdal.Warp(output_name, vrt_filename, options=gdal.WarpOptions(**option_dict))
    return


def _gdal_cmd_from_options(src, dst, option_dict):
    from osgeo import gdal

    opts = deepcopy(option_dict)
    # To see what the list of cli options are (gdal >= 3.5.0)
    opts["options"] = "__RETURN_OPTION_LIST__"
    opt_list = gdal.WarpOptions(**opts)
    out_opt_list = deepcopy(opt_list)
    for idx, o in enumerate(opt_list):
        # Wrap the srs option in quotes
        if o.endswith("srs"):
            out_opt_list[idx + 1] = '"{}"'.format(out_opt_list[idx + 1])
    return "gdalwarp {} {} {}".format(src, dst, " ".join(out_opt_list))


def make_cop_vrt(outname="copernicus_GLO_30_dem.vrt"):
    """Build a VRT from the Copernicus GLO 30m DEM COG dataset

    Note: this is a large VRT file, ~15MB, so it can many hours to build.
    """
    from osgeo import gdal

    gdal.UseExceptions()

    tile_list = get_tile_list()
    url_list = _make_url_list(tile_list)
    vrt_options = gdal.BuildVRTOptions(
        resampleAlg=gdal.GRIORA_NearestNeighbour,
        outputBounds=[-180, -90, 180, 90],
        resolution="highest",
        outputSRS="EPSG:4326+3855",
    )
    logger.info("Building VRT {}".format(outname))
    vrt_file = gdal.BuildVRT(outname, url_list, options=vrt_options)
    vrt_file.FlushCache()
    vrt_file = None


def get_tile_list():
    """Get the list of tiles from the Copernicus DEM 30m tile list"""
    logger.info("Getting list of COP tiles from %s", TILE_LIST_URL)
    r = requests.get(TILE_LIST_URL)
    return r.text.splitlines()


def _make_url_list(tile_list):
    return [("/vsicurl/" + URL_TEMPLATE.format(t=tile)) for tile in tile_list]


def bounds_to_tile_id(bounds: tuple[float, float, float, float]) -> str:
    """Convert bounding box coordinates to a tile ID string.

    Parameters
    ----------
    bounds : tuple of float
        A tuple representing the bounding box in the format (min_x, min_y, max_x, max_y).

    Returns
    -------
    str
        The corresponding tile ID string.

    Examples
    --------
    >>> bounds = (6.0, 0.0, 7.0, 1.0)
    >>> bounds_to_tile_id(bounds)
    'Copernicus_DSM_COG_10_N00_00_E006_00_DEM'
    """
    # Extract bounds
    min_x, min_y, max_x, max_y = bounds

    # Determine latitude and longitude direction based on bounds
    lat_dir = "N" if min_y >= 0 else "S"
    lon_dir = "E" if min_x >= 0 else "W"

    # Construct tile ID
    tile_id = f"Copernicus_DSM_COG_10_{lat_dir}{abs(int(min_y)):02}_00_{lon_dir}{abs(int(min_x)):03}_00_DEM"

    return tile_id


def tile_id_to_bounds(tile_id: str) -> tuple[float, float, float, float]:
    """Convert a tile ID string to bounding box coordinates.

    Parameters
    ----------
    tile_id : str
        The tile ID string to convert.

    Returns
    -------
    tuple of float
        A tuple representing the bounding box in the format (min_x, min_y, max_x, max_y).

    Examples
    --------
    >>> tile_id = 'Copernicus_DSM_COG_10_N00_00_E006_00_DEM'
    >>> tile_id_to_bounds(tile_id)
    (6.0, 0.0, 7.0, 1.0)
    """
    # Extract latitude and longitude values and directions from the Tile ID
    lat_dir = tile_id.split("_")[4][0]
    lat_val = int(tile_id.split("_")[4][1:3])
    lon_dir = tile_id.split("_")[6][0]
    lon_val = int(tile_id.split("_")[6][1:4])

    # Convert directions into multipliers for determining sign
    lat_multiplier = 1 if lat_dir == "N" else -1
    lon_multiplier = 1 if lon_dir == "E" else -1

    # Calculate bounds
    min_x = lon_multiplier * lon_val
    max_x = min_x + 1
    min_y = lat_multiplier * lat_val
    max_y = min_y + 1

    return (min_x, min_y, max_x, max_y)


def intersects_antimeridian(geometry: geometry.Polygon):
    antimeridian = geometry.LineString(((180, -90), (180, 90)))
    x_shift = 360 if geometry.bounds[0] < -180 else 0
    geom_0_360 = affinity.translate(geometry, xoff=x_shift)
    # TODO:
    # https://github.com/ACCESS-Cloud-Based-InSAR/dem-stitcher/blob/dev/dem_stitcher/dateline.py
    # https://shapely.readthedocs.io/en/stable/manual.html#shapely.ops.linemerge
    # https://github-fn.jpl.nasa.gov/isce-3/isce/blob/develop/python/packages/nisar/workflows/stage_dem.py