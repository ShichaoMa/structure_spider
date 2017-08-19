# -*- coding:utf-8 -*-
from scrapy.signals import spider_closed

from .spiders.utils import Logger

 
class BasePipeline(object):

    def __init__(self, settings):
        self.logger = Logger.from_crawler(self.crawler)

    @classmethod
    def from_crawler(cls, crawler):
        cls.crawler = crawler
        o = cls(crawler.settings)
        crawler.signals.connect(o.spider_closed, signal=spider_closed)
        return o

    def spider_closed(self):
        pass

