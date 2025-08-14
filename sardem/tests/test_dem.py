import os
import shutil
import tempfile
import unittest
from os.path import dirname, join

import numpy as np
import responses

from sardem import dem, download, utils


DATA_PATH = join(dirname(__file__), "data")
NETRC_PATH = join(DATA_PATH, "netrc")


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

        sample_hgt_path = join(DATA_PATH, self.test_tile + ".hgt.zip")
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


def test_main_srtm(tmp_path, srtm_tile_path, srtm_tile, srtm_tile_bbox):
    tmp_output = tmp_path / "output.dem"
    dem.main(
        output_name=str(tmp_output),
        bbox=srtm_tile_bbox,
        keep_egm=True,
        data_source="NASA",
        output_type="int16",
        cache_dir=str(srtm_tile_path.parent),
    )
    output = np.fromfile(tmp_output, dtype=np.int16).reshape(3600, 3600)
    np.testing.assert_allclose(srtm_tile[:-1, :-1], output, atol=1)
