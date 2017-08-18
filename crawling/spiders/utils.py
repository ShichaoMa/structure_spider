# -*- coding:utf-8 -*-
import os
import io
import re
import sys
import copy
import time
import json
import errno
import types
import socket
import struct
import psutil
import signal
import logging
import datetime
import requests
import traceback

from queue import Empty
from logging import handlers
from collections import OrderedDict, defaultdict
from influxdb import InfluxDBClient
from functools import wraps, reduce
from pythonjsonlogger.jsonlogger import JsonFormatter
from urllib.parse import urlparse, urlunparse, urlencode, urljoin

from scrapy import Selector
from scrapy.http import Request
from scrapy.loader import ItemLoader
from scrapy.utils.misc import arg_to_iter
from scrapy.loader.processors import Compose


class TakeFirst(object):

    def __call__(self, values):
        return_value = None
        for value in values:
            return_value = value
            if value:
                return return_value
        return return_value


class ItemCollector(object):

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

    def add(self, root):
        self.tuples.append(root)
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
                        current_item_loader.add_value(last_prop, last_item_loader.load_item())
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


# class ItemCollector(object):
#
#     def __init__(self):
#         self.tuples = list()
#         self.depth_nodes_num_hash = defaultdict(int)
#         self.current_node = None
#         self.last_node = None
#         self.depth = -1
#
#     def extend(self, iterable):
#         count = 0
#         if self.depth%2:
#             for i in iterable:
#                 count += 1
#                 self.tuples.insert(0, i)
#         else:
#             for i in iterable:
#                 count += 1
#                 self.tuples.append(i)
#         self.depth_nodes_num_hash[self.depth] += count
#         self.rolldown()
#
#     def add(self, t):
#         self.tuples.append(t)
#         self.depth_nodes_num_hash[self.depth] += 1
#         self.rolldown()
#
#     def load_item(self):
#         if self.last_node:
#             last_prop, last_item_loader, _ = self.last_node
#             _, current_item_loader, _ = self.current_node
#             if last_item_loader is not current_item_loader:
#                 value = last_item_loader.load_item()
#             else:
#                 value = None
#             if value:
#                 current_item_loader.add_value(last_prop, value)
#
#     def get(self):
#         if (self.depth-1)%2:
#             self.current_node = self.tuples[0]
#         else:
#             self.current_node = self.tuples[-1]
#         return self.current_node
#
#     def check_deep_level_finished(self):
#         return not self.depth_nodes_num_hash[self.depth+1]
#
#     def pop(self):
#         if self.check_deep_level_finished():
#             if self.depth%2:
#                 self.last_node = self.tuples.pop(0)
#             else:
#                 self.last_node = self.tuples.pop(-1)
#             self.depth_nodes_num_hash[self.depth] -= 1
#             self.rollup()
#         else:
#             self.rolldown()
#             self.last_node = None
#
#     def rolldown(self):
#         self.depth += 1
#
#     def rollup(self):
#         self.depth -= 1
#
#     def dive(self):
#         while True:
#             if self.tuples:
#                 prop, current_item_loader, funcs = self.get()
#                 self.load_item()
#                 if not funcs:
#                     self.pop()
#                 else:
#                     return prop, current_item_loader, funcs
#             else:
#                 return self.current_node
#
#     def process(self, response, spider):
#         while True:
#             prop, current_item_loader, callable_or_keywords = self.dive()
#             if not callable_or_keywords:
#                 return current_item_loader.load_item()
#             entries = list()
#             while callable_or_keywords:
#                 callable_or_keyword = callable_or_keywords.pop(0)
#                 if isinstance(callable_or_keyword, str):
#                     entry = getattr(spider, callable_or_keyword)(current_item_loader, response)
#                     if entry:
#                         entries.extend(entry)
#                 else:
#                     meta = response.request.meta.copy()
#                     callable_or_keyword.pop("callback", None)
#                     callable_or_keyword.pop("errback", None)
#                     custom_meta = callable_or_keyword.pop("meta", {})
#                     meta["priority"] += 20
#                     meta.update(custom_meta)
#                     return Request(meta=meta, callback="parse_next", errback="errback", **callable_or_keyword)
#             else:
#                 if entries:
#                     self.extend(entries)

    # def process(self, response, spider):
    #     prop, current_item_loader, callable_or_keywords = self.dive()
    #     if not callable_or_keywords:
    #         return current_item_loader.load_item()
    #     entries = list()
    #     while callable_or_keywords:
    #         callable_or_keyword = callable_or_keywords.pop(0)
    #         if isinstance(callable_or_keyword, str):
    #             entry = getattr(spider, callable_or_keyword)(current_item_loader, response)
    #             if entry:
    #                 entries.extend(entry)
    #         else:
    #             meta = response.request.meta.copy()
    #             callable_or_keyword.pop("callback", None)
    #             callable_or_keyword.pop("errback", None)
    #             custom_meta = callable_or_keyword.pop("meta", {})
    #             meta["priority"] += 20
    #             meta.update(custom_meta)
    #             return Request(meta=meta, callback="parse_next", errback="errback", **callable_or_keyword)
    #     else:
    #         if entries:
    #             self.extend(entries)
    #         return self.process(response, spider)


