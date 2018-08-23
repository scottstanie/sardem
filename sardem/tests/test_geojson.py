import unittest
import json
import tempfile
from os.path import join, dirname

from sardem import geojson

DATAPATH = join(dirname(__file__), 'data')


class TestGeojson(unittest.TestCase):
    def setUp(self):
        self.geojson = {
            "type":
            "Polygon",
            "coordinates": [[[-156.0, 18.7], [-154.6, 18.7], [-154.6, 20.3], [-156.0, 20.3],
                             [-156.0, 18.7]]]
        }
        self.jsonfile = tempfile.NamedTemporaryFile(mode='w+')
        with open(self.jsonfile.name, 'w+') as f:
            json.dump(self.geojson, f)

        self.bad_geojson = {"Point": 0}

    def tearDown(self):
        self.jsonfile.close()

    def test_coords(self):
        self.assertEqual(
            geojson.coords(self.geojson),
            [[-156.0, 18.7], [-154.6, 18.7], [-154.6, 20.3], [-156.0, 20.3], [-156.0, 18.7]])

    def test_bounding_box(self):
        self.assertEqual(geojson.bounding_box(self.geojson), (-156.0, 18.7, -154.6, 20.3))

    def test_fail_format(self):
        self.assertRaises(KeyError, geojson.bounding_box, self.bad_geojson)

    def test_print_coordinates(self):
        self.assertEqual(
            geojson.print_coordinates(self.geojson),
            '-156.0,18.7,-154.6,18.7,-154.6,20.3,-156.0,20.3,-156.0,18.7')
