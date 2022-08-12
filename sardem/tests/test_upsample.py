import numpy as np
from numpy.testing import assert_allclose

from sardem import upsample


def test_upsamples():
    d = np.ones((1, 5)) * np.arange(5).reshape((5, -1))
    d_up = np.ones((1, 10)) * np.linspace(0, 4, 10).reshape((10, -1))
    assert_allclose(upsample.upsample(d, 2, 2).round(3), d_up.round(3))
