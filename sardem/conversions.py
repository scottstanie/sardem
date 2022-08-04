import os
import subprocess
import shutil
import requests
from . import utils, loading
import logging

logger = logging.getLogger("sardem")

URL_EGM08 = "http://download.osgeo.org/proj/vdatum/egm08_25/egm08_25.gtx"
URL_EGM96 = "http://download.osgeo.org/proj/vdatum/egm96_15/egm96_15.gtx"
EGM_URLS = {
    "egm96": URL_EGM96,
    "egm08": URL_EGM08,
}
EGM_FILES = {
    "egm96": os.path.join(utils.get_cache_dir(), "egm96_15.gtx"),
    "egm08": os.path.join(utils.get_cache_dir(), "egm08_25.gtx"),
}


def egm_to_wgs84(filename, output=None, overwrite=True, copy_rsc=True, geoid="egm96"):
    """Convert a DEM with a EGM96 vertical datum to WGS84 heights above ellipsoid"""

    if output is None:
        ext = os.path.splitext(filename)[1]
        output = filename.replace(ext, ".wgs84" + ext)

    egm_file = EGM_FILES[geoid]
    if not os.path.exists(egm_file):
        download_egm_grid(geoid=geoid)

    # Note: https://gdal.org/programs/gdalwarp.html#cmdoption-gdalwarp-tr
    # If not specified, gdalwarp will generate an output raster with xsize=ysize
    # We want it to match the input file
    xsize, ysize = _get_size(filename)
    cmd = (
        'gdalwarp {overwrite} -s_srs "+proj=longlat +datum=WGS84 +no_defs +geoidgrids={egm_file}" '
        '-t_srs "+proj=longlat +datum=WGS84 +no_defs" -of ENVI -ts {xsize} {ysize} {inp} {out}'
    )
    cmd = cmd.format(
        inp=filename,
        out=output,
        overwrite="-overwrite" if overwrite else "",
        xsize=xsize,
        ysize=ysize,
        egm_file=egm_file,
    )
    logger.info(cmd)
    subprocess.run(cmd, check=True, shell=True)

    if copy_rsc:
        rsc_file = filename + ".rsc"
        logger.info("Copying {} to {}".format(rsc_file, output + ".rsc"))
        shutil.copyfile(rsc_file, output + ".rsc")
    return output


def _get_size(filename):
    """Retrieve the raster size from a gdal-readable file"""
    from osgeo import gdal

    ds = gdal.Open(filename)
    xsize, ysize = ds.RasterXSize, ds.RasterYSize
    ds = None
    return xsize, ysize


def convert_dem_to_wgs84(dem_filename, geoid="egm96"):
    """Convert the file `dem_filename` from EGM96 heights to WGS84 ellipsoidal heights

    Overwrites file, requires GDAL to be installed
    """
    if not utils._gdal_installed_correctly():
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
        egm_to_wgs84(output_egm, output=dem_filename, overwrite=True, copy_rsc=True, geoid=geoid)
        os.remove(output_egm)
        os.remove(rsc_filename_egm)
    except Exception:
        logger.error("Failed to convert DEM:", exc_info=True)
        logger.error("Reverting back, using EGM dem as output")
        os.rename(output_egm, dem_filename)
        os.rename(rsc_filename_egm, rsc_filename)

    # Now shift back to the .rsc is pointing to the middle of the pixel
    shift_dem_rsc(rsc_filename, to_gdal=False)


def download_egm_grid(geoid="egm96"):
    if geoid == "egm96":
        url = URL_EGM96
    elif geoid in ("egm08", "egm2008"):
        url = URL_EGM08
    else:
        raise ValueError("Unknown geoid: {}".format(geoid))

    egm_file = EGM_FILES[geoid]
    if os.path.exists(egm_file):
        logger.info("{} already exists, skipping.".format(egm_file))
        return

    size = _get_file_size_mb(url)
    logger.info("Performing 1-time download {} ({:f0} MB file), saving to {}".format(url, size, egm_file))
    with open(egm_file, "wb") as f:
        resp = requests.get(url)
        f.write(resp.content)


def _get_file_size_mb(url):
    # https://stackoverflow.com/a/44299915/4174466
    return int(requests.get(url, stream=True).headers['Content-length']) / 1e6


def shift_dem_rsc(rsc_filename, outname=None, to_gdal=True):
    """Shift the top-left of a .rsc file by half pixel

    See here for geotransform info
    https://gdal.org/user/raster_data_model.html#affine-geotransform
    GDAL standard is to reference a raster by its top left edges,
    while the .rsc for SAR focusing might use the middle of a pixel.
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


