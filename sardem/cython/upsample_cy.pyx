"""This .pyx file gets compiled with cython to provide a wrapper
for calling the upsample.c code in python (in dem.py)
upsample_cy.c is the auto-generated cython code
"""
from sardem.cython cimport upsample_cy

def upsample_wrap(filename, xrate, yrate, ncols, nrows, outfileUp="elevation.dem"):
    """Wrapper to call the c upsample function in python. Used in dem.py

    Args:
      filename (str): name of .dem file to open
      xrate (int): upsampling rate in x dir, positive int
      yrate (int): upsampling rate in y dir, positive int
      ncols (int): number of columns in dem
      nrows (int): number of rows in dem
      outfileUp (str): name of output, upsampled file to write to
    """
    upsample_cy.upsample(filename=filename, xrate=xrate, yrate=yrate, ncols=ncols, 
                         nrows=nrows, outfileUp=outfileUp)
