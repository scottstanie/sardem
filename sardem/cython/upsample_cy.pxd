cdef extern from "upsample.c":
    # cpdef exports the c function as accessible from python
    int upsample(const char *filename, const int rate, const long ncols, const long nrows, const char *outfileUp)
