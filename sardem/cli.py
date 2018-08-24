"""
Command line interface for running createdem
"""
from argparse import (
    ArgumentParser,
    ArgumentError,
    ArgumentTypeError,
    FileType,
    RawTextHelpFormatter,
)
import sardem
import sys


def positive_int(argstring):
    try:
        intval = int(argstring)
        assert intval > 0
    except (ValueError, AssertionError):
        raise ArgumentTypeError("--rate must be a positive int")
    return intval


# Note: overriding this to show the positionals first
USAGE = """%(prog)s { left_lon top_lat dlon dlat | --geojson GEOJSON }
                 [-h] [--rate RATE] [--output OUTPUT]
                 [--data-source {NASA,AWS}]
                 """

DESCRIPTION = """Stiches SRTM .hgt files to make (upsampled) DEM

    Pick a lat/lon bounding box for a DEM, and it will download
    the necessary SRTM1 tiles, stitch together, then upsample.
    Also creates elevation.dem.rsc with start lat/lon, stride, and other info.

    If you want to use geojson to describe the DEM area: http://geojson.io
    can give you geojson for any polygon
    Take the output of that and save to a file (e.g. mybox.geojson)

    Usage Examples:
        createdem -150.0 20.2 0.5 0.5 -r 2
        createdem --geojson data/mybox.geojson --rate 2
        createdem -150.0 20.2 0.5 0.5 -r 10 --data-source NASA -o my_elevation.dem

    Default out is elevation.dem for the final upsampled DEM.
    """


def cli():
    parser = ArgumentParser(
        prog='createdem',
        description=DESCRIPTION,
        usage=USAGE,
        formatter_class=RawTextHelpFormatter)
    parser.add_argument(
        "left_lon",
        nargs="?",
        type=float,
        help="Left (western) most longitude of DEM box (in degrees)")
    parser.add_argument(
        "top_lat",
        nargs="?",
        type=float,
        help="Top (northern) most latitude of DEM box (in degrees)")
    parser.add_argument("dlon", nargs="?", type=float, help="Width of DEM box in degrees")
    parser.add_argument("dlat", nargs="?", type=float, help="Height of DEM box in degrees")
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
        type=positive_int,  # Reasonable range of upsampling rates
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
        help="Source of SRTM data. See dem docstring for more about data.")

    args = parser.parse_args()
    if args.left_lon and args.geojson:
        raise ArgumentError(
            args.geojson, "Can't use both positional arguments "
            "(left_lon top_lat dlon dlat) and --geojson")
    # Need all 4 positionals, or the --geosjon
    elif not (args.left_lon and args.top_lat and args.dlon and args.dlat) and not args.geojson:
        parser.print_usage(sys.stderr)
        sys.exit(1)

    sardem.dem.main(args.left_lon, args.top_lat, args.dlon, args.dlat, args.geojson,
                    args.data_source, args.rate, args.output)
