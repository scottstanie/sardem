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
    """Convert a DEM with a EGM96/2008 vertical datum to WGS84 heights above ellipsoid."""
    if output is None:
        ext = os.path.splitext(filename)[1]
        output = filename.replace(ext, ".wgs84" + ext)

    code = EPSG_CODES[geoid]
    # Source srs: WGS84 ellipsoidal horizontal, EGM geoid vertical
    s_srs = f'"epsg:4326+{code}"'
    # Target srs: WGS84 horizontal/vertical
    t_srs = '"epsg:4326"'

    # Note: https://gdal.org/programs/gdalwarp.html#cmdoption-gdalwarp-tr
    # If not specified, gdalwarp will generate an output raster with xsize=ysize
    # We want it to match the input file
    xsize, ysize = _get_size(filename)
    cmd = (
        "gdalwarp {overwrite} -s_srs {s_srs} -t_srs {t_srs}"
        " -of ROI_PAC -ts {xsize} {ysize} "
        " -multi -wo NUM_THREADS=4 -wm 4000 {inp} {out}"
    )
    cmd = cmd.format(
        inp=filename,
        out=output,
        overwrite="-overwrite" if overwrite else "",
        xsize=xsize,
        ysize=ysize,
        s_srs=s_srs,
        t_srs=t_srs,
    )
    logger.info(cmd)
    subprocess.run(cmd, check=True, shell=True)

    if copy_rsc:
        rsc_file = filename + ".rsc"
        logger.info("Copying {} to {}".format(rsc_file, output + ".rsc"))
        shutil.copyfile(rsc_file, output + ".rsc")
    return output


def _get_size(filename):
    """Retrieve the raster size from a gdal-readable file."""
    from osgeo import gdal

    ds = gdal.Open(filename)
    xsize, ysize = ds.RasterXSize, ds.RasterYSize
    ds = None
    return xsize, ysize


def convert_dem_to_wgs84(dem_filename, geoid="egm96"):
    """Convert the file `dem_filename` from EGM96 heights to WGS84 ellipsoidal heights.

    Overwrites file, requires GDAL to be installed
    """
    if not utils._gdal_installed_correctly():
        logger.error("GDAL required to convert DEM to WGS84")
        return

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
        logger.exception("Reverting back, using EGM dem as output")
        os.rename(output_egm, dem_filename)
        os.rename(rsc_filename_egm, rsc_filename)
