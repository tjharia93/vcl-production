from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

# get version from __version__ variable in production_log/__init__.py
from production_log import __version__ as version

setup(
    name="production_log",
    version=version,
    description="Production Log App for VCL (Vimit Converters Ltd)",
    author="VCL",
    author_email="admin@vcl.co.ke",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
