import random
import base64
import traceback

from scrapy.exceptions import IgnoreRequest
from scrapy.http import HtmlResponse, Response
from scrapy.utils.response import response_status_message
from scrapy.core.downloader.handlers.http11 import TunnelError
from scrapy.downloadermiddlewares.redirect import RedirectMiddleware

from twisted.web.client import ResponseFailed
from twisted.internet import defer
from twisted.internet.error import TimeoutError, DNSLookupError, \
    ConnectionRefusedError, ConnectionDone, ConnectError, \
    ConnectionLost, TCPTimedOutError

from toolkit import parse_cookie

from .utils import CustomLogger
from .custom_cookie_jar import CookieJar


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
            proxy = self.crawler.spider.redis_conn.srandmember(
                random.choice(self.proxy_sets))
        except Exception:
            proxy = None
        return proxy and proxy.decode()

    def process_request(self, request, spider):
        if self.settings.get("CHANGE_PROXY", False) or spider.change_proxy:
            spider.proxy = None
            spider.change_proxy = False

        if self.proxy_sets:
                spider.proxy = spider.proxy or self.choice()
        if spider.proxy:
            proxy = "http://" + spider.proxy
            request.meta['proxy'] = proxy
            self.logger.debug("Use proxy %s to send request", proxy)
            if self.settings.get("PROXY_ACCOUNT_PASSWORD"):
                encoded_user_pass = base64.b64encode(
                    self.settings.get("PROXY_ACCOUNT_PASSWORD").encode())
                request.headers['Proxy-Authorization'] =\
                    b'Basic ' + encoded_user_pass


class CustomUserAgentMiddleware(DownloaderBaseMiddleware):
    def __init__(self, settings, user_agent='Scrapy'):
        super(CustomUserAgentMiddleware, self).__init__(settings)
        user_agents = settings.get('USER_AGENT_LIST').decode().split("\n")

        if not user_agents:
            ua = settings.get('USER_AGENT', user_agent)
            self.user_agent_list = [ua]
        else:
            self.user_agent_list = [i.strip() for i in user_agents if i.strip()]

        self.choicer = self.choice()
        self.user_agent = self.choicer.__next__() or user_agent

    def choice(self):
        while True:
            if self.user_agent_list:
                for user_agent in self.user_agent_list:
                    yield user_agent
            else:
                yield None

    def process_request(self, request, spider):
        if self.user_agent:
            request.headers['User-Agent'] = self.user_agent
            self.logger.debug(
                'User-Agent: %s %s', request.headers.get('User-Agent'), request)
        else:
            self.logger.error('User-Agent: ERROR with user agent list')


class CustomRedirectMiddleware(DownloaderBaseMiddleware, RedirectMiddleware):
    def __init__(self, settings):
        super(CustomRedirectMiddleware, self).__init__(settings)
        self.max_redirect_times = self.settings.getint("REDIRECT_MAX_TIMES")
        self.priority_adjust = self.settings.getint("REDIRECT_PRIORITY_ADJUST")

    def _redirect(self, redirected, request, spider, reason):
        reason = response_status_message(reason)
        redirects = request.meta.get('redirect_times', 0) + 1

        if redirects <= self.max_redirect_times:
            redirected.meta['redirect_times'] = redirects
            redirected.meta.setdefault('redirect_urls', []).append(request.url)
            redirected.meta['priority'] += self.priority_adjust
            self.logger.debug(
                "Redirecting %s to %s from %s for %s times.", reason,
                redirected.url, request.url, redirected.meta.get("redirect_times"))
            return redirected
        else:
            if request.callback == spider.parse:
                self.crawler.stats.inc_total_pages(request.meta['crawlid'])
            self.logger.error("Gave up redirecting %s (failed %d times): %s",
                    request.url, redirects, reason)
            spider.crawler.stats.set_failed_download(
                request.meta['crawlid'], request.url, reason)
            if "item_collector" in request.meta:
                return HtmlResponse(
                    request.url, body=b"<html></html>",
                    status=999, request=request)
            else:
                raise IgnoreRequest("%s %s" % (
                    reason, "retry %s times. " % redirects))