class Stack(object):

    def __init__(self):
        self.tuples = list()
        self.current_node = None

    def extend(self, iterable, backwards=0):
        for i in iterable:
            if backwards:
                self.tuples.insert(0, i)
            else:
                self.tuples.append(i)

    def retrieve(self, backwards=0):
        if backwards:
            self.current_node = self.tuples[0]
        else:
            self.current_node = self.tuples[-1]
        return self.current_node

    def reduce(self, backwards=0):
        if backwards:
            return self.tuples.pop(0)
        else:
            return self.tuples.pop(-1)


def c_re_sub(string, pattern, repl):
    return re.sub(pattern, repl, string)


def strip(value):
    if isinstance(value, str):
        return value.strip()
    return value


def function_xpath_common(x, item):
    """
    xpath转换公共函数
    :param x:
    :param item:
    :return:
    """
    return xpath_exchange(x)


def format_html_xpath_common(x, item):
    """
    直接需要抽取html的字段的公共函数
    :param x:
    :param item:
    :return:
    """
    return format_html_string(xpath_exchange(x))


def xpath_exchange(x):
    """
    将xpath结果集进行抽取拼接成字符串
    :param x:
    :return:
    """
    return "".join(x.extract()).strip()


def function_re_common(x, item):
    """
    re转换公共函数
    :param x:
    :param item:
    :return:
    """
    return re_exchange(x)


def safely_json_re_common(x, item):
    """
    直接需要抽取json数据的字段的公共函数
    :param x:
    :param item:
    :return:
    """
    return safely_json_loads(re_exchange(x).replace('&nbsp;', ''))


def re_exchange(x):
    """
    将re的结果集进行抽取拼接成字符串
    :param x:
    :param item:
    :return:
    """
    return "".join(x).strip()


def safely_json_loads(json_str, defaulttype=dict, escape=True):
    """
    返回安全的json类型
    :param json_str: 要被loads的字符串
    :param defaulttype: 若load失败希望得到的对象类型
    :param escape: 是否将单引号变成双引号
    :return:
    """
    if not json_str:
        return defaulttype()
    elif escape:
        data = replace_quote(json_str)
        return json.loads(data)
    else:
        return json.loads(json_str)


def chain_all(iter):
    """
    连接两个序列或字典
    :param iter:
    :return:
    """
    iter = list(iter)
    if not iter:
        return None
    if isinstance(iter[0], dict):
        result = {}
        for i in iter:
            result.update(i)
    else:
        result = reduce(lambda x, y: list(x)+list(y), iter)
    return result


