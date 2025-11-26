"""Digital Elevation Map (DEM) downloading, stitching, upsampling.

Module contains utilities for downloading all necessary .hgt files
for a lon/lat rectangle, stiches them into one DEM, and creates a
.dem.rsc file for SAR processing.

Note: NASA Earthdata requires a signup: https://urs.earthdata.nasa.gov/users/new
Once you have signed up, to avoid a username password prompt create/add to a .netrc
file in your home directory:

machine urs.earthdata.nasa.gov
    login yourusername
    password yourpassword

This will be handled if you run download_all by handle_credentials.
You can choose to save you username in a netrc file for future use

NASA MEaSUREs SRTM Version 3 (SRTMGL1) houses the data
    See https://lpdaac.usgs.gov/dataset_discovery/measures/measures_products_table/srtmgl3s_v003
    more info on SRTMGL1: https://cmr.earthdata.nasa.gov/search/concepts/C1000000240-LPDAAC_ECS.html

Example url: "https://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/2000.02.11/N06W001.SRTMGL1.hgt.zip"
Example Water body url:
    https://e4ftl01.cr.usgs.gov/MEASURES/SRTMSWBD.003/2000.02.11/N05W060.SRTMSWBD.raw.zip


Example .dem.rsc (for N19W156.hgt and N19W155.hgt stitched horizontally):
        WIDTH         7201
        FILE_LENGTH   3601
        X_FIRST       -156.0
        Y_FIRST       20.0
        X_STEP        0.000277777777
        Y_STEP        -0.000277777777
        X_UNIT        degrees
        Y_UNIT        degrees
        Z_OFFSET      0
        Z_SCALE       1
        PROJECTION    LL
"""

import collections
import logging
import os

import numpy as np

from sardem import conversions, loading, upsample, utils
from sardem.constants import NUM_PIXELS_SRTM1
from sardem.download import Downloader, Tile

RSC_KEYS = [
    "WIDTH",
    "FILE_LENGTH",
    "X_FIRST",
    "Y_FIRST",
    "X_STEP",
    "Y_STEP",
    "X_UNIT",
    "Y_UNIT",
    "Z_OFFSET",
    "Z_SCALE",
    "PROJECTION",
]
WARN_LIMIT = 20000 * 20000

logger = logging.getLogger("sardem")
utils.set_logger_handler(logger)


