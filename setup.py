"""
This is a setup.py script generated by py2applet

Usage:
    python setup.py py2app
"""

from setuptools import setup

APP = ['crawl.py']
DATA_FILES = ['./logo.png', './logo.ico']
OPTIONS = {'iconfile': './logo.ico'}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
