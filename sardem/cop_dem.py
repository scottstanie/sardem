import logging
from copy import deepcopy

import requests

from sardem import conversions, utils
from sardem.constants import DEFAULT_RES

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
    output_format="GTiff",
    output_type="float32",
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
        vrt_filename = "/vsicurl/https://raw.githubusercontent.com/scottstanie/sardem/master/sardem/data/cop_global.vrt"

    if keep_egm:
        t_srs = s_srs = None
    else:
        code = conversions.EPSG_CODES["egm08"]
        s_srs = f"epsg:4326+{code}"
        t_srs = "epsg:4326"
    xres = DEFAULT_RES / xrate
    yres = DEFAULT_RES / yrate
    resamp = "bilinear" if (xrate > 1 or yrate > 1) else "nearest"

    # access_mode = "overwrite" if overwrite else None
    option_dict = {
        "format": output_format,
        "outputBounds": bbox,
        "dstSRS": t_srs,
        "srcSRS": s_srs,
        "xRes": xres,
        "yRes": yres,
        "outputType": gdal.GetDataTypeByName(output_type.title()),
        "resampleAlg": resamp,
        "multithread": True,
        "warpMemoryLimit": 5000,
        "warpOptions": ["NUM_THREADS=4"],
    }

    # Used the __RETURN_OPTION_LIST__ to get the list of options for debugging
    logger.info(f"Creating {output_name}")
    logger.info("Fetching remote tiles...")
    try:
        cmd = _gdal_cmd_from_options(vrt_filename, output_name, option_dict)
        logger.info("Running GDAL command:")
        logger.info(cmd)
    except Exception:
        # Can't form the cli version due to `deepcopy` Pickle error, just skip
        logger.info("Running gdal.Warp with options:")
        logger.info(option_dict)
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
            out_opt_list[idx + 1] = f'"{out_opt_list[idx + 1]}"'
    return "gdalwarp {} {} {}".format(src, dst, " ".join(out_opt_list))


def make_cop_vrt(outname="copernicus_GLO_30_dem.vrt"):
    """Build a VRT from the Copernicus GLO 30m DEM COG dataset.

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
    logger.info(f"Building VRT {outname}")
    vrt_file = gdal.BuildVRT(outname, url_list, options=vrt_options)
    vrt_file.FlushCache()
    vrt_file = None


def get_tile_list():
    """Get the list of tiles from the Copernicus DEM 30m tile list."""
    logger.info("Getting list of COP tiles from %s", TILE_LIST_URL)
    r = requests.get(TILE_LIST_URL)
    return r.text.splitlines()


def _make_url_list(tile_list):
    return [("/vsicurl/" + URL_TEMPLATE.format(t=tile)) for tile in tile_list]
