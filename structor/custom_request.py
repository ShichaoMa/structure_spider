"""
scrapy1.5限制request.callback and request.errback不能为非None以外的任何非可调用对象，导致一些功能无法实现，这里将其还原成1.4版本的Request
"""
from scrapy import Request as _Request
from scrapy.http.headers import Headers


class Request(_Request):
    def __init__(self, url, callback=None, method='GET', headers=None, body=None,
                 cookies=None, meta=None, encoding='utf-8', priority=0,
                 dont_filter=False, errback=None, flags=None):

        self._encoding = encoding  # this one has to be set first
        self.method = str(method).upper()
        self._set_url(url)
        self._set_body(body)
        assert isinstance(priority, int), "Request priority not an integer: %r" % priority
        self.priority = priority

        assert callback or not errback, "Cannot use errback without a callback"
        self.callback = callback
        self.errback = errback

        self.cookies = cookies or {}
        self.headers = Headers(headers or {}, encoding=encoding)
        self.dont_filter = dont_filter

        self._meta = dict(meta) if meta else None
        self.flags = [] if flags is None else list(flags)
