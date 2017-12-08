import unittest
from structor.utils import url_arg_increment, url_item_arg_increment, url_path_arg_increment


class PageUrlTest(unittest.TestCase):

    def test_url_arg_increment(self):
        self.assertEqual(url_arg_increment(r'(.*?)(pn=0)(\d+)(.*)', "http://www.nike.com/abc?pn=1"), "http://www.nike.com/abc?pn=2")

    def test_url_item_arg_increment(self):
        self.assertEqual(url_item_arg_increment("start=0", "http://www.ecco.com/abc", 30), "http://www.ecco.com/abc?start=30")

    def test_url_path_arg_increment(self):
        self.assertEqual(url_path_arg_increment(r'1~=(/page/)(\d+)(/)', 'http://www.timberland.com.hk/en/men-apparel-shirts'), 'http://www.timberland.com.hk/en/men-apparel-shirts/page/2/')


if __name__ == "__main__":
    unittest.main()