class CustomCookiesMiddleware(DownloaderBaseMiddleware):

    def __init__(self, settings):
        super(CustomCookiesMiddleware, self).__init__(settings)
        self.jar = CookieJar()

    @classmethod
    def from_crawler(cls, crawler):
        cls.crawler = crawler
        return cls(crawler.settings)

    @staticmethod
    def _format_cookie(cookie):
        cookie_str = '%s=%s' % (cookie['name'], cookie['value'])

        if cookie.get('path', None):
            cookie_str += '; Path=%s' % cookie['path']
        if cookie.get('domain', None):
            cookie_str += '; Domain=%s' % cookie['domain']

        return cookie_str

    def _get_request_cookies(self, jar, request):
        if isinstance(request.cookies, dict):
            cookie_list = \
                [{'name': k, 'value': v} for k, v in request.cookies.items()]
        else:
            cookie_list = request.cookies

        cookies = [self._format_cookie(x) for x in cookie_list]
        headers = {'Set-Cookie': cookies}
        response = Response(request.url, headers=headers)
        return jar.make_cookies(response, request)

    def process_request(self, request, spider):
        cookies = self.settings.get("COOKIES", "")
        if not request.meta.get("dont_update_cookies"):
            request.cookies.update(parse_cookie(cookies))
        # 从request.cookies中获取cookies
        cookies = self._get_request_cookies(self.jar, request)

        # 将cookie放到jar中
        for cookie in cookies:
            self.jar.set_cookie_if_ok(cookie, request)
        # 将reuqest.headers中的cookie删除
        request.headers.pop('Cookie', None)
        # 将jar中的cookie重新应用到request中
        self.jar.add_cookie_header(request)
        cl = request.headers.getlist('Cookie')
        if cl:
            self.logger.debug("Sending cookie %s to %s", cl, request)

    def process_response(self, request, response, spider):
        self.jar.extract_cookies(response, request)
        return response


class CustomRetryMiddleware(DownloaderBaseMiddleware):
    EXCEPTIONS_TO_RETRY = (defer.TimeoutError, TimeoutError, DNSLookupError,
                           ConnectionRefusedError, ConnectionDone, ConnectError,
                           ConnectionLost, TCPTimedOutError, ResponseFailed,
                           IOError, TypeError, ValueError, TunnelError)

    def __init__(self, settings):
        self.max_retry_times = settings.getint('RETRY_TIMES')
        self.retry_http_codes = set(
            int(x) for x in settings.getlist('RETRY_HTTP_CODES'))
        self.priority_adjust = settings.getint('RETRY_PRIORITY_ADJUST')
        super(CustomRetryMiddleware, self).__init__(settings)

    def process_response(self, request, response, spider):
        if response.status in self.retry_http_codes:
            reason = response_status_message(response.status)
            return self._retry(request, reason, spider) or response
        return response

    def process_exception(self, request, exception, spider):
        if isinstance(exception, self.EXCEPTIONS_TO_RETRY):
            return self._retry(request, "%s:%s" % (
                    exception.__class__.__name__, exception), spider)
        else:
            self.logger.error("In retry request error " + traceback.format_exc())
            raise IgnoreRequest("%s:%s unhandle error. " % (
                exception.__class__.__name__, exception))

    def _retry(self, request, reason, spider):
        spider.change_proxy = True
        retries = request.meta.get('retry_times', 0) + 1

        if retries <= self.max_retry_times:
            retryreq = request.copy()
            retryreq.meta['retry_times'] = retries
            retryreq.meta['priority'] = \
                retryreq.meta['priority'] + self.settings.get(
                    "REDIRECT_PRIORITY_ADJUST")
            self.logger.debug("Reason: %s of %s times for %s to retry. ",
                    reason, retries, request.url)
            return retryreq
        else:
            if request.callback == spider.parse:
                spider.crawler.stats.inc_total_pages(request.meta['crawlid'])
            self.logger.error("Gave up retrying %s (failed %d times): %s",
                    request.url, retries, reason)
            spider.crawler.stats.set_failed_download(
                request.meta['crawlid'], request.url, reason)
            if "item_collector" in request.meta:
                return HtmlResponse(
                    request.url, body=b"<html></html>",
                    status=999, request=request)
            else:
                raise IgnoreRequest("%s %s" % (
                    reason, "retry %s times. " % retries))
