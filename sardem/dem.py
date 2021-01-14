"""Digital Elevation Map (DEM) downloading/stitching/upsampling

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

Example url: "http://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/2000.02.11/N06W001.SRTMGL1.hgt.zip"

Other option is to download from Mapzen's tile set on AWS:

    https://mapzen.com/documentation/terrain-tiles/formats/#skadi

These do not require a username and password.
They use the SRTM dataset within the US, but combine other sources to produce
1 arcsecond (30 m) resolution world wide.
    Example url: https://s3.amazonaws.com/elevation-tiles-prod/skadi/N19/N19W156.hgt

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
from __future__ import division, print_function
import collections
import logging
import getpass
import math
from multiprocessing.pool import ThreadPool
import netrc
import os
import re
import subprocess
import numpy as np
import requests
from sardem import utils, loading, upsample_cy

try:
    input = raw_input  # Check for python 2
except NameError:
    pass

NUM_PIXELS = 3601  # For SRTM1
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

logger = logging.getLogger("sardem")
utils.set_logger_handler(logger)


def _get_username_pass():
    """If netrc is not set up, get command line username and password"""
    print("====================================================================")
    print("Please enter NASA Earthdata credentials to download NASA hosted STRM.")
    print("See https://urs.earthdata.nasa.gov/users/new for signup info.")
    print("Or choose data_source=AWS for Mapzen tiles.")
    print("===========================================")
    username = input("Username: ")
    password = getpass.getpass(prompt="Password (will not be displayed): ")
    save_to_netrc = input(
        "Would you like to save these to ~/.netrc (machine={}) for future use (y/n)?  ".format(
            Downloader.NASAHOST
        )
    )
    return username, password, save_to_netrc.lower().startswith("y")


class Netrc(netrc.netrc):
    """Handles saving of .netrc file, fixes bug in stdlib older versions

    https://bugs.python.org/issue30806
    Uses ideas from tinynetrc
    """

    def format(self):
        """Dump the class data in the format of a .netrc file.

        Fixes issue of including single quotes for username and password"""
        rep = ""
        for host in self.hosts.keys():
            attrs = self.hosts[host]
            rep += "machine {host}\n\tlogin {attrs[0]}\n".format(host=host, attrs=attrs)
            if attrs[1]:
                rep += "\taccount {attrs[1]}\n".format(attrs=attrs)
            rep += "\tpassword {attrs[2]}\n".format(attrs=attrs)
        for macro in self.macros.keys():
            rep += "macdef {macro}\n".format(macro=macro)
            for line in self.macros[macro]:
                rep += line
            rep += "\n"

        return rep

    def __repr__(self):
        return self.format()

    def __str__(self):
        return repr(self)


class Tile:
    """class to handle tile name formation and parsing"""

    def __init__(self, left, bottom, right, top):
        self.bounds = (left, bottom, right, top)

    @staticmethod
    def get_tile_parts(tile_name):
        """Parses the lat/lon information of a .hgt tile

        Validates that the string is an actual tile name

        Args:
            tile_name

        Returns:
            tuple: lat_str (either 'N' for north, 'S' for south), lat: int latitude from 0 to 90
                lon_str (either 'W' for west, 'E' for east), lon: int longitude from 0 to 180

        Raises:
            ValueError: if regex match fails on tile_name

        Examples:
            >>> Tile.get_tile_parts('N19W156.hgt')
            ('N', 19, 'W', 156)
            >>> Tile.get_tile_parts('S5E6.hgt')
            ('S', 5, 'E', 6)
            >>> Tile.get_tile_parts('Notrealname.hgt')
            Traceback (most recent call last):
               ...
            ValueError: Invalid SRTM1 tile name: Notrealname.hgt, must match \
