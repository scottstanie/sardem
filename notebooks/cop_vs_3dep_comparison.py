# ---
# jupyter:
#   jupytext:
#     formats: py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
# ---

# %% [markdown]
# # COP vs USGS 3DEP DEM comparison
#
# COP (Copernicus GLO-30) is a **radar-based surface model** (TanDEM-X C-band SAR)
# that reflects the top of whatever the radar sees: tree canopy, buildings, etc.
#
# USGS 3DEP is a **LiDAR-derived bare-earth model** — the LiDAR point cloud is
# classified and ground points are used to build the DEM, so vegetation and
# buildings are stripped away.
#
# This fundamental difference should produce dramatic elevation discrepancies in
# areas with tall vegetation or dense urban development.
#
# | Source | Type | Datum (native) | Resolution |
# |--------|------|---------------|------------|
# | **COP** (GLO-30) | DSM (radar surface) | EGM2008 | 1 arc-sec (~30 m) |
# | **3DEP** | DEM (bare earth, LiDAR) | NAVD88 | up to 1 m (resampled to 1 arc-sec) |
#
# Both are converted to WGS84 ellipsoidal heights by `sardem`.

# %%
from __future__ import annotations

from pathlib import Path

import numpy as np
from osgeo import gdal

gdal.UseExceptions()


# %% [markdown]
# ## Helper functions


# %%
def fetch_dem(bbox: tuple, data_source: str, output: str) -> None:
    """Download a DEM for the given source and bounding box."""
    import sardem.dem

    print(f"Fetching {data_source} DEM -> {output}")
    sardem.dem.main(
        output_name=output, bbox=bbox, data_source=data_source, output_type="float32",
    )


def read_dem(path: str) -> tuple[np.ma.MaskedArray, gdal.Dataset]:
    """Read a single-band raster into a masked float32 array; also return the dataset."""
    ds = gdal.Open(path)
    band = ds.GetRasterBand(1)
    arr = band.ReadAsArray().astype(np.float32)
    nodata = band.GetNoDataValue()
    if nodata is not None:
        arr = np.ma.masked_equal(arr, nodata)
    else:
        arr = np.ma.array(arr)
    return arr, ds


def get_extent(ds: gdal.Dataset) -> list[float]:
    """Return [left, right, bottom, top] for imshow extent from a GDAL dataset."""
    gt = ds.GetGeoTransform()
    left = gt[0]
    top = gt[3]
    right = left + gt[1] * ds.RasterXSize
    bottom = top + gt[5] * ds.RasterYSize
    return [left, right, bottom, top]


# %% [markdown]
# ## Area 1 — Olympic Peninsula old-growth forest (Washington)
#
# The Hoh Rainforest contains some of the tallest trees in the Pacific Northwest:
# Sitka spruce reaching 60-80 m.  COP's C-band radar scatters off the canopy
# tops, while 3DEP's LiDAR ground classification penetrates to bare earth.
# We expect COP to be **systematically higher** than 3DEP throughout the forest,
# with differences of 30-60+ m in old-growth stands.

# %%
bbox_olympic = (-123.95, 47.82, -123.80, 47.92)
area1_dir = Path("area1_olympic")
area1_dir.mkdir(exist_ok=True)

sources = ["COP", "3DEP"]
LABELS = {"COP": "COP (radar surface)", "3DEP": "3DEP (bare earth)"}

area1_files = {s: str(area1_dir / f"olympic_{s.lower()}.tif") for s in sources}

for src in sources:
    fetch_dem(bbox_olympic, src, area1_files[src])

# %%
dems_olympic = {}
extents_olympic = {}
for src in sources:
    arr, ds = read_dem(area1_files[src])
    dems_olympic[src] = arr
    extents_olympic[src] = get_extent(ds)
    ds = None

shapes = {s: arr.shape for s, arr in dems_olympic.items()}
print("Shapes:", shapes)
assert len(set(shapes.values())) == 1, f"Shape mismatch: {shapes}"

extent = extents_olympic["COP"]

