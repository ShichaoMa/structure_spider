# -*- coding:utf-8 -*-
import warnings

from .spider_feeder import SpiderFeeder
from .check_status import main
from .start_project import start, create
from .builder import run

VERSION = '1.2.9'

AUTHOR = "cn"

AUTHOR_EMAIL = "cnaafhvk@foxmail.com"

URL = "https://www.github.com/ShichaoMa/structure_spider"


def start_project():
    warnings.warn("start_project is deprecated, use structure-spider check instead. ",
                  DeprecationWarning, 2)
    start()


def create_spider():
    warnings.warn("create_spider is deprecated, use structure-spider check instead. ",
                  DeprecationWarning, 2)
    create()


def check():
    warnings.warn("check is deprecated, use structure-spider check instead. ",
                  DeprecationWarning, 2)
    main()


def feed():
    warnings.warn("feed is deprecated, use structure-spider check instead. ",
                  DeprecationWarning, 2)
    SpiderFeeder.parse_args().start()
