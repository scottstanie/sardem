import os
import shutil
import tempfile
import unittest
from os.path import dirname, join

import numpy as np
import pytest
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
        output_format="ENVI",
        cache_dir=str(srtm_tile_path.parent),
    )
    output = np.fromfile(tmp_output, dtype=np.int16).reshape(3600, 3600)
    np.testing.assert_allclose(srtm_tile[:-1, :-1], output, atol=1)


def test_main_match_file(tmp_path, srtm_tile_path, srtm_tile):
    """Test sardem with --match-file option by creating a dummy tiff and matching its bounds"""
    import rasterio
    from rasterio.transform import from_bounds

    # Create a small dummy GeoTIFF with bounds within the SRTM tile
    # Using a small area (< 0.5 degrees) that's within N19W156 tile
    test_bounds = (-155.5, 19.2, -155.1, 19.6)  # left, bottom, right, top
    width, height = 100, 100

    # Create the reference file
    ref_file = tmp_path / "reference.tif"
    transform = from_bounds(*test_bounds, width, height)

    with rasterio.open(
        ref_file,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=np.float32,
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        # Write some dummy elevation data
        dst.write(np.ones((height, width), dtype=np.float32) * 100, 1)

    # Run sardem using --match-file (via bbox parameter from get_file_bbox)
    tmp_output = tmp_path / "matched_output.dem"
    match_bbox = utils.get_file_bbox(str(ref_file))

    dem.main(
        output_name=str(tmp_output),
        bbox=match_bbox,
        keep_egm=True,
        data_source="NASA",
        output_type="float32",
        output_format="GTiff",
        cache_dir=str(srtm_tile_path.parent),
    )

    # Verify the output file was created and has correct bounds
    assert tmp_output.exists()

    # Open the output and verify it matches the reference bounds
    with rasterio.open(tmp_output) as src:
        output_bounds = src.bounds
        # The bounds should match within a small tolerance
        assert output_bounds.left == pytest.approx(test_bounds[0], abs=0.001)
        assert output_bounds.bottom == pytest.approx(test_bounds[1], abs=0.001)
        assert output_bounds.right == pytest.approx(test_bounds[2], abs=0.001)
        assert output_bounds.top == pytest.approx(test_bounds[3], abs=0.001)


def test_main_match_file_with_buffer(tmp_path, srtm_tile_path, srtm_tile):
    """Test sardem with --match-file and --buffer options"""
    import rasterio
    from rasterio.transform import from_bounds

    # Create a small dummy GeoTIFF with bounds within the SRTM tile
    test_bounds = (-155.4, 19.3, -155.2, 19.5)  # left, bottom, right, top
    buffer_deg = 0.05  # 0.05 degree buffer
    width, height = 50, 50

    # Create the reference file
    ref_file = tmp_path / "reference_buffer.tif"
    transform = from_bounds(*test_bounds, width, height)

    with rasterio.open(
        ref_file,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=np.float32,
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        # Write some dummy elevation data
        dst.write(np.ones((height, width), dtype=np.float32) * 50, 1)

    # Run sardem using --match-file with buffer
    tmp_output = tmp_path / "matched_buffered_output.dem"
    match_bbox = utils.get_file_bbox(str(ref_file))
    # Apply buffer (simulating --buffer CLI option)
    buffered_bbox = utils.buffer_bbox(match_bbox, buffer_deg)

    dem.main(
        output_name=str(tmp_output),
        bbox=buffered_bbox,
        keep_egm=True,
        data_source="NASA",
        output_type="float32",
        output_format="GTiff",
        cache_dir=str(srtm_tile_path.parent),
    )

    # Verify the output file was created
    assert tmp_output.exists()

    # Calculate expected buffered bounds
    expected_bounds = (
        test_bounds[0] - buffer_deg,  # left
        test_bounds[1] - buffer_deg,  # bottom
        test_bounds[2] + buffer_deg,  # right
        test_bounds[3] + buffer_deg,  # top
    )

    # Open the output and verify it matches the buffered bounds
    with rasterio.open(tmp_output) as src:
        output_bounds = src.bounds
        # The bounds should match the buffered bounds within a small tolerance
        assert output_bounds.left == pytest.approx(expected_bounds[0], abs=0.001)
        assert output_bounds.bottom == pytest.approx(expected_bounds[1], abs=0.001)
        assert output_bounds.right == pytest.approx(expected_bounds[2], abs=0.001)
        assert output_bounds.top == pytest.approx(expected_bounds[3], abs=0.001)