def replace_quote(json_str):
    """
    将要被json.loads的字符串的单引号转换成双引号，如果该单引号是元素主体，而不是用来修饰字符串的。则不对其进行操作。
    :param json_str:
    :return:
    """
    if not isinstance(json_str, str):
        return json_str
    double_quote = []
    new_lst = []
    for index, val in enumerate(json_str):
        if val == '"' and json_str[index-1] != "\\":
            if double_quote:
                double_quote.pop(0)
            else:
                double_quote.append(val)
        if val== "'" and json_str[index-1] != "\\":
            if not double_quote:
                val = '"'
        new_lst.append(val)
    return "".join(new_lst)


def format_html_string(a_string):
    """
    格式化html
    :param a_string:
    :return:
    """
    a_string = a_string.replace('\n', '')
    a_string = a_string.replace('\t', '')
    a_string = a_string.replace('\r', '')
    a_string = a_string.replace('  ', '')
    a_string = a_string.replace(u'\u2018', "'")
    a_string = a_string.replace(u'\u2019', "'")
    a_string = a_string.replace(u'\ufeff', '')
    a_string = a_string.replace(u'\u2022', ":")
    re_ = re.compile(r"<([a-z][a-z0-9]*)\ [^>]*>", re.IGNORECASE)
    a_string = re_.sub('<\g<1>>', a_string, 0)
    re_script = re.compile('<\s*script[^>]*>[^<]*<\s*/\s*script\s*>', re.I)
    a_string = re_script.sub('', a_string)
    re_a = re.compile("</?a.*?>")
    a_string = re_a.sub("", a_string)
    return a_string


def re_search(re_str, text, dotall=True):
    """
    抽取正则规则的第一组元素
    :param re_str:
    :param text:
    :param dotall:
    :return:
    """
    if isinstance(text, bytes):
        text = text.decode("utf-8")

    if not isinstance(re_str, list):
        re_str = [re_str]

    for rex in re_str:

        if dotall:
            match_obj = re.search(rex, text, re.DOTALL)
        else:
            match_obj = re.search(rex, text)

        if match_obj is not None:
            t = match_obj.group(1).replace('\n', '')
            return t

    return ""


class CustomLoader(ItemLoader):
    default_output_processor = Compose(TakeFirst(), strip)

    def add_re(self, field_name, regex):
        regexs = arg_to_iter(regex)
        for regex in regexs:
            self.add_value(field_name, self.selector.re(regex))

    def load_item(self):
        item = self.item
        skip_fields = []
        for field_name, field in sorted(item.fields.items(), key=lambda item: item[1].get("order", 0)):
            value = self.get_output_value(field_name)
            if field.get("skip"):
                skip_fields.append(field_name)
            item[field_name] = value or field.get("default", "")

        for field in skip_fields:
            del item[field]
        return item


def enrich_wrapper(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        item_loader = args[1]
        response = args[2]
        item_loader.selector = Selector(text=response.text)
        result = func(*args, **kwargs)
        item_loader.selector = None
        return result
    return wrapper


class P22P3Encoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, bytes):
           return obj.decode("utf-8")
        if isinstance(obj, (types.GeneratorType, map, filter)):
            return list(obj)
        # Let the base class default method raise the TypeError
        return json.JSONEncoder.default(self, obj)


def async_produce_wrapper(producer, logger):
    count = 0

    def wrapper(func):

        def inner(*args, **kwargs):
            result = func(*args, **kwargs)
            nonlocal count
            count += 1
            if count % 10 == 0:  # adjust this or bring lots of RAM ;)
                while True:
                    try:
                        msg, exc = producer.get_delivery_report(block=False)
                        if exc is not None:
                            logger.error('Failed to deliver msg {}: {}'.format(
                                msg.partition_key, repr(exc)))
                        else:
                            logger.info('Successfully delivered msg {}'.format(
                                msg.partition_key))
                    except Empty:
                        break
            return result
        return inner
    return wrapper


