"""Download USGS 3DEP 1-meter DEM tiles from S3 via the TNM Access API.

Uses the USGS TNM (The National Map) Access API to discover which 1-meter
DEM tiles cover the requested bounding box, then fetches them as Cloud
Optimized GeoTIFFs (COGs) from S3 using GDAL's /vsicurl/ virtual filesystem.

Source tiles are in NAD83/UTM (varying zones) with NAVD88 heights, but without
compound vertical CRS metadata. Horizontal reprojection to EPSG:4326 is always
performed. When keep_egm=False (the default), a second GDAL warp converts
NAVD88 heights to WGS84 ellipsoidal heights.

Coverage: US only -- not all areas have 1m lidar data available.

References:
    https://www.usgs.gov/3d-elevation-program
    https://tnmaccess.nationalmap.gov/api/v1/products
"""

import logging
import os
import tempfile

import requests

from sardem import utils

logger = logging.getLogger("sardem")
utils.set_logger_handler(logger)

TNM_API_URL = "https://tnmaccess.nationalmap.gov/api/v1/products"
TNM_DATASET = "Digital Elevation Model (DEM) 1 meter"
TNM_MAX_ITEMS = 200


def download_and_stitch(
    output_name,
    bbox,
    keep_egm=False,
    xrate=1,
    yrate=1,
    output_format="GTiff",
    output_type="float32",
):
    """Download USGS 3DEP 1m DEM tiles and mosaic them with gdal.Warp.

    Parameters
    ----------
    output_name : str
        Path for the output DEM file.
    bbox : tuple
        (left, bottom, right, top) in decimal degrees.
    keep_egm : bool
        If True, keep NAVD88 geoid heights. If False (default), convert to
        WGS84 ellipsoidal heights.
    xrate : int
        Upsample factor in x direction (ignored for 1m data).
    yrate : int
        Upsample factor in y direction (ignored for 1m data).
    output_format : str
        GDAL output format (default GTiff).
    output_type : str
        Output pixel type (default float32).
    """
    from osgeo import gdal

    gdal.UseExceptions()

    if xrate > 1 or yrate > 1:
        logger.warning(
            "xrate/yrate upsampling is ignored for 3DEP_1M (data is already"
            " ~1m resolution). xrate=%d, yrate=%d.",
            xrate,
            yrate,
        )

    tile_urls = _find_tile_urls(bbox)
    vsicurl_paths = ["/vsicurl/" + url for url in tile_urls]
    logger.info("Found %d tile(s) covering the bounding box", len(vsicurl_paths))

    out_type = gdal.GetDataTypeByName(output_type.title())

    # Source tiles are in NAD83/UTM (various zones). Do NOT override srcSRS --
    # GDAL must read the CRS from each file's metadata for correct reprojection.
    reproject_opts = dict(
        format=output_format,
        outputBounds=list(bbox),
        dstSRS="EPSG:4326",
        outputType=out_type,
        resampleAlg="nearest",
        srcNodata=-999999,
        multithread=True,
        warpMemoryLimit=5000,
        warpOptions=["NUM_THREADS=4"],
    )

    if keep_egm:
        logger.info("Creating %s (keeping NAVD88 heights)", output_name)
        reproject_opts["callback"] = gdal.TermProgress
        gdal.Warp(
            output_name, vsicurl_paths, options=gdal.WarpOptions(**reproject_opts)
        )
    else:
        # Two-step warp:
        # 1) Reproject from UTM to EPSG:4326 (horizontal only, preserves NAVD88 Z)
        # 2) Convert NAVD88 heights to WGS84 ellipsoidal using compound CRS.
        #    After step 1 the file is in geographic coords, so
        #    srcSRS="EPSG:4269+5703" (NAD83 + NAVD88) is correct.
        fd, tmp_path = tempfile.mkstemp(suffix=".tif")
        os.close(fd)
        try:
            logger.info("Reprojecting tiles to EPSG:4326...")
            reproject_opts["callback"] = gdal.TermProgress
            gdal.Warp(
                tmp_path, vsicurl_paths, options=gdal.WarpOptions(**reproject_opts)
            )

            logger.info("Converting NAVD88 heights to WGS84 ellipsoidal...")
            vert_opts = dict(
                format=output_format,
                srcSRS="EPSG:4269+5703",
                dstSRS="EPSG:4326",
                outputType=out_type,
                multithread=True,
                callback=gdal.TermProgress,
            )
            gdal.Warp(
                output_name, tmp_path, options=gdal.WarpOptions(**vert_opts)
            )
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


def _find_tile_urls(bbox):
    """Query TNM Access API for 1m DEM tiles covering bbox.

    Returns list of S3 download URLs, sorted oldest-first so
    newest tiles take priority in gdal.Warp overlap resolution.

    Parameters
    ----------
    bbox : tuple
        (left, bottom, right, top) in decimal degrees.

    Returns
    -------
    list[str]
        S3 URLs to COG tiles.

    Raises
    ------
    RuntimeError
        If no tiles are found for the requested area.
    """
    left, bottom, right, top = bbox
    params = {
        "datasets": TNM_DATASET,
        "bbox": "{},{},{},{}".format(left, bottom, right, top),
        "max": TNM_MAX_ITEMS,
        "outputFormat": "JSON",
    }

    logger.info("Querying TNM API for 1m DEM tiles...")
    response = requests.get(TNM_API_URL, params=params, timeout=60)
    response.raise_for_status()

    data = response.json()
    items = data.get("items", [])
    if not items:
        raise RuntimeError(
            "No 3DEP 1m DEM tiles found for bbox {}. "
            "Not all US areas have 1m coverage.".format(bbox)
        )

    if len(items) >= TNM_MAX_ITEMS:
        logger.warning(
            "TNM API returned the maximum %d items. The bounding box may be"
            " too large to fetch all tiles in one request.",
            TNM_MAX_ITEMS,
        )

    # Sort by dateCreated ascending (oldest first) so that when gdal.Warp
    # processes them in order, newer tiles overwrite older ones in overlaps
    items.sort(key=lambda item: item.get("dateCreated", ""))

    urls = [item["downloadURL"] for item in items]
    logger.info("Found %d tiles from TNM API", len(urls))
    return urls
