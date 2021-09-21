"""
Command line interface for running sardem
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
        sardem --geojson dem_area.geojson -x 11 -y 3
        sardem -156.0 20.2 0.5 0.5 -r 10 --data-source NASA_WATER -o my_watermask.wbd # Water mask

    Default out is elevation.dem for the final upsampled DEM.
    Also creates elevation.dem.rsc with start lat/lon, stride, and other info."""


def cli():
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
        help="Source of SRTM data (default %(default)s). See README for more.",
    )
    parser.add_argument(
        "--convert-to-wgs84",
        "-c",
        action="store_true",
        help=(
            "Convert the DEM heights from geoid heights above EGM96 "
            "to heights above WGS84 ellipsoid"
        ),
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
        and not args.wkt_file
    ):
        parser.print_usage(sys.stderr)
        sys.exit(1)

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
        geojson_dict,
        args.wkt_file,
        args.data_source,
        args.xrate,
        args.yrate,
        args.convert_to_wgs84,
        output,
    )
