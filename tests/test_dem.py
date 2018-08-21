import unittest
import json
import tempfile
import shutil
from os.path import join, dirname
import os
import responses

from sardem import dem, geojson, kml, utils

DATAPATH = join(dirname(__file__), 'data')
NETRC_PATH = join(DATAPATH, 'netrc')


class TestNetrc(unittest.TestCase):
    def test_format(self):
        n = dem.Netrc(NETRC_PATH)
        expected = "machine urs.earthdata.nasa.gov\n\tlogin testuser\n\tpassword testpass\n"

        self.assertEqual(n.format(), expected)


class TestTile(unittest.TestCase):
    def setUp(self):
        self.geojson_path = join(DATAPATH, 'hawaii_small.geojson')
        with open(self.geojson_path, 'r') as f:
            self.geojson = json.load(f)
        self.bounds = geojson.bounding_box(self.geojson)

    def test_init(self):
        t = dem.Tile(*self.bounds)
        expected = (-155.49898624420166, 19.741217531292406, -155.497784614563, 19.74218696311137)

        self.assertEqual(expected, t.bounds)


class TestDownload(unittest.TestCase):
    def setUp(self):
        self.geojson_path = join(DATAPATH, 'hawaii_small.geojson')
        with open(self.geojson_path, 'r') as f:
            self.geojson = json.load(f)
        self.bounds = geojson.bounding_box(self.geojson)
        self.test_tile = 'N19W156.hgt'
        self.hgt_url = "http://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/2000.02.11/N19W156.SRTMGL1.hgt.zip"

        sample_hgt_path = join(DATAPATH, self.test_tile + '.zip')
        with open(sample_hgt_path, 'rb') as f:
            self.sample_hgt_zip = f.read()

        self.cache_dir = tempfile.mkdtemp()

    def test_init(self):

        d = dem.Downloader([self.test_tile], netrc_file=NETRC_PATH)
        self.assertEqual(d.data_url, "http://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/2000.02.11")

    @responses.activate
    def test_download(self):
        responses.add(responses.GET, self.hgt_url, body=self.sample_hgt_zip, status=200)
        d = dem.Downloader([self.test_tile], netrc_file=NETRC_PATH, cache_dir=self.cache_dir)
        d.download_all()
        self.assertTrue(os.path.exists(join(d.cache_dir, self.test_tile)))

    def tearDown(self):
        shutil.rmtree(self.cache_dir)


class TestRsc(unittest.TestCase):
    def setUp(self):
        self.rsc_path = join(DATAPATH, 'elevation.dem.rsc')
        # Sample dict with only lat/lon info
        self.test_rsc_data = {
            "width": 4,
            "file_length": 2,
            "x_first": -10.0,
            "y_first": 3.0,
            "x_step": 0.25,
            "y_step": -0.25
        }

    def test_upsample_dem_rsc(self):
        # Test input checking
        self.assertRaises(
            TypeError,
            utils.upsample_dem_rsc,
            rate=2,
            rsc_dict={'something': 1},
            rsc_filepath=self.rsc_path)
        self.assertRaises(TypeError, utils.upsample_dem_rsc, rate=2)
        self.assertRaises(
            TypeError, utils.upsample_dem_rsc, rsc_filepath=self.rsc_path)  # Need rate

        up_rsc = utils.upsample_dem_rsc(rate=2, rsc_filepath=self.rsc_path)
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

    def test_rsc_bounds(self):
        expected = {'north': 3.0, 'south': 2.5, 'west': -10.0, 'east': -9.0}
        self.assertEqual(expected, kml.rsc_bounds(self.test_rsc_data))

    def test_create_kml(self):
        expected = """\
<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://earth.google.com/kml/2.2">
<GroundOverlay>
    <name> test_title </name>
    <description> my desc </description>
    <Icon>
          <href> out.tif </href>
    </Icon>
    <LatLonBox>
        <north> 3.0 </north>
        <south> 2.5 </south>
        <east> -9.0 </east>
        <west> -10.0 </west>
    </LatLonBox>
</GroundOverlay>
</kml>
"""
        tifname = "out.tif"
        output = kml.create_kml(self.test_rsc_data, tifname, desc="my desc", title="test_title")
        self.assertEqual(expected, output)


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
