from toolkit import test_prepare
test_prepare()

from structor.item_collector import RequestTree
from scrapy.loader import ItemLoader
from scrapy import Item, Field
from scrapy.http import HtmlResponse, Request


class BaseItem(Item):
    baidu = Field()


class BaiduItem(Item):
    amazon = Field()
    name = Field()


class AmazonItem(Item):
    name = Field()


class Spider(object):

    def enrich_data(self, item_loader, response):
        print("In enrich data. url: %s"%response.url)
        return [("baidu", ItemLoader(item=BaiduItem()), {"url": "http://www.baidu.com/"})]

    def enrich_baidu(self, item_loader, response):
        print("In enrich baidu. %s"%response.url)
        item_loader.add_value("name", "baidu")
        return [("amazon", ItemLoader(item=AmazonItem()), {"url": "http://www.amazon.com/"}),
                ("amazon", ItemLoader(item=AmazonItem()), {"url": "https://www.amazon.com/"})]

    def enrich_amazon(self, item_loader, response):
        print("In enrich amazon. %s"%response.url)
        item_loader.add_value("name", "amazon")


def test():
    rt = RequestTree(None, ItemLoader(item=BaseItem()), None, "enrich_data")
    spider = Spider()
    response = HtmlResponse("https://mashichao.com", request=Request(url="https://mashichao.com", meta={"priority": 1}))
    collector = iter(rt)
    collector.send(None)
    while True:
        try:
            result = None
            while result is None:
                result = collector.send((response, spider))
                if isinstance(result, Request):
                  response = HtmlResponse(result.url, request=result)
            print(11111, result)
        except StopIteration as e:
            print(e.args[0])
            break



test()