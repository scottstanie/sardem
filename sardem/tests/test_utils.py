import pytest

from sardem import utils
from sardem.constants import DEFAULT_RES


def test_shift_integer_bbox():
    bbox = [-156.0, 19.0, -155.0, 20.0]
    hp = DEFAULT_RES / 2
    expected = [-156.0 - hp, 19.0 + hp, -155.0 - hp, 20.0 + hp]
    assert utils.shift_integer_bbox(bbox) == pytest.approx(expected)
