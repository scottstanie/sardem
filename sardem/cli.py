"""
Main command line entry point to manage all other sub commands
"""
import click
import sardem
import matplotlib.pyplot as plt


# Main entry point:
@click.group()
@click.option('--verbose', is_flag=True)
@click.option(
    '--path',
    type=click.Path(exists=False, file_okay=False, writable=True),
    default='.',
    help="Path of interest for command. "
    "Will search for files path or change directory, "
    "depending on command.")
@click.pass_context
def cli(ctx, verbose, path):
    """Command line tool for creating upsampled DEMs."""
    # Store these to be passed to all subcommands
    ctx.obj = {}
    ctx.obj['verbose'] = verbose
    ctx.obj['path'] = path


# COMMAND: CREATE
@cli.command()
@click.option(
    "--geojson",
    "-g",
    required=True,
    type=click.File('r'),
    help="File containing the geojson object for DEM bounds")
@click.option(
    "--rate",
    "-r",
    default=1,
    type=click.IntRange(0, 30),  # Reasonable range of upsampling rates
    help="Rate at which to upsample DEM (default=1, no upsampling)")
@click.option(
    "--output",
    "-o",
    default="elevation.dem",
    help="Name of output dem file (default=elevation.dem)")
@click.option(
    "--data-source",
    "-d",
    type=click.Choice(['NASA', 'AWS']),
    default='NASA',
    help="Source of SRTM data. See dem docstring for more about data.")
@click.pass_obj
def create(context, geojson, data_source, rate, output):
    """Stiches .hgt files to make (upsampled) DEM

    Pick a lat/lon bounding box for a DEM, and it will download
    the necessary SRTM1 tile, combine into one array,
    then upsample using upsample.c

    Suggestion for box: http://geojson.io gives you geojson for any polygon
    Take the output of that and save to a file (e.g. mybox.geojson

    Usage:

        sardem create --geojson data/mybox.geojson --rate 2

        sardem create -g data/mybox.geojson -r 2 -o elevation.dem

    Default out is elevation.dem for upsampled version, elevation_small.dem
    Also creates elevation.dem.rsc with start lat/lon, stride, and other info.
    """
    sardem.dem.main(geojson, data_source, rate, output)


# COMMAND: view
@cli.command(name='view')
@click.argument("demfile", type=click.Path(exists=True, dir_okay=False), nargs=-1)
def view(demfile):
    """View a .dem file with matplotlib.

    Can list multiple .dem files to open in separate figures.
    """
    for fname in demfile:
        dem = sardem.utils.load_elevation(fname)
        plt.figure()
        plt.imshow(dem)
        plt.colorbar()

    # Wait for windows to close to exit the script
    plt.show(block=True)
