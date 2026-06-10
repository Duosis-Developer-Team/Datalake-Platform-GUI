from setuptools import setup, find_packages

setup(
    name='dash_hmdl_flow',
    version='0.1.0',
    packages=find_packages(),
    include_package_data=True,
    license='MIT',
    description='Animated HMDL topology flow component for Dash',
    install_requires=['dash'],
    package_data={
        'dash_hmdl_flow': ['*.js', '*.map', '*.json'],
    },
)