([NS])(\d{1,2})([EW])(\d{1,3}).hgt
        """
        lon_lat_regex = r"([NS])(\d{1,2})([EW])(\d{1,3}).hgt"
        match = re.match(lon_lat_regex, tile_name)
        if not match:
            raise ValueError(
                "Invalid SRTM1 tile name: {}, must match {}".format(
                    tile_name, lon_lat_regex
                )
            )

        lat_str, lat, lon_str, lon = match.groups()
        return lat_str, int(lat), lon_str, int(lon)

    @staticmethod
    def srtm1_tile_corner(lon, lat):
        """Integers for the bottom right corner of requested lon/lat

        Examples:
            >>> Tile.srtm1_tile_corner(3.5, 5.6)
            (3, 5)
            >>> Tile.srtm1_tile_corner(-3.5, -5.6)
            (-4, -6)
        """
        return int(math.floor(lon)), int(math.floor(lat))

    def srtm1_tile_names(self):
        """Iterator over all tiles needed to cover the requested bounds

        Args:
            None: bounds provided to Tile __init__()

        Yields:
            str: .hgt tile names that cover all of bounding box
                yielded in order of top left to bottom right

        Examples:
            >>> bounds = (-155.7, 19.1, -154.7, 19.7)
            >>> d = Tile(*bounds)
            >>> from types import GeneratorType  # To check the type
            >>> type(d.srtm1_tile_names()) == GeneratorType
            True
            >>> list(d.srtm1_tile_names())
            ['N19W156.hgt', 'N19W155.hgt']
            >>> bounds = [-156.0, 19.0, -154.0, 20.0]  # Show int bounds
            >>> list(d.srtm1_tile_names())
            ['N19W156.hgt', 'N19W155.hgt']
        """
        left, bottom, right, top = self.bounds
        left_int, top_int = self.srtm1_tile_corner(left, top)
        right_int, bot_int = self.srtm1_tile_corner(right, bottom)
        # If exact integer was requested for top/right, assume tile with that number
        # at the top/right is acceptable (dont download the one above that)
        if isinstance(top, int) or int(top) == top:
            top_int -= 1
        if isinstance(right, int) or int(right) == right:
            right_int -= 1

        # Now iterate in same order in which they'll be stithced together
        for ilat in range(top_int, bot_int - 1, -1):  # north to south
            hemi_ns = "N" if ilat >= 0 else "S"
            lat_str = "{}{:02d}".format(hemi_ns, abs(ilat))
            for ilon in range(left_int, right_int + 1):  # West to east
                hemi_ew = "E" if ilon >= 0 else "W"
                lon_str = "{}{:03d}".format(hemi_ew, abs(ilon))

                yield "{lat_str}{lon_str}.hgt".format(lat_str=lat_str, lon_str=lon_str)


class Downloader:
    """Class to download and save SRTM1 tiles to create DEMs

    Attributes:
        tile_names (iterator): strings of .hgt tiles (e.g. [N19W155.hgt])
        data_url (str): Base url where .hgt tiles are stored
        compress_type (str): format .hgt files are stored in online
        data_source (str): choices: NASA, AWS. See module docstring for explanation of sources
        cache_dir (str): explcitly specify where to store .hgt files

    Raises:
        ValueError: if data_source not a valid source string

    """

    VALID_SOURCES = ("NASA", "AWS")
    DATA_URLS = {
        "NASA": "http://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/2000.02.11",
        "AWS": "https://s3.amazonaws.com/elevation-tiles-prod/skadi",
    }
    COMPRESS_TYPES = {"NASA": "zip", "AWS": "gz"}
    NASAHOST = "urs.earthdata.nasa.gov"

    def __init__(
        self, tile_names, data_source="NASA", netrc_file="~/.netrc", cache_dir=None
    ):
        self.tile_names = tile_names
        self.data_source = data_source
        if data_source not in self.VALID_SOURCES:
            raise ValueError(
                "data_source must be one of: {}".format(",".join(self.VALID_SOURCES))
            )
        self.data_url = self.DATA_URLS[data_source]
        self.compress_type = self.COMPRESS_TYPES[data_source]
        self.netrc_file = os.path.expanduser(netrc_file)
        self.cache_dir = cache_dir or utils.get_cache_dir()

    def _get_netrc_file(self):
        return Netrc(self.netrc_file)

    def _has_nasa_netrc(self):
        try:
            n = self._get_netrc_file()
            # Check account exists, as well is having username and password
            return (
                self.NASAHOST in n.hosts
                and n.authenticators(self.NASAHOST)[0]
                and n.authenticators(self.NASAHOST)[2]
            )
        except (OSError, IOError):
            return False

    @staticmethod
    def _nasa_netrc_entry(username, password):
        """Create a string for a NASA urs account in .netrc format"""
        outstring = "machine {}\n".format(Downloader.NASAHOST)
        outstring += "\tlogin {}\n".format(username)
        outstring += "\tpassword {}\n".format(password)
        return outstring

    def handle_credentials(self):
        """Prompt user for NASA username/password, store as attribute or .netrc

        If the user wants to save as .netrc, add to existing, or create new ~/.netrc
        """
        username, password, do_save = _get_username_pass()
        if do_save:
            try:
                # If they have a netrc existing, add to it
                n = self._get_netrc_file()
                n.hosts[self.NASAHOST] = (username, None, password)
                outstring = str(n)
            except (OSError, IOError):
                # Otherwise, make a fresh one to save
                outstring = self._nasa_netrc_entry(username, password)

            with open(self.netrc_file, "w") as f:
                f.write(outstring)
        else:
            # Save these as attritubes for the NASA url request
            self.username = username
            self.password = password

    def _form_tile_url(self, tile_name):
        """Form the url for a .hgt tile from NASA or AWS

        Args:
            tile_name (str): string name of tile
            e.g. N06W001.SRTMGL1.hgt.zip (usgs) or N19/N19W156.hgt.gz (aws)

        Returns:
            url: formatted url string with tile name

        Examples:
            >>> d = Downloader(['N19W156.hgt', 'N19W155.hgt'], data_source='NASA')
            >>> print(d._form_tile_url('N19W155.hgt'))
            http://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/2000.02.11/N19W155.SRTMGL1.hgt.zip

            >>> d = Downloader(['N19W156.hgt', 'N19W155.hgt'], data_source='AWS')
            >>> print(d._form_tile_url('N19W155.hgt'))
            https://s3.amazonaws.com/elevation-tiles-prod/skadi/N19/N19W155.hgt.gz
        """
        if self.data_source == "AWS":
            lat_str, lat_int, _, _ = Tile.get_tile_parts(tile_name)
            url = "{base}/{lat}/{tile}.{ext}".format(
                base=self.data_url,
                lat=lat_str + str(lat_int),
                tile=tile_name,
                ext=self.compress_type,
            )
        elif self.data_source == "NASA":
            url = "{base}/{tile}.{ext}".format(
                base=self.data_url,
                tile=tile_name.replace(".hgt", ".SRTMGL1.hgt"),
                ext=self.compress_type,
            )
        return url

    def _download_hgt_tile(self, url):
        """Example from https://lpdaac.usgs.gov/data_access/daac2disk "command line tips" """
        # Using AWS or a netrc file are the easy cases
        logger.info("Downloading {}".format(url))
        if self.data_source == "AWS":
            response = requests.get(url)
        elif self.data_source == "NASA" and self._has_nasa_netrc():
            logger.info("Using netrc file: %s", self.netrc_file)
            response = requests.get(url)
        else:
            # NASA without a netrc file needs special auth session handling
            with requests.Session() as session:
                session.auth = (self.username, self.password)
                r1 = session.request("get", url)
                # NASA then redirects to
                # urs.earthdata.nasa.gov/oauth/authorize?scope=uid&app_type=401&client_id=...
                response = session.get(r1.url, auth=(self.username, self.password))

        return response

    def _unzip_file(self, filepath):
        """Unzips in place the .hgt files downloaded"""
        ext = os.path.splitext(filepath)[1]
        if ext == ".gz":
            unzip_cmd = ["gunzip"]
        elif ext == ".zip":
            # -o forces overwrite without prompt, -d specifices unzip directory
            unzip_cmd = "unzip -o -d {}".format(self.cache_dir).split(" ")
        subprocess.check_call(unzip_cmd + [filepath])

    def download_and_save(self, tile_name):
        """Download and save one single tile

        Args:
            tile_name (str): string name of tile
            e.g. N06W001.SRTMGL1.hgt.zip (usgs) or N19/N19W156.gz (aws)

        Returns:
            bool: True/False for Success/Failure of download
        """
        # keep all in one folder, compressed
        local_filename = os.path.join(self.cache_dir, tile_name)
        if os.path.exists(local_filename):
            logger.info("{} already exists, skipping.".format(local_filename))
        else:
            # On AWS these are gzipped: download, then unzip
            local_filename += ".{}".format(self.compress_type)
            with open(local_filename, "wb") as f:
                url = self._form_tile_url(tile_name)
                response = self._download_hgt_tile(url)
                # Now check response for auth issues/ errors
                if response.status_code == 404:
                    logger.warning("Cannot find url %s, using zeros for tile." % url)
                    # Raise only if we want to kill everything
                    # response.raise_for_status()
                    # Return False so caller can track failed downloads
                    return False

                f.write(response.content)
                logger.info("Writing to {}".format(local_filename))
            logger.info("Unzipping {}".format(local_filename))
            self._unzip_file(local_filename)
        # True indicates success for this tile_name
        return True

    def _all_files_exist(self):
        filepaths = [
            os.path.join(self.cache_dir, tile_name) for tile_name in self.tile_names
        ]
        return all(os.path.exists(f) for f in filepaths)

    def download_all(self):
        """Downloads and saves all tiles from tile list"""
        # Only need to get credentials for this case:
        if (
            not self._all_files_exist()
            and self.data_source == "NASA"
            and not self._has_nasa_netrc()
        ):
            self.handle_credentials()

        pool = ThreadPool(processes=5)
        successes = pool.map(self.download_and_save, self.tile_names)
        pool.close()
        if not any(successes):
            raise ValueError(
                "No successful .hgt tiles found and downloaded:"
                " check lats/ lons of DEM box for valid SRTM land area"
                " (<60 deg latitude not open ocean)."
            )


