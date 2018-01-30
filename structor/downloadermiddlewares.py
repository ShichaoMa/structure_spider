import os
import random
import base64
import traceback

from w3lib.url import safe_url_string
from urllib.parse import urljoin

from scrapy import signals
from scrapy.downloadermiddlewares.cookies import CookiesMiddleware
from scrapy.downloadermiddlewares.redirect import RedirectMiddleware
from scrapy.downloadermiddlewares.retry import RetryMiddleware
from scrapy.downloadermiddlewares.useragent import UserAgentMiddleware
from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.utils.response import response_status_message
from twisted.web.client import ResponseFailed
from twisted.internet import defer
from twisted.internet.error import TimeoutError, DNSLookupError, \
    ConnectionRefusedError, ConnectionDone, ConnectError, \
    ConnectionLost, TCPTimedOutError
from scrapy.core.downloader.handlers.http11 import TunnelError

from toolkit import parse_cookie

from .utils import CustomLogger
from .exception_process import process_exception_method_wrapper, \
    process_requset_method_wrapper, process_response_method_wrapper


class DownloaderBaseMiddleware(object):
    def __init__(self, settings):
        self.logger = CustomLogger.from_crawler(self.crawler)
        self.settings = settings

    @classmethod
    def from_crawler(cls, crawler):
        cls.crawler = crawler
        obj = cls(crawler.settings)
        return obj


class ProxyMiddleware(DownloaderBaseMiddleware):

    def __init__(self, settings):

        super(ProxyMiddleware, self).__init__(settings)
        self.proxy_sets = self.settings.get("PROXY_SETS", "proxy_set").split(",")

    def choice(self):
        try:
            proxy = self.crawler.spider.redis_conn.srandmember(random.choice(self.proxy_sets))
        except Exception:
            proxy = None
        return proxy and proxy.decode("utf-8")

    @process_requset_method_wrapper
    def process_request(self, request, spider):
        if self.settings.get("CHANGE_PROXY", False) or spider.change_proxy:
            spider.proxy = None
            spider.change_proxy = False

        if self.proxy_sets:
                spider.proxy = spider.proxy or self.choice()

        if spider.proxy:
            proxy = "http://"+spider.proxy
            request.meta['proxy'] = proxy
            self.logger.debug("use proxy %s to send request"%proxy, extra={"rasp_proxy": proxy})
            if self.settings.get("PROXY_ACCOUNT_PASSWORD"):
                encoded_user_pass = base64.b64encode(self.settings.get("PROXY_ACCOUNT_PASSWORD").encode("utf-8"))
                request.headers['Proxy-Authorization'] = b'Basic ' + encoded_user_pass


class CustomUserAgentMiddleware(UserAgentMiddleware, DownloaderBaseMiddleware):
    def __init__(self, settings, user_agent='Scrapy'):
        DownloaderBaseMiddleware.__init__(self, settings)
        UserAgentMiddleware.__init__(self)
        user_agent_list = settings.get('USER_AGENT_LIST')

        if not user_agent_list:
            ua = settings.get('USER_AGENT', user_agent)
            self.user_agent_list = [ua]
        else:
            self.user_agent_list = [i.strip() for i in user_agent_list.decode("utf-8").split('\n') if i.strip()]

        self.default_agent = user_agent
        self.choicer = self.choice()
        self.user_agent = self.choicer.__next__() or user_agent

    @classmethod
    def from_crawler(cls, crawler):
        cls.crawler = crawler
        obj = cls(crawler.settings)
        crawler.signals.connect(obj.spider_opened,
                                signal=signals.spider_opened)
        return obj

    def choice(self):
        while True:
            if self.user_agent_list:
                for user_agent in self.user_agent_list:
                    yield user_agent
            else:
                yield None

    @process_requset_method_wrapper
    def process_request(self, request, spider):
        if self.user_agent:
            request.headers['User-Agent'] = self.user_agent
            self.logger.debug('User-Agent: {} {}'.format(request.headers.get('User-Agent'), request))
        else:
            self.logger.error('User-Agent: ERROR with user agent list')


class CustomRedirectMiddleware(DownloaderBaseMiddleware, RedirectMiddleware):
    def __init__(self, settings):
        RedirectMiddleware.__init__(self, settings)
        DownloaderBaseMiddleware.__init__(self, settings)
        self.stats = self.crawler.stats

    @process_response_method_wrapper
    def process_response(self, request, response, spider):

        if request.meta.get('dont_redirect', False):
            return response

        if response.status in [302, 303] and 'Location' in response.headers:
            redirected_url = urljoin(request.url, safe_url_string(response.headers['location']))
            redirected = self._redirect_request_using_get(request, redirected_url)
            return self._redirect(redirected, request, spider, response.status)

        if response.status in [301, 307] and 'Location' in response.headers:
            redirected_url = urljoin(request.url, safe_url_string(response.headers['location']))
            redirected = request.replace(url=redirected_url)
            return self._redirect(redirected, request, spider, response.status)

        return response

    def _redirect(self, redirected, request, spider, reason):

        reason = response_status_message(reason)
        redirects = request.meta.get('redirect_times', 0) + 1

        if redirects <= self.max_redirect_times:
            redirected.meta['redirect_times'] = redirects
            redirected.meta['redirect_urls'] = request.meta.get('redirect_urls', []) + \
                                               [request.url]
            redirected.meta['priority'] = redirected.meta['priority'] + self.priority_adjust
            self.logger.debug("Redirecting %s to %s from %s for %s times " % (
                reason, redirected.url, request.url, redirected.meta.get("redirect_times")))
            return redirected
        else:
            self.logger.info("Discarding %s: max redirections reached" % request.url)
            if request.meta.get("callback") == "parse":
                self.crawler.stats.inc_total_pages(crawlid=request.meta['crawlid'])
                self.logger.error(
                    " in redicrect request error to failed pages url:%s, exception:%s, meta:%s" % (
                        request.url, reason, request.meta))

            raise IgnoreRequest("max redirections reached:%s" % reason)


