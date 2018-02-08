import copy

from scrapy import Item
from .custom_request import Request


class Node(object):
    """
    ItemCollector树的节点
    """
    def __init__(self, prop_name, item_loader, req_meta, enricher=None, parent=None, spider=None):
        self.prop_name = prop_name
        self.item_loader = item_loader
        self.req_meta = req_meta
        if not enricher:
            enricher = "enrich_" + prop_name
        self.enricher = enricher if isinstance(enricher, str) else enricher.__name__
        self.parent = parent
        self.children = list()
        self.enriched = False
        # 与父节点共用item_loader的节点不会在完成时生成item。
        if self.parent and self.parent.item_loader == item_loader:
            self.do_not_load = True
        else:
            self.do_not_load = False

    def run(self, response, spider):
        """
        除根节点以外，每个节点会经过两次run的调用。
        第一次run会首先调用enrich方法。丰富其item_loader，并产生子节点。
        两次run调用都会调用dispatch方法。
        :param response:
        :param spider:
        :return:
        """
        if not self.enriched:
            children = getattr(spider, self.enricher)(self.item_loader, response)
            self.enriched = True
            if children:
                self.children.extend(Node(*child, parent=self, spider=spider) for child in children)
        return self.dispatch(response)

    def dispatch(self, response):
        """
        dispatch会调度产生请求/item/None
        当当前节点存在req_meta时，组建请求。
        当当前节点不存在req_meta时，遍历其子节点，查找req_meta，并调用子节点dispatch，返回其结果
        删除不存在req_meta的子节点
        :param response:
        :return:
        """
        if self.req_meta:
            meta = response.request.meta.copy()
            self.req_meta.pop("callback", None)
            self.req_meta.pop("errback", None)
            custom_meta = self.req_meta.pop("meta", {})
            meta["priority"] += 1
            meta.update(custom_meta)
            kw = copy.deepcopy(self.req_meta)
            self.req_meta.clear()
            return Request(meta=meta, callback="parse_next", errback="errback", **kw), self
        else:
            for child in self.children[:]:
                if child.req_meta:
                    return child.dispatch(response)
                else:
                    self.children.remove(child)
        return None if self.do_not_load else self.item_loader.load_item(), self

    def __str__(self):
        return "<Node prop_name: {}, item_loader: {}, enricher: {} >" .format(
            self.prop_name, self.item_loader, self.enricher)

    __repr__ = __str__


class ItemCollector(object):
    """
    ItemCollector:
    """

    def __init__(self, root):
        self.root = root
        self.current_node = root

    def collect(self, response, spider):
        """
        item_collector收集的开始，每次收集返回一个请求或者item。
        调用当前节点的run方法，返回一个请求/item/None及其被产生的节点(哪个节点产生了这个请求/item/None)。
        当返回为Item时，表示该节点及其子节点已经完成所有操作。将其赋值父节点的item_loader。
        当返回为Request时，表示该节点产生了一个新请求，返回该请求交付scrapy调度。
        当返回为None时，表示该节点已完成，但与其父节点共用item_loader，此时item_loader不会生成item。将当前节点指针指向其父节点。
        :param response:
        :param spider:
        :return:
        """
        req_or_item = None
        while not req_or_item:
            req_or_item, self.current_node = self.current_node.run(response, spider)
            if isinstance(req_or_item, Item):
                # 存在parent，置req_or_item为None，循环直到遇见一个request，否则跳出循环返回Item。
                if self.current_node.parent:
                    self.current_node.parent.item_loader.add_value(self.current_node.prop_name, req_or_item)
                    req_or_item = None
                self.current_node = self.current_node.parent
            elif req_or_item is None:
                self.current_node = self.current_node.parent
        return req_or_item
