import os
import zipfile

import numpy as np

from sardem import cop_dem, utils

DATAPATH = os.path.join(os.path.dirname(__file__), "data")


def _write_absolute_vrt():
    # <SourceFilename relativeToVRT="0">/vsizip/{TMP_PATH}/cop_tile_hawaii.dem.zip/cop_tile_hawaii.dem</SourceFilename>
    template = os.path.join(DATAPATH, "N10_W160.vrt.template")
    output_filename = template.replace(".template", "")
    with open(template, "r") as f:
        vrt = f.read()
    vrt = vrt.format(data_path=DATAPATH)
    with open(output_filename, "w") as f:
        f.write(vrt)
    return output_filename


def test_main_cop(tmp_path):
    bbox = [-156.0, 19.0, -155.0, 20.0]
    bbox_shifted = utils.shift_integer_bbox(bbox)
    tmp_output = tmp_path / "output.dem"
    temp_absolute_vrt = _write_absolute_vrt()

    cop_dem.download_and_stitch(
        output_name=str(tmp_output),
        bbox=bbox_shifted,
        keep_egm=True,
        # Point to shrunk version of VRT to avoid downloading
        vrt_filename=os.path.join(DATAPATH, "cop_global.vrt"),
    )
    output = np.fromfile(tmp_output, dtype=np.int16).reshape(3600, 3600)

    # Get the expected output
    path = os.path.join(DATAPATH, "cop_tile_hawaii.dem.zip")
    unzipfile = tmp_path / "cop_tile_hawaii.dem"
    with zipfile.ZipFile(path, "r") as zip_ref:
        with open(unzipfile, "wb") as f:
            f.write(zip_ref.read("cop_tile_hawaii.dem"))
    expected = np.fromfile(unzipfile, dtype=np.int16).reshape(3600, 3600)

    np.testing.assert_allclose(expected, output, atol=1.0)
    os.remove(temp_absolute_vrt)
