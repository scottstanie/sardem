import logging

import numpy as np

from sardem import loading, utils

logger = logging.getLogger("sardem")
utils.set_logger_handler(logger)


def upsample_by_blocks(
    filename, outfile, input_shape, block_rows, dtype, xrate=1, yrate=1
):
    """Perform bilinear upsampling on a raster by blocks

    Parameters
    ----------
    filename : str
        Name of input file
    outfile : str
        Name of output file
    input_shape : tuple[int, int]
        Shape of input raster `filename`
    block_rows : int
        Number of rows to read in at a time per block
    dtype : str, np.dtype
        data type of input raster
    xrate : int, optional.
        Rate to upsample in the x/column direction
        Default = 1, no upsampling
    yrate : int, optional
        Rate to upsample in the y/row direction
        Default = 1, no upsampling
    """
    _, total_cols = input_shape
    block_shape = (block_rows, total_cols)

    dtype = np.dtype(dtype)
    with open(outfile, "wb") as f:
        for rows, _ in block_iterator(input_shape, block_shape):
            offset = total_cols * rows[0] * dtype.itemsize
            cur_block_shape = (rows[1] - rows[0], total_cols)
            logging.info("Upsampling rows {}".format(rows))
            print("Upsampling rows {}".format(rows))
            cur_block = np.memmap(
                filename,
                mode="r",
                dtype=dtype,
                offset=offset,
                shape=cur_block_shape,
            )
            # always upsample as a float
            cur_block_upsampled = upsample(cur_block.astype("float32"), xrate, yrate)
            # then convert back to the original dtype
            if np.issubdtype(dtype, np.integer):
                cur_block_upsampled = np.round(cur_block_upsampled)
            cur_block_upsampled.astype(dtype).tofile(f)


def bilinear_interpolate(arr, x, y):
    x = np.asarray(x)
    y = np.asarray(y)

    x0 = np.floor(x).astype(int)
    x1 = x0 + 1
    y0 = np.floor(y).astype(int)
    y1 = y0 + 1

    wa = (x1 - x) * (y1 - y)
    wb = (x1 - x) * (y - y0)
    wc = (x - x0) * (y1 - y)
    wd = (x - x0) * (y - y0)

    x0 = np.clip(x0, 0, arr.shape[1] - 1)
    x1 = np.clip(x1, 0, arr.shape[1] - 1)
    y0 = np.clip(y0, 0, arr.shape[0] - 1)
    y1 = np.clip(y1, 0, arr.shape[0] - 1)

    Ia = arr[y0, x0]
    Ib = arr[y1, x0]
    Ic = arr[y0, x1]
    Id = arr[y1, x1]

    return wa * Ia + wb * Ib + wc * Ic + wd * Id


def upsample(arr, xrate, yrate):
    """Upsample an array by a factor of xrate and yrate"""
    ny, nx = arr.shape

    xi = np.linspace(0, arr.shape[1] - 1, round(nx * xrate)).reshape((1, -1))
    yi = np.linspace(0, arr.shape[0] - 1, round(ny * yrate)).reshape((-1, 1))
    return bilinear_interpolate(arr, xi, yi)


def block_iterator(arr_shape, block_shape):
    """Iterator to get indexes for accessing blocks of a raster

    Args:
        arr_shape = (num_rows, num_cols), full size of array to access
        block_shape = (height, width), size of accessing blocks
    Yields:
        iterator: ((row_start, row_end), (col_start, col_end))

    Notes:
        If the block_shape/overlaps don't evenly divide the full arr_shape,
        It will return the edges as smaller blocks, rather than skip them

    Examples:
    >>> list(block_iterator((180, 250), (100, 100)))
    [((0, 100), (0, 100)), ((0, 100), (100, 200)), ((0, 100), (200, 250)), \
((100, 180), (0, 100)), ((100, 180), (100, 200)), ((100, 180), (200, 250))]
    """
    rows, cols = arr_shape
    row_off, col_off = 0, 0
    height, width = block_shape

    if height is None:
        height = rows
    if width is None:
        width = cols

    # Check we're not moving backwards with the overlap:
    while row_off < rows:
        while col_off < cols:
            row_end = min(row_off + height, rows)  # Dont yield something OOB
            col_end = min(col_off + width, cols)
            yield ((row_off, row_end), (col_off, col_end))

            col_off += width

        row_off += height
        col_off = 0


def upsample_dem_rsc(xrate=None, yrate=None, rsc_dict=None, rsc_filename=None):
    """Creates a new .dem.rsc file for upsampled version

    Adjusts the FILE_LENGTH, WIDTH, X_STEP, Y_STEP for new rate

    Args:
        xrate (int): rate in x direcion to upsample the DEM
        yrate (int): rate in y direcion to upsample the DEM
        rsc_dict (str): Optional, the rsc data from Stitcher.create_dem_rsc()
        filepath (str): Optional, location of .dem.rsc file

    Note: Must supply only one of rsc_dict or rsc_filename

    Returns:
        str: file same as original with upsample adjusted numbers

    Raises:
        TypeError: if neither (or both) rsc_filename and rsc_dict are given

    """
    if not xrate and not yrate:
        raise ValueError("Must supply either xrate or yrate for upsampling")

    rsc_dict = _load_rsc_dict(rsc_dict=rsc_dict, rsc_filename=rsc_filename)

    xrate = xrate or 1
    yrate = yrate or 1
    outstring = ""
    for field, value in rsc_dict.items():
        # Files seemed to be left justified with 13 spaces? Not sure why 13
        # TODO: its 14- but fix this and previous formatting to be DRY
        if field.lower() == "width":
            new_size = int(round(value * xrate))
            outstring += "{field:<14s}{val}\n".format(field=field.upper(), val=new_size)
        elif field.lower() == "file_length":
            new_size = int(round(value * yrate))
            outstring += "{field:<14s}{val}\n".format(field=field.upper(), val=new_size)
        elif field.lower() == "x_step":
            # New is 1 + (size - 1) * rate, old is size, old rate is 1/(size-1)
            value /= xrate
            # Also give step floats proper sig figs to not output scientific notation
            outstring += "{field:<14s}{val:0.12f}\n".format(
                field=field.upper(), val=value
            )
        elif field.lower() == "y_step":
            value /= yrate
            outstring += "{field:<14s}{val:0.12f}\n".format(
                field=field.upper(), val=value
            )
        else:
            outstring += "{field:<14s}{val}\n".format(field=field.upper(), val=value)

    return outstring


def _load_rsc_dict(rsc_dict=None, rsc_filename=None):
    if rsc_dict and rsc_filename:
        raise ValueError("Can only give one of rsc_dict or rsc_filename")
    elif not rsc_dict and not rsc_filename:
        raise ValueError("Must give at least one of rsc_dict or rsc_filename")

    if rsc_filename:
        rsc_dict = loading.load_dem_rsc(rsc_filename)
    return rsc_dict
