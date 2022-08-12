import pytest
import numpy as np
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
