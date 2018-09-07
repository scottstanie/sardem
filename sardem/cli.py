"""
Command line interface for running createdem
"""
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
        assert (intval > 0 and intval < 50)
    except (ValueError, AssertionError):
        raise ArgumentTypeError("--rate must be positive integer < 50")
    return intval


# Note: overriding this to show the positionals first
USAGE = """%(prog)s { left_lon top_lat dlon dlat | --geojson GEOJSON }
                 [-h] [--rate RATE=1] [--output OUTPUT=elevation.dem]
                 [--data-source {NASA,AWS}]
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
        prog='createdem',
        description=DESCRIPTION,
        usage=USAGE,
        formatter_class=RawTextHelpFormatter)
    parser.add_argument(
        "left_lon",
        nargs='?',
        type=float,
        help="Left (western) most longitude of DEM box (degrees, west=negative)")
    parser.add_argument(
        "top_lat", nargs='?', type=float, help="Top (northern) most latitude of DEM box (degrees)")
    parser.add_argument("dlon", nargs='?', type=float, help="Width of DEM box (degrees)")
    parser.add_argument("dlat", nargs='?', type=float, help="Height of DEM box (degrees)")
    parser.add_argument(
        "--geojson",
        "-g",
        type=FileType(),
        help="Alternate to corner/dlon/dlat box specification: \n"
        "File containing the geojson object for DEM bounds")
    parser.add_argument(
        "--rate",
        "-r",
        default=1,
        type=positive_small_int,
        help="Rate at which to upsample DEM (default=1, no upsampling)")
    parser.add_argument(
        "--output",
        "-o",
        default="elevation.dem",
        help="Name of output dem file (default=elevation.dem)")
    parser.add_argument(
        "--data-source",
        "-d",
        choices=('NASA', 'AWS'),
        default='NASA',
        help="Source of SRTM data (default NASA). See README for more.")

    args = parser.parse_args()
    if args.left_lon and args.geojson:
        raise ArgumentError(
            args.geojson, "Can't use both positional arguments "
            "(left_lon top_lat dlon dlat) and --geojson")
    # Need all 4 positionals, or the --geosjon
    elif any(a is None
             for a in (args.left_lon, args.top_lat, args.dlon, args.dlat)) and not args.geojson:
        parser.print_usage(sys.stderr)
        sys.exit(1)

    geojson_dict = json.load(args.geojson) if args.geojson else None
    sardem.dem.main(args.left_lon, args.top_lat, args.dlon, args.dlat, geojson_dict,
                    args.data_source, args.rate, args.output)
