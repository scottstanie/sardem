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
    import os
    import tempfile

    from osgeo import gdal

    gdal.UseExceptions()

    if vrt_filename is None:
        vrt_filename = "/vsicurl/https://raw.githubusercontent.com/scottstanie/sardem/master/sardem/data/cop_global.vrt"  # noqa

    bboxes = utils.check_dateline(bbox)

    if len(bboxes) == 1:
        _download_single_bbox(
            output_name,
            bbox,
            vrt_filename,
            keep_egm,
            xrate,
            yrate,
            output_format,
            output_type,
        )
        return

    # Dateline crossing: download each sub-bbox, shift tiles, merge
    logger.info(
        "Dateline crossing detected, downloading {} separate regions".format(
            len(bboxes)
        )
    )

    temp_files = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for idx, sub_bbox in enumerate(bboxes):
            temp_file = os.path.join(tmpdir, "dem_part_{}.tif".format(idx))
            temp_files.append(temp_file)
            logger.info("Downloading region {} of {}".format(idx + 1, len(bboxes)))
            _download_single_bbox(
                temp_file,
                sub_bbox,
                vrt_filename,
                keep_egm,
                xrate,
                yrate,
                "GTiff",
                output_type,
            )

        # Shift eastern tiles so they're adjacent to western tiles in pixel space
        for temp_file in temp_files:
            _shift_tile_if_needed(temp_file)

        logger.info("Merging {} regions into final DEM".format(len(temp_files)))
        vrt_temp = os.path.join(tmpdir, "merged.vrt")
        gdal.BuildVRT(vrt_temp, temp_files)

        if output_format == "GTiff":
            gdal.Warp(
                output_name,
                vrt_temp,
                options=gdal.WarpOptions(
                    format=output_format,
                    multithread=True,
                    callback=gdal.TermProgress,
                ),
            )
        else:
            gdal.Translate(
                output_name,
                vrt_temp,
                format=output_format,
                callback=gdal.TermProgress,
            )


def _shift_tile_if_needed(filepath):
    """Shift tile geotransform by -360 if x origin is positive.

    Makes eastern tiles (e.g., 179.7 to 180) adjacent to western tiles
    (e.g., -180 to -179.8) by shifting to (-180.3 to -180).
    Only useful for tiles that are part of a dateline-crossing split.
    """
    from osgeo import gdal

    ds = gdal.Open(filepath, gdal.GA_Update)
    gt = list(ds.GetGeoTransform())
    if gt[0] > 0:
        logger.info("Shifting tile {} x origin from {} to {}".format(
            filepath, gt[0], gt[0] - 360.0
        ))
        gt[0] -= 360.0
        ds.SetGeoTransform(gt)
    ds.FlushCache()
    ds = None


def _download_single_bbox(
    output_name,
    bbox,
    vrt_filename,
    keep_egm,
    xrate,
    yrate,
    output_format,
    output_type,
):
    """Download a single bbox from the COP DEM."""
    from osgeo import gdal

    if keep_egm:
        t_srs = s_srs = None
    else:
        code = conversions.EPSG_CODES["egm08"]
        s_srs = "epsg:4326+{}".format(code)
        t_srs = "epsg:4326"
    xres = DEFAULT_RES / xrate
    yres = DEFAULT_RES / yrate
    resamp = "bilinear" if (xrate > 1 or yrate > 1) else "nearest"

    option_dict = dict(
        format=output_format,
        outputBounds=utils.align_bounds_to_pixel_grid(bbox),
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
    # Preserve ocean (value=0) as nodata during geoid-to-ellipsoid conversion
    if not keep_egm:
        option_dict["srcNodata"] = 0
        option_dict["dstNodata"] = 0

    logger.info("Creating {}".format(output_name))
    logger.info("Fetching remote tiles...")
    try:
        cmd = _gdal_cmd_from_options(vrt_filename, output_name, option_dict)
        logger.info("Running GDAL command:")
        logger.info(cmd)
    except Exception:
        logger.info("Running gdal.Warp with options:")
        logger.info(option_dict)
        pass

    option_dict["callback"] = gdal.TermProgress
    gdal.Warp(output_name, vrt_filename, options=gdal.WarpOptions(**option_dict))


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
