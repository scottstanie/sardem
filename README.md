[![Build Status](https://travis-ci.org/scottstanie/sardem.svg?branch=master)](https://travis-ci.org/scottstanie/sardem)
[![Coverage Status](https://coveralls.io/repos/github/scottstanie/sardem/badge.svg?branch=master)](https://coveralls.io/github/scottstanie/sardem?branch=master)

# DEM creator

Tool for making Digital Elevation Maps (DEMs) in Roipac data format (16-bit integers, little endian) for using in and Interferometric SAR (InSAR) processing

`sardem` creates a cropped (and possibly upsampled) digital elevation map.

## Setup and installation

```bash
# Optional for using virtualenv
virtualenv ~/envs/sardem && source ~/envs/sardem/bin/activate  # Or wherever you store your virtual envs
# Or if you have virtualenv wrapper: mkvirtualenv sardem
pip install sardem
```

This will put the executable `sardem` on your path with several commands available to use:

virtualenv is optional but recommended.

## Command Line Interface Reference

The command line tool in `sardem/cli.py` was made using the [click](https://pocco-click.readthedocs.io/en/latest/) library.

```
$ sardem --help
```



```bash
sardem --geojson data/hawaii.geojson --rate 2 --output elevation.dem
sardem -g data/forrest.geojson -r 5 --output elevation.dem
```

The geojson can be any valid simple Polygon- you can get one easily from http://geojson.io , for example.

Functions for working with digital elevation maps (DEMs) are mostly contained in the `Downloader` and `Stitcher` classes within `sardem/dem.py`.

Once you have made this, if you want to get a quick look in python, the script `sardem view` opens the file and plots with matplotlib.

If you have multiple, you can plot them using matplotlib for a quick look.

```bash
sardem view elevation1.dem elevation2.dem
```

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
sardem -g data/hawaii.geojson --data-source AWS
```

`--data-source NASA` is the default.

Mapzen combines SRTM data with other sources, so the .hgt files will be slightly different.
They also list that they are discontinuing some services, which is why NASA is the default.


#### geojson.py

Simple functions for getting handling geojson inputs:


```python
from insar.geojson import read_json, bounding_box, print_coordinates
json_dict = read_json(input_string)
```

Running the module as a script will give you both the bounding box, and the comma-joined lon,lat pairs of the polygon:

```
$ cat data/hawaii.geojson | python insar/geojson.py 
-155.67626953125,19.077692991868297,-154.77264404296875,19.077692991868297,-154.77264404296875,19.575317892869453,-155.67626953125,19.575317892869453,-155.67626953125,19.077692991868297
-155.67626953125 19.077692991868297 -154.77264404296875 19.575317892869453

$ cat data/hawaii.geojson 
{
  "type": "Polygon",
  "coordinates": [
    [
		  [
		    -155.67626953125,
		    19.077692991868297
		  ],
		  [
		    -154.77264404296875,
		    19.077692991868297
		  ],
		  [
		    -154.77264404296875,
		    19.575317892869453
		  ],
		  [
		    -155.67626953125,
		    19.575317892869453
		  ],
		  [
		    -155.67626953125,
		    19.077692991868297
		  ]
    ]
  ]
}
```
