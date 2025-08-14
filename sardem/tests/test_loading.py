import shutil
import tempfile
import unittest
import zipfile
from collections import OrderedDict
from os.path import dirname, join

from sardem import loading

DATAPATH = join(dirname(__file__), "data")


class TestRsc(unittest.TestCase):
    def setUp(self):
        self.rsc_path = join(DATAPATH, "elevation.dem.rsc")
        self.rsc_data = OrderedDict(
            [
                ("width", 2),
                ("file_length", 3),
                ("x_first", -155.676388889),
                ("y_first", 19.5755555567),
                ("x_step", 0.000138888888),
                ("y_step", -0.000138888888),
                ("x_unit", "degrees"),
                ("y_unit", "degrees"),
                ("z_offset", 0),
                ("z_scale", 1),
                ("projection", "LL"),
            ]
        )
        self.extract_path = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.extract_path)

    def test_load_dem_rsc(self):
        rsc_data = loading.load_dem_rsc(self.rsc_path)
        self.assertEqual(self.rsc_data, rsc_data)

    def test_format_dem_rsc(self):
        output = loading.format_dem_rsc(self.rsc_data)
        read_file = open(self.rsc_path).read()
        self.assertEqual(output, read_file)

    def test_load_elevation(self):
        zip_ref = zipfile.ZipFile(join(DATAPATH, "N19W156.hgt.zip"))
        zip_ref.extractall(self.extract_path)
        zip_ref.close()
        hgt_file = join(self.extract_path, "N19W156.hgt")
        loading.load_elevation(hgt_file)
