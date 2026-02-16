import pytest

from sardem import utils
from sardem.constants import DEFAULT_RES


def test_shift_integer_bbox():
    bbox = [-156.0, 19.0, -155.0, 20.0]
    hp = DEFAULT_RES / 2
    expected = [-156.0 - hp, 19.0 + hp, -155.0 - hp, 20.0 + hp]
    assert utils.shift_integer_bbox(bbox) == pytest.approx(expected)


class TestCheckDateline:
    """Tests for the check_dateline function."""

    def test_no_dateline_crossing(self):
        bbox = (-156.0, 19.0, -155.0, 20.0)
        result = utils.check_dateline(bbox)
        assert len(result) == 1
        assert result[0] == pytest.approx(bbox)

    def test_no_dateline_crossing_positive_lon(self):
        bbox = (100.0, -10.0, 110.0, 10.0)
        result = utils.check_dateline(bbox)
        assert len(result) == 1
        assert result[0] == pytest.approx(bbox)

    def test_dateline_crossing_standard(self):
        # 170E to 170W = from 170 to -170 (crossing 180)
        bbox = (170.0, -10.0, -170.0, 10.0)
        result = utils.check_dateline(bbox)
        assert len(result) == 2

        result = sorted(result, key=lambda x: x[0])

        # Western part: -180 to -170
        assert result[0][0] == pytest.approx(-180.0)
        assert result[0][2] == pytest.approx(-170.0)
        assert result[0][1] == pytest.approx(-10.0)
        assert result[0][3] == pytest.approx(10.0)

        # Eastern part: 170 to 180
        assert result[1][0] == pytest.approx(170.0)
        assert result[1][2] == pytest.approx(180.0)
        assert result[1][1] == pytest.approx(-10.0)
        assert result[1][3] == pytest.approx(10.0)

    def test_dateline_crossing_wide_span(self):
        # 160E to 160W = 40 degrees, crossing dateline
        bbox = (160.0, -5.0, -160.0, 5.0)
        result = utils.check_dateline(bbox)
        assert len(result) == 2

        result = sorted(result, key=lambda x: x[0])

        assert result[0][0] == pytest.approx(-180.0)
        assert result[0][2] == pytest.approx(-160.0)

        assert result[1][0] == pytest.approx(160.0)
        assert result[1][2] == pytest.approx(180.0)

    def test_bbox_at_dateline_not_crossing(self):
        # 175E to 180 (right at dateline but not crossing)
        bbox = (175.0, -10.0, 180.0, 10.0)
        result = utils.check_dateline(bbox)
        assert len(result) == 1
        assert result[0] == pytest.approx(bbox)

    def test_bbox_west_of_dateline_not_crossing(self):
        bbox = (-180.0, -10.0, -170.0, 10.0)
        result = utils.check_dateline(bbox)
        assert len(result) == 1
        assert result[0] == pytest.approx(bbox)
