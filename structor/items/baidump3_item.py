# -*- coding:utf-8 -*-
from functools import partial

from scrapy import Field
from scrapy.loader.processors import MapCompose
from toolkit import rid

from . import BaseItem
from ..utils import TakeAll


class BaiduMp3Item(BaseItem):
    id = Field()
    name = Field()
    singer = Field()
    album = Field()
    lyrics = Field()
    source_url = Field(
        input_processor=MapCompose(partial(rid, old="\\", new="")))
    tags = Field(output_processor=TakeAll())
