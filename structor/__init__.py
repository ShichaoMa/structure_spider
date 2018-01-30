# -*- coding:utf-8 -*-
from .redis_feed import RedisFeed
from .check_status import main
from .start_project import start as start_project, create as create_spider

VERSION = '1.0.6'

AUTHOR = "cn"

AUTHOR_EMAIL = "cnaafhvk@foxmail.com"

URL = "https://www.github.com/ShichaoMa/structure_spider"


def check():
    main()


def feed():
    RedisFeed.parse_args().start()