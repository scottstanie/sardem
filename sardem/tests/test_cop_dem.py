import os
import zipfile

import numpy as np
import rasterio as rio

from sardem import cop_dem
from sardem.constants import DEFAULT_RES

HALF_PIXEL = 0.5 * DEFAULT_RES
DATA_PATH = os.path.join(os.path.dirname(__file__), "data")


def _write_absolute_vrt():
    # <SourceFilename relativeToVRT="0">/vsizip/{data_path}/cop_tile_hawaii.dem.zip/cop_tile_hawaii.dem</SourceFilename>
    template = os.path.join(DATA_PATH, "N10_W160.vrt.template")
    output_filename = template.replace(".template", "")
    with open(template, "r") as f:
        vrt = f.read()
    vrt = vrt.format(data_path=DATA_PATH)
    with open(output_filename, "w") as f:
        f.write(vrt)
    return output_filename


def test_main_cop(tmp_path):
    # bbox = [-156.0, 19.0, -155.0, 20.0]
    # bbox_shifted = utils.shift_integer_bbox(bbox)
    # $ rio bounds --bbox ~/Downloads/Copernicus_DSM_COG_10_N19_00_W156_00_DEM.tif
    # [-156.0001388888889, 19.000138888888888, -155.0001388888889, 20.000138888888888]
    bbox = [
        -156.0 - HALF_PIXEL,
        19.0 + HALF_PIXEL,
        -155.0 - HALF_PIXEL,
        20.0 + HALF_PIXEL,
    ]
    tmp_output = tmp_path / "output.dem.tif"
    temp_absolute_vrt = _write_absolute_vrt()

    cop_dem.download_and_stitch(
        output_name=str(tmp_output),
        bbox=bbox,
        keep_egm=True,
        output_type="int16",
        # Point to shrunk version of VRT to avoid downloading
        vrt_filename=os.path.join(DATA_PATH, "cop_global.vrt"),
    )
    with rio.open(tmp_output) as src:
        output = src.read(1)

    # Get the expected output
    path = os.path.join(DATA_PATH, "cop_tile_hawaii.dem.zip")
    unzipfile = tmp_path / "cop_tile_hawaii.dem"
    with zipfile.ZipFile(path, "r") as zip_ref:
        with open(unzipfile, "wb") as f:
            f.write(zip_ref.read("cop_tile_hawaii.dem"))
    expected = np.fromfile(unzipfile, dtype=np.int16).reshape(3600, 3600)

    np.testing.assert_allclose(expected, output, atol=1.0)
    os.remove(temp_absolute_vrt)


def _egm2008_undulation():
    """Return a function (lon, lat) -> EGM2008 undulation (m), or None.

    It uses GDAL's own PROJ, the same one that ``gdal.Warp`` uses for the
    datum shift. PROJ reads the EGM2008 grid over the network, or from the
    PROJ data directory when it is installed there.
    """
    from osgeo import gdal, osr

    gdal.UseExceptions()
    osr.SetPROJEnableNetwork(True)
    src = osr.SpatialReference()
    src.SetFromUserInput("EPSG:4326+3855")
    dst = osr.SpatialReference()
    dst.ImportFromEPSG(4979)
    for srs in (src, dst):
        srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    transform = osr.CoordinateTransformation(src, dst)

    def undulation(lon, lat):
        return transform.TransformPoint(lon, lat, 0.0)[2]

    try:
        # Without the grid, PROJ leaves the height unchanged
        return undulation if abs(undulation(-155.5, 19.5)) > 1.0 else None
    except RuntimeError:
        return None


def test_ocean_is_converted_to_ellipsoid_heights(tmp_path):
    """Sea level is a valid 0 m EGM2008 height, not nodata.

    Before the fix, ``srcNodata=0`` skipped the ocean during the vertical
    datum shift, so the output had the ocean at 0 m *ellipsoidal* next to
    land shifted by the geoid undulation. The ocean must move by the same
    undulation as the land.
    """
    import pytest

    undulation = _egm2008_undulation()
    if undulation is None:
        pytest.skip("PROJ cannot read the EGM2008 grid (no network or grid file)")

    bbox = [
        -156.0 - HALF_PIXEL,
        19.0 + HALF_PIXEL,
        -155.0 - HALF_PIXEL,
        20.0 + HALF_PIXEL,
    ]
    egm_output = tmp_path / "egm.tif"
    hae_output = tmp_path / "hae.tif"
    temp_absolute_vrt = _write_absolute_vrt()
    vrt = os.path.join(DATA_PATH, "cop_global.vrt")
    cop_dem.download_and_stitch(
        output_name=str(egm_output), bbox=bbox, keep_egm=True,
        output_type="float32", vrt_filename=vrt,
    )
    cop_dem.download_and_stitch(
        output_name=str(hae_output), bbox=bbox, keep_egm=False,
        output_type="float32", vrt_filename=vrt,
    )
    os.remove(temp_absolute_vrt)
    with rio.open(egm_output) as src:
        egm = src.read(1)
    with rio.open(hae_output) as src:
        hae = src.read(1)
        transform = src.transform

    ocean = egm == 0
    land = egm > 5
    assert ocean.sum() > 1000 and land.sum() > 1000
    # Land moved by the geoid undulation, which is large around Hawaii.
    assert abs(np.median(hae[land] - egm[land])) > 5.0
    # No shoreline cliff: the ocean is no longer pinned to 0 m ellipsoidal.
    assert np.abs(hae[ocean]).min() > 1.0

    # Ocean pixels must sit at the geoid undulation of their own location.
    # The undulation changes by meters across this tile, so compare per
    # pixel rather than land against ocean.
    rows, cols = np.nonzero(ocean)
    rng = np.random.default_rng(0)
    for i in rng.choice(rows.size, size=20, replace=False):
        lon, lat = transform * (cols[i] + 0.5, rows[i] + 0.5)
        assert abs(hae[rows[i], cols[i]] - undulation(lon, lat)) < 0.5
