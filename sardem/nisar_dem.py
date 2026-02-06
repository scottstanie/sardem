import logging
import netrc
import os
from copy import deepcopy

from sardem import utils
from sardem.constants import DEFAULT_RES

_NISAR_BASE_URL = "https://nisar.asf.earthdatacloud.nasa.gov/NISAR/DEM/v1.2"
NISAR_VRTS = {
    "EPSG4326": f"{_NISAR_BASE_URL}/EPSG4326/EPSG4326.vrt",
    "EPSG3031": f"{_NISAR_BASE_URL}/EPSG3031/EPSG3031.vrt",  # South pole
    "EPSG3413": f"{_NISAR_BASE_URL}/EPSG3413/EPSG3413.vrt",  # North pole
}
# Latitude thresholds for switching to polar stereographic VRTs
_SOUTH_POLE_LAT = -60.0
_NORTH_POLE_LAT = 60.0

EARTHDATA_HOST = "urs.earthdata.nasa.gov"

logger = logging.getLogger("sardem")
utils.set_logger_handler(logger)


def _check_earthdata_credentials() -> None:
    """Verify that ~/.netrc has credentials for urs.earthdata.nasa.gov.

    Raises
    ------
    RuntimeError
        If credentials are missing or incomplete.
    """
    netrc_path = os.path.expanduser("~/.netrc")
    try:
        nrc = netrc.netrc(netrc_path)
        auth = nrc.authenticators(EARTHDATA_HOST)
        assert auth is not None and auth[0] and auth[2]
    except (OSError, netrc.NetrcParseError, AssertionError):
        raise RuntimeError(
            "NASA Earthdata credentials not found in ~/.netrc for"
            f" {EARTHDATA_HOST}.\n"
            "The NISAR DEM requires a free NASA Earthdata account.\n"
            "Sign up at: https://urs.earthdata.nasa.gov/users/new\n"
            "Then add to ~/.netrc:\n"
            f"  machine {EARTHDATA_HOST}\n"
            "      login <username>\n"
            "      password <password>"
        )


def _configure_gdal_auth() -> None:
    """Set GDAL config options for cookie-based NASA Earthdata authentication."""
    from osgeo import gdal

    cookie_file = os.path.join(utils.get_cache_dir(), "earthdata_cookies.txt")
    gdal.SetConfigOption("GDAL_HTTP_COOKIEFILE", cookie_file)
    gdal.SetConfigOption("GDAL_HTTP_COOKIEJAR", cookie_file)
    gdal.SetConfigOption("GDAL_HTTP_AUTH", "BASIC")
    gdal.SetConfigOption("GDAL_HTTP_NETRC", "YES")


def _select_vrt(bbox: tuple) -> tuple[str, str | None]:
    """Choose the appropriate NISAR VRT and output SRS based on bbox latitude.

    Parameters
    ----------
    bbox : tuple
        (left, bottom, right, top) in degrees.

    Returns
    -------
    vrt_url : str
        The ``/vsicurl/`` URL to the selected VRT.
    dst_srs : str or None
        Target SRS for ``gdal.Warp``.  ``None`` when the VRT is already
        EPSG:4326; ``"EPSG:4326"`` when reprojecting from a polar VRT.
    """
    _left, bottom, _right, top = bbox
    if top <= _SOUTH_POLE_LAT:
        key = "EPSG3031"
    elif bottom >= _NORTH_POLE_LAT:
        key = "EPSG3413"
    else:
        key = "EPSG4326"
    url = "/vsicurl/" + NISAR_VRTS[key]
    dst_srs = "EPSG:4326" if key != "EPSG4326" else None
    logger.info("Selected NISAR VRT: %s", key)
    return url, dst_srs


def download_and_stitch(
    output_name: str,
    bbox: tuple,
    xrate: int = 1,
    yrate: int = 1,
    vrt_filename: str | None = None,
    output_format: str = "GTiff",
    output_type: str = "float32",
) -> None:
    """Download the NISAR DEM via its global VRT.

    The NISAR DEM is a Copernicus-derived DEM prepared by JPL with
    EGM2008-to-WGS84 conversion pre-applied and ocean gaps filled.
    No vertical datum conversion is needed.

    Parameters
    ----------
    output_name : str
        Path for the output DEM file.
    bbox : tuple
        (left, bottom, right, top) in degrees.
    xrate : int
        Column upsampling rate.
    yrate : int
        Row upsampling rate.
    vrt_filename : str, optional
        Override the VRT source (for testing). Defaults to the NISAR VRT URL.
    output_format : str
        GDAL output format (default ``"GTiff"``).
    output_type : str
        GDAL output data type (default ``"float32"``).

    References
    ----------
    https://nisar.asf.earthdatacloud.nasa.gov/NISAR/DEM/v1.2/EPSG4326/
    """
    from osgeo import gdal

    gdal.UseExceptions()

    dst_srs = None
    if vrt_filename is None:
        _check_earthdata_credentials()
        _configure_gdal_auth()
        vrt_filename, dst_srs = _select_vrt(bbox)

    xres = DEFAULT_RES / xrate
    yres = DEFAULT_RES / yrate
    resamp = "bilinear" if (xrate > 1 or yrate > 1) else "nearest"

    option_dict = dict(
        format=output_format,
        outputBounds=bbox,
        dstSRS=dst_srs,
        xRes=xres,
        yRes=yres,
        outputType=gdal.GetDataTypeByName(output_type.title()),
        resampleAlg=resamp,
        multithread=True,
        warpMemoryLimit=5000,
        warpOptions=["NUM_THREADS=4"],
    )

    logger.info("Creating %s", output_name)
    logger.info("Fetching remote tiles...")
    try:
        cmd = _gdal_cmd_from_options(vrt_filename, output_name, option_dict)
        logger.info("Running GDAL command:")
        logger.info(cmd)
    except Exception:
        logger.info("Running gdal.Warp with options:")
        logger.info(option_dict)

    option_dict["callback"] = gdal.TermProgress
    gdal.Warp(output_name, vrt_filename, options=gdal.WarpOptions(**option_dict))


def _gdal_cmd_from_options(src: str, dst: str, option_dict: dict) -> str:
    """Build an equivalent ``gdalwarp`` CLI string for debugging."""
    from osgeo import gdal

    opts = deepcopy(option_dict)
    opts["options"] = "__RETURN_OPTION_LIST__"
    opt_list = gdal.WarpOptions(**opts)
    out_opt_list = deepcopy(opt_list)
    for idx, o in enumerate(opt_list):
        if o.endswith("srs"):
            out_opt_list[idx + 1] = '"{}"'.format(out_opt_list[idx + 1])
    return "gdalwarp {} {} {}".format(src, dst, " ".join(out_opt_list))
