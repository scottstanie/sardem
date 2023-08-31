import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="sardem",
    version="0.12.0",
    author="Scott Staniewicz",
    author_email="scott.stanie@gmail.com",
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
        "License :: OSI Approved :: MIT License",
        "Topic :: Scientific/Engineering",
        "Intended Audience :: Science/Research",
    ],
    install_requires=["numpy", "requests", "shapely"],
    entry_points={
        "console_scripts": [
            "sardem=sardem.cli:cli",
        ],
    },
    zip_safe=False,
)
