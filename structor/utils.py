# -*- coding:utf-8 -*-
import re
import copy
import json
import logging

from collections import defaultdict
from functools import wraps
from urllib.parse import urlparse, urlunparse, urlencode
from toolkit import strip
from toolkit.logger import Logger

from scrapy import Selector, Item
from scrapy.loader import ItemLoader
from scrapy.utils.misc import arg_to_iter
from scrapy.loader.processors import Compose

from .custom_request import Request


class TakeAll(object):
    """
    自定义TakeAll
    """
    def __call__(self, values):
        return values


class TakeFirst(object):
    """
    自定义TakeFirst
    """
    def __call__(self, values):
        return_value = None
        for value in values:
            return_value = value
            if value:
                return return_value
        return return_value


def xpath_exchange(x):
    """
    将xpath结果集进行抽取拼接成字符串
    :param x:
    :return:
    """
    return "".join(x.extract()).strip()


def re_exchange(x):
    """
    将re的结果集进行抽取拼接成字符串
    :param x:
    :return:
    """
    return "".join(x).strip()


class ItemEncoder(json.JSONEncoder):
    """
    将Item转换成字典
    """
    def default(self, obj):
        if isinstance(obj, Item):
            return dict(obj)
        # Let the base class default method raise the TypeError
        return json.JSONEncoder.default(self, obj)


class CustomLoader(ItemLoader):
    """
    自定义ItemLoader
    """
    default_output_processor = Compose(TakeFirst(), strip)

    def add_re(self, field_name, regex, **kwargs):
        """
        自实现add_re方法
        :param field_name:
        :param regex:
        :param kwargs:
        :return:
        """
        regexs = arg_to_iter(regex)
        for regex in regexs:
            try:
                self.add_value(field_name, self.selector.re(regex), **kwargs)
            except json.decoder.JSONDecodeError:
                self.add_value(field_name, self.selector.re(regex, False), **kwargs)

    def load_item(self):
        """
        增加skip, default, order的实现
        :return:
        """
        item = self.item
        skip_fields = []
        for field_name, field in sorted(item.fields.items(), key=lambda item: item[1].get("order", 0)):
            value = self.get_output_value(field_name)
            if field.get("skip"):
                skip_fields.append(field_name)
            if not (value or isinstance(value, type(field.get("default", "")))):
                item[field_name] = field.get("default", "")
            else:
                item[field_name] = value

        for field in skip_fields:
            del item[field]
        return item

    def __str__(self):
        return "<CustomLoader item: %s at %s >" % (self.item.__class__, id(self))

    __repr__ = __str__