def timeout(timeout_time, default):
    '''
    Decorate a method so it is required to execute in a given time period,
    or return a default value.
    '''

    class DecoratorTimeout(Exception):
        pass

    def timeout_function(f):
        def f2(*args):
            def timeout_handler(signum, frame):
                raise DecoratorTimeout()

            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            # triger alarm in timeout_time seconds
            signal.alarm(timeout_time)
            try:
                retval = f(*args)
            except DecoratorTimeout:
                return default
            finally:
                signal.signal(signal.SIGALRM, old_handler)
            signal.alarm(0)
            return retval

        return f2

    return timeout_function


def custom_re(regex, text):
    return re.findall(regex, text)


def re_size(x, y):
    x, y = int(x), int(y)
    m = max(x, y)
    if m > 2000:
        if m == x:
            y, x = y * 2000 // x, 2000
        else:
            x, y = x * 2000 // y, 2000
    return x, y


def replace_dot(data):

    new_data = {}
    for k, v in data.items():
        new_data[k.replace(".", "_")] = v

    return new_data


def extras_wrapper(self, item):

    def logger_func_wrapper(func):

        @wraps(func)
        def wrapper(*args, **kwargs):
            if len(args) > 2:
                extras = args[1]
            else:
                extras = kwargs.pop("extras", {})
            extras = self.add_extras(extras, item)
            return func(args[0], extra=extras)

        return wrapper

    return logger_func_wrapper


def findCaller(stack_info=False):
    """
    Find the stack frame of the caller so that we can note the source
    file name, line number and function name.
    """
    f = logging.currentframe()
    #On some versions of IronPython, currentframe() returns None if
    #IronPython isn't run with -X:Frames.
    if f is not None:
        f = f.f_back
    rv = "(unknown file)", 0, "(unknown function)", None
    while hasattr(f, "f_code"):
        co = f.f_code
        filename = os.path.normcase(co.co_filename)
        if not (filename.count("crawling") and not filename.count("utils")):
            f = f.f_back
            continue
        sinfo = None
        if stack_info:
            sio = io.StringIO()
            sio.write('Stack (most recent call last):\n')
            traceback.print_stack(f, file=sio)
            sinfo = sio.getvalue()
            if sinfo[-1] == '\n':
                sinfo = sinfo[:-1]
            sio.close()
        rv = (co.co_filename, f.f_lineno, co.co_name, sinfo)
        break
    return rv


def logger_find_call_wrapper(func):

    @wraps(func)
    def wrapper(*args, **kwargs):
        return findCaller(*args, **kwargs)
    return wrapper


class CustomJsonFormatter(JsonFormatter):

    def format(self, record):
        """Formats a log record and serializes to json"""
        message_dict = {}
        if isinstance(record.msg, dict):
            message_dict = record.msg
            record.message = None
        else:
            record.message = record.getMessage()
        # only format time if needed
        if "asctime" in self._required_fields:
            record.asctime = self.formatTime(record, self.datefmt)

        # Display formatted exception, but allow overriding it in the
        # user-supplied dict.
        if record.exc_info and not message_dict.get('exc_info'):
            message_dict['exc_info'] = self.formatException(record.exc_info)
        if not message_dict.get('exc_info') and record.exc_text:
            message_dict['exc_info'] = record.exc_text
        message_dict["module"] = record.module
        message_dict["lineno"] = record.lineno
        message_dict["funcName"] = record.funcName

        try:
            log_record = OrderedDict()
        except NameError:
            log_record = {}
        self.add_fields(log_record, record, message_dict)
        log_record = self.process_log_record(log_record)

        return "%s%s" % (self.prefix, self.jsonify_log_record(log_record))


