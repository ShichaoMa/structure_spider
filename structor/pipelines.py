# -*- coding:utf-8 -*-
import json

from scrapy.signals import spider_closed

from .spiders.utils import Logger, ItemEncoder


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


class FilePipeline(BasePipeline):

    def process_item(self, item, spider):
        open("test.json", "w").write(json.dumps(item, cls=ItemEncoder))
        return item


class MongoPipeline(BasePipeline):

    def __init__(self, settings):
        super(MongoPipeline, self).__init__(settings)
        import pymongo
        self.db = pymongo.MongoClient(settings.get("MONGO_HOST"), settings.get("MONGO_PORT"))[settings.get("MONGO_DB")]
        self.col = self.db[settings.get("MONGO_TABLE")]

    def process_item(self, item, spider):
        self.col.insert(json.loads(json.dumps(item, cls=ItemEncoder)))
        return item