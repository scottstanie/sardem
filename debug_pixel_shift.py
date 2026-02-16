"""Debug the 1-pixel shift between COP and NISAR DEMs from sardem.

Strategy:
1. Read raw COP tile directly from S3 (no reprojection)
2. Read raw NISAR tile area directly from VRT (no reprojection)
3. Create DEMs with sardem for both COP and NISAR at the same bbox
4. Compare raw tiles to each other and to sardem outputs

Tile: Copernicus_DSM_COG_10_N31_00_W104_00_DEM
Covers: lon [-104, -103], lat [31, 32]
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from osgeo import gdal

gdal.UseExceptions()

# -- Configuration --
BBOX = (-104, 31, -103, 32)  # (left, bottom, right, top)
OUT_DIR = Path("debug_shift")
OUT_DIR.mkdir(exist_ok=True)

COP_TILE_URL = (
    "/vsicurl/https://copernicus-dem-30m.s3.amazonaws.com/"
    "Copernicus_DSM_COG_10_N31_00_W104_00_DEM/"
    "Copernicus_DSM_COG_10_N31_00_W104_00_DEM.tif"
)

# ============================================================
# Step 1: Read raw COP tile
# ============================================================
print("=" * 60)
print("Step 1: Read raw COP tile")
print("=" * 60)
ds = gdal.Open(COP_TILE_URL)
cop_gt = ds.GetGeoTransform()
cop_raw = ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
print(f"  COP tile shape: {cop_raw.shape}")
print(f"  COP GeoTransform: {cop_gt}")
print(f"  COP UL pixel center: ({cop_gt[0] + cop_gt[1]/2:.10f}, {cop_gt[3] + cop_gt[5]/2:.10f})")
print(f"  COP pixel edges: X=[{cop_gt[0]:.10f}, {cop_gt[0] + cop_gt[1]*ds.RasterXSize:.10f}]")
print(f"                    Y=[{cop_gt[3] + cop_gt[5]*ds.RasterYSize:.10f}, {cop_gt[3]:.10f}]")
ds = None

# ============================================================
# Step 2: Read raw NISAR tile area
# ============================================================
print("\n" + "=" * 60)
print("Step 2: Read raw NISAR tile area (same extent as COP tile)")
print("=" * 60)
from sardem.nisar_dem import _configure_gdal_auth

_configure_gdal_auth()
nisar_vrt = "/vsicurl/https://nisar.asf.earthdatacloud.nasa.gov/NISAR/DEM/v1.2/EPSG4326/EPSG4326.vrt"

# Read NISAR using the same pixel extent as the COP tile (pixel edges)
nisar_raw_file = str(OUT_DIR / "nisar_raw_tile.tif")
gdal.Warp(
    nisar_raw_file,
    nisar_vrt,
    options=gdal.WarpOptions(
        format="GTiff",
        outputBounds=(cop_gt[0], cop_gt[3] + cop_gt[5] * 3600, cop_gt[0] + cop_gt[1] * 3600, cop_gt[3]),
        xRes=abs(cop_gt[1]),
        yRes=abs(cop_gt[5]),
        resampleAlg="nearest",
    ),
)
ds = gdal.Open(nisar_raw_file)
nisar_gt = ds.GetGeoTransform()
nisar_raw = ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
print(f"  NISAR tile shape: {nisar_raw.shape}")
print(f"  NISAR GeoTransform: {nisar_gt}")
ds = None

# Compare raw COP vs raw NISAR at same pixel positions
# NISAR = COP + geoid_undulation (roughly), so difference should be smooth
diff_raw = nisar_raw - cop_raw
print(f"\n  Raw NISAR - COP (geoid undulation signal):")
print(f"    mean={diff_raw.mean():.4f} std={diff_raw.std():.4f}")
print(f"    min={diff_raw.min():.4f} max={diff_raw.max():.4f}")

# ============================================================
# Step 3: Create DEMs with sardem
# ============================================================
print("\n" + "=" * 60)
print("Step 3: Create DEMs with sardem for bbox", BBOX)
print("=" * 60)
import sardem.dem

cop_dem_file = str(OUT_DIR / "cop_sardem.tif")
nisar_dem_file = str(OUT_DIR / "nisar_sardem.tif")

print("\n  Creating COP DEM...")
sardem.dem.main(output_name=cop_dem_file, bbox=BBOX, data_source="COP", output_type="float32")

print("\n  Creating NISAR DEM...")
sardem.dem.main(output_name=nisar_dem_file, bbox=BBOX, data_source="NISAR", output_type="float32")

# ============================================================
# Step 4: Read and compare sardem outputs
# ============================================================
print("\n" + "=" * 60)
print("Step 4: Compare sardem outputs")
print("=" * 60)


def read_tif(path):
    ds = gdal.Open(path)
    gt = ds.GetGeoTransform()
    arr = ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
    ds = None
    return arr, gt


cop_sardem, cop_sardem_gt = read_tif(cop_dem_file)
nisar_sardem, nisar_sardem_gt = read_tif(nisar_dem_file)

print(f"  COP sardem:  shape={cop_sardem.shape}  GT={cop_sardem_gt}")
print(f"  NISAR sardem: shape={nisar_sardem.shape} GT={nisar_sardem_gt}")

diff_sardem = cop_sardem - nisar_sardem
print(f"\n  COP_sardem - NISAR_sardem (should be ~0 if aligned):")
print(f"    mean={diff_sardem.mean():.4f} std={diff_sardem.std():.4f}")
print(f"    min={diff_sardem.min():.4f} max={diff_sardem.max():.4f}")
print(f"    |max|={np.abs(diff_sardem).max():.4f}")

# ============================================================
# Step 5: Test pixel shifts
# ============================================================
print("\n" + "=" * 60)
print("Step 5: Test if 1-pixel shifts improve alignment")
print("=" * 60)

# Try all 1-pixel shifts between cop_sardem and nisar_sardem
c = cop_sardem
n = nisar_sardem
shifts = {
    "(0,0) no shift": (c, n),
    "(0,+1) nisar shifted right": (c[:, 1:], n[:, :-1]),
    "(0,-1) nisar shifted left": (c[:, :-1], n[:, 1:]),
    "(+1,0) nisar shifted down": (c[1:, :], n[:-1, :]),
    "(-1,0) nisar shifted up": (c[:-1, :], n[1:, :]),
    "(+1,+1) nisar shifted down-right": (c[1:, 1:], n[:-1, :-1]),
    "(-1,-1) nisar shifted up-left": (c[:-1, :-1], n[1:, 1:]),
    "(+1,-1) nisar shifted down-left": (c[1:, :-1], n[:-1, 1:]),
    "(-1,+1) nisar shifted up-right": (c[:-1, 1:], n[1:, :-1]),
}

print(f"  {'Shift':<40} {'|max|':>10} {'std':>10} {'mean':>10}")
print("  " + "-" * 72)
for label, (a, b) in shifts.items():
    d = a - b
    print(f"  {label:<40} {np.abs(d).max():10.4f} {d.std():10.4f} {d.mean():10.4f}")

# ============================================================
# Step 6: Compare raw tiles to sardem outputs
# ============================================================
print("\n" + "=" * 60)
print("Step 6: Compare raw COP tile to COP sardem output")
print("=" * 60)
print(f"  Raw COP tile: shape={cop_raw.shape}, GT origin=({cop_gt[0]:.10f}, {cop_gt[3]:.10f})")
print(f"  COP sardem:   shape={cop_sardem.shape}, GT origin=({cop_sardem_gt[0]:.10f}, {cop_sardem_gt[3]:.10f})")

# The COP sardem output went through EGM2008->WGS84 conversion, so values differ.
# But we can also create a COP DEM with keep_egm=True to compare directly
cop_egm_file = str(OUT_DIR / "cop_sardem_egm.tif")
print("\n  Creating COP DEM with keep_egm=True (no vertical conversion)...")
sardem.dem.main(output_name=cop_egm_file, bbox=BBOX, data_source="COP", output_type="float32", keep_egm=True)
cop_egm, cop_egm_gt = read_tif(cop_egm_file)
print(f"  COP EGM sardem: shape={cop_egm.shape}, GT={cop_egm_gt}")

# Now the COP EGM values should match the raw tile (both are geoid heights)
# Test all pixel shifts between raw tile and sardem EGM output
print(f"\n  Testing shifts: raw COP tile vs COP_sardem(keep_egm=True)")
r = cop_raw
s = cop_egm
shifts_raw = {
    "(0,0) no shift": (r, s),
    "(0,+1) sardem shifted right": (r[:, 1:], s[:, :-1]),
    "(0,-1) sardem shifted left": (r[:, :-1], s[:, 1:]),
    "(+1,0) sardem shifted down": (r[1:, :], s[:-1, :]),
    "(-1,0) sardem shifted up": (r[:-1, :], s[1:, :]),
}
print(f"  {'Shift':<40} {'|max|':>10} {'std':>10} {'mean':>10}")
print("  " + "-" * 72)
for label, (a, b) in shifts_raw.items():
    d = a - b
    print(f"  {label:<40} {np.abs(d).max():10.4f} {d.std():10.4f} {d.mean():10.4f}")


# ============================================================
# Step 7: Compare raw NISAR tile to NISAR sardem output
# ============================================================
print("\n" + "=" * 60)
print("Step 7: Compare raw NISAR tile to NISAR sardem output")
print("=" * 60)
r = nisar_raw
s = nisar_sardem
shifts_nisar = {
    "(0,0) no shift": (r, s),
    "(0,+1) sardem shifted right": (r[:, 1:], s[:, :-1]),
    "(0,-1) sardem shifted left": (r[:, :-1], s[:, 1:]),
    "(+1,0) sardem shifted down": (r[1:, :], s[:-1, :]),
    "(-1,0) sardem shifted up": (r[:-1, :], s[1:, :]),
}
print(f"  {'Shift':<40} {'|max|':>10} {'std':>10} {'mean':>10}")
print("  " + "-" * 72)
for label, (a, b) in shifts_nisar.items():
    d = a - b
    print(f"  {label:<40} {np.abs(d).max():10.4f} {d.std():10.4f} {d.mean():10.4f}")
