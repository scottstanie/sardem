"""
Command line interface for running createdem
"""
from sardem.dem import Downloader
import sys
import json
from argparse import (
    ArgumentError,
    ArgumentParser,
    ArgumentTypeError,
    FileType,
    RawTextHelpFormatter,
)
import sardem


def positive_small_int(argstring):
    try:
        intval = int(argstring)
        assert intval > 0 and intval < 50
    except (ValueError, AssertionError):
        raise ArgumentTypeError("--rate must be positive integer < 50")
    return intval


# Note: overriding this to show the positionals first
USAGE = """%(prog)s { left_lon top_lat dlon dlat | --geojson GEOJSON | --bbox left bot right top }
                 [-h] [--rate RATE=1] [--output OUTPUT=elevation.dem]
                 [--data-source {NASA,AWS,NASA_WATER}]
                 """

DESCRIPTION = """Stiches SRTM .hgt files to make (upsampled) DEM

    Pick a lat/lon bounding box for a DEM, and it will download
    the necessary SRTM1 tiles, stitch together, then upsample.

    Usage Examples:
        createdem -156.0 20.2 1 2 --rate 2  # Makes a box 1 degree wide, 2 deg high
        createdem -156.0 20.2 0.5 0.5 -r 10 --data-source NASA -o my_elevation.dem
        createdem --geojson dem_area.geojson -r 10

    Default out is elevation.dem for the final upsampled DEM.
    Also creates elevation.dem.rsc with start lat/lon, stride, and other info."""


def cli():
    parser = ArgumentParser(
        prog="sardem",
        description=DESCRIPTION,
        usage=USAGE,
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
        help="Source of SRTM data (default %(default)s). See README for more.",
    )

    args = parser.parse_args()
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
    ):
        parser.print_usage(sys.stderr)
        sys.exit(1)

    geojson_dict = json.load(args.geojson) if args.geojson else None
    if args.bbox:
        left, bot, right, top = args.bbox
        left_lon, top_lat = left, top
        dlon = right - left
        dlat = top - bot
    elif args.left_lon:
        left_lon, top_lat = args.left_lon, args.top_lat
        dlon, dlat = args.dlon, args.dlat
    
    if not args.output:
        output = "watermask.wbd" if args.data_source == "NASA_WATER" else "elevation.dem"

    sardem.dem.main(
        left_lon,
        top_lat,
        dlon,
        dlat,
        geojson_dict,
        args.data_source,
        args.xrate,
        args.yrate,
        output,
    )
