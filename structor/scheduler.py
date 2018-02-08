# -*- coding:utf-8 -*-
import time
import pickle

from .utils import CustomLogger


class Scheduler(object):
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
        self.queue_name = None
        self.queues = {}
        self.request_interval = 60/self.settings.getint("SPEED", 60)
        self.last_acs_time = time.time()

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def open(self, spider):
        self.spider = spider
        self.queue_name = \
            self.settings.get("TASK_QUEUE_TEMPLATE", "%s:request:queue") % spider.name
        spider.set_redis(self.redis_conn)

    def enqueue_request(self, request):
        request.callback = getattr(request.callback, "__name__", request.callback)
        request.errback = getattr(request.errback, "__name__", request.errback)
        self.redis_conn.zadd(
            self.queue_name, pickle.dumps(request), -int(request.meta["priority"]))
        self.logger.debug(
            "Crawlid: %s, url: %s added to queue. " % (request.meta['crawlid'], request.url))

    def next_request(self):
        self.logger.debug(
            "length of queue %s is %s" % (self.queue_name, self.redis_conn.zcard(self.queue_name)))
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
            request = pickle.loads(item)
            request.callback = request.callback and getattr(self.spider, request.callback)
            request.errback = request.errback and getattr(self.spider, request.errback)
            return request

    def close(self, reason):
        self.logger.info("Closing Spider: %s. " % self.spider.name)

    def has_pending_requests(self):
        return False


class SingleTaskScheduler(Scheduler):

    def __init__(self, crawler):
        super(SingleTaskScheduler, self).__init__(crawler)
        self.queue_name = "%s:single:queue"

    def has_pending_requests(self):
        return self.redis_conn.zcard(self.queue_name) > 0
