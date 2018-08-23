"""
Takes in coordinates, outputs bounds to use for dem download

Can come from a top corner and bot corner, corner and height/width,
or used with http://geojson.io to get a quick geojson polygon

Coordinates are (lon, lat) to match (x, y)
Bounding box order is  (left, bottom, right, top) (floats)
"""
import itertools


def coords(geojson):
    """Finds the coordinates of a geojson polygon

    Note: we are assuming one simple polygon with no holes

    Args:
        geojson (dict): loaded geojson dict

    Returns:
        list: coordinates of polygon in the geojson

    Raises:
        ValueError: if invalid geojson type (no 'geometry' in the json)
    """
    # First, if given a deeper object (e.g. from geojson.io), extract just polygon
    try:
        if geojson.get('type') == 'FeatureCollection':
            geojson = geojson['features'][0]['geometry']
        elif geojson.get('type') == 'Feature':
            geojson = geojson['geometry']
    except KeyError:
        raise ValueError("Invalid geojson")

    return geojson['coordinates'][0]


def bounding_box(geojson=None):
    """From a geojson object, compute bounding lon/lats

    Valid geojson types: Geometry, Feature (Polygon), Feature Collection
        (will choose the first Feature in the collection)

    Args:
        geojson (dict): json pre-loaded into a dict

    Returns:
        tuple[float]: the left,bottom,right,top bounding box of the Polygon
    """
    coordinates = coords(geojson)

    left = min(float(lon) for (lon, lat) in coordinates)
    right = max(float(lon) for (lon, lat) in coordinates)

    top = max(float(lat) for (lon, lat) in coordinates)
    bottom = min(float(lat) for (lon, lat) in coordinates)
    return left, bottom, right, top


def print_coordinates(geojson_dict):
    """Prints out the lon,lat points in the polygon joined in one string

    Used for ASF API queries: https://www.asf.alaska.edu/get-data/learn-by-doing/
    E.g. (from their example api request, the following URL params are used)
    polygon=-155.08,65.82,-153.5,61.91,-149.50,63.07,-149.94,64.55,-153.28,64.47,-155.08,65.82

    Args:
        geojson (dict): json pre-loaded into a dict

    Returns:
        str: lon,lat points of the Polygon in order as 'lon1,lat1,lon2,lat2,...'
    """
    c = coords(geojson_dict)
    return ','.join(str(coord) for coord in itertools.chain.from_iterable(c))
