import os
import numpy as np
import zipfile
import gzip
import shutil
import tempfile
import unittest
from os.path import dirname, join
import pytest

import responses

from sardem import dem, download, utils, loading
from sardem.constants import DEFAULT_RES

HALF_PIXEL = 0.5 * DEFAULT_RES

DATAPATH = join(dirname(__file__), "data")
NETRC_PATH = join(DATAPATH, "netrc")


class TestNetrc(unittest.TestCase):
    def test_format(self):
        n = download.Netrc(NETRC_PATH)
        expected = (
            "machine urs.earthdata.nasa.gov\n\tlogin testuser\n\tpassword testpass\n"
        )

        self.assertEqual(n.format(), expected)


class TestTile(unittest.TestCase):
    def setUp(self):
        self.bounds = utils.bounding_box(-155.4, 19.75, 0.001, 0.001)

    def test_init(self):
        t = download.Tile(*self.bounds)
        expected = (-155.4, 19.749, -155.399, 19.75)

        self.assertEqual(expected, t.bounds)


class TestDownload(unittest.TestCase):
    def setUp(self):
        self.bounds = utils.bounding_box(-155.4, 19.75, 0.001, 0.001)
        self.test_tile = "N19W156"
        self.hgt_url = "https://e4ftl01.cr.usgs.gov/MEASURES/\
SRTMGL1.003/2000.02.11/N19W156.SRTMGL1.hgt.zip"

        sample_hgt_path = join(DATAPATH, self.test_tile + ".hgt.zip")
        with open(sample_hgt_path, "rb") as f:
            self.sample_hgt_zip = f.read()

        self.cache_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.cache_dir)

    def test_init(self):
        d = download.Downloader([self.test_tile], netrc_file=NETRC_PATH)
        self.assertEqual(
            d.data_url, "https://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/2000.02.11"
        )

    @responses.activate
    def test_download(self):
        responses.add(responses.GET, self.hgt_url, body=self.sample_hgt_zip, status=200)
        d = download.Downloader(
            [self.test_tile], netrc_file=NETRC_PATH, cache_dir=self.cache_dir
        )
        d.download_all()
        self.assertTrue(os.path.exists(d._filepath(self.test_tile)))


class TestRsc:
    rsc_path = join(DATAPATH, "elevation.dem.rsc")

    def test_upsample_dem_rsc(self):
        # Test input checking
        with pytest.raises(ValueError):
            utils.upsample_dem_rsc(
                xrate=2,
                rsc_dict={"something": 1},
                rsc_filename=self.rsc_path,
            )
        with pytest.raises(ValueError):
            utils.upsample_dem_rsc(xrate=2)

        up_rsc = utils.upsample_dem_rsc(xrate=1, yrate=1, rsc_filename=self.rsc_path)
        expected = """\
WIDTH         2
FILE_LENGTH   3
X_FIRST       -155.676388889
Y_FIRST       19.5755555567
X_STEP        0.000138888888
Y_STEP        -0.000138888888
X_UNIT        degrees
Y_UNIT        degrees
Z_OFFSET      0
Z_SCALE       1
PROJECTION    LL
"""
        up_rsc = utils.upsample_dem_rsc(xrate=2, rsc_filename=self.rsc_path)
        expected = """\
WIDTH         3
FILE_LENGTH   3
X_FIRST       -155.676388889
Y_FIRST       19.5755555567
X_STEP        0.000069444444
Y_STEP        -0.000138888888
X_UNIT        degrees
Y_UNIT        degrees
Z_OFFSET      0
Z_SCALE       1
PROJECTION    LL
"""

        up_rsc = utils.upsample_dem_rsc(xrate=2, yrate=2, rsc_filename=self.rsc_path)
        expected = """\
WIDTH         3
FILE_LENGTH   5
X_FIRST       -155.676388889
Y_FIRST       19.5755555567
X_STEP        0.000069444444
Y_STEP        -0.000069444444
X_UNIT        degrees
Y_UNIT        degrees
Z_OFFSET      0
Z_SCALE       1
PROJECTION    LL
"""
        assert expected == up_rsc


class TestBounds:
    coords = [
        [-156.0, 18.7],
        [-154.6, 18.7],
        [-154.6, 20.3],
        [-156.0, 20.3],
        [-156.0, 18.7],
    ]
    left_lon = -156.0
    top_lat = 20.3
    dlat = 1.6
    dlon = 1.4

    def test_corner_input(self):
        result = utils.corner_coords(self.left_lon, self.top_lat, self.dlon, self.dlat)
        assert set(tuple(c) for c in result) == set(tuple(c) for c in self.coords)

    def test_bounding_box(self):
        assert utils.bounding_box(
            self.left_lon, self.top_lat, self.dlon, self.dlat
        ) == ((-156.0, 18.7, -154.6, 20.3))


class TestMain:
    bbox = [-156.0, 19.0, -155.0, 20.0]

    def test_main_srtm(self, tmp_path):
        path = join(DATAPATH, "N19W156.hgt.zip")
        # tmpfile = tmp_path / "N19W156.hgt.zip"
        unzipfile = tmp_path / "N19W156.hgt"
        with zipfile.ZipFile(path, "r") as zip_ref:
            with open(unzipfile, "wb") as f:
                f.write(zip_ref.read("N19W156.hgt"))
        expected = loading.load_elevation(unzipfile)
        expected[expected < -1000] = 0

        tmp_output = tmp_path / "output.dem"
        dem.main(
            output_name=str(tmp_output),
            bbox=self.bbox,
            keep_egm=True,
            data_source="NASA",
            cache_dir=str(tmp_path),
        )
        output = np.fromfile(tmp_output, dtype=np.int16).reshape(3600, 3600)
        np.testing.assert_allclose(expected[:-1, :-1], output)

    def test_main_cop(self, tmp_path):
        path = join(DATAPATH, "cop_tile_hawaii.dem.gz")
        unzipfile = tmp_path / "cop_tile_hawaii.dem"
        with gzip.open(path, "rb") as f_in:
            with open(unzipfile, "wb") as f_out:
                f_out.write(f_in.read())

        expected = np.fromfile(unzipfile, dtype=np.int16).reshape(3600, 3600)
        tmp_output = tmp_path / "output.dem"
        dem.main(
            output_name=str(tmp_output),
            bbox=self.bbox,
            keep_egm=True,
            data_source="COP",
            cache_dir=str(tmp_path),
        )
        output = np.fromfile(tmp_output, dtype=np.int16).reshape(3600, 3600)
        np.testing.assert_allclose(expected, output, atol=1.0)
