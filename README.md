# USAGE
### 安装structure_spider
```
dev@ubuntu:~$ pip install structure_spider>=0.9.10
```
### 生成项目
```
dev@ubuntu:~$ startproject myapp
New structure-spider project 'myapp', using template directory '/home/dev/.pyenv/versions/3.6.0/lib/python3.6/site-packages/structor/templates/project', created in:
    /home/dev/myapp

You can start the spider with:
    cd myapp
    custom-redis-server -ll INFO -lf
    scrapy crawl douban
```
### 开始简单redis，可以使用正式版redis，只需把settings.py中的`CUSTOM_REDIS=True`注释掉即可
```
dev@ubuntu:~$ custom-redis-server -ll INFO -lf
```
### 生成自定义spider及item
```
dev@ubuntu:~$ cd myapp/myapp/
dev@ubuntu:~/myapp/myapp$ ls
items  settings.py  spiders
dev@ubuntu:~/myapp/myapp$ createspider -s taobao id title brand price colors images
TaobaoSpdier and TaobaoItem have been created.
dev@ubuntu:~/myapp/myapp$
```
### 为爬虫编写规则
请看wiki

参考资料：[使用structure_spider多请求组合抓取结构化数据](https://zhuanlan.zhihu.com/p/28636195)
### 启动爬虫
```
dev@ubuntu:~/myapp/myapp$ scrapy crawl taobao
```
### 投入任务
```
dev@ubuntu:~/myapp$ feed -s taobao -c test -uf myapp/text.txt --custom # --custom代表使用的是简单redis
```

更多资源:

[[structure_spider每周一练]：一键下载百度mp3](https://zhuanlan.zhihu.com/p/29076630)


