# -*- coding:utf-8 -*-
try:
    from setuptools import setup, find_packages
except:
    from distutils.core import setup


VERSION = '1.2.0'

AUTHOR = "cn"

AUTHOR_EMAIL = "cnaafhvk@foxmail.com"

URL = "https://www.github.com/ShichaoMa/structure_spider"

NAME = "structure-spider"

DESCRIPTION = "mutil requests to combine a structure item. "

try:
    LONG_DESCRIPTION = open("README.rst").read()
except UnicodeDecodeError:
    LONG_DESCRIPTION = open("README.rst", encoding="utf-8").read()

KEYWORDS = "crawl web spider scrapy structure"

LICENSE = "MIT"

PACKAGES = ["structor", "structor.spiders", "structor.items"]

setup(
    name=NAME,
    version=VERSION,
    description=DESCRIPTION,
    long_description=LONG_DESCRIPTION,
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
    ],
    entry_points={
        'console_scripts': [
            'feed = structor:feed',
            'check = structor:check',
            'startproject = structor:start_project',
            'createspider = structor:create_spider'
        ],
    },
    keywords=KEYWORDS,
    author=AUTHOR,
    author_email=AUTHOR_EMAIL,
    url=URL,
    license=LICENSE,
    packages=PACKAGES,
    install_requires=["parsel>=1.2.0", "scrapy>=1.4.0", "toolkity", "jinja2", "custom-redis>=3.1.2"],
    include_package_data=True,
    zip_safe=True,
)
