
# DEM creator

Tool for making Digital Elevation Maps (DEMs) in binary data format (16-bit integers, little endian) for use in Interferometric SAR (InSAR) processing

`sardem` creates a cropped (and possibly upsampled) digital elevation map:

```bash
usage: sardem [-h] [--bbox left bottom right top] [--geojson GEOJSON] [--wkt-file WKT_FILE] [--xrate XRATE] [--yrate YRATE] [--output OUTPUT] [--data-source {NASA,NASA_WATER,COP}] [-isce] [--keep-egm] [--shift-rsc]
              [left_lon] [top_lat] [dlon] [dlat]
```

The default data source, `--data-source NASA`, uses the SRTM 1 arcsecond data. You can also use the newer [Copernicus Digital Surface Model (DSM)](https://registry.opendata.aws/copernicus-dem/). 

**Note** To convert the elevation values to heights about the WGS84 ellipsoid (which is the default), or to use the Copernicus data, GDAL is required. 
For the Copernicus data, the minimum required GDAL version is 3.4.2; version earlier than 3.4.0 seem to hang upon using `gdalwarp` on the global VRT, and <3.4.2 have an internal bug https://github.com/isce-framework/isce2/issues/556 .


See below for installation:

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

### Converting to WGS84 ellipsoidal heights from EGM96/EGM2008 geoid heights

GDAL is required for the conversion, which is most easily installed using `conda` (or `mamba`):

```bash 
conda install -c conda-forge "gdal>=3.4.2"

# or
# conda install -c conda-forge mamba
# mamba install -c conda-forge "gdal>=3.4.2"
```


## Command Line Interface

The full options for the command line tool in `sardem/cli.py` can be found using

```
$ sardem --help
sardem -h
usage: sardem [-h] [--bbox left bottom right top] [--geojson GEOJSON] [--wkt-file WKT_FILE] [--xrate XRATE] [--yrate YRATE] [--output OUTPUT] [--data-source {NASA,NASA_WATER,COP}] [-isce] [--keep-egm] [--shift-rsc]
              [left_lon] [top_lat] [dlon] [dlat]

Stiches SRTM .hgt files to make (upsampled) DEM

    Pick a lat/lon bounding box for a DEM, and it will download
    the necessary SRTM1 tiles, stitch together, then upsample.

    Usage Examples:
        sardem --bbox -156 18.8 -154.7 20.3  # bounding box: left  bottom  right top
        sardem -156.0 20.2 1 2 --xrate 2 --yrate 2  # Makes a box 1 degree wide, 2 deg high
        sardem --bbox -156 18.8 -154.7 20.3 --data-source COP  # Copernicus DEM
        sardem --geojson dem_area.geojson -x 11 -y 3 # Use geojson file to define area
        sardem --bbox -156 18.8 -154.7 20.3 --data-source NASA_WATER -o my_watermask.wbd # Water mask
        sardem --bbox -156 18.8 -154.7 20.3 --data COP -isce  # Generate .isce XML files as well

    Default out is elevation.dem for the final upsampled DEM.
    Also creates elevation.dem.rsc with start lat/lon, stride, and other info.

positional arguments:
  left_lon              Left (western) most longitude of DEM box (degrees, west=negative)
  top_lat               Top (northern) most latitude of DEM box (degrees)
  dlon                  Width of DEM box (degrees)
  dlat                  Height of DEM box (degrees)

options:
  -h, --help            show this help message and exit
  --bbox left bottom right top
                        Bounding box of area of interest  (e.g. --bbox -106.1 30.1 -103.1 33.1 ).
  --geojson GEOJSON, -g GEOJSON
                        Alternate to corner/dlon/dlat box specification:
                        File containing the geojson object for DEM bounds
  --wkt-file WKT_FILE   Alternate to corner/dlon/dlat box specification:
                        File containing the WKT string for DEM bounds
  --xrate XRATE, -x XRATE
                        Rate in x dir to upsample DEM (default=1, no upsampling)
  --yrate YRATE, -y YRATE
                        Rate in y dir to upsample DEM (default=1, no upsampling)
  --output OUTPUT, -o OUTPUT
                        Name of output dem file (default=elevation.dem for DEM, watermask.wbd for water mask)
  --data-source {NASA,NASA_WATER,COP}, -d {NASA,NASA_WATER,COP}
                        Source of DEM data (default NASA). See README for more.
  -isce, --make-isce-xml
                        Make an isce2 XML file for the DEM.
  --keep-egm            Keep the DEM heights as geoid heights above EGM96 or EGM2008. Default is to convert to WGS84 for InSAR processing.
  --shift-rsc           Shift the .rsc file by half a pixel so that X_FIRST and Y_FIRST are at the pixel center (instead of GDAL's convention of the top left edge). Default is GDAL's top-left edge convention.
```

The code used for bilinear interpolation in the upsampling routine is in `cython/upsample.c`, and is wrapped in [cython](http://docs.cython.org/en/latest/) to allow easier installation and ability to call the function from Python.
The installation is handled through `pip install`, or by running `make build`.

Functions for working with digital elevation maps (DEMs) are mostly contained in the `Downloader` and `Stitcher` classes within `sardem/dem.py` and `sardem/download.py`.


### NASA SRTM Data access

The default data source is NASA's Shuttle Radar Topography Mission (SRTM) version 3 global 1 degree data.
See https://lpdaac.usgs.gov/dataset_discovery/measures/measures_products_table/srtmgl3s_v003 .
The data is valid outside of arctic regions (-60 to 60 degrees latitude), and is zeros over open ocean.

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
