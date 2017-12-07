# -*- coding:utf-8 -*-
"""
item的建立
1 所有item的公共父类为BaseItem。用来提供最基本的信息，base item必须继承BaseItem， child item可以不继承于BaseItem。
2 item中定义所有item属性prop = Field(...)。
3 Field定义如下：
  1）input_processor: processor函数，参见https://docs.scrapy.org/en/latest/topics/loaders.html#input-and-output-processors
  2）output_processor：默认为TakeFirst()，可以重写该processor。
  3) default：当prop值为空时为该字段提供默认值。
  4）order：对prop进行排序，有些prop依赖于之前的prop，这种情况下，对这两个属性进行排序是有必要的，默认order=0。
  5）skip: 是否在item中略过此prop，默认skip=False。
"""
from scrapy import Item, Field
from scrapy.loader.processors import MapCompose
from toolkit import format_html_string

from . import BaseItem
from ..utils import TakeAll


class FilmItem(BaseItem):
    id = Field()
    title = Field()
    info = Field(input_processor=MapCompose(format_html_string))
    score = Field()
    description = Field()
    celebrities = Field(output_processor=TakeAll())
    related_pics = Field()
    recommendations = Field(output_processor=TakeAll())
    comments = Field(output_processor=TakeAll())
    questions = Field(output_processor=TakeAll())
    reviews = Field(output_processor=TakeAll())


class CommentBaseItem(Item):
    content = Field()
    datetime = Field()
    upvotes = Field()
    author = Field()


class QuestionItem(CommentBaseItem):
    title = Field()
    answers = Field(output_processor=TakeAll())
    upvotes = Field(skip=True)


class AnswerItem(CommentBaseItem):
    replies = Field(output_processor=TakeAll())


class ReviewItem(CommentBaseItem):
    title = Field()
    score = Field(input_processor=MapCompose(lambda value: int(value or 0)/5))
    downvotes = Field()
    comments = Field(output_processor=TakeAll())
