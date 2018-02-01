# -*- coding:utf-8 -*-
import fnmatch
import argparse

from redis import Redis


def format(d, f=False):
    for k, v in d.items():
        if f:
            print("reason --> %s" % v.decode().ljust(30))
            print("url    --> %s" % k.decode().ljust(30))
        else:
            print("%s -->  %s" % (k.decode().ljust(30), v.decode()))


def start(crawlid, host, port):
    redis_conn = Redis(host, port)
    key = "crawlid:%s" % crawlid
    data = redis_conn.hgetall(key)
    failed_keys = [x for x in data.keys() if fnmatch.fnmatch(x.decode(), "failed_download_*")]
    format(data)
    for fk in failed_keys:
        print_if = input("show the %s? y/n default n:" % fk.replace("_", " "))
        if print_if == "y":
            key_ = "%s:%s" % (fk, crawlid)
            p = redis_conn.hgetall(key_)
            format(p, True)


def main():
    parser = argparse.ArgumentParser(description="usage: %prog [options]")
    parser.add_argument("--host", default="127.0.0.1", help="redis host")
    parser.add_argument("-p", "--port", default=6379, help="redis port")
    parser.add_argument("crawlids", nargs="+", help="Crawlids to check. ")
    args = parser.parse_args()
    for crawlid in args.crawlids:
        start(crawlid=crawlid, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
