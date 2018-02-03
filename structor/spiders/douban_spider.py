# -*- coding:utf-8 -*-
"""
spider编写规则
1 spider必须继承自StructureSpider
2 若执行分类抓取则需要配置item_pattern = (), page_pattern = ()，其中：
    1）item_pattern元组中的元素为分类页中每个item链接所对应的xpath表达式
    2）page_pattern元组中的元素可以是下一页链接所所对应的正则表达式，或者其它规则，详见https://github.com/ShichaoMa/structure_spider/wiki/%08page_partten%E5%92%8Citem_partten%E7%BC%96%E5%86%99%E8%A7%84%E5%88%99
3 提供get_base_loader静态方法，传入response，返回CustomLoader对应一个Item
4 提供enrich_data方法，必须被enrich_wrapper装饰，其中：
    1）传入item_loader, response，使用item_loader的方法(add_value, add_xpath, add_re)添加要抓取的属性名及其对应表达式或值。
    2）如该次渲染需要产生新的请求，则通过response.meta["item_collector"]提供的(add, extend)方法，
       则将(prop, item_loader, request_meta)添加到item_collector中。其中：
        prop: 指下次请求获取的全部字段如果做为一个子item返回时，子item在其父item中对应的字段名称。
        item_loader: 用来抽取下次请求中字段的item_loader，如果下次请求返回子item，则此item_loader与父级item_loader不同
        request_meta: 组建request所需要的kwargs type: dict
4 下次请求所回调的enrich函数名称为 enrich_`prop`
"""
from w3lib.html import replace_entities
from toolkit import safely_json_loads, re_search

from . import StructureSpider
from ..utils import xpath_exchange, CustomLoader, enrich_wrapper
from ..items.douban_item import FilmItem, QuestionItem, AnswerItem, ReviewItem


