# -*- coding:utf-8 -*-
import pickle
import time
import types

from scrapy.http.request import Request
from toolkit import parse_cookie

from .exception_process import next_request_method_wrapper, enqueue_request_method_wrapper
from .utils import CustomLogger


class Scheduler(object):
    # 记录当前正在处理的item, 在处理异常时使用
    present_item = None
    spider = None

    def __init__(self, crawler):
        self.settings = crawler.settings
        self.logger = CustomLogger.from_crawler(crawler)
        if self.settings.getbool("CUSTOM_REDIS"):
            from custom_redis.client import Redis
        else:
            from redis import Redis
        self.redis_conn = Redis(self.settings.get("REDIS_HOST"),
                                self.settings.getint("REDIS_PORT"))
        self.queue_name = self.queue_name = self.settings.get("TASK_QUEUE_TEMPLATE", "%s:request:queue")
        self.queues = {}
        self.request_interval = 60/self.settings.getint("SPEED", 60)
        self.last_acs_time = time.time()


    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def open(self, spider):
        self.spider = spider
        self.queue_name = self.queue_name % spider.name
        spider.set_redis(self.redis_conn)

    def request_to_dict(self, request):

        headers = dict([(item[0].decode("ascii"), item[1]) for item in request.headers.items()])
        req_dict = {
            'url': request.url,
            'method': request.method,
            'headers': headers,
            'body': request.body,
            'cookies': request.cookies,
            'meta': request.meta,
            '_encoding': request._encoding,
            'dont_filter': request.dont_filter,
            'callback': request.callback if not isinstance(
                request.callback, types.MethodType) else request.callback.__name__,
            'errback': request.errback if not isinstance(
                request.errback, types.MethodType) else request.errback.__name__,
        }
        return req_dict

    @enqueue_request_method_wrapper
    def enqueue_request(self, request):
        req_dict = self.request_to_dict(request)
        self.redis_conn.zadd(self.queue_name, pickle.dumps(req_dict), -int(req_dict["meta"]["priority"]))
        self.logger.debug("Crawlid: '{id}' Url: '{url}' added to queue"
                          .format(id=req_dict['meta']['crawlid'],
                                  url=req_dict['url']))

    @next_request_method_wrapper
    def next_request(self):

        self.logger.info("length of queue %s is %s" % (self.queue_name, self.redis_conn.zcard(self.queue_name)))
        item = None
        if time.time() - self.request_interval < self.last_acs_time:
            return item
        if self.settings.getbool("CUSTOM_REDIS"):
            item = self.redis_conn.zpop(self.queue_name)
        else:
            pipe = self.redis_conn.pipeline()
            pipe.multi()
            pipe.zrange(self.queue_name, 0, 0).zremrangebyrank(self.queue_name, 0, 0)
            result, _ = pipe.execute()

            if result:
                item = result[0]

        if item:
            self.last_acs_time = time.time()
            item = pickle.loads(item)
            self.present_item = item
            headers = item.get("headers", {})
            body = item.get("body")
            if item.get("method"):
                method = item.get("method")
            else:
                method = "GET"

            try:
                req = Request(item['url'], method=method, body=body, headers=headers)
            except ValueError:
                req = Request('http://' + item['url'], method=method, body=body, headers=headers)

            if 'callback' in item:
                cb = item['callback']
                if cb and self.spider:
                    cb = getattr(self.spider, cb)
                    req.callback = cb

            if 'errback' in item:
                eb = item['errback']
                if eb and self.spider:
                    eb = getattr(self.spider, eb)
                    req.errback = eb

            if 'meta' in item:
                item = item['meta']

            # defaults not in schema
            if 'curdepth' not in item:
                item['curdepth'] = 0

            if "retry_times" not in item:
                item['retry_times'] = 0

            for key in item.keys():
                req.meta[key] = item[key]

            if 'useragent' in item and item['useragent'] is not None:
                req.headers['User-Agent'] = item['useragent']

            if 'cookie' in item and item['cookie'] is not None:
                if isinstance(item['cookie'], dict):
                    req.cookies = item['cookie']
                elif isinstance(item['cookie'], (str, bytes)):
                    req.cookies = parse_cookie(item['cookie'])

            return req

    def close(self, reason):
        self.logger.info("Closing Spider", {'spiderid': self.spider.name})

    def has_pending_requests(self):
        return False


class SingleTaskScheduler(Scheduler):

    def __init__(self, crawler):
        super(SingleTaskScheduler, self).__init__(crawler)
        self.queue_name = "%s:single:queue"

    def has_pending_requests(self):
        return self.redis_conn.zcard(self.queue_name) > 0