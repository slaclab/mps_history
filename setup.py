from setuptools import setup, find_packages

with open('./requirements.txt') as f:
    requirements = f.read().split('\n')
    
setup(
    name='mps_history',
    version='0.2.0',
    author='Laura King',
    author_email='lking@slac.stanford.edu',
    packages=find_packages(include=['mps_history'], exclude=[]),
    url='https://github.com/slaclab/mps_history',
    license='MIT',
    description='Various tools and scripts for the mps history server.',
    long_description=open('README.md').read(),
)
