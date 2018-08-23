import unittest
import json
import tempfile
from os.path import join, dirname

from sardem import geojson

DATAPATH = join(dirname(__file__), 'data')


class TestGeojson(unittest.TestCase):
    def setUp(self):
        self.coords = [[-156.0, 18.7], [-154.6, 18.7], [-154.6, 20.3], [-156.0, 20.3],
                       [-156.0, 18.7]]
        self.geojson = {"type": "Polygon", "coordinates": [self.coords]}
        # Same data, but as corner + width/height
        self.top_corner = [-156.0, 20.3]
        self.dlat = 1.6
        self.dlon = 1.4
        self.jsonfile = tempfile.NamedTemporaryFile(mode='w+')
        with open(self.jsonfile.name, 'w+') as f:
            json.dump(self.geojson, f)

        self.bad_geojson = {"Point": 0}

    def tearDown(self):
        self.jsonfile.close()

    def test_coords(self):
        self.assertEqual(geojson.coords(self.geojson), self.coords)

    def test_fail_format(self):
        self.assertRaises(KeyError, geojson.bounding_box, self.bad_geojson)

    def test_print_coordinates(self):
        self.assertEqual(
            geojson.print_coordinates(self.geojson),
            '-156.0,18.7,-154.6,18.7,-154.6,20.3,-156.0,20.3,-156.0,18.7')

    def test_corner_input(self):
        result = geojson.corner_coords(self.top_corner, self.dlon, self.dlat)
        self.assertEqual(set(tuple(c) for c in result), set(tuple(c) for c in self.coords))

    def test_bounding_box(self):
        self.assertEqual(geojson.bounding_box(self.geojson), (-156.0, 18.7, -154.6, 20.3))
        self.assertEqual(
            geojson.bounding_box(top_corner=self.top_corner, dlon=self.dlon, dlat=self.dlat),
            (-156.0, 18.7, -154.6, 20.3))
