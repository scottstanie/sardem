
# sardem

A tool for making Digital Elevation Maps (DEMs) in binary data format (16-bit integers, little endian) for use in interferometric synthetic aperture radar (InSAR) processing (e.g. using [isce2](https://github.com/isce-framework/isce2).

The `sardem` command creates a cropped (and possibly upsampled) digital elevation map:

```bash
usage: sardem [-h] [--bbox left bottom right top] [--geojson GEOJSON] [--wkt-file WKT_FILE] [--xrate XRATE] [--yrate YRATE] [--output OUTPUT] [--data-source {NASA,NASA_WATER,COP}] [-isce] [--keep-egm] [--shift-rsc]
              [left_lon] [top_lat] [dlon] [dlat]
```

## Setup and installation

Using conda:
```bash
conda install -c conda-forge sardem
# Or, if mamba is installed, mamba install -c conda-forge sardem
```

Using pip:
```bash
pip install sardem
```
This creates the command line executable `sardem`

Using `uv`:
```bash
uv add sardem
```
You can also run the `sardem` command line tool using `uvx`:
```bash
uvx sardem --help
```

Alternatively, you can clone to build/install:

```bash
git clone https://github.com/scottstanie/sardem
cd sardem
# Install requirements using either pip or conda
# conda install -c conda-forge --file environment.yml
# pip install -r requirements.txt
# the conda environment.yml is more complete, as rasterio is required for some of the functionality
pip install -e .
```
which will run `pip install --upgrade .` and create the command line script.

## Data sources
The default data source, `--data-source NASA`, uses the SRTM 1 arcsecond data. You can also use the newer [Copernicus Digital Surface Model (DSM)](https://registry.opendata.aws/copernicus-dem/). 
To see a comparison of the two, see the [srtm_copernicus_comparison](notebooks/srtm_copernicus_comparison.ipynb) notebook.

**Note:** To convert the elevation values to heights about the WGS84 ellipsoid (which is the default), or to use the Copernicus data, **rasterio is required**.
For the Copernicus data, rasterio >= 1.0.0 is required for coordinate transformations and data warping.

## Bounding box convention

`sardem` uses the gdal convention ("pixel is area") where `--bbox` points to the *edges* of the [left, bottom, right, top] pixels.
I.e. (left, bottom) refers to the lower left corner of the lower left pixel.

## Command Line Interface

The full options for the command line tool in `sardem/cli.py` can be found using

```
$ sardem -h
usage: sardem [-h] [--bbox left bottom right top] [--geojson GEOJSON] [--wkt-file WKT_FILE] [--xrate XRATE] [--yrate YRATE] [--output OUTPUT] [--data-source {NASA,NASA_WATER,COP}] [-isce] [--keep-egm] [--shift-rsc]
              [--cache-dir CACHE_DIR]
              [left_lon] [top_lat] [dlon] [dlat]

Stiches SRTM .hgt files to make (upsampled) DEM

    Pick a lat/lon bounding box for a DEM, and it will download
    the necessary SRTM1 tiles, stitch together, then upsample.

    The `--bbox` convention points to the *edges* of the [left, bottom, right, top]
    pixels, following the "pixel is area" convention as used in rasterio.
    I.e. (left, bottom) refers to the lower left corner of the lower left pixel.

    Usage Examples:
        sardem --bbox -156 18.8 -154.7 20.3  # bounding box: [left  bottom  right top]
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
                        --bbox points to the *edges* of the pixels,
                         following the 'pixel is area' convention as used in gdal.
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
  --cache-dir CACHE_DIR
                        Location to save downloaded files (Default = /Users/staniewi/.cache/sardem)
```


## NASA SRTM Data access

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