class DoubanSpider(StructureSpider):
    name = "douban"
    custom_settings = {
        "ITEM_PIPELINES": {
            "structor.pipelines.FilePipeline": 100,
            # "structor.pipelines.FilePipeline": 101,
        },
        #"RETRY_HTTP_CODES": [500, 502, 503, 504, 400, 408, 304]
    }
    @staticmethod
    def get_base_loader(response):
        return CustomLoader(item=FilmItem())

    @enrich_wrapper
    def enrich_data(self, item_loader, response):
        self.logger.debug("Start to enrich_data. ")
        item_loader.add_value("id", response.url, re=r"subject/(\d+)/")
        item_loader.add_xpath("title", '//h1/span/text()')
        item_loader.add_xpath("info", '//div[@id="info"]')
        item_loader.add_xpath("score", '//strong[@class="ll rating_num"]/text()')
        item_loader.add_xpath("recommendations", '//div[@class="recommendations-bd"]/dl/dd/a/text()')
        item_loader.add_xpath("description", '//div[@id="link-report"]/span/text()')
        nodes = list()

        celebrities_url = xpath_exchange(response.xpath('//div[@id="celebrities"]/h2/span/a/@href'))
        if celebrities_url:
            nodes.append(("celebrities", item_loader, {"url": response.urljoin(celebrities_url)}))

        related_pic_urls = response.xpath('//div[@id="related-pic"]/h2/span[@class="pl"]/a/@href').extract()
        if len(related_pic_urls) >= 2:
            related_pic_url = related_pic_urls[-2]
        else:
            related_pic_url = ""
        if related_pic_url:
            nodes.append(("related_pics", item_loader, {"url": related_pic_url}))

        comments_url = xpath_exchange(response.xpath('//div[@id="comments-section"]//h2/span/a/@href'))
        if comments_url:
            nodes.append(("comments", item_loader, {"url": comments_url}))

        questions_url = xpath_exchange(response.xpath('//div[@id="askmatrix"]/div/h2/span/a/@href'))
        if questions_url:
            nodes.append(("questions", item_loader, {"url": questions_url}))

        reviews_url = xpath_exchange(response.xpath('//section[@class="reviews mod movie-content"]//h2/span/a/@href'))
        if reviews_url:
            nodes.append(("reviews", item_loader, {"url": response.url.split("?")[0] + reviews_url}))

        response.meta["item_collector"].extend(nodes)

    @enrich_wrapper
    def enrich_celebrities(self, item_loader, response):
        self.logger.debug("Start to enrich_celebrities. ")
        positions = response.xpath('//div[@id="celebrities"]/div[@class="list-wrapper"]')
        celebrity_list = list()

        for position in positions:
            pos = xpath_exchange(position.xpath("h2/text()"))
            for position_actor in position.xpath('ul/li'):
                celebrity = dict()
                role = xpath_exchange(position_actor.xpath('div/span[@class="role"]/text()'))
                if role:
                    celebrity["role"] = re_search(r"饰 (.*)", role)
                celebrity["position"] = pos
                celebrity["name"] = xpath_exchange(position_actor.xpath('div/span[@class="name"]/a/text()'))
                celebrity["representative"] = position_actor.xpath('div/span[@class="works"]/a/text()').extract()
                celebrity_list.append(celebrity)
        item_loader.add_value("celebrities", celebrity_list)

    @enrich_wrapper
    def enrich_related_pics(self, item_loader, response):
        self.logger.debug("Start to enrich_related_pics. ")
        types = response.xpath('//div[@class="article"]/div[@class="mod"]')
        related_pics = dict()
        for type in types:
            related_pics[re_search(r"(\w+)", xpath_exchange(type.xpath('div[@class="hd"]/h2/text()')))] = \
                type.xpath('div[@class="bd"]/ul/li/a/img/@src').extract()

        item_loader.add_value("related_pics", related_pics)

    @enrich_wrapper
    def enrich_comments(self, item_loader, response):
        self.logger.debug("Start to enrich_comments. ")
        comments = response.xpath('//div[@id="comments"]/div[@class="comment-item"]')
        comment_list = list()
        for comment_div in comments:
            comment = dict()
            comment["author"] = xpath_exchange(comment_div.xpath('div/a/@title'))
            comment["upvotes"] = xpath_exchange(comment_div.xpath('div/h3/span/span[@class="votes"]/text()'))

            comment["score"] = int(re_search(r"allstar(\d+)", xpath_exchange(
                comment_div.xpath('div/h3/span[@class="comment-info"]/span[contains(@class, "rating")]/@class'))) or 0)/5
            comment["datetime"] = xpath_exchange(comment_div.xpath('div/h3/span/span[@class="comment-time "]/@title'))
            comment["content"] = xpath_exchange(comment_div.xpath('div/p/text()'))
            comment_list.append(comment)
        item_loader.add_value("comments", comment_list)
        next_url = xpath_exchange(response.xpath('//div[@id="paginator"]/a[@class="next"]/@href'))
        if next_url:
            response.meta["item_collector"].add(("comments", item_loader, {"url": response.urljoin(next_url)}))

    @enrich_wrapper
    def enrich_questions(self, item_loader, response):
        self.logger.debug("Start to enrich_questions. ")
        nodes = list()
        next_url = xpath_exchange(response.xpath('//span[@class="next"]/a/@href'))
        if next_url:
            nodes.append(("questions", item_loader, {"url": response.urljoin(next_url)}))
        qustions = response.xpath('//div[@class="questions"]/div[@class="item"]')
        for question in qustions:
            nodes.append(("question", CustomLoader(item=QuestionItem()), {"url": xpath_exchange(question.xpath('h3/a/@href'))}))

        response.meta["item_collector"].extend(nodes)

    @enrich_wrapper
    def enrich_question(self, item_loader, response):
        self.logger.debug("Start to enrich_question. ")
        item_loader.add_xpath("title", '//div[@class="article"]/h1/text()')
        item_loader.add_xpath("content", '//div[@id="question-content"]/p/text()')
        item_loader.add_xpath("author", '//div[@class="article"]/p[@class="meta"]/a/text()')
        item_loader.add_xpath("datetime", '//div[@class="article"]/p[@class="meta"]/text()', lambda values: values[-1])
        answer_url = response.url.split("?")[0] + "answers/?start=0&limit=20"
        response.meta["item_collector"].add(("answers", item_loader, {"url": answer_url}))

    @enrich_wrapper
    def enrich_answers(self, item_loader, response):
        data = safely_json_loads(response.body)
        nodes = list()
        for answer in data["answers"]:
            answer_item_loader = CustomLoader(item=AnswerItem())
            answer_item_loader.add_value("upvotes", answer["useness"])
            answer_item_loader.add_value("author", answer["user"]["name"])
            answer_item_loader.add_value("datetime", answer["created_at"])
            answer_item_loader.add_value("content", replace_entities(answer["content"]))
            num_of_comments = answer["num_of_comments"]
            if num_of_comments:
                answer_id = answer["id"]
                for start in range(0, num_of_comments, 20):
                    reply_url = "%sanswers/%s/comments/?start=%s" % (response.url.split("?")[0], answer_id, start)
                    nodes.append(("replies", answer_item_loader, {"url": reply_url}))
            else:
                item_loader.add_value("answers", answer_item_loader.load_item())
        response.meta["item_collector"].extend(nodes)

    @enrich_wrapper
    def enrich_replies(self, item_loader, response):
        self.logger.debug("Start to enrich_replies. ")
        data = safely_json_loads(response.body)
        item_loader.add_value("replies", data["comments"])

    @enrich_wrapper
    def enrich_reviews(self, item_loader, response):
        self.logger.debug("Start to enrich_reviews. ")
        nodes = list()
        next_url = xpath_exchange(response.xpath('//span[@class="next"]/a/@href'))
        if next_url:
            nodes.append(("reviews", item_loader, {"url": response.urljoin(next_url)}))
        reviews = response.xpath('//div[@class="review-list"]/div/div[@class="main review-item"]')
        for review in reviews:
            nodes.append(
                ("review", CustomLoader(item=ReviewItem()), {"url": xpath_exchange(review.xpath('header/h3/a/@href'))}))
        response.meta["item_collector"].extend(nodes)

    @enrich_wrapper
    def enrich_review(self, item_loader, response):
        self.logger.debug("Start to enrich_review. ")
        item_loader.add_xpath("title", '//h1/span/text()')
        item_loader.add_xpath("content", '//div[@id="link-report"]/div')
        item_loader.add_xpath("author", '//div[@class="article"]/div/div/header/a/span/text()')
        item_loader.add_xpath("datetime", '//div[@class="article"]/div/div/header/span[@class="main-meta"]/text()')
        item_loader.add_xpath("score", '//div[@class="article"]/div/div/header/span[contains(@class, "rating")]/@class',
                              re=r"allstar(\d+)")
        item_loader.add_xpath("upvotes", '//div[@class="main-ft"]/div/div/button[1]/text()', re=r"(\d+)")
        item_loader.add_xpath("downvotes", '//div[@class="main-ft"]/div/div/button[2]/text()', re=r"(\d+)")
        comments = response.xpath('//div[@id="comments"]/div[@class="comment-item"]')
        comment_list = list()
        for comment_div in comments:
            comment = dict()
            comment["author"] = xpath_exchange(comment_div.xpath('div//div[@class="header"]/a/text()'))
            comment["datetime"] = xpath_exchange(comment_div.xpath('div//div[@class="header"]/span/text()'))
            comment["content"] = xpath_exchange(comment_div.xpath('div/p/text()'))
            comment["reply-quote"] = xpath_exchange(comment_div.xpath('div/div[@class="reply-quote"]/span[@class="all"]/text()'))
            comment["reply"] = xpath_exchange(comment_div.xpath('div/div[@class="reply-quote"]/span/a/text()'))
            comment_list.append(comment)
        item_loader.add_value("comments", comment_list)
