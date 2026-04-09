from setuptools import setup, find_packages

setup(
    name='dash_globe_component',
    version='0.1.0',
    author='',
    packages=find_packages(),
    include_package_data=True,
    license='MIT',
    description='A Globe.gl component for Dash',
    install_requires=['dash'],
    package_data={
        'dash_globe_component': ['*.js', '*.map', '*.json'],
    },
)
