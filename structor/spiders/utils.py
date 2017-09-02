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
import traceback

from logging import handlers
from collections import OrderedDict, defaultdict
from functools import wraps, reduce
from pythonjsonlogger.jsonlogger import JsonFormatter
from urllib.parse import urlparse, urlunparse, urlencode, urljoin

from scrapy import Selector, Item
from scrapy.http import Request
from scrapy.loader import ItemLoader
from scrapy.utils.misc import arg_to_iter
from scrapy.loader.processors import Compose


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


def strip(value, chars=None):
    """
    strip字段
    :param value:
    :param chars:
    :return:
    """
    if isinstance(value, str):
        return value.strip(chars)
    return value


def decode(value, encoding="utf-8"):
    """
    decode字段
    :param value:
    :param encoding:
    :return:
    """
    return value.decode(encoding)


def encode(value, encoding="utf-8"):
    """
    encode字段
    :param value:
    :param encoding:
    :return:
    """
    return value.encode(encoding)


def rid(value, repl):
    """
    去掉指定字段
    :param value:
    :param repl: 去掉的字段
    :return:
    """
    value.replace(repl, "")


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
    :param item:
    :return:
    """
    return "".join(x).strip()


def wrap_key(json_str, key_pattern=re.compile(r"([a-zA-Z_]\w*)[\s]*\:")):
    """
    将javascript 对象字串串形式的key转换成被双字符包裹的格式如{a: 1} => {"a": 1}
    :param json_str:
    :param key_pattern:
    :return:
    """
    json_str = key_pattern.sub('"\g<1>":', json_str)
    return json_str


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
        return []
    if isinstance(iter[0], dict):
        result = {}
        for i in iter:
            result.update(i)
    else:
        result = reduce(lambda x, y: list(x) + list(y), iter)
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
        if val == '"' and json_str[index - 1] != "\\":
            if double_quote:
                double_quote.pop(0)
            else:
                double_quote.append(val)
        if val == "'" and json_str[index - 1] != "\\":
            if not double_quote:
                val = '"'
        new_lst.append(val)
    return "".join(new_lst)


def format_html_string(html):
    """
    格式化html
    :param html:
    :return:
    """
    trims = [(r'\n', ''),
             (r'\t', ''),
             (r'\r', ''),
             (r'  ', ''),
             (r'\u2018', "'"),
             (r'\u2019', "'"),
             (r'\ufeff', ''),
             (r'\u2022', ":"),
             (r"<([a-z][a-z0-9]*)\ [^>]*>", '<\g<1>>'),
             (r'<\s*script[^>]*>[^<]*<\s*/\s*script\s*>', ''),
             (r"</?a.*?>", '')]
    return reduce(lambda string, replacement: re.sub(replacement[0], replacement[1], html), trims, html)


def urldecode(query):
    """
    与urlencode相反，不过没有unquote
    :param query:
    :return:
    """
    return dict(x.split("=") for x in query.split("&"))


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


class P22P3Encoder(json.JSONEncoder):
    """
    python2转换python3时使用的json encoder
    """

    def default(self, obj):
        if isinstance(obj, bytes):
            return obj.decode("utf-8")
        if isinstance(obj, (types.GeneratorType, map, filter)):
            return list(obj)
        # Let the base class default method raise the TypeError
        return json.JSONEncoder.default(self, obj)


def timeout(timeout_time, default):
    """
    Decorate a method so it is required to execute in a given time period,
    or return a default value.
    :param timeout_time:
    :param default:
    :return:
    """

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
    """
    模仿selector.re
    :param regex:
    :param text:
    :return:
    """
    return re.findall(regex, text)


def replace_dot(data):
    """
    mongodb不支持key中带有.，该函数用来将.转换成_
    :param data:
    :return:
    """
    new_data = {}
    for k, v in data.items():
        new_data[k.replace(".", "_")] = v

    return new_data


def groupby(it, key):
    """
    自实现groupby，itertool的groupby不能合并不连续但是相同的组, 且返回值是iter
    :return: 字典对象
    """
    groups = dict()
    for item in it:
        groups.setdefault(key(item), []).append(item)
    return groups


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
        replace_entities = True
        regexs = arg_to_iter(regex)
        while True:
            try:
                for regex in regexs:
                    self.add_value(field_name, self.selector.re(regex, replace_entities), **kwargs)
                break
            except json.decoder.JSONDecodeError:
                replace_entities = False

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
            item[field_name] = value or field.get("default", "")

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


def parse_cookie(string):
    """
    解析cookie
    :param string:
    :return:
    """
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
    for k, v in info.items():
        for item in v:
            if item[0] == 2 and not item[1] == '127.0.0.1':
                netcard_info.append((k, item[1]))
    return netcard_info


def get_ip_address():
    """
    获取本机局域网ip
    :return:
    """
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


class ItemCollector(object):
    """
    ItemCollector的实现
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


class ItemEncoder(json.JSONEncoder):
    """
    将Item转换成字典
    """
    def default(self, obj):
        if isinstance(obj, Item):
            return dict(obj)
        # Let the base class default method raise the TypeError
        return json.JSONEncoder.default(self, obj)


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
        if filename.count("utils"):
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
        logger.format_string = '%(asctime)s [%(name)s] %(levelname)s: %(message)s'
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


if __name__ == "__main__":
    pass
