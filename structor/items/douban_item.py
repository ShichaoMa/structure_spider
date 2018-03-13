# -*- coding:utf-8 -*-
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
