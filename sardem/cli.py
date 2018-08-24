"""
Command line interface for running createdem
"""
import argparse
import sardem


def positive_int(argstring):
    try:
        intval = int(argstring)
        assert intval > 0
    except (ValueError, AssertionError):
        raise argparse.ArgumentError("--rate must be a positive int")
    return intval


USAGE_STRING = """Stiches .hgt files to make (upsampled) DEM

    Pick a lat/lon bounding box for a DEM, and it will download
    the necessary SRTM1 tile, combine into one array,
    then upsample using upsample.c
    Also creates elevation.dem.rsc with start lat/lon, stride, and other info.

    If you want geojson: http://geojson.io gives you geojson for any polygon
    Take the output of that and save to a file (e.g. mybox.geojson)

    Usage:

        sardem create --geojson data/mybox.geojson --rate 2

        sardem create --corner -150.0 20.2 --dlon 0.5 --dlat 0.5 -r 2

    Default out is elevation.dem for upsampled version
    """


def main():
    parser = argparse.ArgumentParser(prog='createdem', description=USAGE_STRING)
    parser.add_argument(
        "corner",
        type=float,
        nargs='*',
        help="Specify box with 'left-long top-lat dlon dlat' in degrees, "
        " where dlon is width in degrees, dlat is height in degrees "
        " Example.: -150.0 20.0 1.5 2.0"
        "Used instead of --geojson, must also specify --dlat and --dlon")
    parser.add_argument(
        "--geojson",
        "-g",
        type=argparse.FileType(),
        help="Alternate to corner box specification: "
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

    start_lon, start_lat, dlon, dlat = args.corner
    sardem.dem.main(start_lon, start_lat, dlon, dlat, args.geojson, args.data_source, args.rate,
                    args.output)
