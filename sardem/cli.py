"""
Command line interface for running sardem
"""
from sardem.download import Downloader
import json
from argparse import (
    ArgumentError,
    ArgumentParser,
    ArgumentTypeError,
    FileType,
    RawTextHelpFormatter,
)


def positive_small_int(argstring):
    try:
        intval = int(argstring)
        assert 0 < intval < 50
    except (ValueError, AssertionError):
        raise ArgumentTypeError("--rate must be positive integer < 50")
    return intval


DESCRIPTION = """Stiches SRTM .hgt files to make (upsampled) DEM

    Pick a lat/lon bounding box for a DEM, and it will download
    the necessary SRTM1 tiles, stitch together, then upsample.

    Usage Examples:
        sardem --bbox -156 18.8 -154.7 20.3  # bounding box: left  bottom  right top
        sardem -156.0 20.2 1 2 --xrate 2 --yrate 2  # Makes a box 1 degree wide, 2 deg high
        sardem --bbox -156 18.8 -154.7 20.3 --data-source COP  # Copernicus DEM
        sardem --geojson dem_area.geojson -x 11 -y 3 # Use geojson file to define area
        sardem --bbox -156 18.8 -154.7 20.3 --data-source NASA_WATER -o my_watermask.wbd # Water mask
        sardem --bbox -156 18.8 -154.7 20.3 --data COP -isce  # Generate .isce XML files as well


    Default out is elevation.dem for the final upsampled DEM.
    Also creates elevation.dem.rsc with start lat/lon, stride, and other info."""


def get_cli_args():
    parser = ArgumentParser(
        prog="sardem",
        description=DESCRIPTION,
        formatter_class=RawTextHelpFormatter,
    )
    parser.add_argument(
        "left_lon",
        nargs="?",
        type=float,
        help="Left (western) most longitude of DEM box (degrees, west=negative)",
    )
    parser.add_argument(
        "top_lat",
        nargs="?",
        type=float,
        help="Top (northern) most latitude of DEM box (degrees)",
    )
    parser.add_argument(
        "dlon", nargs="?", type=float, help="Width of DEM box (degrees)"
    )
    parser.add_argument(
        "dlat", nargs="?", type=float, help="Height of DEM box (degrees)"
    )
    parser.add_argument(
        "--bbox",
        nargs=4,
        metavar=("left", "bottom", "right", "top"),
        type=float,
        help="Bounding box of area of interest "
        " (e.g. --bbox -106.1 30.1 -103.1 33.1 ). ",
    )
    parser.add_argument(
        "--geojson",
        "-g",
        type=FileType(),
        help="Alternate to corner/dlon/dlat box specification: \n"
        "File containing the geojson object for DEM bounds",
    )
    parser.add_argument(
        "--wkt-file",
        type=FileType(),
        help="Alternate to corner/dlon/dlat box specification: \n"
        "File containing the WKT string for DEM bounds",
    )
    parser.add_argument(
        "--xrate",
        "-x",
        default=1,
        type=positive_small_int,
        help="Rate in x dir to upsample DEM (default=1, no upsampling)",
    )
    parser.add_argument(
        "--yrate",
        "-y",
        default=1,
        type=positive_small_int,
        help="Rate in y dir to upsample DEM (default=1, no upsampling)",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Name of output dem file"
        " (default=elevation.dem for DEM, watermask.wbd for water mask)",
    )
    parser.add_argument(
        "--data-source",
        "-d",
        choices=Downloader.VALID_SOURCES,
        type=str.upper,
        default="NASA",
        help="Source of DEM data (default %(default)s). See README for more.",
    )
    parser.add_argument(
        "-isce",
        "--make-isce-xml",
        action="store_true",
        help="Make an isce2 XML file for the DEM.",
    )
    parser.add_argument(
        "--keep-egm",
        action="store_true",
        help=(
            "Keep the DEM heights as geoid heights above EGM96 or EGM2008. "
            "Default is to convert to WGS84 for InSAR processing."
        ),
    )
    parser.add_argument(
        "--shift-rsc",
        action="store_true",
        help=(
            "Shift the .rsc file by half a pixel so that X_FIRST and Y_FIRST "
            "are at the pixel center (instead of GDAL's convention of the top left edge)."
            " Default is GDAL's top-left edge convention."
        ),
    )

    return parser.parse_args()


def cli():
    args = get_cli_args()
    import sardem.dem

    if args.left_lon and args.geojson or args.left_lon and args.bbox:
        raise ArgumentError(
            args.geojson,
            "Can only use one of positional arguments (left_lon top_lat dlon dlat) "
            ", --geojson, or --bbox",
        )
    # Need all 4 positionals, or the --geosjon
    elif (
        any(a is None for a in (args.left_lon, args.top_lat, args.dlon, args.dlat))
        and not args.geojson
        and not args.bbox
        and not args.wkt_file
    ):
        raise ValueError("Need --bbox, --geojoin, or --wkt-file")

    geojson_dict = json.load(args.geojson) if args.geojson else None
    if args.bbox:
        left, bot, right, top = args.bbox
        left_lon, top_lat = left, top
        dlon = right - left
        dlat = top - bot
    elif args.wkt_file:
        left_lon, top_lat, dlon, dlat = None, None, None, None
    elif args.left_lon:
        left_lon, top_lat = args.left_lon, args.top_lat
        dlon, dlat = args.dlon, args.dlat

    if not args.output:
        output = (
            "watermask.wbd" if args.data_source == "NASA_WATER" else "elevation.dem"
        )
    else:
        output = args.output

    sardem.dem.main(
        left_lon,
        top_lat,
        dlon,
        dlat,
        geojson=geojson_dict,
        wkt_file=args.wkt_file,
        data_source=args.data_source,
        xrate=args.xrate,
        yrate=args.yrate,
        make_isce_xml=args.make_isce_xml,
        keep_egm=args.keep_egm,
        shift_rsc=args.shift_rsc,
        output_name=output,
    )