def enrich_wrapper(func):
    """
    item_loader在使用pickle 序列化时，不能包含response对象和selector对象, 使用该装饰器，
    在进去enrich函数之前加上selector，使用完毕后清除selector
    :param func:
    :return:
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        item_loader = args[1]
        response = args[2]
        selector = Selector(text=response.text)
        item_loader.selector = selector
        result = func(*args, **kwargs)
        item_loader.selector = None
        return result
    return wrapper


class ItemCollector(object):
    """
    ItemCollector的实现
    过时
    """
    def __init__(self):
        self.tuples = list()
        self.depth = 0
        self.current_node = None
        self.last_node = None
        self.nodes_num_per_level = defaultdict(int)

    def extend(self, iterable):
        count = 0
        if self.depth % 2:
            for i in iterable:
                count += 1
                self.tuples.insert(0, i)
        else:
            for i in iterable:
                count += 1
                self.tuples.append(i)
        if count:
            self.nodes_num_per_level[self.depth] += count
            self.rolldown()

    def rolldown(self):
        self.depth += 1

    def rollup(self):
        self.depth -= 1

    def get(self):
        if (self.depth-1)%2:
            self.current_node = self.tuples[0]
        else:
            self.current_node = self.tuples[-1]
        return self.current_node

    def check_deep_level_finished(self):
        return not self.nodes_num_per_level[self.depth]

    def pop(self):
        if (self.depth - 1) % 2:
            self.last_node = self.tuples.pop(0)
        else:
            self.last_node = self.tuples.pop(-1)
        self.nodes_num_per_level[self.depth - 1] -= 1
        self.rollup()

    def add(self, node):
        if self.depth % 2:
            self.tuples.insert(0, node)
        else:
            self.tuples.append(node)
        self.nodes_num_per_level[self.depth] += 1
        self.rolldown()

    def dive(self):
        while True:
            if self.tuples:
                prop, current_item_loader, kwargs = self.get()
                if self.last_node:
                    last_prop, last_item_loader, _ = self.last_node
                    prop, current_item_loader, kwargs = self.current_node
                    if last_item_loader is not current_item_loader:
                        try:
                            current_item_loader.add_value(last_prop, last_item_loader.load_item())
                        except KeyError:
                            current_item_loader.add_value(prop, last_item_loader.load_item())
                if not kwargs:
                    if self.check_deep_level_finished():
                        self.pop()
                    else:
                        self.rolldown()
                        self.last_node = None
                else:
                    return prop, current_item_loader, kwargs
            else:
                return self.current_node

    def load(self, response):
        while True:
            prop, current_item_loader, kwargs = self.dive()
            if not kwargs:
                return current_item_loader.load_item()
            else:
                meta = response.request.meta.copy()
                kwargs.pop("callback", None)
                kwargs.pop("errback", None)
                custom_meta = kwargs.pop("meta", {})
                meta["priority"] += 1
                meta.update(custom_meta)
                kw = copy.deepcopy(kwargs)
                kwargs.clear()
                return Request(meta=meta, callback="parse_next", errback="errback", **kw)


class CustomLogger(Logger):
    """
    logger的实现
    """

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings, crawler.spidercls.name)

    def __init__(self, settings, name):
        self.json = settings.getbool('SC_LOG_JSON', True)
        self.level = settings.get('SC_LOG_LEVEL', 'DEBUG')
        self.stdout = settings.getbool('SC_LOG_STDOUT', True)
        self.dir = settings.get('SC_LOG_DIR', 'logs')
        self.bytes = settings.get('SC_LOG_MAX_BYTES', '10MB')
        self.backups = settings.getint('SC_LOG_BACKUPS', 5)
        self.udp_host = settings.get("SC_LOG_UDP_HOST", "127.0.0.1")
        self.udp_port = settings.getint("SC_LOG_UDP_PORT", 5230)
        self.log_file = settings.getbool('SC_LOG_FILE', False)
        self.name = name
        self.logger = logging.getLogger(name)
        self.logger.propagate = False
        self.set_up()


def url_arg_increment(arg_pattern, url):
    """
    对于使用url arguments标志page字段而实现分页的url，使用这个函数生成下一页url
    关于正则表达式：
    第一组匹配url分页参数前面的部分
    第二组匹配分页参数的名字+等号+起始页的页序数
    第三组匹配当前页数
    第四组匹配分页参数后来的值
    正常使用时，一 三 四组不需要修改，只需要修改第二组中的值即可
    @param arg_pattern:r'(.*?)(pn=0)(\d+)(.*)',
    @param url:http://www.nike.com/abc?pn=1
    @return:http://www.nike.com/abc?pn=2
    """
    first_next_page_index = int(re.search(r"\d+", arg_pattern).group())
    arg_pattern = arg_pattern.replace(str(first_next_page_index), "")
    mth = re.search(arg_pattern, url)
    if mth:
        prefix = mth.group(1)
        midfix = mth.group(2)
        page = int(mth.group(3))
        stuffix = mth.group(4)
        return "%s%s%s%s" % (prefix, midfix, page + 1, stuffix)
    else:
        midfix = re.sub(r"[\(\)\\d\+\.\*\?]+", "", arg_pattern)
        if url.count("?"):
            midfix = "&" + midfix
        else:
            midfix = "?" + midfix
        return "%s%s%s" % (url, midfix, first_next_page_index + 1)


def url_item_arg_increment(partten, url, count):
    """
    对于使用url arguments标志item的partten而实现分页的url，使用这个函数生成下一页url
    @param partten: `keyword`=`begin_num`(eg: start=0)用来指定partten的相应字段
    @param url: http://www.ecco.com/abc?start=30
    @param count:  30当前页item的数量
    @return: http://www.ecco.com/abc?start=60
    """
    keyword, begin_num = partten.split("=")
    mth = re.search(r"%s=(\d+)"%keyword, url)
    if mth:
        start = int(mth.group(1))
    else:
        start = int(begin_num)
    parts = urlparse(url)
    if parts.query:
        query = dict(x.split("=") for x in parts.query.split("&"))
        query[keyword] = start + count
    else:
        query = {keyword: count+start}
    return urlunparse(parts._replace(query=urlencode(query)))


def url_path_arg_increment(pattern_str, url):
    """
    对于将页数放到path中的url,使用这个函数生成下一页url
    如下：
    其中{first_page_num}~={regex}用来标明该url是用urlpath中某一部分自增来进行翻页
    ~=前面代表该分类第一页若是缺省页面，是从第几页开始计算
    ~=后面为正则表达式
        第一组用来匹配自增数字前面可能存在的部分（可为空）
        第二组用来匹配自增数字
        第三组来匹配自增数字后面可能存在的部分（可为空）
    如示例中给出的url，经过转换后得到下一页的url为
    'http://www.timberland.com.hk/en/men-apparel-shirts/page/2/'
    其中http://www.timberland.com.hk/en/men-apparel-shirts为原url
    /page/为第一组所匹配; 2为第二组匹配的; /为第三组匹配的
    当给出的url为'http://www.timberland.com.hk/en/men-apparel-shirts/page/2/'
    输出结果为'http://www.timberland.com.hk/en/men-apparel-shirts/page/3/'
    @param pattern_str: r'1~=(/page/)(\d+)(/)'
    @param url: 'http://www.timberland.com.hk/en/men-apparel-shirts‘
    @return:'http://www.timberland.com.hk/en/men-apparel-shirts/page/2/'
    """
    parts = urlparse(url)
    first_page_num, pattern = pattern_str.split("~=", 1)
    mth = re.search(pattern, parts.path)
    if mth:
        path = re.sub(pattern, "\g<1>%s\g<3>" % (int(mth.group(2))+1), parts.path)
    else:
        page_num = int(first_page_num) + 1
        path = re.sub(r"\((.*)\)(?:\(.*\))\((.*)\)",
                      _repl_wrapper(parts.path, page_num),
                      pattern).replace("\\", "")
    return urlunparse(parts._replace(path=path))


def _repl_wrapper(path, page_num):
    def _repl(mth):
        sub_path = "%s%d%s"%(mth.group(1), page_num, mth.group(2))
        if path.endswith(mth.group(2).replace("\\", "")):
            return path[:path.rfind(mth.group(2).replace("\\", ""))]+sub_path
        else:
            return path + sub_path
    return _repl


if __name__ == "__main__":
    pass
