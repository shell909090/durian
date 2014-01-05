#!/usr/bin/python
# -*- coding: utf-8 -*-
'''
@date: 2014-01-05
@author: shell.xu
'''
from distutils.core import setup

version = '1.0'
description = 'proxy written by python'
long_description = ' proxy written by python'

setup(
    name='durian', version=version,
    description=description, long_description=long_description,
    author='Shell.E.Xu', author_email='shell909090@gmail.com',
    scripts=['run_durian'],
    packages=['durian',],
    data_files=[
        ('/etc/durian/', ['durian.conf',]),
    ]
)