class Logger(object):

    logger = None

    def __new__(cls, *args, **kwargs):
        # 保证单例
        if not cls.logger:
            cls.logger = super(Logger, cls).__new__(cls)
        return cls.logger

    def __init__(self, name):
        self.logger = logging.getLogger(name)
        self.logger.findCaller = logger_find_call_wrapper(self.logger.findCaller)

    @classmethod
    def from_crawler(cls, crawler):
        return Logger.logger or cls.init_logger(crawler)

    @classmethod
    def init_logger(cls, crawler):
        json = crawler.settings.get('SC_LOG_JSON', True)
        level = crawler.settings.get('SC_LOG_LEVEL', 'INFO')
        name = "%s_%s" % (crawler.spidercls.name, get_ip_address().replace(".", "_"))
        stdout = crawler.settings.get('SC_LOG_STDOUT', True)
        dir = crawler.settings.get('SC_LOG_DIR', 'logs')
        bytes = crawler.settings.get('SC_LOG_MAX_BYTES', '10MB')
        file = "%s_%s.log" % (crawler.spidercls.name, get_ip_address().replace(".", "_"))
        backups = crawler.settings.get('SC_LOG_BACKUPS', 5)
        logger = cls(name=name)
        logger.logger.propagate = False
        logger.json = json
        logger.name = name
        logger.format_string = '%(asctime)s [%(name)s][%(module)s.%(funcName)s:%(lineno)d] %(levelname)s: %(message)s'
        root = logging.getLogger()
        # 将的所有使用Logger模块生成的logger设置一样的logger level
        for log in root.manager.loggerDict.keys():
            root.getChild(log).setLevel(getattr(logging, level, 10))

        if stdout:
            logger.set_handler(logging.StreamHandler(sys.stdout))
        else:
            try:
                os.makedirs(dir)
            except OSError as exception:
                if exception.errno != errno.EEXIST:
                    raise

            file_handler = handlers.RotatingFileHandler(
                os.path.join(dir, file),
                maxBytes=bytes,
                backupCount=backups)
            logger.set_handler(file_handler)
        return logger

    def set_handler(self, handler):
        handler.setLevel(logging.DEBUG)
        formatter = self._get_formatter(self.json)
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.debug("Logging to %s"%handler.__class__.__name__)

    def __getattr__(self, item):
        if item.upper() in logging._nameToLevel:
            return extras_wrapper(self, item)(getattr(self.logger, item))
        raise AttributeError

    def _get_formatter(self, json):
        if json:
            return CustomJsonFormatter()
        else:
            return logging.Formatter(self.format_string)

    def add_extras(self, dict, level):
        my_copy = copy.deepcopy(dict)
        if 'level' not in my_copy:
            my_copy['level'] = level
        if 'timestamp' not in my_copy:
            my_copy['timestamp'] = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        if 'logger' not in my_copy:
            my_copy['logger'] = self.name
        return my_copy


class LoggerDescriptor(object):

    def __init__(self, logger=None):
        self.logger = logger

    def __get__(self, instance, cls):
        if not self.logger:
            self.logger = Logger.from_crawler(instance.crawler)

        return self.logger

    def __getattr__(self, item):
        raise AttributeError


def parse_cookie(string):
    results = re.findall('([^=]+)=([^\;]+);?\s?', string)
    my_dict = {}

    for item in results:
        my_dict[item[0]] = item[1]

    return my_dict


def _get_ip_address(ifname):

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    import fcntl
    return socket.inet_ntoa(fcntl.ioctl(
        s.fileno(), 0x8915, struct.pack('256s', ifname[:15])
    )[20:24])


def _get_net_interface():

    p = os.popen("ls /sys/class/net")
    buf = p.read(10000)
    return buf.strip(" \nlo")


def get_netcard():
    netcard_info = []
    info = psutil.net_if_addrs()
    for k,v in info.items():
        for item in v:
            if item[0] == 2 and not item[1]=='127.0.0.1':
                netcard_info.append((k,item[1]))
    return netcard_info


def get_ip_address():

    if sys.platform == "win32":
        hostname = socket.gethostname()
        IPinfo = socket.gethostbyname_ex(hostname)
        try:
            return IPinfo[-1][-1]
        except IndexError:
            return "127.0.0.1"
    else:
        ips = get_netcard()

        if ips:
            return ips[0][1]
        else:
            shell_command = "ip addr | grep 'state UP' -A2 | tail -n1 | awk '{print $2}' | cut -f1  -d'/'"
            return os.popen(shell_command).read().strip()


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



