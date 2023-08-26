#!/usr/bin/env python

from setuptools import setup, find_packages

REQUIREMENTS = [
    line.strip().split('==')[0] for line in
    open("requirements.txt").readlines()
    if line[0].isalpha()]

setup(
    name='stl-scraper',
    version='0.1',
    author='Joe Bashe',
    url='https://github.com/JoeBashe/stl-scraper',
    description='Short-Term Listings Scraper',
    license='unknown',
    classifiers=['Development Status :: 3 - Alpha',
                 'Environment :: Console',
                 'Intended Audience :: Developers',
                 'Operating System :: OS Independent',
                 'Programming Language :: Python',
                 "Programming Language :: Python :: 3",
                 ],
    packages=['stl'],
    package_dir={'stl': 'stl'},
    package_data={},
    install_requires=REQUIREMENTS,
)
