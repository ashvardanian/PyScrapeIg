import setuptools
from pathlib import Path

setuptools.setup(
    name='ig',
    version='0.5.0',
    description=('Instagram scraper with proper pagination, that can collect posts, likes, comments and a lot more.'),
    long_description=Path('README.md').read_text(),
    long_description_content_type='text/markdown',
    packages=setuptools.find_packages(),
    license='MIT',
    maintainer='ashvardanian, realsirjoe, leungwaiban',
    author='ashvardanian, realsirjoe, leungwaiban',
    url='https://github.com/ashvardanian/PyScrapeIg',
    install_requires=[
        'requests==2.21.0',
        'python-slugify==3.0.2'
    ],
    classifiers=[
        'Development Status :: 5 - Beta',
        'Operating System :: OS Independent',
        'Intended Audience :: Developers',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.6',
        'Topic :: Software Development :: Libraries'
    ],
)