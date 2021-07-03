import os
import requests
from . import utils
import logging

logger = logging.getLogger("sardem")
utils.set_logger_handler(logger)

EGM_FILE = os.path.join(utils.get_cache_dir(), "egm96_15.gtx")


def egm96_to_wgs84(filename, output=None, overwrite=True, copy_rsc=True):
    """Convert a DEM with a EGM96 vertical datum to WGS84 heights above ellipsoid"""
    import subprocess
    import shutil

    if output is None:
        ext = os.path.splitext(filename)[1]
        output = filename.replace(ext, ".wgs84" + ext)

    if not os.path.exists(EGM_FILE):
        download_egm96_grid()

    cmd = (
        'gdalwarp {overwrite} -s_srs "+proj=longlat +datum=WGS84 +no_defs +geoidgrids={egm_file}" '
        '-t_srs "+proj=longlat +datum=WGS84 +no_defs" -of ENVI {inp} {out}'
    )
    cmd = cmd.format(
        inp=filename,
        out=output,
        overwrite="-overwrite" if overwrite else "",
        egm_file=EGM_FILE,
    )
    logger.info(cmd)
    subprocess.run(cmd, check=True, shell=True)

    if copy_rsc:
        rsc_file = filename + ".rsc"
        logger.info("Copying {} to {}".format(rsc_file, output + ".rsc"))
        shutil.copyfile(rsc_file, output + ".rsc")


def download_egm96_grid():
    url = "http://download.osgeo.org/proj/vdatum/egm96_15/egm96_15.gtx"
    if os.path.exists(EGM_FILE):
        logger.info("{} already exists, skipping.".format(EGM_FILE))
        return

    logger.info("Downloading from {} to {}".format(url, EGM_FILE))
    with open(EGM_FILE, "wb") as f:
        resp = requests.get(url)
        f.write(resp.content)
