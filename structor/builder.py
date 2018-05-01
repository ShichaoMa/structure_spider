import re
import sys
import glob
import string

from os import makedirs, getcwd
from argparse import ArgumentParser
from importlib import import_module
from jinja2 import Environment, FileSystemLoader
from os.path import join, exists, abspath, dirname, isdir, basename

from .utils import ArgparseHelper
from .spider_feeder import SpiderFeeder
from .check_status import start as check


class Command(object):
    """
    项目构建工具
    """
    def __init__(self):
        self.args = self.parse_args()
        self.templates_path = getattr(self.args, "templates", None) or \
                              join(abspath(dirname(__file__)), "templates")

    def run(self):
        getattr(self, self.args.action)()

    def feed(self):
        sf = SpiderFeeder(self.args.crawlid, self.args.spiderid,
                          self.args.url, self.args.urls_file,
                          self.args.priority, self.args.redis_port,
                          self.args.redis_host, self.args.custom)
        sf.start()

    def check(self):
        for crawlid in self.args.crawlids:
            check(crawlid=crawlid, host=self.args.redis_host,
                  port=self.args.redis_port, custom=self.args.custom)

    def create(self):
        env = Environment(loader=FileSystemLoader(self.templates_path))
        getattr(self, "create_{}".format(self.args.type))(env)

    def copytree(self, env, copy_path, src_path="."):
        for file in glob.glob(join(copy_path, "*")):
            if file.count("__pycache__"):
                continue
            if isdir(file):
                dir_name = join(src_path, string.Template(
                    basename(file)).substitute(project_name=self.args.name))
                makedirs(dir_name, exist_ok=True)
                self.copytree(env, file, dir_name)
            else:
                template = env.get_template(file.replace(self.templates_path, ""))
                filename = join(src_path, basename(file)).replace(".tmpl", "")
                with open(filename, "w") as f:
                    f.write(template.render(project_name=self.args.name))

    def create_project(self, env):
        if exists(join(self.args.name, 'scrapy.cfg')):
            print('Error: scrapy.cfg already exists in', self.args.name)
            return

        if not self._is_valid_name(self.args.name):
            return

        makedirs(self.args.name, exist_ok=True)
        self.copytree(env, join(self.templates_path, "project"), self.args.name)

        print("New structure-spider project %r, "
              "using template directory %r, created in:" % (
            self.args.name, self.templates_path))
        print("    %s\n" % abspath(self.args.name))
        print("You can start the spider with:")
        print("    cd %s" % self.args.name)
        print("    custom-redis-server -ll INFO -lf &")
        print("    scrapy crawl douban")

    def create_spider(self, env):
        words = re.findall(r"([A-Za-z0-9]+)", self.args.name)
        if words[0][0].isdigit():
            print("spider name cannot start with number!")
            exit(1)
        class_name = "".join(word.capitalize() for word in words)

        current_dir = getcwd()
        entities = ["spider", "item"]
        parsed_props = dict()
        for prop in self.args.props:
            if prop.count("="):
                p, e = prop.split("=", 1)
                sep = '"' if e.count("'") else "'"
                type = self.guess_type(e)
                prefix = "r" if type == "re" else ""
                parsed_props[p] = (prefix, type, e, sep)
            else:
                parsed_props[prop] = ("", "xpath", "", "'")

        for entity in entities:
            if not exists(join(current_dir, "%ss" % entity)):
                self.exitcode = 1
                print("Error dir! ")
                exit(1)
            with open("%ss/%s_%s.py" % (
                    entity, class_name.lower(), entity), "w") as f:
                template = env.get_template(join("spider", entity + ".py.tmpl"))
                f.write(
                    template.render(class_name=class_name,
                             spider_name=self.args.name,
                             props=parsed_props,
                             item_pattern=(
                                 self.args.item_pattern, '"'
                                 if self.args.item_pattern.count(
                                     "'") else "'"),
                             page_pattern=(
                                 self.args.page_pattern, '"'
                                 if self.args.page_pattern.count(
                                     "'") else "'"),
                             )
                )

        print(
            "%sSpdier and %sItem have been created." % (class_name, class_name))

    def guess_type(self, expression):
        if expression.startswith("//"):
            return "xpath"
        elif expression.count("("):
            return "re"
        else:
            return "css"

    def _is_valid_name(self, project_name):
        def _module_exists(module_name):
            try:
                import_module(module_name)
                return True
            except ImportError:
                return False

        if not re.search(r'^[_a-zA-Z]\w*$', project_name):
            print('Error: Project names must begin with a letter and contain '
                  'only\nletters, numbers and underscores')
        elif _module_exists(project_name):
            print('Error: Module %r already exists' % project_name)
        else:
            return True
        return False

    def parse_args(self):
        base_parser = ArgumentParser(add_help=False)
        base_parser.add_argument("-t", "--templates", help="templates dir. ")
        base_parser.add_argument("-n", "--name", required=True, help="name. ")

        parser = ArgumentParser(
            description="Structure spider controller. ", add_help=False)
        parser.add_argument('-h', '--help', action=ArgparseHelper,
                            help='Show help text and exit. ')
        sub_parsers = parser.add_subparsers(
            dest="action", help="Action to achieve. ")

        create = sub_parsers.add_parser(
            "create", help="Create project or spider. ")

        ssub_parsers = create.add_subparsers(dest="type", help="Create type. ")
        project = ssub_parsers.add_parser(
            "project", parents=[base_parser], help="Create project. ")
        spider = ssub_parsers.add_parser(
            "spider", parents=[base_parser], help="Create spider. ")

        spider.add_argument(
            "-ip", "--item_pattern", default="",
            help="Spider item xpath expression for acquire item link. ")
        spider.add_argument(
            "-pp", "--page_pattern", default="",
            help="Spider page pattern expression for acquire next page link. ")
        spider.add_argument(
            "props", nargs="+",
            help="Prop name and re/css/xpath pairs: title=//h1/text()")

        base_parser = ArgumentParser(add_help=False)
        base_parser.add_argument(
            '-rh', "--redis-host", default="127.0.0.1", help="Redis host. ")
        base_parser.add_argument(
            '-rp', "--redis-port", type=int, default=6379, help="Redis port. ")
        base_parser.add_argument(
            "--custom", action="store_true", help="Use custom redis or not. ")

        check = sub_parsers.add_parser(
            "check", parents=[base_parser], help="Check spider status. ")
        check.add_argument("crawlids", nargs="+", help="Crawlids to check. ")

        feed = sub_parsers.add_parser(
            "feed", parents=[base_parser], help="Feed tasks. ")
        feed.add_argument(
            '-u', '--url', help="Product list url. ")
        feed.add_argument(
            '-uf', '--urls-file', help="File within product url per line. ")
        feed.add_argument(
            '-c', '--crawlid', required=True, help="Id for a crawl task. ")
        feed.add_argument(
            '-s', '--spiderid', required=True, help="Spider to crawl. ")
        feed.add_argument(
            '-p', '--priority', type=int, default=100, help="Priority. ")

        if len(sys.argv) < 2 or \
                len(sys.argv) == 2 and sys.argv[1] not in ["feed", "check"]:
            parser.print_help()
            exit(1)
        return parser.parse_args()


def run():
    Command().run()


if __name__ == "__main__":
    run()
