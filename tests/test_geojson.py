import unittest
import tempfile
import json

from sardem.geojson import read_json, parse_coordinates, bounding_box, print_coordinates


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

    def test_read_json(self):
        loaded_json = read_json(self.jsonfile.name)
        self.assertEqual(loaded_json, self.geojson)

    def test_parse_coordinates(self):
        coords = parse_coordinates(self.geojson)
        self.assertEqual(coords, self.geojson['coordinates'][0])

    def test_bounding_box(self):
        self.assertEqual(bounding_box(self.geojson), (-156.0, 18.7, -154.6, 20.3))
        self.assertEqual(bounding_box(self.jsonfile.name), (-156.0, 18.7, -154.6, 20.3))

    def test_fail_format(self):
        self.assertRaises(KeyError, bounding_box, self.bad_geojson)

    def test_print_coordinates(self):
        desired_string = "-156.0,18.7,-154.6,18.7,-154.6,20.3,-156.0,20.3,-156.0,18.7"
        self.assertEqual(desired_string, print_coordinates(self.geojson))
