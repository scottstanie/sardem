import contextlib
import logging
import os
import shutil
import subprocess

from . import utils

logger = logging.getLogger("sardem")

EPSG_CODES = {
    "egm96": "5773",  # https://epsg.io/5773
    "egm08": "3855",  # https://epsg.io/3855
    "navd88": "5703",  # https://epsg.io/5703
}
EGM_FILES = {
    "egm96": os.path.join(utils.get_cache_dir(), "egm96_15.gtx"),
    "egm08": os.path.join(utils.get_cache_dir(), "egm08_25.gtx"),
}


def vertical_shift(s_srs, lon, lat):
    """Return the height change (m) PROJ applies at (lon, lat) from `s_srs` to WGS84 ellipsoidal heights.

    `s_srs` is a compound CRS with a geoid vertical datum, e.g. "EPSG:4326+3855".
    """
    from osgeo import osr

    src = osr.SpatialReference()
    src.SetFromUserInput(s_srs)
    dst = osr.SpatialReference()
    dst.ImportFromEPSG(4979)
    for srs in (src, dst):
        srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return osr.CoordinateTransformation(src, dst).TransformPoint(lon, lat, 0.0)[2]


@contextlib.contextmanager
def geoid_grid_access(s_srs, lon, lat):
    """Make sure PROJ can convert `s_srs` geoid heights to ellipsoidal heights while the block runs.

    PROJ needs a geoid grid for this shift. The conda-forge `proj` package ships no
    geoid grids and PROJ network access is off by default. Without a grid, PROJ falls
    back to a no-op vertical transformation, so gdalwarp writes geoid heights where
    ellipsoidal heights were requested, with no error or warning.

    PROJ network access is enabled for the duration of the block, so a missing grid is
    fetched on demand from the PROJ CDN and cached (a locally installed grid is used as
    is). It has to be enabled before the first lookup: PROJ remembers a grid it could
    not find for the rest of the process. If the shift is still unavailable (e.g.
    offline), raise rather than write wrong heights. The previous setting is restored.
    """
    from osgeo import osr

    previous = osr.GetPROJEnableNetwork()
    osr.SetPROJEnableNetwork(True)
    try:
        if abs(vertical_shift(s_srs, lon, lat)) < 1e-6:
            raise RuntimeError(
                "PROJ cannot convert {} heights to WGS84 ellipsoidal heights at lon={}, lat={}: "
                "the geoid grid is not installed and could not be downloaded. Without it the "
                "output would silently keep geoid heights. Fix one of: allow network access, "
                "install the grids (`projsync --source-id us_nga`, or the conda-forge "
                "`proj-data` package), or keep geoid heights on purpose "
                "(keep_egm=True).".format(s_srs, lon, lat)
            )
        yield
    finally:
        osr.SetPROJEnableNetwork(previous)


def _raster_center(filename):
    """Return the (lon, lat) of the centre of a gdal-readable, lon/lat-gridded raster."""
    from osgeo import gdal

    ds = gdal.Open(filename)
    gt = ds.GetGeoTransform()
    lon = gt[0] + gt[1] * ds.RasterXSize / 2 + gt[2] * ds.RasterYSize / 2
    lat = gt[3] + gt[4] * ds.RasterXSize / 2 + gt[5] * ds.RasterYSize / 2
    ds = None
    return lon, lat


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

    # Note: https://gdal.org/programs/gdalwarp.html#cmdoption-gdalwarp-tr
    # If not specified, gdalwarp will generate an output raster with xsize=ysize
    # We want it to match the input file
    xsize, ysize = _get_size(filename)
    cmd = (
        'gdalwarp {overwrite} -s_srs {s_srs} -t_srs {t_srs}'
        ' -of ROI_PAC -ts {xsize} {ysize} '
        ' -multi -wo NUM_THREADS=4 -wm 4000 {inp} {out}'
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
    lon, lat = _raster_center(filename)
    with geoid_grid_access(s_srs.strip('"'), lon, lat):
        subprocess.run(cmd, check=True, shell=True, env=dict(os.environ, PROJ_NETWORK="ON"))

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
        logger.error("Reverting back to the EGM dem")
        os.rename(output_egm, dem_filename)
        os.rename(rsc_filename_egm, rsc_filename)
        # The caller asked for ellipsoidal heights; do not hand back geoid heights silently.
        raise