[![Build Status](https://travis-ci.org/scottstanie/sardem.svg?branch=master)](https://travis-ci.org/scottstanie/sardem)
[![Coverage Status](https://coveralls.io/repos/github/scottstanie/sardem/badge.svg?branch=master)](https://coveralls.io/github/scottstanie/sardem?branch=master)

# DEM creator

Tool for making Digital Elevation Maps (DEMs) in Roipac data format (16-bit integers, little endian) for use in Interferometric SAR (InSAR) processing

`sardem` creates a cropped (and possibly upsampled) digital elevation map:

```bash
usage: sardem { left_lon top_lat dlon dlat | --geojson GEOJSON | --bbox left bot right top }
                 [-h] [--xrate XRATE=1] [--yrate YRATE=1] [--output OUTPUT=elevation.dem]
                 [--data-source {NASA,AWS,NASA_WATER}]
```

## Setup and installation

```bash
pip install sardem
```
This creates the command line executable `sardem`

Alternatively, you can clone to build/install:

```bash
git clone https://github.com/scottstanie/sardem
cd sardem
make
```
which will run `pip install --upgrade .` and create the command line script.


If you use `virtualenv`
```bash
# Optional for using virtualenv
virtualenv ~/envs/sardem && source ~/envs/sardem/bin/activate  # Or wherever you store your virtual envs
# Or if you have virtualenv wrapper: mkvirtualenv sardem
pip install sardem
```


## Command Line Interface

The full options for the command line tool in `sardem/cli.py` can be found using

```
$ sardem --help
usage: sardem { left_lon top_lat dlon dlat | --geojson GEOJSON | --bbox left bot right top }
                 [-h] [--xrate XRATE=1] [--yrate YRATE=1] [--output OUTPUT=elevation.dem]
                 [--data-source {NASA,AWS,NASA_WATER}]


Stiches SRTM .hgt files to make (upsampled) DEM

    Pick a lat/lon bounding box for a DEM, and it will download
    the necessary SRTM1 tiles, stitch together, then upsample.

    Usage Examples:
        sardem --bbox -156 18.8 -154.7 20.3  # bounding box: left  bottom  right top
        sardem -156.0 20.2 1 2 --xrate 2 --yrate 2  # Makes a box 1 degree wide, 2 deg high
        sardem --geojson dem_area.geojson -x 11 -y 3
        sardem -156.0 20.2 0.5 0.5 -r 10 --data-source NASA_WATER -o my_watermask.wbd # Water mask

    Default out is elevation.dem for the final upsampled DEM.
    Also creates elevation.dem.rsc with start lat/lon, stride, and other info.

positional arguments:
  left_lon              Left (western) most longitude of DEM box (degrees, west=negative)
  top_lat               Top (northern) most latitude of DEM box (degrees)
  dlon                  Width of DEM box (degrees)
  dlat                  Height of DEM box (degrees)

optional arguments:
  -h, --help            show this help message and exit
  --bbox left bottom right top
                        Bounding box of area of interest  (e.g. --bbox -106.1 30.1 -103.1 33.1 ).
  --geojson GEOJSON, -g GEOJSON
                        Alternate to corner/dlon/dlat box specification:
                        File containing the geojson object for DEM bounds
  --xrate XRATE, -x XRATE
                        Rate in x dir to upsample DEM (default=1, no upsampling)
  --yrate YRATE, -y YRATE
                        Rate in y dir to upsample DEM (default=1, no upsampling)
  --output OUTPUT, -o OUTPUT
                        Name of output dem file (default=elevation.dem for DEM, watermask.wbd for water mask)
  --data-source {NASA,NASA_WATER,AWS}, -d {NASA,NASA_WATER,AWS}
                        Source of SRTM data (default NASA). See README for more.

```

The code used for bilinear interpolation in the upsampling routine is in `cython/upsample.c`, and is wrapped in [cython](http://docs.cython.org/en/latest/) to allow easier installation and ability to call the function from Python.
The installation is handled through `pip install`, or by running `make build`.

Functions for working with digital elevation maps (DEMs) are mostly contained in the `Downloader` and `Stitcher` classes within `sardem/dem.py`.


### NASA SRTM Data access

The default datasource is NASA's SRTM version 3 global 1 degree data.
See https://lpdaac.usgs.gov/dataset_discovery/measures/measures_products_table/srtmgl3s_v003 .
The data is valid outside of artic regions (-60 to 60 degrees latitude), and is zeros over open ocean.

This data requires a username and password from here:
https://urs.earthdata.nasa.gov/users/new

You will be prompted for a username and password when running with NASA data.
It will save into your ~/.netrc file for future use, which means you will not have to enter a username and password any subsequent times.
The entry will look like this:

```
machine urs.earthdata.nasa.gov
    login USERNAME
    password PASSWORD
```

If you want to avoid this entirely, you can [use Mapzen's data hosted on AWS](https://registry.opendata.aws/terrain-tiles/) by specifying
```bash
sardem 156.0 20.0 .5 0.5 --data-source AWS
```

`--data-source NASA` is the default.

Mapzen combines SRTM data with other sources, so the .hgt files will be slightly different (but often not noticeable)

Warning: Mapzen notes that they are discontinuing some services, which is why NASA is the default.
