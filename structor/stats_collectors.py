# -*- coding:utf-8 -*-
import time

from scrapy.statscollectors import MemoryStatsCollector

from toolkit.managers import ExceptContext


class StatsCollector(MemoryStatsCollector):
    """
        use redis to collect stats.
    """
    def __init__(self, crawler):
        super(StatsCollector, self).__init__(crawler)
        self.crawler = crawler

    @property
    def redis_conn(self):
        return self.crawler.spider.redis_conn

    def update(self, crawlid):
        key = "crawlid:%s" % crawlid
        self.redis_conn.hmset(key, {
            "crawlid": crawlid,
            "update_time": time.strftime("%Y-%m-%d %H:%M:%S")
        })
        start_time = self.redis_conn.hget(key, "start_time")

        if not start_time:
            self.redis_conn.hmset(key, {
                "spiderid": self.crawler.spider.name,
                "start_time": time.strftime("%Y-%m-%d %H:%M:%S")
            })
        self.redis_conn.expire("crawlid:%s" % crawlid, 60 * 60 * 24 * 2)

    def set_failed_download(self, meta, reason, _type="pages"):
        with ExceptContext():
            self.redis_conn.hincrby("crawlid:%s" % meta.get('crawlid'), "failed_download_%s"%_type, 1)
            self.update(meta.get('crawlid'))
            self.set_failed(meta, reason, _type)

    def set_failed(self, meta, reason, _type="pages"):
        with ExceptContext():
            self.redis_conn.hset("failed_download_%s:%s" % (_type, meta.get('crawlid')), meta.get('url'), reason)
            self.redis_conn.expire("failed_download_%s:%s" % (_type, meta.get('crawlid')), 60 * 60 * 24 * 2)

    def inc_total_pages(self, crawlid, num=1):
        with ExceptContext():
            self.redis_conn.hincrby("crawlid:%s" % crawlid, "total_pages", num)
            self.update(crawlid)

    def set_total_pages(self, crawlid, num=1):
        with ExceptContext():
            self.redis_conn.hset("crawlid:%s" % crawlid, "total_pages", num)
            self.update(crawlid)

    def inc_crawled_pages(self, crawlid):
        with ExceptContext():
            self.redis_conn.hincrby("crawlid:%s" % crawlid, "crawled_pages", 1)
            self.update(crawlid)