def url_item_arg_increment(index, url, count):
    """
    对于使用url arguments标志item的index而实现分页的url，使用这个函数生成下一页url
    @param index: start 用来指定index的相应字段
    @param url: http://www.ecco.com/abc?start=30
    @param count:  30当前页item的数量
    @return: http://www.ecco.com/abc?start=60
    """
    mth = re.search(r"%s=(\d+)"%index, url)
    if mth:
        start = int(mth.group(1))
    else:
        start = 1
    parts = urlparse(url)
    if parts.query:
        query = dict(x.split("=") for x in parts.query.split("&"))
        query[index] = start + count
    else:
        query = {index:count+1}
    return urlunparse(parts._replace(query=urlencode(query)))


def url_path_arg_increment(pattern_str, url):
    """
    对于将页数放到path中的url,使用这个函数生成下一页url
    如下：
    其中subpath=用来标明该url是用urlpath中某一部分自增来进行翻页
    等号后面为正则表达式
        第一组用来匹配自增数字前面可能存在的部分（可为空）
        第二组用来匹配自增数字
        第三组来匹配自增数字后面可能存在的部分（可为空）
    如示例中给出的url，经过转换后得到下一页的url为
    'http://www.timberland.com.hk/en/men-apparel-shirts/page/2/'
    其中http://www.timberland.com.hk/en/men-apparel-shirts为原url
    /page/为第一组所匹配; 2为第二组匹配的; /为第三组匹配的
    当给出的url为'http://www.timberland.com.hk/en/men-apparel-shirts/page/2/'
    输出结果为'http://www.timberland.com.hk/en/men-apparel-shirts/page/3/'
    @param pattern_str: r'subpath=(/page/)(\d+)(/)'
    @param url: 'http://www.timberland.com.hk/en/men-apparel-shirts‘
    @return:'http://www.timberland.com.hk/en/men-apparel-shirts/page/2/'
    """
    parts = urlparse(url)
    pattern = pattern_str.split("=", 1)[1]
    mth = re.search(pattern, parts.path)
    if mth:
        path = re.sub(pattern, "\g<1>%s\g<3>"%(int(mth.group(2))+1), parts.path)
    else:
        page_num = 2
        path = re.sub(r"\((.*)\)(?:\(.*\))\((.*)\)", repl_wrapper(parts.path, page_num), pattern).replace("\\", "")
    return urlunparse(parts._replace(path=path))


def repl_wrapper(path, page_num):
    def _repl(mth):
        sub_path = "%s%d%s"%(mth.group(1), page_num, mth.group(2))
        if path.endswith(mth.group(2).replace("\\", "")):
            return path[:path.rfind(mth.group(2).replace("\\", ""))]+sub_path
        else:
            return path + sub_path
    return _repl


def get_val(sel_meta, response, item=None, is_after=False, self=None, key=None):
    sel = response.selector if hasattr(response, "selector") else response
    value = ""
    expression_list = ["re", "xpath", "css"]
    while not value:

        try:
            selector = expression_list.pop(0)
        except IndexError:
            break
        expressions = sel_meta.get(selector)

        if expressions:
            function = sel_meta.get("function") or globals()["function_%s_common" % selector]

            if is_after:
                function = sel_meta.get("function_after") or function

            for expression in expressions:
                try:
                    raw_data = getattr(sel, selector)(expression)
                    try:
                        value = function(raw_data, item)
                    except Exception:
                        if sel_meta.get("catch", False):
                            value = None
                        else:
                            raise
                except Exception as ex:
                    if self.crawler.settings.get("PDB_DEBUG", False):
                        traceback.print_exc()
                        import pdb
                        pdb.set_trace()
                    if ex:
                        raise
                if value:
                    break

    if not value:
        try:
            extract = sel_meta.get("extract")
            if is_after:
                extract = sel_meta.get("extract_after") or extract
            if extract:
                value = extract(item, response)
        except Exception as ex:
            if self.crawler.settings.get("PDB_DEBUG", False):
                traceback.print_exc()
                import pdb
                pdb.set_trace()
            if ex:
                raise

    return value