# %% [markdown]
# ### Side-by-side elevation maps

# %%
import matplotlib.pyplot as plt

fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharex=True, sharey=True)
vmin = min(arr.min() for arr in dems_olympic.values())
vmax = max(arr.max() for arr in dems_olympic.values())

for ax, src in zip(axes, sources):
    im = ax.imshow(
        dems_olympic[src], vmin=vmin, vmax=vmax, cmap="terrain", extent=extent,
    )
    ax.set_title(LABELS[src])
    ax.set_xlabel("Longitude")
axes[0].set_ylabel("Latitude")
fig.colorbar(im, ax=axes, label="Elevation [m, WGS84]", shrink=0.8)
fig.suptitle("Olympic Peninsula — Elevation", y=1.02)
fig.savefig("olympic_elevation.png", dpi=150, bbox_inches="tight")

# %% [markdown]
# ### Difference map (COP - 3DEP)
#
# Positive values = COP higher than 3DEP = canopy height signal.

# %%
diff_olympic = dems_olympic["COP"] - dems_olympic["3DEP"]

fig, ax = plt.subplots(figsize=(10, 7))
im = ax.imshow(diff_olympic, cmap="RdBu_r", vmin=-20, vmax=80, extent=extent)
ax.set_title("COP - 3DEP  (positive = canopy/surface above bare earth)")
ax.set_xlabel("Longitude")
ax.set_ylabel("Latitude")
fig.colorbar(im, ax=ax, label="Difference [m]", shrink=0.8)
fig.savefig("olympic_diff.png", dpi=150, bbox_inches="tight")

# %% [markdown]
# ### Histogram of differences

# %%
fig, ax = plt.subplots(figsize=(8, 4))
ax.hist(diff_olympic.compressed(), bins=200, range=(-20, 100), edgecolor="none", alpha=0.8)
ax.axvline(np.ma.median(diff_olympic), color="red", ls="--", label=f"median = {np.ma.median(diff_olympic):.1f} m")
ax.axvline(diff_olympic.mean(), color="orange", ls="--", label=f"mean = {diff_olympic.mean():.1f} m")
ax.set_xlabel("COP - 3DEP [m]")
ax.set_ylabel("Pixel count")
ax.set_title("Olympic Peninsula — COP minus 3DEP distribution")
ax.legend()
fig.savefig("olympic_hist.png", dpi=150, bbox_inches="tight")

# %% [markdown]
# ### Summary statistics

# %%
print(f"{'Statistic':<12} {'Value':>10}")
print("-" * 24)
for name, fn in [("mean", np.ma.mean), ("median", np.ma.median), ("std", np.ma.std),
                 ("min", np.ma.min), ("max", np.ma.max)]:
    print(f"{name:<12} {fn(diff_olympic):10.2f} m")

# %% [markdown]
# ## Area 2 — San Francisco (California)
#
# Dense urban core with skyscrapers (Salesforce Tower 326 m, Transamerica Pyramid
# 260 m) surrounded by steep residential hills.  COP radar sees building rooftops;
# 3DEP LiDAR extracts bare earth.  We expect large positive COP-3DEP spikes
# at tall buildings and smaller but still visible effects in residential areas.

# %%
bbox_sf = (-122.44, 37.76, -122.38, 37.81)
area2_dir = Path("area2_sf")
area2_dir.mkdir(exist_ok=True)

area2_files = {s: str(area2_dir / f"sf_{s.lower()}.tif") for s in sources}

for src in sources:
    fetch_dem(bbox_sf, src, area2_files[src])

# %%
dems_sf = {}
extents_sf = {}
for src in sources:
    arr, ds = read_dem(area2_files[src])
    dems_sf[src] = arr
    extents_sf[src] = get_extent(ds)
    ds = None

shapes = {s: arr.shape for s, arr in dems_sf.items()}
print("Shapes:", shapes)
assert len(set(shapes.values())) == 1, f"Shape mismatch: {shapes}"

extent_sf = extents_sf["COP"]