class Stitcher:
    """Class to combine separate .hgt tiles into one .dem file

    Attributes:
        tile_file_list (list[str]) names of .hgt tiles
            E.g.: ['N19W156.hgt', 'N19W155.hgt']
        failures (list[bool]): list of True (for successes) False
            (for failed downloads) matching tile_file_list
        num_pixels (int): size of the squares of the .hgt files
            Assumes 3601 for SRTM1 (SRTM3, 3 degree not implemented/tested)

    """

    def __init__(self, tile_names, failures=[], num_pixels=NUM_PIXELS):
        """List should come from Tile.srtm1_tile_names()"""
        self.tile_file_list = list(tile_names)
        self.failures = failures
        # Assuming SRTMGL1: 3601 x 3601 squares
        self.num_pixels = num_pixels

    @property
    def shape(self):
        """Number of rows/columns in pixels for stitched .dem

        Uses the blockshape property, along with num_pixels property
        Returned as a tuple

        Examples:
            >>> s = Stitcher(['N19W156.hgt', 'N19W155.hgt'])
            >>> s.shape
            (3601, 7201)
        """
        blockrows, blockcols = self.blockshape
        return (self._total_length(blockrows), self._total_length(blockcols))

    def _total_length(self, numblocks):
        """Computes the total number of pixels in one dem from numblocks"""
        return numblocks * (self.num_pixels - 1) + 1

    @property
    def blockshape(self):
        """Number of tile in rows cols"""
        return self._compute_shape()

    def _compute_shape(self):
        """Takes the tile list and computes the number of tile rows and tile cols

        Figures out how many lons wide and lats tall the tile array spans
        Note: This is not the total number of pixels, which can be found in .shape

        Examples:
            >>> s = Stitcher(['N19W156.hgt', 'N19W155.hgt'])
            >>> s._compute_shape()
            (1, 2)
        """
        lon_lat_tups = [self.start_lon_lat(t) for t in self.tile_file_list]
        # Unique each lat/lon: length of lats = num rows, lons = cols
        num_lons = len(set(tup[0] for tup in lon_lat_tups))
        num_lats = len(set(tup[1] for tup in lon_lat_tups))
        return (num_lats, num_lons)

    @staticmethod
    def start_lon_lat(tile_name):
        """Takes an SRTM1 data tile_name and returns the first (lon, lat) point

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
            >>> Stitcher.start_lon_lat('N19W156.hgt')
            (-156.0, 20.0)
            >>> Stitcher.start_lon_lat('S5E6.hgt')
            (6.0, -4.0)
            >>> Stitcher.start_lon_lat('Notrealname.hgt')
            Traceback (most recent call last):
               ...
            ValueError: Invalid SRTM1 tile name: Notrealname.hgt, must match \
([NS])(\d{1,2})([EW])(\d{1,3}).hgt
        """

        lat_str, lat, lon_str, lon = Tile.get_tile_parts(tile_name)

        # lat gets added to or subtracted
        top_lat = float(lat) + 1 if lat_str == "N" else -float(lat) + 1

        # lon is negative if we're in western hemisphere
        # No +1 addition needed to lon: bottom left and top left are same
        left_lon = -1 * float(lon) if lon_str == "W" else float(lon)
        return (left_lon, top_lat)

    def _create_file_array(self):
        """Finds filenames and reshapes into numpy.array matching DEM shape

        Examples:
            >>> s = Stitcher(['N19W156.hgt', 'N19W155.hgt', 'N18W156.hgt', 'N18W155.hgt'])
            >>> print(s._create_file_array())
            [['N19W156.hgt' 'N19W155.hgt']
             ['N18W156.hgt' 'N18W155.hgt']]
        """
        nrows, ncols = self.blockshape
        return np.array(self.tile_file_list).reshape((nrows, ncols))

    def _load_tile(self, tile_name):
        """Loads the tile, or returns a square of zeros if missing"""
        filename = os.path.join(utils.get_cache_dir(), tile_name)
        if os.path.exists(filename):
            return loading.load_elevation(filename)
        else:
            return np.zeros((NUM_PIXELS, NUM_PIXELS), dtype=np.int16)

    def load_and_stitch(self):
        """Function to load combine .hgt tiles

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
        """Calculates the step size for the dem.rsc

        Note: assuming same step size in x and y direction

        Args:
            ndigits (int) default=12 because that's what was given

        Returns:
            (float, float): x_step, y_step

        Example:
            >>> s = Stitcher(['N19W156.hgt', 'N19W155.hgt'])
            >>> print(s._find_step_sizes())
            (0.000277777777, -0.000277777777)
        """
        step_size = utils.floor_float(1 / (self.num_pixels - 1), ndigits)
        return (step_size, -1 * step_size)

    def create_dem_rsc(self):
        """Takes a list of the SRTM1 tile names and outputs .dem.rsc file values

        See module docstring for example .dem.rsc file.

        Args:
            srtm1_tile_list (list[str]): names of tiles (e.g. N19W156)
                must be sorted with top-left tile first, as in from
                output of Tile.srtm1_tile_names

        Returns:
            OrderedDict: key/value pairs in order to write to a .dem.rsc file

        Examples:
            >>> s = Stitcher(['N19W156.hgt', 'N19W155.hgt'])
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
        # TODO: figure out where to generalize for SRTM3
        rsc_dict.update({"WIDTH": ncols, "FILE_LENGTH": nrows})
        rsc_dict.update({"X_FIRST": x_first, "Y_FIRST": y_first})

        x_step, y_step = self._find_step_sizes()
        rsc_dict.update({"X_STEP": x_step, "Y_STEP": y_step})
        return rsc_dict


