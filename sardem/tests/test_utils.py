import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from sardem import utils
from sardem.constants import DEFAULT_RES


def test_shift_integer_bbox():
    bbox = [-156.0, 19.0, -155.0, 20.0]
    hp = DEFAULT_RES / 2
    expected = [-156.0 - hp, 19.0 + hp, -155.0 - hp, 20.0 + hp]
    assert utils.shift_integer_bbox(bbox) == pytest.approx(expected)


def test_get_file_bbox(tmp_path):
    """Test extracting bounding box from a raster file"""
    # Create a small dummy GeoTIFF with known bounds
    test_bounds = (-155.5, 19.2, -155.0, 19.6)  # small area, < 1 degree
    width, height = 100, 100

    # Create the file
    test_file = tmp_path / "test_bounds.tif"
    transform = from_bounds(*test_bounds, width, height)

    with rasterio.open(
        test_file,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=np.float32,
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        # Write some dummy data
        dst.write(np.ones((height, width), dtype=np.float32), 1)

    # Test that get_file_bbox returns the correct bounds
    result = utils.get_file_bbox(str(test_file))
    assert result == pytest.approx(test_bounds)


def test_buffer_bbox():
    """Test buffering a bounding box"""
    bbox = (-155.5, 19.2, -155.0, 19.6)  # left, bottom, right, top
    buffer = 0.1

    # Apply buffer
    result = utils.buffer_bbox(bbox, buffer)
    expected = (-155.6, 19.1, -154.9, 19.7)

    assert result == pytest.approx(expected)


def test_buffer_bbox_negative():
    """Test shrinking a bounding box with negative buffer"""
    bbox = (-155.5, 19.2, -155.0, 19.6)  # left, bottom, right, top
    buffer = -0.05  # negative to shrink

    # Apply buffer
    result = utils.buffer_bbox(bbox, buffer)
    expected = (-155.45, 19.25, -155.05, 19.55)

    assert result == pytest.approx(expected)


def test_buffer_bbox_zero():
    """Test that zero buffer returns unchanged bbox"""
    bbox = (-155.5, 19.2, -155.0, 19.6)
    result = utils.buffer_bbox(bbox, 0.0)
    assert result == pytest.approx(bbox)
