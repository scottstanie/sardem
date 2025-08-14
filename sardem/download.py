import getpass
import logging
import math
import netrc
import os
import re
import subprocess
from multiprocessing.pool import ThreadPool

import numpy as np
import requests

from sardem import utils
from sardem.constants import DEFAULT_RES

try:
    input = raw_input  # Check for python 2
except NameError:
    pass

logger = logging.getLogger("sardem")


def _get_username_pass():
    """If netrc is not set up, get command line username and password"""
    print("====================================================================")
    print("Please enter NASA Earthdata credentials to download NASA hosted STRM.")
    print("See https://urs.earthdata.nasa.gov/users/new for signup info.")
    print("Or choose data_source=COP for Copernicus DSM.")
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
            >>> Tile.get_tile_parts('N19W156')
            ('N', 19, 'W', 156)
            >>> Tile.get_tile_parts('S5E6')
            ('S', 5, 'E', 6)
            >>> Tile.get_tile_parts('Notrealname')
            Traceback (most recent call last):
               ...
            ValueError: Invalid SRTM1 tile name: Notrealname, must match \
([NS])(\d{1,2})([EW])(\d{1,3})
        """
        lon_lat_regex = r"([NS])(\d{1,2})([EW])(\d{1,3})"
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
            str: tile names that cover all of bounding box
                yielded in order of top left to bottom right

        Examples:
            >>> bounds = (-155.7, 19.1, -154.7, 19.7)
            >>> d = Tile(*bounds)
            >>> from types import GeneratorType  # To check the type
            >>> type(d.srtm1_tile_names()) == GeneratorType
            True
            >>> list(d.srtm1_tile_names())
            ['N19W156', 'N19W155']
            >>> hp = 1 / 3600 / 2  # Half a degree in decimal degrees
            >>> bounds = [-156.0 - hp, 19.0 - hp, -154.0 + hp, 20.0 + hp]
            >>> list(d.srtm1_tile_names())
            ['N19W156', 'N19W155']
        """
        # `bounds` should refer to the edges of the bounding box
        # shift each inward by half pixel so they point to the boundary pixel centers
        shift_inward = np.array([1, 1, -1, -1]) * DEFAULT_RES / 2
        left, bottom, right, top = np.array(self.bounds) + shift_inward

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

                yield "{lat_str}{lon_str}".format(lat_str=lat_str, lon_str=lon_str)


class Downloader:
    """Class to download and save SRTM1 tiles to create DEMs

    Attributes:
        tile_names (iterator): strings of .hgt tiles (e.g. [N19W155.hgt])
        data_url (str): Base url where .hgt tiles are stored
        compress_type (str): format .hgt files are stored in online
        data_source (str): choices: NASA, NASA_WATER, COP
            See module docstring for explanation of sources
        cache_dir (str): explcitly specify where to store .hgt files

    Raises:
        ValueError: if data_source not a valid source string

    """

    DATA_URLS = {
        "NASA": "https://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/2000.02.11",
        "NASA_WATER": "https://e4ftl01.cr.usgs.gov/MEASURES/SRTMSWBD.003/2000.02.11",
        "COP": "https://copernicus-dem-30m.s3.amazonaws.com/{t}/{t}.tif",
    }
    VALID_SOURCES = DATA_URLS.keys()
    TILE_ENDINGS = {
        "NASA": ".SRTMGL1.hgt",
        "NASA_WATER": ".SRTMSWBD.raw",
    }
    COMPRESS_TYPES = {"NASA": "zip", "NASA_WATER": "zip"}
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
        self.ext_type = "raw" if data_source == "NASA_WATER" else "hgt"
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
        """Form the url for a .hgt tile

        Args:
            tile_name (str): string name of tile
            e.g. N06W001.SRTMGL1.hgt.zip (usgs)

        Returns:
            url: formatted url string with tile name

        Examples:
            >>> d = Downloader(['N19W156', 'N19W155'], data_source='NASA')
            >>> print(d._form_tile_url('N19W155'))
            https://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/2000.02.11/N19W155.SRTMGL1.hgt.zip

            >>> d = Downloader(['N19W156', 'N19W155'], data_source='NASA_WATER')
            >>> print(d._form_tile_url('N19W155'))
            https://e4ftl01.cr.usgs.gov/MEASURES/SRTMSWBD.003/2000.02.11/N19W155.SRTMSWBD.raw.zip

        """
        if self.data_source.startswith("NASA"):
            url = "{base}/{tile}.{ext}".format(
                base=self.data_url,
                tile=tile_name + self.TILE_ENDINGS[self.data_source],
                ext=self.compress_type,
            )
        return url

    def _download_hgt_tile(self, url):
        """Example from https://lpdaac.usgs.gov/data_access/daac2disk "command line tips" """
        # Using a netrc file is the easy cases
        logger.info("Downloading {}".format(url))
        if self.data_source.startswith("NASA") and self._has_nasa_netrc():
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
        # -o forces overwrite without prompt, -d specifices unzip directory
        unzip_cmd = "unzip -o -d {}".format(self.cache_dir).split(" ")
        subprocess.check_call(unzip_cmd + [filepath])

    def download_and_save(self, tile_name):
        """Download and save one single tile

        Args:
            tile_name (str): string name of tile
            e.g. N06W001.SRTMGL1.hgt.zip (usgs)

        Returns:
            bool: True/False for Success/Failure of download
        """
        # keep all in one folder, compressed
        local_filename = self._filepath(tile_name)
        if os.path.exists(local_filename):
            logger.info("{} already exists, skipping.".format(local_filename))
        else:
            # download, then unzip
            local_filename += ".{}".format(self.compress_type)
            with open(local_filename, "wb") as f:
                url = self._form_tile_url(tile_name)
                response = self._download_hgt_tile(url)
                # Now check response for auth issues/ errors
                if response.status_code == 404:
                    logger.warning("Cannot find url %s, using zeros for tile." % url)
                    # Raise only if we want to kill everything
                    # response.raise_for_status()
                    local_filename = os.path.splitext(local_filename)[0]
                    self._write_zeros(local_filename)
                    return local_filename

                f.write(response.content)
                logger.info("Writing to {}".format(local_filename))
            logger.info("Unzipping {}".format(local_filename))
            self._unzip_file(local_filename)
            # Now get rid of the .zip again
            local_filename = os.path.splitext(local_filename)[0]
        # True indicates success for this tile_name
        return local_filename

    def _filepath(self, tile_name):
        return os.path.join(self.cache_dir, tile_name + "." + self.ext_type)

    def _all_files_exist(self):
        filepaths = [self._filepath(tile_name) for tile_name in self.tile_names]
        return all(os.path.exists(f) for f in filepaths)

    def _write_zeros(self, local_filename):
        shape = (3601, 3601)
        if self.data_source == "NASA_WATER":
            dtype = np.uint8
        else:
            dtype = np.int16
        data = np.zeros(shape, dtype=dtype)
        data.tofile(local_filename)

    def download_all(self):
        """Downloads and saves all tiles from tile list"""
        # Only need to get credentials for this case:
        if (
            not self._all_files_exist()
            and self.data_source.startswith("NASA")
            and not self._has_nasa_netrc()
        ):
            self.handle_credentials()

        pool = ThreadPool(processes=5)
        local_filenames = pool.map(self.download_and_save, self.tile_names)
        pool.close()
        if not any(local_filenames):
            raise ValueError(
                "No successful .hgt tiles found and downloaded:"
                " check lats/ lons of DEM box for valid SRTM land area"
                " (<60 deg latitude not open ocean)."
            )
        return local_filenames