def crop_stitched_dem(bounds, stitched_dem, rsc_data):
    """Takes the output of Stitcher.load_and_stitch, crops to bounds

    Args:
        bounds (tuple[float]): (left, bot, right, top) lats and lons of
            desired bounding box for the DEM
        stitched_dem (numpy.array, 2D): result from .hgt files
            through Stitcher.load_and_stitch()
        rsc_data (dict): data from .dem.rsc file, from Stitcher.create_dem_rsc

    Returns:
        numpy.array: a cropped version of the bigger stitched_dem
    """
    indexes, new_starts = utils.find_bounding_idxs(
        bounds,
        rsc_data["X_STEP"],
        rsc_data["Y_STEP"],
        rsc_data["X_FIRST"],
        rsc_data["Y_FIRST"],
    )
    left_idx, bot_idx, right_idx, top_idx = indexes
    cropped_dem = stitched_dem[top_idx:bot_idx, left_idx:right_idx]
    new_sizes = cropped_dem.shape
    return cropped_dem, new_starts, new_sizes


def main(
    left_lon=None,
    top_lat=None,
    dlon=None,
    dlat=None,
    geojson=None,
    data_source=None,
    rate=None,
    output_name=None,
):
    """Function for entry point to create a DEM with `sardem`

    Args:
        left_lon (float): Left most longitude of DEM box
        top_lat (float): Top most longitude of DEM box
        dlon (float): Width of box in longitude degrees
        dlat (float): Height of box in latitude degrees
        geojson (dict): geojson object outlining DEM (alternative to lat/lon)
        data_source (str): 'NASA' or 'AWS', where to download .hgt tiles from
        rate (int): rate to upsample DEM (positive int)
        output_name (str): name of file to save final DEM (usually elevation.dem)
    """
    if geojson:
        bounds = utils.bounding_box(geojson=geojson)
    else:
        bounds = utils.bounding_box(left_lon, top_lat, dlon, dlat)
    logger.info("Bounds: %s", " ".join(str(b) for b in bounds))

    tile_names = list(Tile(*bounds).srtm1_tile_names())
    d = Downloader(tile_names, data_source=data_source)
    d.download_all()

    s = Stitcher(tile_names)
    stitched_dem = s.load_and_stitch()

    # Now create corresponding rsc file
    rsc_dict = s.create_dem_rsc()

    # Cropping: get very close to the bounds asked for:
    logger.info("Cropping stitched DEM to boundaries")
    stitched_dem, new_starts, new_sizes = crop_stitched_dem(
        bounds, stitched_dem, rsc_dict
    )
    new_x_first, new_y_first = new_starts
    new_rows, new_cols = new_sizes
    # Now adjust the .dem.rsc data to reflect new top-left corner and new shape
    rsc_dict["X_FIRST"] = new_x_first
    rsc_dict["Y_FIRST"] = new_y_first
    rsc_dict["FILE_LENGTH"] = new_rows
    rsc_dict["WIDTH"] = new_cols

    # Upsampling:
    rsc_filename = output_name + ".rsc"
    if rate == 1:
        logger.info("Rate = 1: No upsampling to do")
        logger.info("Writing DEM to %s", output_name)
        stitched_dem.tofile(output_name)
        logger.info("Writing .dem.rsc file to %s", rsc_filename)
        with open(rsc_filename, "w") as f:
            f.write(loading.format_dem_rsc(rsc_dict))
        return

    logger.info("Upsampling by {}".format(rate))
    dem_filename_small = output_name.replace(".dem", "_small.dem")
    rsc_filename_small = rsc_filename.replace(".dem.rsc", "_small.dem.rsc")

    logger.info("Writing non-upsampled dem temporarily to %s", dem_filename_small)
    stitched_dem.tofile(dem_filename_small)
    logger.info("Writing non-upsampled dem.rsc temporarily to %s", rsc_filename_small)
    with open(rsc_filename_small, "w") as f:
        f.write(loading.format_dem_rsc(rsc_dict))

    # Redo a new .rsc file for it
    logger.info("Writing new upsampled dem.rsc to %s", rsc_filename)
    with open(rsc_filename, "w") as f:
        upsampled_rsc = utils.upsample_dem_rsc(rate=rate, rsc_dict=rsc_dict)
        f.write(upsampled_rsc)

    # Now upsample this block
    nrows, ncols = stitched_dem.shape
    upsample_cy.upsample_wrap(
        dem_filename_small.encode(), rate, ncols, nrows, output_name.encode()
    )

    # Clean up the _small versions of dem and dem.rsc
    logger.info("Cleaning up %s and %s", dem_filename_small, rsc_filename_small)
    os.remove(dem_filename_small)
    os.remove(rsc_filename_small)
