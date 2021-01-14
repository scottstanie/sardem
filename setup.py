import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="sardem",
    version="0.4.5",
    author="Scott Staniewicz",
    author_email="scott.stanie@utexas.com",
    description="Create upsampled DEMs for InSAR processing",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/scottstanie/sardem",
    packages=setuptools.find_packages(),
    include_package_data=True,
    classifiers=[
        "Programming Language :: Python",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3.3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: C",
        "License :: OSI Approved :: MIT License",
        "Topic :: Scientific/Engineering",
        "Intended Audience :: Science/Research",
    ],
    install_requires=["numpy", "requests"],
    entry_points={
        "console_scripts": [
            "createdem=sardem.cli:cli",
        ],
    },
    ext_modules=[
        setuptools.Extension(
            "sardem.upsample_cy",
            ["sardem/cython/upsample_cy.pyx"],
            extra_compile_args=["-O3", "-std=gnu99"],
        )
    ],
    zip_safe=False,
)
