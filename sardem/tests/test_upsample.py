import os

import numpy as np
import pytest
from numpy.testing import assert_allclose

from sardem import upsample


def test_upsample(tmp_path):
    d = np.ones((1, 5)) * np.arange(5).reshape((5, -1))
    d_up = np.ones((1, 10)) * np.linspace(0, 4, 10).reshape((10, -1))
    assert_allclose(upsample.upsample(d, 2, 2).round(3), d_up.round(3))

    demfile_in = tmp_path / "demfile_in.dem"
    d.astype("int16").tofile(demfile_in)
    demfile_out = tmp_path / "demfile_out.dem"
    block_rows = 3

    dtype = "int16"
    upsample.upsample_by_blocks(
        demfile_in, demfile_out, d.shape, block_rows, dtype, xrate=2, yrate=2
    )
    d_up2 = np.fromfile(demfile_out, dtype="int16").reshape(d_up.shape)
    assert_allclose(d_up2, d_up.round().astype(dtype))


def test_resample():
    a = np.arange(16).reshape(4, 4).astype("float32")
    expected = np.array([[2.5, 3.5, 4.5], [6.5, 7.5, 8.5], [10.5, 11.5, 12.5]])
    rsc_dict_mid = {
        "width": 4,
        "file_length": 4,
        "x_first": 1.0,
        "x_step": 1,
        "y_first": 4.0,
        "y_step": -1,
    }
    bbox = (1, 1, 4, 4)
    a_resampled = upsample.resample(a, rsc_dict_mid, bbox)
    assert_allclose(expected, a_resampled) 

    bbox = (0.5, 0.5, 4.5, 4.5)
    a_resampled = upsample.resample(a, rsc_dict_mid, bbox)
    assert_allclose(a, a_resampled) 


def test_upsample_dem_rsc():
    rsc_path = os.path.join(os.path.dirname(__file__), "data", "elevation.dem.rsc")
    # Test input checking
    with pytest.raises(ValueError):
        upsample.upsample_dem_rsc(
            xrate=2,
            rsc_dict={"something": 1},
            rsc_filename=rsc_path,
        )
    with pytest.raises(ValueError):
        upsample.upsample_dem_rsc(xrate=2)

    up_rsc = upsample.upsample_dem_rsc(xrate=1, yrate=1, rsc_filename=rsc_path)
    expected = """\
WIDTH         2
FILE_LENGTH   3
X_FIRST       -155.676388889
Y_FIRST       19.5755555567
X_STEP        0.000138888888
Y_STEP        -0.000138888888
X_UNIT        degrees
Y_UNIT        degrees
Z_OFFSET      0
Z_SCALE       1
PROJECTION    LL
"""
    up_rsc = upsample.upsample_dem_rsc(xrate=2, rsc_filename=rsc_path)
    expected = """\
WIDTH         4
FILE_LENGTH   3
X_FIRST       -155.676388889
Y_FIRST       19.5755555567
X_STEP        0.000069444444
Y_STEP        -0.000138888888
X_UNIT        degrees
Y_UNIT        degrees
Z_OFFSET      0
Z_SCALE       1
PROJECTION    LL
"""

    up_rsc = upsample.upsample_dem_rsc(xrate=2, yrate=2, rsc_filename=rsc_path)
    expected = """\
WIDTH         4
FILE_LENGTH   6
X_FIRST       -155.676388889
Y_FIRST       19.5755555567
X_STEP        0.000069444444
Y_STEP        -0.000069444444
X_UNIT        degrees
Y_UNIT        degrees
Z_OFFSET      0
Z_SCALE       1
PROJECTION    LL
"""
    assert expected == up_rsc
