import json

import pytest
import responses

from sardem.usgs_3dep_1m import TNM_API_URL, _find_tile_urls


def _make_tnm_response(items):
    """Build a fake TNM API JSON response body."""
    return json.dumps({"items": items})


def _make_item(url, date_created="2020-01-01"):
    """Build a minimal TNM API item dict."""
    return {"downloadURL": url, "dateCreated": date_created}


@responses.activate
def test_find_tile_urls_success():
    """Mock TNM API response, verify URL extraction and sorting."""
    items = [
        _make_item("https://prd-tnm.s3.amazonaws.com/tile_newer.tif", "2022-06-15"),
        _make_item("https://prd-tnm.s3.amazonaws.com/tile_older.tif", "2019-03-01"),
    ]
    responses.add(
        responses.GET,
        TNM_API_URL,
        body=_make_tnm_response(items),
        status=200,
        content_type="application/json",
    )

    urls = _find_tile_urls((-118.4, 33.7, -118.3, 33.8))

    assert len(urls) == 2
    # Oldest first so newest overwrites in gdal.Warp
    assert "tile_older" in urls[0]
    assert "tile_newer" in urls[1]


@responses.activate
def test_find_tile_urls_empty():
    """Mock empty response, verify RuntimeError."""
    responses.add(
        responses.GET,
        TNM_API_URL,
        body=_make_tnm_response([]),
        status=200,
        content_type="application/json",
    )

    with pytest.raises(RuntimeError, match="No 3DEP 1m DEM tiles found"):
        _find_tile_urls((-118.4, 33.7, -118.3, 33.8))


@responses.activate
def test_find_tile_urls_http_error():
    """Mock 500, verify exception."""
    responses.add(responses.GET, TNM_API_URL, status=500)

    with pytest.raises(Exception):
        _find_tile_urls((-118.4, 33.7, -118.3, 33.8))
