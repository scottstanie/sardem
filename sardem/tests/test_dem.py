import unittest
import json
import tempfile
import shutil
from os.path import join, dirname
import os
import responses

from sardem import dem, utils

DATAPATH = join(dirname(__file__), "data")
NETRC_PATH = join(DATAPATH, "netrc")


class TestNetrc(unittest.TestCase):
    def test_format(self):
        n = dem.Netrc(NETRC_PATH)
        expected = (
            "machine urs.earthdata.nasa.gov\n\tlogin testuser\n\tpassword testpass\n"
        )

        self.assertEqual(n.format(), expected)


class TestTile(unittest.TestCase):
    def setUp(self):
        self.bounds = utils.bounding_box(-155.4, 19.75, 0.001, 0.001)

    def test_init(self):
        t = dem.Tile(*self.bounds)
        expected = (-155.4, 19.749, -155.399, 19.75)

        self.assertEqual(expected, t.bounds)


class TestDownload(unittest.TestCase):
    def setUp(self):
        self.bounds = utils.bounding_box(-155.4, 19.75, 0.001, 0.001)
        self.test_tile = "N19W156"
        self.hgt_url = "http://e4ftl01.cr.usgs.gov/MEASURES/\
SRTMGL1.003/2000.02.11/N19W156.SRTMGL1.hgt.zip"

        sample_hgt_path = join(DATAPATH, self.test_tile + ".hgt.zip")
        with open(sample_hgt_path, "rb") as f:
            self.sample_hgt_zip = f.read()

        self.cache_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.cache_dir)

    def test_init(self):
        d = dem.Downloader([self.test_tile], netrc_file=NETRC_PATH)
        self.assertEqual(
            d.data_url, "http://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/2000.02.11"
        )

    @responses.activate
    def test_download(self):
        responses.add(responses.GET, self.hgt_url, body=self.sample_hgt_zip, status=200)
        d = dem.Downloader(
            [self.test_tile], netrc_file=NETRC_PATH, cache_dir=self.cache_dir
        )
        d.download_all()
        self.assertTrue(os.path.exists(d._filepath(self.test_tile)))


class TestRsc(unittest.TestCase):
    def setUp(self):
        self.rsc_path = join(DATAPATH, "elevation.dem.rsc")

    def test_upsample_dem_rsc(self):
        # Test input checking
        self.assertRaises(
            ValueError,
            utils.upsample_dem_rsc,
            xrate=2,
            rsc_dict={"something": 1},
            rsc_filename=self.rsc_path,
        )
        self.assertRaises(ValueError, utils.upsample_dem_rsc, xrate=2)
        self.assertRaises(
            ValueError, utils.upsample_dem_rsc, rsc_filename=self.rsc_path
        )  # Need rate

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
        self.assertEqual(expected, up_rsc)


class TestBounds(unittest.TestCase):
    def setUp(self):
        self.coords = [
            [-156.0, 18.7],
            [-154.6, 18.7],
            [-154.6, 20.3],
            [-156.0, 20.3],
            [-156.0, 18.7],
        ]
        self.left_lon = -156.0
        self.top_lat = 20.3
        self.dlat = 1.6
        self.dlon = 1.4

    def test_corner_input(self):
        result = utils.corner_coords(self.left_lon, self.top_lat, self.dlon, self.dlat)
        self.assertEqual(
            set(tuple(c) for c in result), set(tuple(c) for c in self.coords)
        )

    def test_bounding_box(self):
        self.assertEqual(
            utils.bounding_box(self.left_lon, self.top_lat, self.dlon, self.dlat),
            (-156.0, 18.7, -154.6, 20.3),
        )


"""
TODO:
    finish cropped, upsampled dem, show  this:
        expected_dem = np.array(
            [[2071, 2072, 2074, 2076, 2078, 2078, 2079, 2080, 2082], [
                2071, 2072, 2073, 2075, 2076, 2077, 2078, 2079, 2081
            ], [2071, 2072, 2073, 2074, 2075, 2076, 2078, 2079, 2080], [
                2071, 2071, 2072, 2073, 2074, 2075, 2077, 2078, 2080
            ], [2071, 2071, 2072, 2073, 2074, 2075, 2076, 2078, 2080], [
                2071, 2071, 2072, 2072, 2073, 2074, 2076, 2077, 2079
            ], [2071, 2071, 2072, 2072, 2073, 2074, 2076, 2077, 2078]],
            dtype='<i2')

        output_dem = sario.load_file('elevation.dem')
        # assert_array_almost_equal(expected_dem)
    """
