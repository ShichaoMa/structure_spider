# -*- coding:utf-8 -*-
import json
from urllib.parse import unquote

from scrapy.signals import spider_closed
from toolkit import re_search

from .utils import ItemEncoder, CustomLogger


class BasePipeline(object):

    def __init__(self, settings):
        self.logger = CustomLogger.from_crawler(self.crawler)

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


class Mp3DownloadPipeline(BasePipeline):

    def __init__(self, settings):
        super(Mp3DownloadPipeline, self).__init__(settings)
        import requests
        self.downloader = requests.Session()

    def download(self, url, name):
        resp = self.downloader.get(url, stream=True)
        filename = unquote(re_search(r'filename="(.*?)"(?:;|$)', resp.headers.get("Content-Disposition", ""))) or name
        with open(filename, "wb") as f:
            for chunk in self.downloader.get(url, stream=True).iter_content(chunk_size=1024):
                f.write(chunk)

    def process_item(self, item, spider):
        self.download(item["source_url"], "%s.mp3"%item["name"])
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