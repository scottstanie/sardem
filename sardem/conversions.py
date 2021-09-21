import os
import subprocess
import shutil
import requests
from . import utils, loading
import logging

logger = logging.getLogger("sardem")

EGM_FILE = os.path.join(utils.get_cache_dir(), "egm96_15.gtx")


def egm96_to_wgs84(filename, output=None, overwrite=True, copy_rsc=True):
    """Convert a DEM with a EGM96 vertical datum to WGS84 heights above ellipsoid"""

    if output is None:
        ext = os.path.splitext(filename)[1]
        output = filename.replace(ext, ".wgs84" + ext)

    if not os.path.exists(EGM_FILE):
        download_egm96_grid()

    xres, yres = _get_resolution(filename)
    cmd = (
        'gdalwarp {overwrite} -s_srs "+proj=longlat +datum=WGS84 +no_defs +geoidgrids={egm_file}" '
        '-t_srs "+proj=longlat +datum=WGS84 +no_defs" -of ENVI -tr {xres} {yres} {inp} {out}'
    )
    cmd = cmd.format(
        inp=filename,
        out=output,
        overwrite="-overwrite" if overwrite else "",
        xres=xres,
        yres=yres,
        egm_file=EGM_FILE,
    )
    logger.info(cmd)
    subprocess.run(cmd, check=True, shell=True)

    if copy_rsc:
        rsc_file = filename + ".rsc"
        logger.info("Copying {} to {}".format(rsc_file, output + ".rsc"))
        shutil.copyfile(rsc_file, output + ".rsc")
    return output


def _get_resolution(filename):
    from osgeo import gdal

    ds = gdal.Open(filename)
    gt = ds.GetGeoTransform()
    xres, yres = gt[1], gt[5]
    return xres, yres


def convert_dem_to_wgs84(dem_filename):
    """Convert the file `dem_filename` from EGM96 heights to WGS84 ellipsoidal heights

    Overwrites file, requires GDAL to be installed
    """
    if not _gdal_installed_correctly():
        logger.error("GDAL required to convert DEM to WGS84")
        return

    path_, fname = os.path.split(dem_filename)
    rsc_filename = os.path.join(path_, fname + ".rsc")
    shift_dem_rsc(rsc_filename, to_gdal=True)

    output_egm = os.path.join(path_, "egm_" + fname)
    # output_wgs = dem_filename.replace(ext, ".wgs84" + ext)
    rsc_filename_egm = os.path.join(path_, "egm_" + fname + ".rsc")
    os.rename(dem_filename, output_egm)
    os.rename(rsc_filename, rsc_filename_egm)
    try:
        egm96_to_wgs84(output_egm, output=dem_filename, overwrite=True, copy_rsc=True)
        os.remove(output_egm)
        os.remove(rsc_filename_egm)
    except Exception:
        logger.error("Failed to convert DEM:", exc_info=True)
        logger.error("Reverting back, using EGM dem as output")
        os.rename(output_egm, dem_filename)
        os.rename(rsc_filename_egm, rsc_filename)

    # Now shift back to the .rsc is pointing to the middle of the pixel
    shift_dem_rsc(rsc_filename, to_gdal=False)


def download_egm96_grid():
    url = "http://download.osgeo.org/proj/vdatum/egm96_15/egm96_15.gtx"
    if os.path.exists(EGM_FILE):
        logger.info("{} already exists, skipping.".format(EGM_FILE))
        return

    logger.info("Downloading from {} to {}".format(url, EGM_FILE))
    with open(EGM_FILE, "wb") as f:
        resp = requests.get(url)
        f.write(resp.content)


def shift_dem_rsc(rsc_filename, outname=None, to_gdal=True):
    """Shift the top-left of a .rsc file by half pixel

    See here for geotransform info
    https://gdal.org/user/raster_data_model.html#affine-geotransform
    GDAL standard is to reference a raster by its top left edges,
    while often the .rsc for SAR focusing is using the middle of a pixel.
    `to_gdal`=True means it moves the X_FIRST, Y_FIRST up and left half a pixel.
    `to_gdal`=False does the reverse, back to the middle of the top left pixel
    """
    msg = "Shifting %s for GDAL conversion by half pixel "
    msg += "to edges" if to_gdal else "back to center"
    logger.info(msg, rsc_filename)
    if outname is None:
        outname = rsc_filename
    rsc_dict = loading.load_dem_rsc(rsc_filename)

    rsc_dict["x_step"]
    x_first, y_first = rsc_dict["x_first"], rsc_dict["y_first"]
    x_step, y_step = rsc_dict["x_step"], rsc_dict["y_step"]
    if to_gdal:
        new_first = {
            "x_first": x_first - 0.5 * x_step,
            "y_first": y_first - 0.5 * y_step,
        }
    else:
        new_first = {
            "x_first": x_first + 0.5 * x_step,
            "y_first": y_first + 0.5 * y_step,
        }
    rsc_dict.update(new_first)
    with open(outname, "w") as f:
        f.write(loading.format_dem_rsc(rsc_dict))


def _gdal_installed_correctly():
    cmd = "gdalinfo --help-general"
    # cmd = "gdalinfo -h"
    try:
        subprocess.check_output(cmd, shell=True)
        return True
    except subprocess.CalledProcessError:
        logger.error("GDAL command failed to run.", exc_info=True)
        logger.error("Check GDAL installation.")
        return False