def post_es(host, port, finger):
    resp = requests.post(url="http://%s:%s/roc/parent_ware/_search"%(host, port), json={
        "query": {
            "term": {
                "fingerprint": finger
            }
        }
    })
    if json.loads(resp.text)["hits"]["total"]:
        return True


def drugstore_image_urls(full_image_url, image_urls):

    while 1:
        response_image = requests.get(full_image_url)
        sel = Selector(text=response_image.text)
        image_url = ''.join(sel.xpath('//*[@id="productImage"]/img/@src'))
        image_urls.append(image_url)
        no_next_image = sel.xpath('//img[contains(@src,"right_arrow_grey.gif") and @alt="no image"]')

        if no_next_image:
            break
        else:
            full_image_url = urljoin(
                full_image_url,
                ''.join(sel.xpath('//img[@alt="see next image"]/../@href'))
            )
            if not full_image_url:
                break
    return image_urls


def asos_get_skus(response):
    product_lists=[]
    size_list = re.findall(r'Array\((.*?,"\S*?",".*?",".*?",.*?)\);', response.body)

    for i in size_list:
        pro_dict = []
        size_list = [x.strip('"').strip("'") for x in i.split(',')]
        pro_dict.append(size_list)
        pattern = re.compile(r'"' + size_list[0] + size_list[2] +'":(\{.*?\})')
        sku_dict = json.loads(re.search(pattern, response.body).group(1))
        pro_dict.append(sku_dict)
        product_lists.append(pro_dict)

    return product_lists


def ae_get_colors(response):
    products_list = []
    pd_jsons = re.findall(r'\S*?\:\{colorId.*?sizedd:\[(.*?)\],(colorName:.*?,colorPrdId:.*?),.*?Information:.*?\}',
                          ''.join(re.findall(r'pdpJson:(\{.*?\})\}.*?\};', response.body)))

    for color_tuple in pd_jsons:
        prolist = []
        color_str = ''.join(color_tuple)
        size_list = re.findall(r'\{(.*?)\}', color_str)
        color_list = re.findall(r'(colorName:.*?,colorPrdId:.*)', color_str)
        for size_str in size_list:
            prolist.append(dict([[x.strip('"').strip("'") for x in l.split(':')] for l in size_str.split(',')]))

        for color in color_list:
            prolist.append(dict([[x.strip('"').strip("'") for x in l.split(':')] for l in color.split(',')]))
        products_list.append(prolist)
    return products_list


def groupby(it, key):
    """
    自实现groupby，itertool的groupby不能合并不连续但是相同的组, 且返回值是iter
    :return: 字典对象
    """
    groups = dict()
    for item in it:
        groups.setdefault(key(item), []).append(item)
    return groups


def shoebug_image_urls(response):
    prefix = ''.join(re.findall(r'"mcfileroot":"(.*?)"', response.body))
    color_dict = [json.loads(x) for x in re.findall(
        r'\{.*?\}', ''.join(re.findall(r'"colors":\[(\{.*?\})+\],', response.body)))]
    image_urls = []

    for color in color_dict:
        color_id = color['id']
        image_urls.extend(
            'http://www.shoebuy.com' + prefix + str(color_id) + '_jb' + str(x) + '.jpg' for x in color['multiImages'])

    return image_urls


def bloomingdales_price_size(response):
    price_size = []
    price_list = [','.join(x).replace('"','') for x in re.findall(
        r'"id":.*?,("upc":.*?),.*?"price":\{('
        r'"originalPrice":.*?,"intermediatePrice":.*?,"retailPrice":.*?),.*?\}', response.body)]

    for i in price_list:
        price_size.append(dict(tuple(x.split(':')) for x in i.split(',')))

    return price_size


