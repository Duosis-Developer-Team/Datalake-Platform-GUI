import os as _os
import sys as _sys
import json

_basepath = _os.path.dirname(__file__)
_filepath = _os.path.abspath(_os.path.join(_basepath, 'package-info.json'))

if _os.path.exists(_filepath):
    with open(_filepath) as _f:
        package = json.load(_f)
    __version__ = package['version']
else:
    __version__ = '0.1.0'

_js_dist = [
    {
        'relative_package_path': 'dash_globe_component.min.js',
        'external_url': None,
        'namespace': 'dash_globe_component'
    }
]

_css_dist = []

from .DashGlobe import DashGlobe
