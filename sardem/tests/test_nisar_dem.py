import os
import zipfile

import numpy as np
import pytest
import rasterio as rio

from sardem import nisar_dem
from sardem.constants import DEFAULT_RES

HALF_PIXEL = 0.5 * DEFAULT_RES
DATA_PATH = os.path.join(os.path.dirname(__file__), "data")


def _write_nisar_absolute_vrt():
    """Write the leaf VRT with an absolute path to the test tile data."""
    template = os.path.join(DATA_PATH, "N10_W160_nisar.vrt.template")
    output_filename = template.replace(".template", "")
    with open(template, "r") as f:
        vrt = f.read()
    vrt = vrt.format(data_path=DATA_PATH)
    with open(output_filename, "w") as f:
        f.write(vrt)
    return output_filename


def test_main_nisar(tmp_path):
    bbox = [
        -156.0 - HALF_PIXEL,
        19.0 + HALF_PIXEL,
        -155.0 - HALF_PIXEL,
        20.0 + HALF_PIXEL,
    ]
    tmp_output = tmp_path / "output_nisar.tif"
    temp_absolute_vrt = _write_nisar_absolute_vrt()

    nisar_dem.download_and_stitch(
        output_name=str(tmp_output),
        bbox=bbox,
        output_type="int16",
        vrt_filename=os.path.join(DATA_PATH, "nisar_global.vrt"),
    )
    with rio.open(tmp_output) as src:
        output = src.read(1)

    # Get the expected output from the same tile data used by COP tests
    path = os.path.join(DATA_PATH, "cop_tile_hawaii.dem.zip")
    unzipfile = tmp_path / "cop_tile_hawaii.dem"
    with zipfile.ZipFile(path, "r") as zip_ref:
        with open(unzipfile, "wb") as f:
            f.write(zip_ref.read("cop_tile_hawaii.dem"))
    expected = np.fromfile(unzipfile, dtype=np.int16).reshape(3600, 3600)

    np.testing.assert_allclose(expected, output, atol=1.0)
    os.remove(temp_absolute_vrt)


@pytest.mark.parametrize(
    "bbox, expected_key",
    [
        ((-104, 30, -103, 31), "EPSG4326"),  # mid-latitude
        ((0, -80, 10, -70), "EPSG3031"),  # Antarctica
        ((0, 70, 10, 80), "EPSG3413"),  # Arctic
        ((-104, -60, -103, -50), "EPSG4326"),  # top above threshold -> mid-lat
        ((-104, 50, -103, 60), "EPSG4326"),  # bottom below threshold -> mid-lat
    ],
)
def test_select_vrt(bbox, expected_key):
    url, dst_srs = nisar_dem._select_vrt(bbox)
    assert expected_key in url
    if expected_key == "EPSG4326":
        assert dst_srs is None
    else:
        assert dst_srs == "EPSG:4326"