def bloomingdales_color_map(response):

    primary = json.loads(''.join(re.findall(r'BLOOMIES.pdp.primaryImages\[.*?\].*?=.*?(\{.*?\})', response.body)))
    additional = json.loads(''.join(re.findall(r'BLOOMIES.pdp.additionalImages\[.*?\].*?=.*?(\{.*?\})', response.body)))
    for k1, v1 in primary.items():
        for k2, v2 in additional.items():
            if k1 == k2:
                primary[k1] = primary[k1] + ',' + additional[k2]

    return primary

def bloomingdales_image_urls(response):

    image_urls = []
    image_url_dicts = bloomingdales_color_map(response)

    for i in image_url_dicts.values():
        for rel_url in i.split(','):
            url = "http://images.bloomingdales.com/is/image/BLM/products/%s?" \
                  "wid=1424&qlt=90,0&layer=comp&op_sharpen=0&resMode=sharp2&op_usm=0.7,1.0,0.5,0&fmt=jpeg" % rel_url
            image_urls.append(url)

    return list(set(image_urls))


def joesnewbalanceoutlet_image_urls(x, item):

    product_id = item["product_id"]
    image_urls = []
    for code in x.extract():
        id = re.search(r"AltView\('(\d+?)', '(\w+?)'", code).group(1)
        prefix, stuffix = ("", "xl") if id == "0" else ('alt_views/', "alt%s"%id)
        image_urls.append(urljoin(item["response_url"], "/products/%s%s_%s.jpg"%(prefix, product_id, stuffix)))
    return image_urls




def neimanmarcus_color_size(item, response):

    size_and_color_json_obj = safely_json_loads(response.body)
    size_color = []
    sku_str = ''.join(size_and_color_json_obj['ProductSizeAndColor']['productSizeAndColorJSON'])
    for sku in re.findall(r'"skus":\[(.*?)\]', sku_str):
        for per_sku in re.findall(r'(\{.*?\})', sku):
            size_color.append(safely_json_loads(per_sku))
    return size_color


class InfluxDB(object):

    def __init__(self, influxdb_host, influxdb_port, influxdb_username, influxdb_password, influxdb_db):
        self.client = InfluxDBClient(influxdb_host, influxdb_port, influxdb_username, influxdb_password, influxdb_db)

    def insert_into(self, table_name, tags, fields):
        try:
            self.client.write_points([{
                "measurement": table_name,
                "tags": tags,
                "time": datetime.datetime.utcnow(),
                "fields": fields
            }])
        except Exception:
            traceback.print_exc()


class InfluxDBDescriptor(object):
    def __init__(self, client=None):
        self.client = client

    def __get__(self, instance, owner):
        if not self.client:
            self.client = InfluxDB(
                instance.crawler.settings.get("INFLUXDB_HOST", '192.168.200.131'),
                instance.crawler.settings.get("INFLUXDB_POST", 8086),
                instance.crawler.settings.get("INFLUXDB_USERNAME", ""),
                instance.crawler.settings.get("INFLUXDB _PASSWORD", ""),
                instance.crawler.settings.get("INFLUXDB_DB", 'db_roc'))
        return self.client


def retry_wrapper(retry_times, exception=Exception, error_handler=None, interval=0.1):
    """
    函数重试装饰器
    :param retry_times: 重试次数
    :param exception: 需要重试的异常
    :param error_handler: 出错时的回调函数
    :param interval: 重试间隔时间
    :return:
    """
    def out_wrapper(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            count = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except exception as e:
                    count += 1
                    if error_handler:
                        result = error_handler(func.__name__, count, e, *args, **kwargs)
                        if result:
                            count -= 1
                    if count >= retry_times:
                        raise
                    time.sleep(interval)
        return wrapper

    return out_wrapper


if __name__ == "__main__":
    pass
