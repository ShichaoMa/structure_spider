# -*- coding:utf-8 -*-
"""
spider编写规则
1 spider必须继承自StructureSpider
2 若执行分类抓取则需要配置item_pattern = (), page_pattern = ()，其中：
    1）item_pattern元组中的元素为分类页中每个item链接所对应的xpath表达式
    2）page_pattern元组中的元素可以是下一页链接所所对应的正则表达式，或者其它规则，详见https://github.com/ShichaoMa/structure_spider/wiki/%08page_partten%E5%92%8Citem_partten%E7%BC%96%E5%86%99%E8%A7%84%E5%88%99
3 提供get_base_loader静态方法，传入response，返回CustomLoader对应一个Item
4 提供enrich_data方法，必须被enrich_wrapper装饰，其中：
    1）传入item_loader, response，使用item_loader的方法(add_value, add_xpath, add_re)添加要抓取的属性名及其对应表达式或值。
    2）如该次渲染需要产生新的请求，则通过response.meta["item_collector"]提供的(add, extend)方法，
       则将(prop, item_loader, request_meta)添加到item_collector中。其中：
        prop: 指下次请求获取的全部字段如果做为一个子item返回时，子item在其父item中对应的字段名称。
        item_loader: 用来抽取下次请求中字段的item_loader，如果下次请求返回子item，则此item_loader与父级item_loader不同
        request_meta: 组建request所需要的kwargs. type: dict
4 下次请求所回调的enrich函数名称为 enrich_`prop`
5 可以为spider类提供一个need_duplicate方法用来去重，传入详情页链接url,返回用来标识重复部分。
6 可以重写基类的方法来实现个性化抓取。
"""
import random
import time
from urllib.parse import urlencode, urlparse

from scrapy import Selector
from toolkit import re_search, safely_json_loads, urldecode

from . import StructureSpider
from ..utils import CustomLoader, enrich_wrapper
from ..items.baidump3_item import BaiduMp3Item


class BaiduMp3Spider(StructureSpider):
    name = "baidu_mp3"
    # 分类抓取的时候使用这两个属性
    item_pattern = ('//span[@class="song-title "]/a[1]/@href',)
    page_pattern = ('start=0',)
    custom_settings = {
        "ITEM_PIPELINES": {
            "structor.pipelines.Mp3DownloadPipeline": 100,
            # "structor.pipelines.FilePipeline": 101,
        }
    }

    def page_url(self, response):
        next_page_url = "http://music.baidu.com/data/user/getsongs"
        query = urldecode(urlparse(response.url).query)
        query.setdefault("ting_uid", re_search(r"artist/(\d+)", response.url))
        query.setdefault("hotmax", re_search(r"var hotbarMax = (\d+)", response.body))
        query["order"] = "hot"
        query[".r"] = str(random.random()) + str(int(time.time() * 1000))
        query.setdefault("pay", "")
        return "%s?%s" % (next_page_url, urlencode(query))

    def extract_item_urls(self, response):
        try:
            html = safely_json_loads(response.body)['data']["html"]
        except Exception:
            html = response.body
        sel = Selector(text=html)
        return [response.urljoin(x) for x in set(sel.xpath("|".join(self.item_pattern)).extract())]

    @staticmethod
    def get_base_loader(response):
        return CustomLoader(item=BaiduMp3Item())

    @enrich_wrapper
    def enrich_data(self, item_loader, response):
        self.logger.debug("Start to enrich_data. ")
        item_loader.add_xpath("name", '//h2/span[@class="name"]/text()')
        item_loader.add_value("id", response.url, re=r"song/(\d+)")
        item_loader.add_re("id", r"source_id: '(\d+)'")
        item_loader.add_xpath("singer", '//ul/li/span[@class="author_list"]/@title')
        item_loader.add_xpath("album", '//ul/li[contains(text(), "专辑")]/a/text()')
        item_loader.add_xpath("tags", '//ul/li[@class="clearfix tag"]/a/text()')
        node_list = list()
        # 添加抓取歌词的请求
        lyrics_url = "".join(response.xpath('//div[@id="lyricCont"]/@data-lrclink').extract()).strip()
        if lyrics_url:
            node_list.append(("lyrics", item_loader,
                              {"url": lyrics_url}))

        node_list.append(("source_url", item_loader,
                          {"url": "http://tingapi.ting.baidu.com/v1/restserver/ting?method=baidu.ting.song.play&"
                                  "format=jsonp&callback=jQuery_%s&songid=%s&_=%s" % (
                                      int(time.time() * 1000), (re_search(r"song/(\d+)", response.url) or
                                      re_search(r"source_id: '(\d+)'", response.body)),
                                      int(time.time() * 1000))}))
        response.meta["item_collector"].extend(node_list)

    @enrich_wrapper
    def enrich_lyrics(self, item_loader, response):
        self.logger.debug("Start to enrich_lyrics. ")
        item_loader.add_value("lyrics", response.body.decode("utf-8"))

    @enrich_wrapper
    def enrich_source_url(self, item_loader, response):
        self.logger.debug("Start to enrich_source_url. ")
        item_loader.add_re("source_url", r'"file_link":"(.*?)"')