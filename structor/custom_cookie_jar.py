# -*- coding:utf-8 -*-
import copy
from http import cookiejar

from scrapy.http.cookies import WrappedRequest, WrappedResponse


class CookieJar(cookiejar.LWPCookieJar):

    def clear_except(self, *names):
        for domain, domain_cookie in copy.deepcopy(self._cookies).items():
            for path, path_cookie in domain_cookie.items():
                for name, value in path_cookie.items():
                    if name in names:
                        continue
                    else:
                        del self._cookies[domain][path][name]
                                        
    def make_cookies(self, response, request):
        if not isinstance(request, WrappedRequest):
            request = WrappedRequest(request)
        if not isinstance(response, WrappedResponse):
            response = WrappedResponse(response)
        return super(CookieJar, self).make_cookies(response, request)

    def set_cookie_if_ok(self, cookie, request):
        super(CookieJar, self).set_cookie_if_ok(cookie, WrappedRequest(request))
        
    def extract_cookies(self, response, request):
        wreq = WrappedRequest(request)
        wrsp = WrappedResponse(response)
        return super(CookieJar, self).extract_cookies(wrsp, wreq)
    
    def add_cookie_header(self, request):
        super(CookieJar, self).add_cookie_header(WrappedRequest(request))