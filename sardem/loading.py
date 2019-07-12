from __future__ import division
import collections
import os
import numpy as np

INT_16_LE = np.dtype('<i2')
INT_16_BE = np.dtype('>i2')

RSC_KEY_TYPES = [
    ('width', int),
    ('file_length', int),
    ('x_first', float),
    ('y_first', float),
    ('x_step', float),
    ('y_step', float),
    ('x_unit', str),
    ('y_unit', str),
    ('z_offset', int),
    ('z_scale', int),
    ('projection', str),
]
RSC_KEYS = [tup[0] for tup in RSC_KEY_TYPES]

# in case only speciying rows/cols/steps, these always seem to be same
DEFAULT_KEYS = {
    'x_unit': 'degrees',
    'y_unit': 'degrees',
    'z_offset': 0,
    'z_scale': 1,
    'projection': 'LL',
}


def load_elevation(filename):
    """Loads a digital elevation map from either .hgt file or .dem

    .hgt is the NASA SRTM files given. Documentation on format here:
    https://dds.cr.usgs.gov/srtm/version2_1/Documentation/SRTM_Topo.pdf
    Key point: Big-endian 2 byte (16-bit) integers

    .dem is format used by Zebker geo-coded and ROI-PAC SAR software
    Only difference is data is stored little-endian (like other SAR data)

    Note on both formats: gaps in coverage are given by INT_MIN -32768,
    so either manually set data(data == np.min(data)) = 0,
        data = np.clip(data, 0, None), or when plotting, plt.imshow(data, vmin=0)
    """
    ext = os.path.splitext(filename)[1]
    data_type = INT_16_LE if ext == '.dem' else INT_16_BE
    data = np.fromfile(filename, dtype=data_type)
    # Make sure we're working with little endian
    if data_type == INT_16_BE:
        data = data.astype(INT_16_LE)

    # Reshape to correct size.
    # Either get info from .dem.rsc
    if ext == '.dem':
        info = load_dem_rsc(filename)
        dem_img = data.reshape((info['file_length'], info['width']))

    # Or check if we are using STRM1 (3601x3601) or SRTM3 (1201x1201)
    else:
        if (data.shape[0] / 3601) == 3601:
            # STRM1- 1 arc second data, 30 meter data
            dem_img = data.reshape((3601, 3601))
        elif (data.shape[0] / 1201) == 1201:
            # STRM3- 3 arc second data, 90 meter data
            dem_img = data.reshape((1201, 1201))
        else:
            raise ValueError("Invalid .hgt data size: must be square size 1201 or 3601")
        # TODO: Verify that the min real value will be above -1000
        min_valid = -1000
        # Set NaN values to 0
        dem_img[dem_img < min_valid] = 0

    return dem_img


def load_dem_rsc(filename, lower=False, **kwargs):
    """Loads and parses the .dem.rsc file

    Args:
        filename (str) path to either the .dem or .dem.rsc file.
            Function will add .rsc to path if passed .dem file
        lower (bool): make keys of the dict lowercase

    Returns:
        dict: dem.rsc file parsed out, keys are all caps

    example file:
    WIDTH         10801
    FILE_LENGTH   7201
    X_FIRST       -157.0
    Y_FIRST       21.0
    X_STEP        0.000277777777
    Y_STEP        -0.000277777777
    X_UNIT        degrees
    Y_UNIT        degrees
    Z_OFFSET      0
    Z_SCALE       1
    PROJECTION    LL
    """

    # Use OrderedDict so that upsample_dem_rsc creates with same ordering as old
    output_data = collections.OrderedDict()
    # Second part in tuple is used to cast string to correct type

    rsc_filename = '{}.rsc'.format(filename) if not filename.endswith('.rsc') else filename
    with open(rsc_filename, 'r') as f:
        for line in f.readlines():
            for field, num_type in RSC_KEY_TYPES:
                if line.startswith(field.upper()):
                    output_data[field] = num_type(line.split()[1])

    if lower:
        output_data = {k.lower(): d for k, d in output_data.items()}
    return output_data


def format_dem_rsc(rsc_dict):
    """Creates the .dem.rsc file string from key/value pairs of an OrderedDict

    Output of function can be written to a file as follows
        with open('my.dem.rsc', 'w') as f:
            f.write(outstring)

    Args:
        rsc_dict (OrderedDict): data about dem in ordered key/value format
            See `load_dem_rsc` output for example

    Returns:
        outstring (str) formatting string to be written to .dem.rsc

    """
    outstring = ""
    rsc_dict = {k.lower(): v for k, v in rsc_dict.items()}
    # for field, value in rsc_dict.items():
    for field in RSC_KEYS:
        # Make sure to skip extra keys that might be in the dict
        if field not in RSC_KEYS:
            continue

        value = rsc_dict.get(field, DEFAULT_KEYS.get(field))
        if value is None:
            raise ValueError("%s is necessary for .rsc file: missing from dict" % field)

        # Files seemed to be left justified with 14 spaces? Not sure why 14
        # Apparently it was an old fortran format, where they use "read(15)"
        if field in ('x_step', 'y_step'):
            # give step floats proper sig figs to not output scientific notation
            outstring += "{field:<14s}{val:0.12f}\n".format(field=field.upper(), val=value)
        else:
            outstring += "{field:<14s}{val}\n".format(field=field.upper(), val=value)

    return outstring
