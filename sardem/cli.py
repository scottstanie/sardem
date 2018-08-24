"""
Command line interface for running createdem
"""
from argparse import (
    ArgumentParser,
    ArgumentTypeError,
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
USAGE = """%(prog)s left_lon top_lat dlon dlat
                 [-h] [--rate RATE=1] [--output OUTPUT=elevation.dem]
                 [--data-source {NASA,AWS}]
                 """

DESCRIPTION = """Stiches SRTM .hgt files to make (upsampled) DEM

    Pick a lat/lon bounding box for a DEM, and it will download
    the necessary SRTM1 tiles, stitch together, then upsample.

    Usage Examples:
        createdem -156.0 20.2 1 2 --rate 2  # Makes a box 1 degree wide, 2 deg high
        createdem -156.0 20.2 0.5 0.5 -r 10 --data-source NASA -o my_elevation.dem

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
        type=float,
        help="Left (western) most longitude of DEM box (degrees, west=negative)")
    parser.add_argument(
        "top_lat", type=float, help="Top (northern) most latitude of DEM box (degrees)")
    parser.add_argument("dlon", type=float, help="Width of DEM box (degrees)")
    parser.add_argument("dlat", type=float, help="Height of DEM box (degrees)")
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
    sardem.dem.main(args.left_lon, args.top_lat, args.dlon, args.dlat, args.data_source, args.rate,
                    args.output)
