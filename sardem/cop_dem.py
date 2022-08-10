# Based on https://github.com/MarcYin/Copernicus_GLO_30_DEM_VRT
import logging
import os
from copy import deepcopy

import requests

from sardem import conversions, utils

TILE_LIST_URL = "https://copernicus-dem-30m.s3.amazonaws.com/tileList.txt"
URL_TEMPLATE = "https://copernicus-dem-30m.s3.amazonaws.com/{t}/{t}.tif"
DEFAULT_RES = 1 / 3600

logger = logging.getLogger("sardem")
utils.set_logger_handler(logger)


def download_and_stitch(
    output_name, bounds, keep_egm=False, xrate=1, yrate=1, download_vrt=False
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
    geoid = "egm08"
    if download_vrt:
        cache_dir = utils.get_cache_dir()
        vrt_filename = os.path.join(cache_dir, "copernicus_GLO_30_dem.vrt")
        if not os.path.exists(vrt_filename):
            make_cop_vrt(vrt_filename)
    else:
        vrt_filename = "/vsicurl/https://raw.githubusercontent.com/scottstanie/sardem/master/sardem/data/copernicus_GLO_30_dem.vrt"  # noqa
    egm_file = conversions.EGM_FILES[geoid]
    if not os.path.exists(egm_file):
        conversions.download_egm_grid(geoid=geoid)

    if keep_egm:
        t_srs = s_srs = None
    else:
        s_srs = "+proj=longlat +datum=WGS84 +no_defs +geoidgrids={}".format(egm_file)
        t_srs = "+proj=longlat +datum=WGS84 +no_defs"

    xres = DEFAULT_RES / xrate
    yres = DEFAULT_RES / yrate

    # access_mode = "overwrite" if overwrite else None
    option_dict = dict(
        format="ENVI",
        outputBounds=bounds,
        dstSRS=t_srs,
        srcSRS=s_srs,
        xRes=xres,
        yRes=yres,
        outputType=gdal.GDT_Int16,
        resampleAlg="bilinear",
        multithread=True,
        warpMemoryLimit=5000,
        warpOptions=["NUM_THREADS=4"],
    )

    # Used the __RETURN_OPTION_LIST__ to get the list of options for debugging
    logger.info("Creating {}".format(output_name))
    cmd = _gdal_cmd_from_options(vrt_filename, output_name, option_dict)
    logger.info("Running GDAL command:")
    option_dict["callback"] = gdal.TermProgress
    logger.info(cmd)
    # Now convert to something GDAL can actuall use
    gdal.Warp(output_name, vrt_filename, options=gdal.WarpOptions(**option_dict))
    return


def _gdal_cmd_from_options(src, dst, option_dict):
    from osgeo import gdal

    opts = deepcopy(option_dict)
    # To see what the list of cli options are
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
    logger.info("Getting list of COP tiles from ", TILE_LIST_URL)
    r = requests.get(TILE_LIST_URL)
    return r.text.splitlines()


def _make_url_list(tile_list):
    return [("/vsicurl/" + URL_TEMPLATE.format(t=tile)) for tile in tile_list]
