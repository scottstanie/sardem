[![Build Status](https://travis-ci.org/scottstanie/sardem.svg?branch=master)](https://travis-ci.org/scottstanie/sardem)
[![Coverage Status](https://coveralls.io/repos/github/scottstanie/sardem/badge.svg?branch=master)](https://coveralls.io/github/scottstanie/sardem?branch=master)

# DEM creator

Tool for making Digital Elevation Maps (DEMs) in Roipac data format (16-bit integers, little endian) for use in Interferometric SAR (InSAR) processing

`createdem` creates a cropped (and possibly upsampled) digital elevation map.

## Setup and installation

```bash
pip install sardem
```
This creates the command line executable `createdem`

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


## Command Line Interface Reference

The full options for the command line tool in `sardem/cli.py` can be found using

```
$ createdem --help
```

#### Examples:

```bash
createdem --geojson data/hawaii.geojson --rate 2 --output elevation.dem
createdem -g data/forrest.geojson -r 5 --output elevation.dem
```

The geojson can be any valid simple Polygon- you can get one easily from http://geojson.io , for example.

The code used for bilinear interpolation in the upsampling routine is in `cython/upsample.c`, and is wrapped in [cython](http://docs.cython.org/en/latest/) to allow easier installation and ability to call the function from Python.
The installation is  handled through `pip install`, or by running `make build`.

Functions for working with digital elevation maps (DEMs) are mostly contained in the `Downloader` and `Stitcher` classes within `sardem/dem.py`.


### NASA SRTM Data access

The default datasource is NASA's SRTM version 3 global 1 degree data.
See https://lpdaac.usgs.gov/dataset_discovery/measures/measures_products_table/srtmgl3s_v003

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
