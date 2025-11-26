import os
import zipfile

import pytest

from sardem import loading
from sardem.constants import DEFAULT_RES

HALF_PIXEL = 0.5 * DEFAULT_RES
DATA_PATH = os.path.join(os.path.dirname(__file__), "data")


@pytest.fixture
def srtm_tile_path(tmp_path):
    return tmp_path / "N19W156.hgt"


@pytest.fixture
def srtm_tile(srtm_tile_path):
    path = os.path.join(DATA_PATH, "N19W156.hgt.zip")
    with zipfile.ZipFile(path, "r") as zip_ref, open(srtm_tile_path, "wb") as f:
        f.write(zip_ref.read("N19W156.hgt"))
    expected = loading.load_elevation(srtm_tile_path)
    expected[expected < -1000] = 0
    return expected


@pytest.fixture
def srtm_tile_bbox():
    # $ rio bounds --bbox ~/.cache/sardem/N19W156.hgt
    # [-156.0001388888889, 18.99986111111111, -154.99986111111113, 20.000138888888888]
    # but dropping the bottom row and right column of pixels to make 3600x3600
    return [
        -156.0 - HALF_PIXEL,
        19.0 + HALF_PIXEL,
        -155.0 - HALF_PIXEL,
        20.0 + HALF_PIXEL,
    ]
