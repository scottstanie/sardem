
# sardem

A tool for making Digital Elevation Maps (DEMs) in binary data format (16-bit integers, little endian) for use in interferometric synthetic aperture radar (InSAR) processing (e.g. using [isce2](https://github.com/isce-framework/isce2).

The `sardem` command creates a cropped (and possibly upsampled) digital elevation map:

```bash
usage: sardem [-h] [--bbox left bottom right top] [--geojson GEOJSON] [--wkt-file WKT_FILE] [--xrate XRATE] [--yrate YRATE] [--output OUTPUT] [--data-source {NASA,NASA_WATER,COP,3DEP,NISAR}] [-isce] [--keep-egm] [--shift-rsc]
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

Alternatively, you can clone to build/install:

```bash
git clone https://github.com/scottstanie/sardem
cd sardem
# Install requirements using either pip or conda
# conda install -c conda-forge --file environment.yml
# pip install -r requirements.txt
# the conda environment.yml is more complete, as GDAL is required for some of the functionality
pip install -e .
```
which will run `pip install --upgrade .` and create the command line script.


## Data sources
The default data source is `--data-source COP`, which uses the newer [Copernicus Digital Surface Model (DSM)](https://registry.opendata.aws/copernicus-dem/). You can also use `--data-source NASA` for the SRTM 1 arcsecond data, `--data-source 3DEP` for the USGS 3DEP lidar-derived DEM (see below), or `--data-source NISAR` for the NISAR DEM (see below).
The [srtm_copernicus_comparison](notebooks/srtm_copernicus_comparison.ipynb) notebook has a comparison of the COP and SRTM 1 data.

**Note:** To convert the elevation values to heights about the WGS84 ellipsoid (which is the default), or to use the Copernicus data, **GDAL is required**. 
For the Copernicus data, the minimum required GDAL version is 3.4.2; versions earlier than 3.4.0 seem to hang upon using `gdalwarp` on the global VRT, and <3.4.2 have an internal bug https://github.com/isce-framework/isce2/issues/556 .


## Bounding box convention

`sardem` uses the gdal convention ("pixel is area") where `--bbox` points to the *edges* of the [left, bottom, right, top] pixels.
I.e. (left, bottom) refers to the lower left corner of the lower left pixel.

### Converting to WGS84 ellipsoidal heights from EGM96/EGM2008 geoid heights

GDAL is required for the conversion, which is installed when using `conda install -c conda-forge sardem`.
If you already are using an existing environment, make sure that the GDAL version is >=3.4.2.

```bash
conda install -c conda-forge "gdal>=3.4.2"

# or
# conda install -c conda-forge mamba
# mamba install -c conda-forge "gdal>=3.4.2"
```

## Command Line Interface

The full options for the command line tool in `sardem/cli.py` can be found using

```bash
sardem --help
```

```bash
usage: sardem [-h] [--bbox left bottom right top] [--geojson GEOJSON] [--wkt-file WKT_FILE] [--xrate XRATE] [--yrate YRATE] [--output OUTPUT] [--data-source {NASA,NASA_WATER,COP,3DEP,NISAR}] [-isce] [--keep-egm]
              [--shift-rsc] [--cache-dir CACHE_DIR] [--output-format {ENVI,GTiff,ROI_PAC}] [--output-type {int16,float32,uint8}]
              [left_lon] [top_lat] [dlon] [dlat]

Download and stitch DEM data for local InSAR processing.

    Pick a lat/lon bounding box for a DEM, and it will download
    the necessary SRTM1 tiles, stitch together, then upsample.

    The `--bbox` convention points to the *edges* of the [left, bottom, right, top]
    pixels, following the "pixel is area" convention as used in gdal.
    I.e. (left, bottom) refers to the lower left corner of the lower left pixel.

    Usage Examples:
        sardem --bbox -156 18.8 -154.7 20.3  # bounding box: [left  bottom  right top]
        sardem -156.0 20.2 1 2 --xrate 2 --yrate 2  # Makes a box 1 degree wide, 2 deg high
        sardem --bbox -156 18.8 -154.7 20.3 --data-source COP  # Copernicus DEM
        sardem --geojson dem_area.geojson -x 11 -y 3 # Use geojson file to define area
        sardem --bbox -156 18.8 -154.7 20.3 --data-source NASA_WATER -o my_watermask.wbd # Water mask
        sardem --bbox -104 30 -103 31 --data-source 3DEP  # USGS 3DEP lidar DEM (US only)
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
  --data-source {NASA,NASA_WATER,COP,3DEP,NISAR}, -d {NASA,NASA_WATER,COP,3DEP,NISAR}
                        Source of DEM data (default COP). See README for more.
  -isce, --make-isce-xml
                        Make an isce2 XML file for the DEM.
  --keep-egm            Keep the DEM heights as geoid heights above EGM96 or EGM2008. Default is to convert to WGS84 for InSAR processing.
  --shift-rsc           Shift the .rsc file by half a pixel so that X_FIRST and Y_FIRST are at the pixel center (instead of GDAL's convention of the top left edge). Default is GDAL's top-left edge convention.
  --cache-dir CACHE_DIR
                        Location to save downloaded files (Default = /Users/staniewi/.cache/sardem)
  --output-format {ENVI,GTiff,ROI_PAC}, -of {ENVI,GTiff,ROI_PAC}
                        Output format (for copernicus DEM option, default GTiff).
  --output-type {int16,float32,uint8}, -ot {int16,float32,uint8}
                        Output data type (default float32).
```

## NASA SRTM Data access

NASA's Shuttle Radar Topography Mission (SRTM) version 3 global 1 degree data is available with `--data-source NASA`.
This was the original default data source prior to version 0.12.0, but can still be selected explicitly.
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

## NISAR DEM

The NISAR DEM (`--data-source NISAR`) is a modified Copernicus DEM prepared by JPL for the NISAR mission. The DEM has been converted to WGS84 ellipsoidal heights, and is available as a hierarchical VRT at `https://nisar.asf.earthdatacloud.nasa.gov/NISAR/DEM/v1.2/EPSG4326/EPSG4326.vrt` for mid-latitudes, `EPSG3031.vrt` for the south pole, `EPSG3413.vrt` for the north pole.

The NISAR DEM requires NASA Earthdata credentials like the SRTM data.

### Usage

```bash
sardem --bbox -104 30 -103 31 --data-source NISAR
```

## USGS 3DEP Lidar DEM

The USGS 3D Elevation Program (3DEP) (`--data-source 3DEP`) provides high-resolution lidar-derived elevation data for the United States. The data is accessed via the USGS National Map ImageServer and is available at 1/3 arc-second (~10m) resolution for most of CONUS, with 1-meter resolution in many areas.

Unlike the global Copernicus DEM, 3DEP coverage is limited to the US, but offers higher accuracy in areas with lidar coverage. The [cop_vs_3dep_comparison](notebooks/cop_vs_3dep_comparison.ipynb) notebook has a comparison of the Copernicus and 3DEP data.

No authentication is required.

### Usage

```bash
sardem --bbox -104 30 -103 31 --data-source 3DEP
```

## USGS 3DEP 1-Meter Lidar DEM

The `--data-source 3DEP_1M` option provides access to 1-meter resolution lidar-derived DEMs from the USGS 3DEP program. Tiles are discovered via the [TNM Access API](https://tnmaccess.nationalmap.gov/api/v1/products) and fetched as Cloud Optimized GeoTIFFs (COGs) from S3.

- **US coverage only** — not all areas have 1m lidar data. If no tiles are found, the command will raise an error.
- **No authentication required.**
- Output resolution matches the native ~1m resolution of the source tiles.
- `--xrate`/`--yrate` upsampling is not supported (data is already high-resolution).

### Usage

```bash
sardem --bbox -118.4 33.7 -118.3 33.8 --data-source 3DEP_1M
```

## Citations and Acknowledgments

### Copernicus DEM

When using the Copernicus DEM data (default `--data-source COP`), please cite the dataset using the following DOI:

**https://doi.org/10.5270/ESA-c5d3d65**

And include the following attribution notice:

> © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved

For more information about the Copernicus DEM, visit: https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM

### USGS 3DEP

When using the 3DEP data (`--data-source 3DEP`), please cite:

> U.S. Geological Survey, 2019, USGS 3D Elevation Program Digital Elevation Model, accessed [date] at https://www.usgs.gov/3d-elevation-program

For more details on citing USGS data, see: https://www.usgs.gov/faqs/how-should-i-cite-datasets-and-services-national-map

### NISAR DEM

When using the NISAR DEM (`--data-source NISAR`), [you can cite the data as described here.](https://www.earthdata.nasa.gov/data/catalog/asf-nisar-dem-1#toc-citation)
