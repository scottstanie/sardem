import os

import pytest
from osgeo import osr

from sardem import conversions, cop_dem
from sardem.constants import DEFAULT_RES

HALF_PIXEL = 0.5 * DEFAULT_RES
DATA_PATH = os.path.join(os.path.dirname(__file__), "data")
EGM08 = "EPSG:4326+3855"


@pytest.fixture
def network_off():
    previous = osr.GetPROJEnableNetwork()
    osr.SetPROJEnableNetwork(False)
    yield
    osr.SetPROJEnableNetwork(previous)


def test_missing_geoid_grid_raises_instead_of_keeping_geoid_heights(monkeypatch, network_off):
    # PROJ without a usable grid applies a no-op vertical shift
    monkeypatch.setattr(conversions, "vertical_shift", lambda *args: 0.0)
    with pytest.raises(RuntimeError, match="geoid grid"):
        with conversions.geoid_grid_access(EGM08, -155.5, 19.5):
            pass
    assert osr.GetPROJEnableNetwork() is False


def test_network_is_enabled_during_the_conversion_and_restored(monkeypatch, network_off):
    # A grid that is only reachable over the network
    monkeypatch.setattr(
        conversions, "vertical_shift", lambda *args: 10.0 if osr.GetPROJEnableNetwork() else 0.0
    )
    with conversions.geoid_grid_access(EGM08, -155.5, 19.5):
        assert osr.GetPROJEnableNetwork() is True
    assert osr.GetPROJEnableNetwork() is False


def test_an_enabled_network_setting_is_kept(monkeypatch):
    previous = osr.GetPROJEnableNetwork()
    osr.SetPROJEnableNetwork(True)
    try:
        monkeypatch.setattr(conversions, "vertical_shift", lambda *args: 10.0)
        with conversions.geoid_grid_access(EGM08, -155.5, 19.5):
            pass
        assert osr.GetPROJEnableNetwork() is True
    finally:
        osr.SetPROJEnableNetwork(previous)


def _write_absolute_vrt():
    template = os.path.join(DATA_PATH, "N10_W160.vrt.template")
    output_filename = template.replace(".template", "")
    with open(template) as f:
        vrt = f.read().format(data_path=DATA_PATH)
    with open(output_filename, "w") as f:
        f.write(vrt)
    return output_filename


def test_cop_dem_refuses_to_write_geoid_heights_as_ellipsoidal(monkeypatch, tmp_path, network_off):
    monkeypatch.setattr(conversions, "vertical_shift", lambda *args: 0.0)
    bbox = [-156.0 - HALF_PIXEL, 19.0 + HALF_PIXEL, -155.0 - HALF_PIXEL, 20.0 + HALF_PIXEL]
    temp_vrt = _write_absolute_vrt()
    vrt = os.path.join(DATA_PATH, "cop_global.vrt")
    try:
        with pytest.raises(RuntimeError, match="geoid grid"):
            cop_dem.download_and_stitch(
                output_name=str(tmp_path / "hae.tif"), bbox=bbox, keep_egm=False,
                output_type="float32", vrt_filename=vrt,
            )
        assert not (tmp_path / "hae.tif").exists()
        # Keeping geoid heights on purpose needs no grid
        cop_dem.download_and_stitch(
            output_name=str(tmp_path / "egm.tif"), bbox=bbox, keep_egm=True,
            output_type="float32", vrt_filename=vrt,
        )
        assert (tmp_path / "egm.tif").exists()
    finally:
        os.remove(temp_vrt)