class Stitcher:
    """Class to combine separate .hgt tiles into one .dem file.

    Attributes:
        tile_file_list (list[str]) names of .hgt tiles
            E.g.: ['N19W156', 'N19W155']
        filenames (list[str]): locations of downloaded files
        num_pixels (int): size of the squares of the .hgt files
            Assumes 3601 for SRTM1 (SRTM3, 3 degree not implemented/tested)

    """

    def __init__(
        self,
        tile_names,
        filenames=None,
        data_source="NASA",
        num_pixels=NUM_PIXELS_SRTM1,
    ):
        """List should come from Tile.srtm1_tile_names()."""
        if filenames is None:
            filenames = []
        self.tile_file_list = list(tile_names)
        self.filenames = filenames
        # Assuming SRTMGL1: 3601 x 3601 squares
        self.num_pixels = num_pixels
        self.data_source = data_source
        self.dtype = np.uint8 if data_source == "NASA_WATER" else np.int16

    @property
    def shape(self):
        """Number of rows/columns in pixels for stitched .dem.

        Uses the blockshape property, along with num_pixels property
        Returned as a tuple

        Examples:
            >>> s = Stitcher(['N19W156', 'N19W155'])
            >>> s.shape
            (3601, 7201)

        """
        blockrows, blockcols = self.blockshape
        return (self._total_length(blockrows), self._total_length(blockcols))

    def _total_length(self, numblocks):
        """Computes the total number of pixels in one dem from numblocks."""
        return numblocks * (self.num_pixels - 1) + 1

    @property
    def blockshape(self):
        """Number of tile in rows cols."""
        return self._compute_shape()

    def _compute_shape(self):
        """Takes the tile list and computes the number of tile rows and tile cols.

        Figures out how many lons wide and lats tall the tile array spans
        Note: This is not the total number of pixels, which can be found in .shape

        Examples:
            >>> s = Stitcher(['N19W156', 'N19W155'])
            >>> s._compute_shape()
            (1, 2)

        """
        lon_lat_tups = [self.start_lon_lat(t) for t in self.tile_file_list]
        # Unique each lat/lon: length of lats = num rows, lons = cols
        num_lons = len({tup[0] for tup in lon_lat_tups})
        num_lats = len({tup[1] for tup in lon_lat_tups})
        return (num_lats, num_lons)

    @staticmethod
    def start_lon_lat(tile_name):
        """Takes an SRTM1 data tile_name and returns the first (lon, lat) point.

        The reverse of Tile.srtm1_tile_names()

        Used for .rsc file formation to make X_FIRST and Y_FIRST
        The names of individual data tiles refer to the longitude
        and latitude of the lower-left (southwest) corner of the tile.

        Example: N19W156.hgt refers to `bottom left` corner, while data starts
        at top left. This would return (X_FIRST, Y_FIRST) = (-156.0, 20.0)

        Args:
            tile_name (str): name of .hgt file for SRTM1 tile

        Returns:
            tuple (float, float) of first (lon, lat) point in .hgt file

        Raises:
            ValueError: if regex match fails on tile_name

        Examples:
            >>> Stitcher.start_lon_lat('N19W156')
            (-156.0, 20.0)
            >>> Stitcher.start_lon_lat('S5E6')
            (6.0, -4.0)

        """
        lat_str, lat, lon_str, lon = Tile.get_tile_parts(tile_name)

        # lat gets added to or subtracted
        top_lat = float(lat) + 1 if lat_str == "N" else -float(lat) + 1

        # lon is negative if we're in western hemisphere
        # No +1 addition needed to lon: bottom left and top left are same
        left_lon = -1 * float(lon) if lon_str == "W" else float(lon)
        return (left_lon, top_lat)

    def _create_file_array(self):
        """Finds filenames and reshapes into numpy.array matching DEM shape.

        Examples:
            >>> s = Stitcher(['N19W156', 'N19W155', 'N18W156', 'N18W155'])
            >>> print(s._create_file_array())
            [['N19W156' 'N19W155']
             ['N18W156' 'N18W155']]

        """
        nrows, ncols = self.blockshape
        return np.array(self.tile_file_list).reshape((nrows, ncols))

    def _load_tile(self, tile_name):
        """Loads the tile, or returns a square of zeros if missing."""
        idx = self.tile_file_list.index(tile_name)
        filename = self.filenames[idx]
        if filename and os.path.exists(filename):
            if self.data_source == "NASA_WATER":
                return loading.load_watermask(filename)
            else:
                return loading.load_elevation(filename)
        else:
            return np.zeros((NUM_PIXELS_SRTM1, NUM_PIXELS_SRTM1), dtype=self.dtype)

    def load_and_stitch(self):
        """Function to load combine .hgt tiles.

        Uses hstack first on rows, then vstacks rows together.
        Also handles the deleting of overlapped rows/columns of SRTM tiles
        TODO: break this up to more testable chunks

        Returns:
            ndarray: the stitched .hgt tiles in 2D np.array

        """
        row_list = []
        # ncols in the number of .hgt blocks wide
        _, ncols = self.blockshape
        tile_grid = self._create_file_array()
        for idx, row in enumerate(tile_grid):
            cur_row = np.hstack([self._load_tile(tile_name) for tile_name in row])
            # Delete columns: 3601*[1, 2,... not-including last column]
            delete_cols = self.num_pixels * np.arange(1, ncols)
            cur_row = np.delete(cur_row, delete_cols, axis=1)
            if idx > 0:
                # For all except first block-row, delete repeated first row of data
                cur_row = np.delete(cur_row, 0, axis=0)
            row_list.append(cur_row)
        return np.vstack(row_list)

    def _find_step_sizes(self, ndigits=12):
        """Calculates the step size for the dem.rsc.

        Note: assuming same step size in x and y direction

        Args:
            ndigits (int) default=12 because that's what was given

        Returns:
            (float, float): x_step, y_step

        Example:
            >>> s = Stitcher(['N19W156', 'N19W155'])
            >>> print(s._find_step_sizes())
            (0.000277777777, -0.000277777777)

        """
        step_size = utils.floor_float(1 / (self.num_pixels - 1), ndigits)
        return (step_size, -1 * step_size)

    def create_dem_rsc(self):
        """Takes a list of the SRTM1 tile names and outputs .dem.rsc file values.

        See module docstring for example .dem.rsc file.

        Note: the X_FIRST and Y_FIRST are set to the top left *center*.
            Use utils.shift_rsc_dict(to_gdal=True) to shift to top left edge

        Returns:
            OrderedDict: key/value pairs in order to write to a .dem.rsc file

        Examples:
            >>> s = Stitcher(['N19W156', 'N19W155'])
            >>> s.create_dem_rsc()
            OrderedDict([('WIDTH', 7201), ('FILE_LENGTH', 3601), ('X_FIRST', -156.0), \
('Y_FIRST', 20.0), ('X_STEP', 0.000277777777), ('Y_STEP', -0.000277777777), ('X_UNIT', 'degrees'), \
('Y_UNIT', 'degrees'), ('Z_OFFSET', 0), ('Z_SCALE', 1), ('PROJECTION', 'LL')])

        """
        # Use an OrderedDict for the key/value pairs so writing to file easy
        rsc_dict = collections.OrderedDict.fromkeys(RSC_KEYS)
        rsc_dict.update(
            {
                "X_UNIT": "degrees",
                "Y_UNIT": "degrees",
                "Z_OFFSET": 0,
                "Z_SCALE": 1,
                "PROJECTION": "LL",
            }
        )

        # Remove paths from tile filenames, if they exist
        x_first, y_first = self.start_lon_lat(self.tile_file_list[0])
        nrows, ncols = self.shape
        rsc_dict.update({"WIDTH": ncols, "FILE_LENGTH": nrows})
        rsc_dict.update({"X_FIRST": x_first, "Y_FIRST": y_first})

        x_step, y_step = self._find_step_sizes()
        rsc_dict.update({"X_STEP": x_step, "Y_STEP": y_step})
        return rsc_dict


