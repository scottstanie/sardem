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
    import rasterio
    import rasterio.warp
    from rasterio.enums import Resampling

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
    # Map resampling algorithm names
    resamp_map = {
        "bilinear": Resampling.bilinear,
        "nearest": Resampling.nearest,
        "cubic": Resampling.cubic,
        "average": Resampling.average,
    }
    resample_alg = resamp_map.get(resamp, Resampling.bilinear)

    logger.info("Creating {}".format(output_name))
    logger.info("Fetching remote tiles...")

    # Use rasterio for warping
    with rasterio.open(vrt_filename) as src:
        # Calculate output transform and dimensions
        dst_transform, dst_width, dst_height = (
            rasterio.warp.calculate_default_transform(
                src.crs if s_srs is None else s_srs,
                t_srs if t_srs is not None else src.crs,
                src.width,
                src.height,
                *src.bounds,
                resolution=(xres, yres),
            )
        )

        # If bbox is provided, override the transform calculation
        if bbox:
            left, bottom, right, top = bbox
            dst_width = int(round((right - left) / xres))
            dst_height = int(round((top - bottom) / abs(yres)))
            dst_transform = rasterio.transform.from_bounds(
                left, bottom, right, top, dst_width, dst_height
            )

        # Create output profile
        profile = src.profile.copy()
        profile.update(
            {
                "driver": "ENVI" if output_format == "ENVI" else output_format,
                "height": dst_height,
                "width": dst_width,
                "transform": dst_transform,
                "crs": t_srs if t_srs is not None else src.crs,
                "dtype": output_type,
            }
        )

        warp_opts = {"XSCALE": 1, "YSCALE": 1, "APPLY_VERTICAL_SHIFT": True}
        with rasterio.open(output_name, "w", **profile) as dst:
            for i in range(1, src.count + 1):
                rasterio.warp.reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs if s_srs is None else s_srs,
                    dst_transform=dst_transform,
                    dst_crs=t_srs if t_srs is not None else src.crs,
                    resampling=resample_alg,
                    num_threads=4,
                    **warp_opts,
                )
    return


def make_cop_vrt(outname="copernicus_GLO_30_dem.vrt"):
    """Build a VRT from the Copernicus GLO 30m DEM COG dataset

    Note: this is a large VRT file, ~15MB, so it can many hours to build.
    """
    import rasterio
    from rasterio.vrt import WarpedVRT

    tile_list = get_tile_list()
    url_list = _make_url_list(tile_list)

    logger.info("Building VRT {}".format(outname))

    # Create a simple VRT by writing XML directly (rasterio doesn't have BuildVRT equivalent)
    vrt_xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    vrt_xml += '<VRTDataset rasterXSize="1296000" rasterYSize="417600">\n'
    vrt_xml += "  <SRS>EPSG:4326+3855</SRS>\n"
    vrt_xml += "  <GeoTransform>-1.800000000000000e+02, 2.777777777777778e-04, 0.000000000000000e+00, 8.333333333333334e+01, 0.000000000000000e+00, -2.777777777777778e-04</GeoTransform>\n"
    vrt_xml += '  <VRTRasterBand dataType="Int16" band="1">\n'
    vrt_xml += "    <NoDataValue>-32768</NoDataValue>\n"

    for url in url_list:
        vrt_xml += f"    <SimpleSource>\n"
        vrt_xml += f'      <SourceFilename relativeToVRT="0">{url}</SourceFilename>\n'
        vrt_xml += f"      <SourceBand>1</SourceBand>\n"
        vrt_xml += f"    </SimpleSource>\n"

    vrt_xml += "  </VRTRasterBand>\n"
    vrt_xml += "</VRTDataset>\n"

    with open(outname, "w") as f:
        f.write(vrt_xml)

    logger.info(f"VRT written to {outname} with {len(url_list)} tiles")


def get_tile_list():
    """Get the list of tiles from the Copernicus DEM 30m tile list"""
    logger.info("Getting list of COP tiles from %s", TILE_LIST_URL)
    r = requests.get(TILE_LIST_URL)
    return r.text.splitlines()


def _make_url_list(tile_list):
    return [("/vsicurl/" + URL_TEMPLATE.format(t=tile)) for tile in tile_list]