# %% [markdown]
# ### Side-by-side elevation maps

# %%
fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharex=True, sharey=True)
vmin = min(arr.min() for arr in dems_sf.values())
vmax = max(arr.max() for arr in dems_sf.values())

for ax, src in zip(axes, sources):
    im = ax.imshow(
        dems_sf[src], vmin=vmin, vmax=vmax, cmap="terrain", extent=extent_sf,
    )
    ax.set_title(LABELS[src])
    ax.set_xlabel("Longitude")
axes[0].set_ylabel("Latitude")
fig.colorbar(im, ax=axes, label="Elevation [m, WGS84]", shrink=0.8)
fig.suptitle("San Francisco — Elevation", y=1.02)
fig.savefig("sf_elevation.png", dpi=150, bbox_inches="tight")

# %% [markdown]
# ### Difference map (COP - 3DEP)

# %%
diff_sf = dems_sf["COP"] - dems_sf["3DEP"]

fig, ax = plt.subplots(figsize=(10, 7))
im = ax.imshow(diff_sf, cmap="RdBu_r", vmin=-10, vmax=50, extent=extent_sf)
ax.set_title("COP - 3DEP  (positive = buildings/surface above bare earth)")
ax.set_xlabel("Longitude")
ax.set_ylabel("Latitude")
fig.colorbar(im, ax=ax, label="Difference [m]", shrink=0.8)
fig.savefig("sf_diff.png", dpi=150, bbox_inches="tight")

# %% [markdown]
# ### Histogram of differences

# %%
fig, ax = plt.subplots(figsize=(8, 4))
ax.hist(diff_sf.compressed(), bins=200, range=(-20, 60), edgecolor="none", alpha=0.8)
ax.axvline(np.ma.median(diff_sf), color="red", ls="--", label=f"median = {np.ma.median(diff_sf):.1f} m")
ax.axvline(diff_sf.mean(), color="orange", ls="--", label=f"mean = {diff_sf.mean():.1f} m")
ax.set_xlabel("COP - 3DEP [m]")
ax.set_ylabel("Pixel count")
ax.set_title("San Francisco — COP minus 3DEP distribution")
ax.legend()
fig.savefig("sf_hist.png", dpi=150, bbox_inches="tight")

# %% [markdown]
# ### Summary statistics

# %%
print(f"{'Statistic':<12} {'Value':>10}")
print("-" * 24)
for name, fn in [("mean", np.ma.mean), ("median", np.ma.median), ("std", np.ma.std),
                 ("min", np.ma.min), ("max", np.ma.max)]:
    print(f"{name:<12} {fn(diff_sf):10.2f} m")

# %% [markdown]
# ## Discussion
#
# The key insight is that COP and 3DEP measure fundamentally different things:
#
# - **COP** is a Digital Surface Model (DSM) derived from X-band SAR radar
#   (TanDEM-X). The radar scatters off the first surface it hits: tree canopy,
#   building rooftops, etc.
#
# - **3DEP** is a Digital Elevation Model (DEM) derived from classified LiDAR
#   point clouds. Ground returns are separated from vegetation/building returns,
#   so the result is a bare-earth surface.
#
# **Olympic Peninsula (forest):**
# COP should be systematically 30-60+ m higher than 3DEP across forested areas,
# reflecting the canopy height of old-growth Sitka spruce and western hemlock.
# The difference map is effectively a proxy for canopy height — a valuable
# remote sensing product in its own right.
#
# **San Francisco (urban):**
# COP should show elevation spikes at tall buildings in the Financial District
# and SoMa, while 3DEP shows the true ground level. Residential neighborhoods
# on hills should show smaller differences (1-2 story buildings at 30 m
# resolution are mostly averaged out). The difference map reveals the urban
# built environment.
#
# Both areas also have a datum conversion difference: COP converts from EGM2008,
# while 3DEP converts from NAVD88. This adds a small (~1 m) spatially smooth
# offset that is dwarfed by the DSM-vs-DEM signal.
