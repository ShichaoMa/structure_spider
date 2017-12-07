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
    source_url = Field(input_processor=MapCompose(partial(rid, old="\\", new="")))
    tags = Field(output_processor=TakeAll())