def _float_is_on_bounds(x):
    return int(x) == x


def main(
    output_name=None,
    bbox=None,
    geojson=None,
    wkt_file=None,
    data_source=None,
    xrate=1,
    yrate=1,
    make_isce_xml=False,
    keep_egm=False,
    shift_rsc=False,
    cache_dir=None,
    output_type="float32",
    output_format="GTiff",
):
    """Function for entry point to create a DEM with `sardem`.

    Args:
        output_name (str): name of file to save final DEM (default = elevation.dem)
        bbox (tuple[float]): (left, bot, right, top)
            Longitude/latitude desired bounding box for the DEM
        geojson (dict): geojson object outlining DEM (alternative to bbox)
        wkt_file (str): path to .wkt file outlining DEM (alternative to bbox)
        data_source (str): 'NASA' or 'AWS', where to download .hgt tiles from
        xrate (int): x-rate (columns) to upsample DEM (positive int)
        yrate (int): y-rate (rows) to upsample DEM (positive int)
        make_isce_xml (bool): whether to make an isce2-compatible XML file
        keep_egm (bool): Don't convert the DEM heights from geoid heights
            above EGM96 or EGM2008 to heights above WGS84 ellipsoid
            (default = False: do the conversion)
        shift_rsc (bool): Shift the .dem.rsc file down/right so that the
            X_FIRST and Y_FIRST values represent the pixel *center* (instead of
            GDAL's convention of pixel edge). Default = False.
        cache_dir (str): directory to cache downloaded tiles
        output_type (str): output type for DEM (default = int16)
        output_format (str): output format for copernicus DEM (default = ENVI)

    """
    if bbox is None:
        if geojson:
            bbox = utils.bounding_box(geojson=geojson)
        elif wkt_file:
            bbox = utils.get_wkt_bbox(wkt_file)

    if bbox is None:
        msg = "Must provide either bbox or geojson or wkt_file"
        raise ValueError(msg)
    logger.info("Bounds: %s", " ".join(str(b) for b in bbox))

    # if all(_float_is_on_bounds(b) for b in bbox):
    #     logger.info("Shifting bbox to nearest tile bounds")
    #     bbox = utils.shift_integer_bbox(bbox)
    #     logger.info("New edge bounds: %s", " ".join(str(b) for b in bbox))
    # Now we're assuming that `bbox` refers to the edges of the desired bounding box

    # Print a warning if they're possibly requesting too-large a box by mistake
    outrows, outcols = utils.get_output_size(bbox, xrate, yrate)
    if outrows * outcols > WARN_LIMIT:
        logger.warning(f"Caution: Output size is {outrows} x {outcols} pixels.")
        logger.warning("Are the bounds correct (left, bottom, right, top)?")

    # For copernicus, use GDAL to warp from the VRT
    if data_source == "COP":
        utils._gdal_installed_correctly()
        from sardem import cop_dem

        cop_dem.download_and_stitch(
            output_name,
            bbox,
            keep_egm=keep_egm,
            xrate=xrate,
            yrate=yrate,
            output_format=output_format,
            output_type=output_type,
        )
        if make_isce_xml:
            logger.info("Creating ISCE2 XML file")
            utils.gdal2isce_xml(output_name, keep_egm=keep_egm)
        return

    # If using SRTM, download tiles manually and stitch
    if output_format != "ENVI":
        logger.warning(
            "NASA data source only supports ENVI format. Ignoring output_format=%s",
            output_format,
        )

    tile_names = list(Tile(*bbox).srtm1_tile_names())

    d = Downloader(tile_names, data_source=data_source, cache_dir=cache_dir)
    local_filenames = d.download_all()

    s = Stitcher(tile_names, filenames=local_filenames, data_source=data_source)
    stitched_dem = s.load_and_stitch()

    # Now create corresponding rsc file for all the tiles
    rsc_dict_tiles = s.create_dem_rsc()

    logger.info("Cropping stitched DEM to boundaries")
    stitched_dem = upsample.resample(stitched_dem, rsc_dict_tiles, bbox)
    rsc_dict = rsc_dict_tiles.copy()
    rsc_dict["X_FIRST"] = bbox[0]
    rsc_dict["Y_FIRST"] = bbox[3]
    rsc_dict["FILE_LENGTH"] = stitched_dem.shape[0]
    rsc_dict["WIDTH"] = stitched_dem.shape[1]

    rsc_filename = output_name + ".rsc"

    # Upsampling:
    dtype = np.dtype(output_type.lower())
    if xrate == 1 and yrate == 1:
        logger.info("Rate = 1: No upsampling to do")
        logger.info("Writing DEM to %s", output_name)
        stitched_dem.astype(dtype).tofile(output_name)
        logger.info("Writing .dem.rsc file to %s", rsc_filename)
        with open(rsc_filename, "w") as f:
            f.write(loading.format_dem_rsc(rsc_dict))
    else:
        logger.info(f"Upsampling by ({xrate}, {yrate}) in (x, y) directions")
        # dem_filename_small = output_name.replace(".dem", "_small.dem")
        # rsc_filename_small = rsc_filename.replace(".dem.rsc", "_small.dem.rsc")
        dem_filename_small = "small_" + output_name
        rsc_filename_small = "small_" + rsc_filename

        logger.info("Writing non-upsampled dem temporarily to %s", dem_filename_small)
        stitched_dem.astype(dtype).tofile(dem_filename_small)
        logger.info(
            "Writing non-upsampled dem.rsc temporarily to %s", rsc_filename_small
        )
        with open(rsc_filename_small, "w") as f:
            f.write(loading.format_dem_rsc(rsc_dict))

        # Redo a new .rsc file for it
        logger.info("Writing new upsampled dem.rsc to %s", rsc_filename)
        with open(rsc_filename, "w") as f:
            upsampled_rsc = upsample.upsample_dem_rsc(
                xrate=xrate, yrate=yrate, rsc_dict=rsc_dict
            )
            f.write(upsampled_rsc)

        # Now upsample using with GDAL or python
        if utils._gdal_installed_correctly():
            logger.info("Using GDAL Translate for upsampling")
            upsample.upsample_with_gdal(
                dem_filename_small,
                output_name,
                method="bilinear",  # make this an option?
                xrate=xrate,
                yrate=yrate,
            )
        else:
            # Figure out size of row blocks to keep memory under 100 MB
            nrows, ncols = stitched_dem.shape
            block_rows = int(np.round(10e6 / ncols / 2, -2))  # round to 100s
            logger.info(f"Upsampling by blocks of {block_rows} rows")
            upsample.upsample_by_blocks(
                dem_filename_small,
                output_name,
                (nrows, ncols),
                block_rows=block_rows,
                dtype=dtype,
                xrate=xrate,
                yrate=yrate,
            )
        # Clean up the _small versions of dem and dem.rsc
        logger.info("Cleaning up %s and %s", dem_filename_small, rsc_filename_small)
        os.remove(dem_filename_small)
        os.remove(rsc_filename_small)

    if make_isce_xml:
        logger.info("Creating ISCE2 XML file")
        utils.gdal2isce_xml(output_name, keep_egm=keep_egm)

    if data_source == "NASA_WATER":
        logger.info("Water mask requires no geoid correction.")
        # Overwrite with smaller dtype for water mask
        upsampled_dict = loading.load_dem_rsc(rsc_filename)
        rows, cols = upsampled_dict["file_length"], upsampled_dict["width"]
        mask = np.fromfile(output_name, dtype=dtype).reshape((rows, cols))
        mask.astype(bool).tofile(output_name)
    elif keep_egm:
        logger.info("Keeping DEM as EGM96 geoid heights")
    else:
        logger.info("Correcting DEM to heights above WGS84 ellipsoid")
        conversions.convert_dem_to_wgs84(output_name, geoid="egm96")

    # If the user wants the .rsc file to point to pixel center:
    if shift_rsc:
        utils.shift_rsc_file(rsc_filename, to_gdal=False)
