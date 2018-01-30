# -*- coding:utf-8 -*-
# 这个配置文件包含所有爬虫所需要的配置信息
# 使用自定义的localsettings.py可以重写配置信息
# Web Walker Settings
# ~~~~~~~~~~~~~~~~~~~~~~~
# 测试专用
import sys
#sys.path.insert(0, "/home/ubuntu/myprojects/webWalker")
#sys.path.insert(0, "log_to_kafka")
import os
import pkgutil

# Redis host and port
REDIS_HOST = os.environ.get("REDIS_HOST", '127.0.0.1')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))

IDLE = eval(os.environ.get("IDLE", "True"))

RETRY_HTTP_CODES = [500, 502, 503, 504, 400, 408, 403, 304]

CONCURRENT_REQUESTS = int(os.environ.get('CONCURRENT_REQUESTS', 1))
CONCURRENT_REQUESTS_PER_DOMAIN = int(os.environ.get('CONCURRENT_REQUESTS_PER_DOMAIN', 1))
CONCURRENT_REQUESTS_PER_IP = int(os.environ.get('CONCURRENT_REQUESTS_PER_IP', 1))

DEFAULT_REQUEST_HEADERS = {
    b'Accept': b'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    b'Accept-Language': b'en',
    b'Accept-Encoding': b'deflate, gzip'
}

# 测试环境下如果没有安装redis可以使用简单redis
CUSTOM_REDIS = True

# 在redis中使用多个set存放代理 格式：ip:port
# 目前在custom_redis中不支持
PROXY_SETS = "good_proxies"

PROXY_ACCOUNT_PASSWORD = os.environ.get("PROXY_ACCOUNT_PASSWORD", '')

# 每次请求都更换代理
CHANGE_PROXY = eval(os.environ.get("CHANGE_PROXY", "False"))

# 自带了一些user_agents，推荐不改
USER_AGENT_LIST = pkgutil.get_data('structor', 'user_agents.list')

# 重试次数
RETRY_TIMES = int(os.environ.get('RETRY_TIMES', 100))

# 对于有去重需求的分类链接，去重的超时时间，默认3600s
# 如果该分类抓取完毕需要很长时间，中间还有可能关闭，那这个时间需要长一点
DUPLICATE_TIMEOUT = int(os.environ.get('DUPLICATE_TIMEOUT', 60*60))

# 重定向次数
REDIRECT_MAX_TIMES = int(os.environ.get('REDIRECT_MAX_TIMES', 20))

# 每次重定向优先级调整
REDIRECT_PRIORITY_ADJUST = int(os.environ.get('REDIRECT_PRIORITY_ADJUST', -1))

# 最大请求速度n/min
SPEED = 1000

# 日志配置
SC_LOG_LEVEL = os.environ.get('SC_LOG_LEVEL', 'DEBUG')
SC_LOG_JSON = eval(os.environ.get('SC_LOG_JSON', "False"))
SC_LOG_DIR = os.environ.get('SC_LOG_DIR', "logs")
SC_LOG_STDOUT = eval(os.environ.get('SC_LOG_STDOUT', "True"))
SC_LOG_MAX_BYTES = os.environ.get('SC_LOG_MAX_BYTES', 10*1024*1024)
SC_LOG_BACKUPS = int(os.environ.get('SC_LOG_BACKUPS', 5))
SC_LOG_UDP_HOST = os.environ.get('SC_LOG_UDP_HOST', '192.168.200.132')
SC_LOG_UDP_PORT = os.environ.get('SC_LOG_UDP_PORT', 5230)
SC_LOG_FILE = eval(os.environ.get('SC_LOG_FILE', "False"))

# 有些网站可能需要提供一些自定义的请求头
HEADERS = {
    # "douban": {
    #             "Cookie": """bid=ypX2zypkXfo; _pk_ref.100001.4cf6=%5B%22%22%2C%22%22%2C1503200061%2C%22https%3A%2F%2Fwww.douban.com%2F%22%5D; __yadk_uid=VYhLceTc9qMjKNcE5vccErw6xCuxRrXv; ps=y; dbcl2="165640820:ANsb2+OLOcY"; ck=pjDa; ap=1; __utmt=1; ct=y; _pk_id.100001.4cf6=6d068bdaab71bc42.1503200061.1.1503204354.1503200061.; _pk_ses.100001.4cf6=*; __utma=30149280.1022566207.1503192225.1503196092.1503199543.3; __utmb=30149280.46.9.1503204347489; __utmc=30149280; __utmz=30149280.1503196092.2.2.utmcsr=baidu|utmccn=(organic)|utmcmd=organic; __utmv=30149280.16564; __utma=223695111.1433844575.1503200061.1503200061.1503200061.1; __utmb=223695111.0.10.1503200061; __utmc=223695111; __utmz=223695111.1503200061.1.1.utmcsr=douban.com|utmccn=(referral)|utmcmd=referral|utmcct=/; ll="0"; push_noty_num=0; push_doumail_num=0; _vwo_uuid_v2=95C0F810F7385DBB9DEA9306CD09844E|387c6a20e70c3042562fba44cc709e9f""",
    #             },
}

BOT_NAME = 'structor'

SPIDER_MODULES = ['structor.spiders']

NEWSPIDER_MODULE = 'structor.spiders'

# Enables scheduling storing requests queue in redis.
SCHEDULER = "structor.scheduler.Scheduler"

TASK_QUEUE_TEMPLATE = "%s:request:queue"

# 统计抓取信息
STATS_CLASS = 'structor.stats_collectors.StatsCollector'


# Store scraped item in redis for post-processing.
ITEM_PIPELINES = {
    # 'structor.pipelines.MongoPipeline': 100,
}

DOWNLOADER_MIDDLEWARES = {
    'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
    'scrapy.downloadermiddlewares.retry.RetryMiddleware':None,
    'scrapy.downloadermiddlewares.redirect.RedirectMiddleware': None,
    'scrapy.downloadermiddlewares.cookies.CookiesMiddleware': None,
    'structor.downloadermiddlewares.CustomUserAgentMiddleware': 400,
    # Handle timeout retries with the redis scheduler and logger
    'structor.downloadermiddlewares.CustomRetryMiddleware': 510,
    # custom cookies to not persist across crawl requests
    # cookie中间件需要放在验证码中间件后面，验证码中间件需要放到代理中间件后面
    'structor.downloadermiddlewares.CustomCookiesMiddleware': 585,
    'structor.downloadermiddlewares.ProxyMiddleware': 590,
    'structor.downloadermiddlewares.CustomRedirectMiddleware': 600,
}

# 在生产上关闭内建logging
LOG_ENABLED = eval(os.environ.get('LOG_ENABLED', "True"))

# http错误也会返回
HTTPERROR_ALLOW_ALL = eval(os.environ.get('HTTPERROR_ALLOW_ALL', "True"))

# 下载超时时间
DOWNLOAD_TIMEOUT = int(os.environ.get('DOWNLOAD_TIMEOUT', 30))

# Avoid in-memory DNS cache. See Advanced topics of docs for info
DNSCACHE_ENABLED = True

try:
    from .localsettings import *
except ImportError:
    pass
