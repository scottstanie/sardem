import os
import shutil
import tempfile
import unittest
import zipfile
from os.path import dirname, join

import numpy as np
import responses

from sardem import dem, download, loading, utils
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


def test_main_srtm(tmp_path):
    # $ rio bounds --bbox ~/.cache/sardem/N19W156.hgt
    # [-156.0001388888889, 18.99986111111111, -154.99986111111113, 20.000138888888888]
    # but dropping the bottom row and right column of pixels to make 3600x3600
    bbox = [
        -156.0 - HALF_PIXEL,
        19.0 + HALF_PIXEL,
        -155.0 - HALF_PIXEL,
        20.0 + HALF_PIXEL,
    ]
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
        bbox=bbox,
        keep_egm=True,
        data_source="NASA",
        cache_dir=str(tmp_path),
    )
    output = np.fromfile(tmp_output, dtype=np.int16).reshape(3600, 3600)
    np.testing.assert_allclose(expected[:-1, :-1], output, atol=1)
