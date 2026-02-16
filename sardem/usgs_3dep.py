"""Download USGS 3DEP elevation data via the ImageServer REST API.

The USGS 3D Elevation Program (3DEP) provides high-resolution elevation data
for the United States, including 1-meter LiDAR-derived DEMs in many areas.

Data is accessed via the ArcGIS ImageServer exportImage endpoint, which
dynamically resamples multi-resolution 3DEP sources for a given bounding box.

Vertical datum: 3DEP data is in NAVD88 (EPSG:5703). When keep_egm=False
(the default), heights are converted to WGS84 ellipsoidal heights using GDAL.

Coverage: US and territories only (CONUS, Alaska, Hawaii, etc.)

References:
    https://www.usgs.gov/3d-elevation-program
    https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer
"""

import logging
import math
import os
import tempfile

import requests

from sardem import utils
from sardem.constants import DEFAULT_RES

logger = logging.getLogger("sardem")
utils.set_logger_handler(logger)

EXPORT_URL = (
    "https://elevation.nationalmap.gov/arcgis/rest/services"
    "/3DEPElevation/ImageServer/exportImage"
)
# ArcGIS ImageServer typically limits exports; use a safe chunk size
MAX_EXPORT_SIZE = 4000


def download_and_stitch(
    output_name,
    bbox,
    keep_egm=False,
    xrate=1,
    yrate=1,
    output_format="GTiff",
    output_type="float32",
):
    """Download USGS 3DEP DEM data and optionally convert to WGS84 heights.

    Data is downloaded from the 3DEP ImageServer exportImage endpoint as
    GeoTIFF chunks, then merged and optionally datum-converted using GDAL.

    Args:
        output_name (str): path for the output DEM file
        bbox (tuple): (left, bottom, right, top) in decimal degrees
        keep_egm (bool): if True, keep NAVD88 geoid heights; if False (default),
            convert to WGS84 ellipsoidal heights
        xrate (int): upsample factor in x (longitude) direction
        yrate (int): upsample factor in y (latitude) direction
        output_format (str): GDAL output format (default GTiff)
        output_type (str): output pixel type (default float32)
    """
    from osgeo import gdal

    gdal.UseExceptions()

    left, bottom, right, top = bbox
    xres = DEFAULT_RES / xrate
    yres = DEFAULT_RES / yrate

    total_width = int(round((right - left) / xres))
    total_height = int(round((top - bottom) / yres))

    logger.info("Requesting 3DEP DEM: %d x %d pixels", total_width, total_height)

    cache_dir = utils.get_cache_dir()
    tmp_files = _download_in_chunks(
        left, bottom, right, top, total_width, total_height, cache_dir
    )

    try:
        # Build source: single file or VRT mosaic of chunks
        if len(tmp_files) == 1:
            src = tmp_files[0]
        else:
            vrt_path = os.path.join(cache_dir, "_3dep_mosaic.vrt")
            logger.info("Building VRT from %d chunks", len(tmp_files))
            vrt_ds = gdal.BuildVRT(vrt_path, tmp_files)
            vrt_ds.FlushCache()
            vrt_ds = None
            src = vrt_path

        # Set up datum conversion
        if keep_egm:
            t_srs = s_srs = None
        else:
            # 3DEP data is NAD83 + NAVD88; convert to WGS84 ellipsoidal
            s_srs = "EPSG:4269+5703"
            t_srs = "EPSG:4326"

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

        logger.info("Creating %s", output_name)
        option_dict["callback"] = gdal.TermProgress
        gdal.Warp(output_name, src, options=gdal.WarpOptions(**option_dict))
    finally:
        # Clean up temp files
        for f in tmp_files:
            if os.path.exists(f):
                os.remove(f)
        vrt_mosaic = os.path.join(cache_dir, "_3dep_mosaic.vrt")
        if os.path.exists(vrt_mosaic):
            os.remove(vrt_mosaic)


def _download_in_chunks(left, bottom, right, top, total_width, total_height, cache_dir):
    """Split a large area into chunks and download each as a GeoTIFF.

    Returns:
        list[str]: paths to downloaded temporary GeoTIFF files
    """
    n_chunks_x = max(1, math.ceil(total_width / MAX_EXPORT_SIZE))
    n_chunks_y = max(1, math.ceil(total_height / MAX_EXPORT_SIZE))

    if n_chunks_x * n_chunks_y > 1:
        logger.info(
            "Area requires %d x %d chunks (%d total)",
            n_chunks_x,
            n_chunks_y,
            n_chunks_x * n_chunks_y,
        )

    lon_span = right - left
    lat_span = top - bottom
    files = []

    for iy in range(n_chunks_y):
        for ix in range(n_chunks_x):
            # Calculate chunk bounding box
            chunk_left = left + ix * lon_span / n_chunks_x
            chunk_right = left + (ix + 1) * lon_span / n_chunks_x
            chunk_top = top - iy * lat_span / n_chunks_y
            chunk_bottom = top - (iy + 1) * lat_span / n_chunks_y

            # Calculate chunk pixel dimensions
            chunk_w = total_width // n_chunks_x
            chunk_h = total_height // n_chunks_y
            # Give extra pixels to the last chunk in each direction
            if ix == n_chunks_x - 1:
                chunk_w = total_width - chunk_w * (n_chunks_x - 1)
            if iy == n_chunks_y - 1:
                chunk_h = total_height - chunk_h * (n_chunks_y - 1)

            logger.info(
                "Downloading chunk [%d,%d] (%d x %d px)...",
                ix,
                iy,
                chunk_w,
                chunk_h,
            )
            tmp_path = _download_chunk(
                chunk_left,
                chunk_bottom,
                chunk_right,
                chunk_top,
                chunk_w,
                chunk_h,
                cache_dir,
            )
            files.append(tmp_path)

    return files


def _download_chunk(left, bottom, right, top, width, height, cache_dir):
    """Download a single chunk from the 3DEP ImageServer exportImage endpoint.

    Args:
        left, bottom, right, top: bounding box in EPSG:4326
        width, height: pixel dimensions for the request
        cache_dir: directory to store the temp file

    Returns:
        str: path to the downloaded GeoTIFF file

    Raises:
        RuntimeError: if the server returns an error or non-image response
    """
    params = {
        "bbox": "{},{},{},{}".format(left, bottom, right, top),
        "bboxSR": "4326",
        "imageSR": "4326",
        "format": "tiff",
        "pixelType": "F32",
        "size": "{},{}".format(width, height),
        "f": "image",
        "interpolation": "RSP_BilinearInterpolation",
        "noData": "-999999",
    }

    response = requests.get(EXPORT_URL, params=params, timeout=120)
    response.raise_for_status()

    # Check that the response is actually a TIFF, not an error page
    content_type = response.headers.get("Content-Type", "")
    if "tiff" not in content_type and "image" not in content_type:
        # Server may return JSON or HTML error
        msg = "3DEP server did not return image data."
        try:
            err = response.json()
            if "error" in err:
                msg += " Error: {}".format(err["error"].get("message", err["error"]))
        except Exception:
            pass
        raise RuntimeError(msg)

    fd, tmp_path = tempfile.mkstemp(suffix=".tif", dir=cache_dir)
    try:
        os.write(fd, response.content)
    finally:
        os.close(fd)

    return tmp_path
