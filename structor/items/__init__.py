# -*- coding: utf-8 -*-

# Define here the models for your scraped items
#
# See documentation in:
# http://doc.scrapy.org/en/latest/topics/items.html
from scrapy import Item, Field
"""
item的建立
1 所有item的公共父类为BaseItem。用来提供最基本的信息，base item必须继承， child item可以不继承。
2 item中定义所有item属性prop = Field(...)。
3 Field定义如下：
  1）input_processor: processor函数，参见https://docs.scrapy.org/en/latest/topics/loaders.html#input-and-output-processors
  2）output_processor：默认为TakeFirst()，可以重写该processor。
  3) default：当prop值为空时为该字段提供默认值。
  4）order：对prop进行排序，有些prop依赖于之前的prop，这种情况下，对这两个属性进行排序是有必要的，默认order=0。
  5）skip: 是否在item中略过此prop，默认skip=False。
"""


class BaseItem(Item):
    domain = Field()
    crawlid = Field()
    spiderid = Field()
    response_url = Field()
    status_code = Field()
    status_msg = Field()
    url = Field()
    seed = Field()
    timestamp = Field()