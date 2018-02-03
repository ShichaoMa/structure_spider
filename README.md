# USAGE
### 安装structure_spider
```
dev@ubuntu:~$ pip install structure_spider>=1.1.3
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
使用createspider可以生成直接可用的spider，-s指定spider名称，随后创建要抓取的字段及其规则
，使用=连接。规则可以是正则表达式，xpath, css。

如需进一步增加复杂规则或进行数据清洗，请参考wiki。
```
dev@ubuntu:~$ cd myapp/myapp/
dev@ubuntu:~/myapp/myapp$ ls
items  settings.py  spiders
dev@ubuntu:~/myapp/myapp$ createspider -s zhaopin "product_id=/(\d+)\\.htm" "job=//h1/text()" "salary=//a/../../strong/text()" 'city=//ul[@class="terminal-ul clearfix"]//strong/a/text()' 'education=//span[contains(text(), "学历")]/following-sibling::strong/text()' "company=h2 > a" -ip '//td[@class="zwmc"]/div/a[1]/@href' -pp '//li[@class="pagesDown-pos"]/a/@href'
ZhaopinSpdier and ZhaopinItem have been created.
dev@ubuntu:~/myapp/myapp$
```

参考资料：[使用structure_spider多请求组合抓取结构化数据](https://zhuanlan.zhihu.com/p/28636195)
### 启动爬虫
```
dev@ubuntu:~/myapp/myapp$ scrapy crawl zhaopin
```
### 投入任务
```
dev@ubuntu:~/myapp$ feed -s zhaopin -u "https://sou.zhaopin.com/jobs/searchresult.ashx?jl=%E6%B5%8E%E5%8D%97&kw=%E9%94%80%E5%94%AE&sm=0&p=1" -c zhaopin --custom # --custom代表使用的是简单redis
```
### 查看任务状态
```
dev@ubuntu:~/myapp$ check zhaopin
```
更多资源:

[[structure_spider每周一练]：一键下载百度mp3](https://zhuanlan.zhihu.com/p/29076630)