class CustomCookiesMiddleware(DownloaderBaseMiddleware, CookiesMiddleware):
    def __init__(self, settings):
        DownloaderBaseMiddleware.__init__(self, settings)
        CookiesMiddleware.__init__(self, settings.getbool('COOKIES_DEBUG'))
        self.current_cookies = {}

    @classmethod
    def from_crawler(cls, crawler):
        cls.crawler = crawler
        obj = cls(crawler.settings)
        if not crawler.settings.getbool('COOKIES_ENABLED'):
            raise NotConfigured
        return obj

    @process_requset_method_wrapper
    def process_request(self, request, spider):

        if 'dont_merge_cookies' in request.meta:
            return
        self.logger.debug("process in CustomCookiesMiddleware. ")
        headers = self.settings.get("HEADERS", {}).get(spider.name, {}).copy()
        cookiejarkey = request.meta.get("cookiejar", spider.proxy)
        jar = self.jars[cookiejarkey]
        if not request.meta.get("dont_update_cookies"):
            request.cookies.update(parse_cookie(headers.get("Cookie", "")))
        cookies = self._get_request_cookies(jar, request)

        for cookie in cookies:
            jar.set_cookie_if_ok(cookie, request)

        request.headers.pop('Cookie', None)
        jar.add_cookie_header(request)
        for key in headers.keys():
            if key not in request.headers:
                request.headers[key] = [headers[key]]
        cl = request.headers.getlist('Cookie')
        if cl:
            msg = "Sending cookies to: %s" % request + os.linesep
            msg += os.linesep.join("Cookie: %s" % c for c in cl)
            self.logger.debug(msg)

    @process_response_method_wrapper
    def process_response(self, request, response, spider):

        if request.meta.get('dont_merge_cookies', False):
            return response

        self._debug_set_cookie(response, spider)
        cookiejarkey = request.meta.get("cookiejar", "default")
        jar = self.jars[cookiejarkey]
        jar.extract_cookies(response, request)
        return response


class CustomRetryMiddleware(DownloaderBaseMiddleware, RetryMiddleware):
    EXCEPTIONS_TO_RETRY = (defer.TimeoutError, TimeoutError, DNSLookupError,
                           ConnectionRefusedError, ConnectionDone, ConnectError,
                           ConnectionLost, TCPTimedOutError, ResponseFailed,
                           IOError, TypeError, ValueError, TunnelError)

    def __init__(self, settings):
        RetryMiddleware.__init__(self, settings)
        DownloaderBaseMiddleware.__init__(self, settings)

    @process_response_method_wrapper
    def process_response(self, request, response, spider):

        if request.meta.get('dont_retry', False):
            return response

        if response.status in self.retry_http_codes:
            reason = response_status_message(response.status)
            return self._retry(request, reason, spider) or response

        return response

    @process_exception_method_wrapper
    def process_exception(self, request, exception, spider):

        if isinstance(exception, self.EXCEPTIONS_TO_RETRY) \
                and not request.meta.get('dont_retry', False):
            return self._retry(request, "%s:%s" % (exception.__class__.__name__, exception), spider)

        else:
            if request.meta.get("callback") == "parse":
                spider.crawler.stats.inc_total_pages(crawlid=request.meta['crawlid'])

            self.logger.error("in retry request error %s" % traceback.format_exc())
            raise IgnoreRequest("%s:%s unhandle error. " % (exception.__class__.__name__, exception))

    def _retry(self, request, reason, spider):
        spider.change_proxy = True
        retries = request.meta.get('retry_times', 0) + 1

        if request.meta.get("if_next_page"):
            self.logger.debug("in _retry re-yield next_pages request: %s, reason: %s. " % (request.url, reason))
            return request.copy()
        elif retries <= self.max_retry_times:
            retryreq = request.copy()
            retryreq.meta['retry_times'] = retries
            retryreq.dont_filter = True
            retryreq.meta['priority'] = retryreq.meta['priority'] + self.crawler.settings.get(
                "REDIRECT_PRIORITY_ADJUST")
            self.logger.debug("in _retry retries times: %s, re-yield request: %s, reason: %s" % (
            retries, request.url, reason))
            return retryreq

        else:
            if request.meta.get("callback") == "parse":
                spider.crawler.stats.inc_total_pages(crawlid=request.meta['crawlid'])
            self.logger.error(
                "retry request error to failed pages url:%s, exception:%s, meta:%s" % (
                    request.url, reason, request.meta))
            self.logger.info("Gave up retrying %s (failed %d times): %s" % (request.url, retries, reason))
            raise IgnoreRequest("%s %s" % (reason, "retry %s times. "%retries))

