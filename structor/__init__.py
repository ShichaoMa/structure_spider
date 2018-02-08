# -*- coding:utf-8 -*-
from .spider_feeder import SpiderFeeder
from .check_status import main
from .start_project import start as start_project, create as create_spider

VERSION = '1.2.0'

AUTHOR = "cn"

AUTHOR_EMAIL = "cnaafhvk@foxmail.com"

URL = "https://www.github.com/ShichaoMa/structure_spider"


def check():
    main()


def feed():
    SpiderFeeder.parse_args().start()
