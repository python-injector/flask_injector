#!/usr/bin/env python
from setuptools import setup

long_description = open('README.rst').read()

setup(
    name='Flask-Injector',
    version='0.2.0',
    url='https://github.com/alecthomas/flask_injector',
    license='BSD',
    author='Alec Thomas',
    author_email='alec@swapoff.org',
    description='Adds Injector support to Flask.',
    long_description=long_description,
    py_modules=['flask_injector'],
    zip_safe=True,
    platforms='any',
    install_requires=[
        'Flask', 'injector',
    ],
)
