import logging
import os
from copy import deepcopy
from pathlib import Path

import requests
from osgeo import gdal, osr

from sardem import conversions, utils
from sardem.constants import DEFAULT_RES

TILE_LIST_URL = "https://copernicus-dem-30m.s3.amazonaws.com/tileList.txt"
URL_TEMPLATE = "https://copernicus-dem-30m.s3.amazonaws.com/{t}/{t}.tif"

logger = logging.getLogger("sardem")
utils.set_logger_handler(logger)

gdal.UseExceptions()


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


# -------------------------------------------------------------------------
# Existing code above...
# -------------------------------------------------------------------------


def _gt_to_bounds(gt, xsize, ysize):
    """Convert GeoTransform + size to (xmin, ymin, xmax, ymax), assuming north-up."""
    gt0, gt1, gt2, gt3, gt4, gt5 = gt
    xmin = gt0
    ymax = gt3
    xmax = gt0 + xsize * gt1
    ymin = gt3 + ysize * gt5
    return xmin, ymin, xmax, ymax


def make_cop_gti_index(
    outname: str = "copernicus_GLO_30_dem.gti.gpkg",
    layer_name: str = "cop_dem_tiles",
):
    """Build a GTI-compatible GeoPackage index for the Copernicus GLO 30m DEM.

    This uses the remote COG URLs directly (via /vsicurl/), so you do NOT
    need to have the DEM tiles downloaded locally.

    Parameters
    ----------
    outname : str
        Output GeoPackage path. Recommended extension: *.gti.gpkg
        so GDAL will pick it up as GTI by default.
    layer_name : str
        Name of the vector tile index layer inside the GeoPackage.
    """

    # 1. Get the full tile list + URL list (with /vsicurl/)
    tile_list = get_tile_list()
    url_list = _make_url_list(tile_list)
    if not url_list:
        raise RuntimeError("No Cop DEM tiles found from TILE_LIST_URL")

    logger.info("Found %d Cop DEM tiles", len(url_list))

    # 2. Open the first tile to define SRS, resolution, band count, data type, etc.
    logger.info("Inspecting first tile: %s", url_list[0])
    ds0 = gdal.Open(url_list[0])
    if ds0 is None:
        raise RuntimeError(
            f"Failed to open first Cop DEM tile {url_list[0]!r} with GDAL"
        )

    gt0 = ds0.GetGeoTransform()
    proj_wkt = ds0.GetProjection()
    band_count = ds0.RasterCount

    band0 = ds0.GetRasterBand(1)
    dtype = band0.DataType
    nodata = band0.GetNoDataValue()

    srs = osr.SpatialReference()
    if proj_wkt:
        srs.ImportFromWkt(proj_wkt)
    else:
        # This should not happen for Cop DEM, but keep a sensible fallback
        srs.ImportFromEPSG(4326)

    resx = abs(gt0[1])
    resy = abs(gt0[5])

    logger.info("Resolution: RESX=%.12f, RESY=%.12f", resx, resy)
    logger.info("Band count: %d", band_count)
    logger.info("Data type: %s", gdal.GetDataTypeName(dtype))

    ds0 = None  # close

    # 3. Create GeoPackage + layer
    from osgeo import ogr as _ogr_driver  # alias just to be explicit

    driver = _ogr_driver.GetDriverByName("GPKG")
    if Path(outname).exists():
        logger.info("Removing existing %s", outname)
        driver.DeleteDataSource(outname)

    ds = driver.CreateDataSource(outname)
    if ds is None:
        raise RuntimeError(f"Failed to create GeoPackage {outname!r}")

    layer = ds.CreateLayer(layer_name, srs=srs, geom_type=_ogr_driver.wkbPolygon)
    if layer is None:
        raise RuntimeError("Failed to create layer in GeoPackage")

    # Required field for GTI: "location" (string) with a path/URL to each tile
    fld_location = _ogr_driver.FieldDefn("location", _ogr_driver.OFTString)
    fld_location.SetWidth(2048)
    layer.CreateField(fld_location)

    # Optional helper: tile_id (e.g. N00E000)
    fld_tile_id = _ogr_driver.FieldDefn("tile_id", _ogr_driver.OFTString)
    fld_tile_id.SetWidth(64)
    layer.CreateField(fld_tile_id)

    layer_defn = layer.GetLayerDefn()

    xmin_all = ymin_all = xmax_all = ymax_all = None

    # 4. Loop over all tiles, compute polygon extents, add features
    for tile_id, url in zip(tile_list, url_list):
        ds_tile = gdal.Open(url)
        if ds_tile is None:
            logger.warning("Skipping %s (GDAL failed to open)", url)
            continue

        gt = ds_tile.GetGeoTransform()
        xsize = ds_tile.RasterXSize
        ysize = ds_tile.RasterYSize
        ds_tile = None

        xmin, ymin, xmax, ymax = _gt_to_bounds(gt, xsize, ysize)

        if xmin_all is None:
            xmin_all, ymin_all, xmax_all, ymax_all = xmin, ymin, xmax, ymax
        else:
            xmin_all = min(xmin_all, xmin)
            ymin_all = min(ymin_all, ymin)
            xmax_all = max(xmax_all, xmax)
            ymax_all = max(ymax_all, ymax)

        ring = _ogr_driver.Geometry(_ogr_driver.wkbLinearRing)
        ring.AddPoint(xmin, ymin)
        ring.AddPoint(xmin, ymax)
        ring.AddPoint(xmax, ymax)
        ring.AddPoint(xmax, ymin)
        ring.AddPoint(xmin, ymin)

        poly = _ogr_driver.Geometry(_ogr_driver.wkbPolygon)
        poly.AddGeometry(ring)

        feat = _ogr_driver.Feature(layer_defn)
        feat.SetField("location", url)  # full /vsicurl/https://... URL
        feat.SetField("tile_id", tile_id)
        feat.SetGeometry(poly)

        if layer.CreateFeature(feat) != 0:
            logger.warning("Failed to create feature for %s", tile_id)
        feat = None

    # Optional but recommended: spatial index for fast GTI spatial filtering
    try:
        layer.CreateSpatialIndex()
        logger.info("Created spatial index on layer %s", layer_name)
    except Exception as e:
        logger.warning("Could not create spatial index: %s", e)

    # 5. Set layer metadata so GTI can infer mosaic properties quickly
    md = {
        "RESX": f"{resx:.12f}",
        "RESY": f"{resy:.12f}",
        "BAND_COUNT": str(band_count),
        "DATA_TYPE": gdal.GetDataTypeName(dtype),
        "SRS": srs.ExportToWkt(),
    }

    if xmin_all is not None:
        md.update(
            {
                "MINX": f"{xmin_all:.12f}",
                "MINY": f"{ymin_all:.12f}",
                "MAXX": f"{xmax_all:.12f}",
                "MAXY": f"{ymax_all:.12f}",
            }
        )

    if nodata is not None:
        md["NODATA"] = str(nodata)

    layer.SetMetadata(md)

    ds = None
    logger.info("Wrote Cop DEM GTI tile index to %s (layer=%s)", outname, layer_name)
    return outname
