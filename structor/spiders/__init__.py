# -*- coding:utf-8 -*-
# This package will contain the spiders of your Scrapy project
#
# Please refer to the documentation for information on how to create and manage
# your spiders.
import time
from urllib.parse import urlparse

from scrapy.spiders import Spider
from scrapy import signals, Request
from scrapy.exceptions import DontCloseSpider
from scrapy.utils.response import response_status_message

from .exception_process import parse_method_wrapper
from .utils import LoggerDescriptor, url_arg_increment, url_item_arg_increment, \
    url_path_arg_increment, enrich_wrapper, ItemCollector


class StructureSpider(Spider):

    name = "structure"
    have_duplicate = False
    item_pattern = tuple()
    page_pattern = tuple()
    log = LoggerDescriptor()

    def __init__(self, *args, **kwargs):
        Spider.__init__(self, *args, **kwargs)
        self.redis_conn = None

    @property
    def logger(self):
        return self.log

    def _set_crawler(self, crawler):
        super(StructureSpider, self)._set_crawler(crawler)
        self.crawler.signals.connect(self.spider_idle,
                                     signal=signals.spider_idle)

    def set_redis(self, redis_conn):
        self.redis_conn = redis_conn

    def spider_idle(self):
        print('Don\'t close spider......')
        raise DontCloseSpider

    def extract_item_urls(self, response):
        return [response.urljoin(x) for x in set(response.xpath("|".join(self.item_pattern)).extract())]

    @staticmethod
    def adjust(response):
        if "if_next_page" in response.meta:
            del response.meta["if_next_page"]
        else:
            response.meta["seed"] = response.url

        # 防止代理继承  add at 16.10.26
        response.meta.pop("proxy", None)
        response.meta["callback"] = "parse_item"
        response.meta["priority"] -= 20

    def extract_page_urls(self, response, effective_urls):
        xpath = "|".join(self.page_pattern)

        if xpath.count("?") == 1:
            next_page_urls = [url_arg_increment(xpath, response.url)] if len(effective_urls) else []
        elif xpath.count("subpath="):
            next_page_urls = [url_path_arg_increment(xpath, response.url)] if len(effective_urls) else []
        elif xpath.count("/") > 1:
            next_page_urls = [response.urljoin(x) for x in set(response.xpath(xpath).extract())]
        else:
            next_page_urls = [url_item_arg_increment(xpath, response.url, len(effective_urls))] if len(effective_urls) else []

        response.meta["if_next_page"] = True
        response.meta["callback"] = "parse"
        response.meta["priority"] += 20
        return next_page_urls

    @enrich_wrapper
    def enrich_base_data(self, item_loader, response):
        item_loader.add_value('spiderid', response.meta.get('spiderid'))
        item_loader.add_value('url', response.meta.get("url"))
        item_loader.add_value("seed", response.meta.get("seed", ""))
        item_loader.add_value("timestamp", time.strftime("%Y%m%d%H%M%S"))
        item_loader.add_value('status_code', response.status)
        item_loader.add_value("status_msg", response_status_message(response.status))
        item_loader.add_value('domain', urlparse(response.url).hostname.split(".", 1)[1])
        item_loader.add_value('crawlid', response.meta.get('crawlid'))
        item_loader.add_value('response_url', response.url)

    def duplicate_filter(self, response, url, func):
        crawlid = response.meta["crawlid"]
        common_part = func(url)

        if self.redis_conn.sismember("crawlid:%s:model" % crawlid, common_part):
            return True
        else:
            self.redis_conn.sadd("crawlid:%s:model" % crawlid, common_part)
            self.redis_conn.expire("crawlid:%s:model" % crawlid,
                                   self.crawler.settings.get("DUPLICATE_TIMEOUT", 60 * 60))
            return False

    @staticmethod
    def get_base_loader(response):
        pass

    def enrich_data(self, item_loader, response):
        pass

    @parse_method_wrapper
    def parse(self, response):
        self.logger.debug("Start response in parse. ")
        item_urls = self.extract_item_urls(response)
        self.adjust(response)
        # 增加这个字段的目的是为了记住去重后的url有多少个，如果为空，对于按参数翻页的网站，有可能已经翻到了最后一页。
        effective_urls = []
        for item_url in item_urls:
            if self.have_duplicate:
                if self.duplicate_filter(response, item_url, self.have_duplicate):
                    continue
            response.meta["url"] = item_url
            self.crawler.stats.inc_total_pages(response.meta['crawlid'])
            effective_urls.append(item_url)
            yield Request(url=item_url,
                          callback=self.parse_item,
                          meta=response.meta,
                          errback=self.errback)

        for next_page_url in self.extract_page_urls(response, effective_urls) or []:
            response.meta["url"] = next_page_url
            yield Request(url=next_page_url,
                          callback=self.parse,
                          meta=response.meta)
            # next_page_url有且仅有一个，多出来的肯定是重复的
            break

    def process_forward(self, response, item):
        self.logger.info("crawlid:%s, id: %s, %s requests send for successful yield item" % (
            item.get("crawlid"), item.get("id", "unknow"), response.meta.get("request_count_per_item", 1)))
        self.crawler.stats.inc_crawled_pages(response.meta['crawlid'])
        return item

    @parse_method_wrapper
    def parse_item(self, response):
        response.meta["request_count_per_item"] = 1
        base_loader = self.get_base_loader(response)
        meta = response.request.meta
        meta["item_collector"] = ItemCollector()
        self.enrich_base_data(base_loader, response)
        meta["item_collector"].add((None, base_loader, None))
        self.enrich_data(base_loader, response)
        return self.yield_item_or_req(meta["item_collector"], response)

    def yield_item_or_req(self, item_collector, response):
        item_or_req = item_collector.load(response)
        if isinstance(item_or_req, Request):
            return item_or_req
        return self.process_forward(response, item_or_req)

    @parse_method_wrapper
    def parse_next(self, response):
        response.meta["request_count_per_item"] = response.meta.get("request_count_per_item", 1) + 1
        item_collector = response.request.meta["item_collector"]
        prop, item_loader, funcs = item_collector.get()
        getattr(self, "enrich_%s"%prop)(item_loader, response)
        return self.yield_item_or_req(item_collector, response)

    def errback(self, failure):
        if failure and failure.value and hasattr(failure.value, 'response'):
            response = failure.value.response

            if response:
                loader = self.get_base_loader(response)
                self.enrich_base_data(loader, response)
                item = loader.load_item()
                self.logger.error("errback: %s" % item)
                self.crawler.stats.inc_crawled_pages(response.meta['crawlid'])
                return item
            else:
                self.logger.error("failure has NO response")
        else:
            self.logger.error("failure or failure.value is NULL, failure: %s" % failure)
