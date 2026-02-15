import struct

import numpy as np
import pytest
import responses

from sardem.usgs_3dep import (
    EXPORT_URL,
    MAX_EXPORT_SIZE,
    _download_chunk,
    _download_in_chunks,
)


def _make_tiff_bytes(width=10, height=10):
    """Create a minimal valid TIFF file in memory for testing.

    Creates a simple single-strip TIFF with float32 pixel data.
    """
    # Pixel data: float32
    pixel_data = np.zeros((height, width), dtype=np.float32)
    pixel_bytes = pixel_data.tobytes()

    # TIFF structure: header + IFD + pixel data
    # We'll use a very minimal TIFF (little-endian)
    # Header: byte order (II) + magic (42) + offset to first IFD
    ifd_offset = 8  # right after header
    header = struct.pack("<2sHI", b"II", 42, ifd_offset)

    # IFD entries (each 12 bytes): tag, type, count, value/offset
    num_entries = 8
    pixel_data_offset = 8 + 2 + num_entries * 12 + 4  # header + count + entries + next_ifd

    entries = b""
    # ImageWidth (256)
    entries += struct.pack("<HHII", 256, 3, 1, width)
    # ImageLength (257)
    entries += struct.pack("<HHII", 257, 3, 1, height)
    # BitsPerSample (258) - 32 for float32
    entries += struct.pack("<HHII", 258, 3, 1, 32)
    # SampleFormat (339) - 3 = IEEE floating point
    entries += struct.pack("<HHII", 339, 3, 1, 3)
    # Compression (259) - 1 = no compression
    entries += struct.pack("<HHII", 259, 3, 1, 1)
    # PhotometricInterpretation (262) - 1 = min is black
    entries += struct.pack("<HHII", 262, 3, 1, 1)
    # StripOffsets (273) - offset to pixel data
    entries += struct.pack("<HHII", 273, 3, 1, pixel_data_offset)
    # StripByteCounts (279)
    entries += struct.pack("<HHII", 279, 3, 1, len(pixel_bytes))

    ifd = struct.pack("<H", num_entries) + entries + struct.pack("<I", 0)  # next IFD = 0

    return header + ifd + pixel_bytes


@responses.activate
def test_download_chunk_success(tmp_path):
    """Test that _download_chunk successfully downloads and saves a TIFF."""
    tiff_bytes = _make_tiff_bytes(10, 10)
    responses.add(
        responses.GET,
        EXPORT_URL,
        body=tiff_bytes,
        status=200,
        content_type="image/tiff",
    )

    result = _download_chunk(-105.1, 40.0, -105.0, 40.1, 360, 360, str(tmp_path))

    assert result.endswith(".tif")
    with open(result, "rb") as f:
        content = f.read()
    assert content == tiff_bytes


@responses.activate
def test_download_chunk_error_response(tmp_path):
    """Test that _download_chunk raises on non-image response."""
    error_body = b'{"error": {"message": "Invalid request"}}'
    responses.add(
        responses.GET,
        EXPORT_URL,
        body=error_body,
        status=200,
        content_type="application/json",
    )

    with pytest.raises(RuntimeError, match="3DEP server did not return image data"):
        _download_chunk(-105.1, 40.0, -105.0, 40.1, 360, 360, str(tmp_path))


@responses.activate
def test_download_chunk_http_error(tmp_path):
    """Test that _download_chunk raises on HTTP errors."""
    responses.add(responses.GET, EXPORT_URL, status=500)

    with pytest.raises(Exception):
        _download_chunk(-105.1, 40.0, -105.0, 40.1, 360, 360, str(tmp_path))


@responses.activate
def test_download_in_chunks_single(tmp_path):
    """Test that a small area results in a single chunk."""
    tiff_bytes = _make_tiff_bytes(100, 100)
    responses.add(
        responses.GET,
        EXPORT_URL,
        body=tiff_bytes,
        status=200,
        content_type="image/tiff",
    )

    files = _download_in_chunks(-105.1, 40.0, -105.0, 40.1, 100, 100, str(tmp_path))

    assert len(files) == 1


@responses.activate
def test_download_in_chunks_multiple(tmp_path):
    """Test that a large area is split into multiple chunks."""
    tiff_bytes = _make_tiff_bytes(100, 100)

    # Add enough mocked responses for all expected chunks
    for _ in range(4):
        responses.add(
            responses.GET,
            EXPORT_URL,
            body=tiff_bytes,
            status=200,
            content_type="image/tiff",
        )

    # Request a size larger than MAX_EXPORT_SIZE in both dimensions
    large = MAX_EXPORT_SIZE + 100
    files = _download_in_chunks(-106.0, 39.0, -105.0, 40.0, large, large, str(tmp_path))

    assert len(files) == 4  # 2x2 chunks


def test_download_chunk_request_params(tmp_path):
    """Test that _download_chunk sends the correct request parameters."""
    tiff_bytes = _make_tiff_bytes(10, 10)

    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            EXPORT_URL,
            body=tiff_bytes,
            status=200,
            content_type="image/tiff",
        )

        _download_chunk(-105.1, 40.0, -105.0, 40.1, 360, 360, str(tmp_path))

        # Check the request parameters
        assert len(rsps.calls) == 1
        request_url = rsps.calls[0].request.url
        assert "bboxSR=4326" in request_url
        assert "imageSR=4326" in request_url
        assert "format=tiff" in request_url
        assert "pixelType=F32" in request_url
        assert "f=image" in request_url
        assert "size=360%2C360" in request_url or "size=360,360" in request_url
