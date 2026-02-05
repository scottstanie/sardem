import os
import zipfile

import numpy as np
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
