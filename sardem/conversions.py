import logging
import os
import shutil
import subprocess

from . import utils

logger = logging.getLogger("sardem")

EPSG_CODES = {
    "egm96": "5773",  # https://epsg.io/5773
    "egm08": "3855",  # https://epsg.io/3855
}
EGM_FILES = {
    "egm96": os.path.join(utils.get_cache_dir(), "egm96_15.gtx"),
    "egm08": os.path.join(utils.get_cache_dir(), "egm08_25.gtx"),
}


def egm_to_wgs84(filename, output=None, overwrite=True, copy_rsc=True, geoid="egm96"):
    """Convert a DEM with a EGM96/2008 vertical datum to WGS84 heights above ellipsoid"""

    if output is None:
        ext = os.path.splitext(filename)[1]
        output = filename.replace(ext, ".wgs84" + ext)

    code = EPSG_CODES[geoid]
    # Source srs: WGS84 ellipsoidal horizontal, EGM geoid vertical
    s_srs = '"epsg:4326+{}"'.format(code)
    # Target srs: WGS84 horizontal/vertical
    t_srs = '"epsg:4326"'

    # Use rasterio for coordinate system transformation
    import rasterio
    from rasterio.warp import reproject, Resampling

    xsize, ysize = _get_size(filename)

    with rasterio.open(filename) as src:
        # Create output profile
        profile = src.profile.copy()
        profile.update(
            {
                "driver": "ENVI",  # ROI_PAC equivalent
                "crs": t_srs.strip('"'),
                "width": xsize,
                "height": ysize,
            }
        )

        if not overwrite and os.path.exists(output):
            logger.warning("Output file {} exists and overwrite=False".format(output))
            return output

        logger.info("Converting {} from {} to {}".format(filename, s_srs, t_srs))
        with rasterio.open(output, "w", **profile) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=s_srs.strip('"'),
                    dst_transform=dst.transform,
                    dst_crs=t_srs.strip('"'),
                    resampling=Resampling.nearest,
                    num_threads=4,
                )

    if copy_rsc:
        rsc_file = filename + ".rsc"
        logger.info("Copying {} to {}".format(rsc_file, output + ".rsc"))
        shutil.copyfile(rsc_file, output + ".rsc")
    return output


def _get_size(filename):
    """Retrieve the raster size from a rasterio-readable file"""
    import rasterio

    with rasterio.open(filename) as ds:
        xsize, ysize = ds.width, ds.height
    return xsize, ysize


def convert_dem_to_wgs84(dem_filename, geoid="egm96"):
    """Convert the file `dem_filename` from EGM96 heights to WGS84 ellipsoidal heights

    Overwrites file, uses rasterio for conversion
    """

    path_, fname = os.path.split(dem_filename)
    rsc_filename = os.path.join(path_, fname + ".rsc")

    output_egm = os.path.join(path_, "egm_" + fname)
    # output_wgs = dem_filename.replace(ext, ".wgs84" + ext)
    rsc_filename_egm = os.path.join(path_, "egm_" + fname + ".rsc")
    os.rename(dem_filename, output_egm)
    os.rename(rsc_filename, rsc_filename_egm)
    try:
        egm_to_wgs84(
            output_egm, output=dem_filename, overwrite=True, copy_rsc=True, geoid=geoid
        )
        os.remove(output_egm)
        os.remove(rsc_filename_egm)
    except Exception:
        logger.error("Failed to convert DEM:", exc_info=True)
        logger.error("Reverting back, using EGM dem as output")
        os.rename(output_egm, dem_filename)
        os.rename(rsc_filename_egm, rsc_filename)
