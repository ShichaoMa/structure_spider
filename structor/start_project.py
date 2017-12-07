# -*- coding:utf-8 -*-
import re
import os
import string

from shutil import move
from argparse import ArgumentParser
from scrapy.commands import startproject
from scrapy.utils.template import render_templatefile, string_camelcase
from os.path import exists, join, abspath, dirname, isabs, isfile


class CustomStart(startproject.Command):

    def run(self, project, opt=None):

        project_name = project
        project_dir = project

        if exists(join(project_dir, 'scrapy.cfg')):
            self.exitcode = 1
            print('Error: scrapy.cfg already exists in %s' % abspath(project_dir))
            return

        if not self._is_valid_name(project_name):
            self.exitcode = 1
            return

        self._copytree(self.templates_dir, abspath(project_dir))
        move(join(project_dir, 'module'), join(project_dir, project_name))
        for paths in (('scrapy.cfg',),('${project_name}', 'settings.py.tmpl'),):
            path = join(*paths)
            tplfile = join(project_dir,
                string.Template(path).substitute(project_name=project_name))
            render_templatefile(tplfile, project_name=project_name,
                ProjectName=string_camelcase(project_name))
        print("New structure-spider project %r, using template directory %r, created in:" % \
              (project_name, self.templates_dir))
        print("    %s\n" % abspath(project_dir))
        print("You can start the spider with:")
        print("    cd %s" % project_dir)
        print("    custom-redis-server -ll INFO -lf &")
        print("    scrapy crawl douban")


class Jinja2Template(object):
    """ Base class and minimal API for template adapters """
    extensions = ['tpl','html','thtml','stpl']
    settings = {} #used in prepare()
    defaults = {} #used in render()

    def __init__(self, source=None, name=None, lookup=[], encoding='utf8', **settings):
        """ Create a new template.
        If the source parameter (str or buffer) is missing, the name argument
        is used to guess a template filename. Subclasses can assume that
        self.source and/or self.filename are set. Both are strings.
        The lookup, encoding and settings parameters are stored as instance
        variables.
        The lookup parameter stores a list containing directory paths.
        The encoding parameter should be used to decode byte strings or files.
        The settings parameter contains a dict for engine-specific settings.
        """
        self.name = name
        self.source = source.read() if hasattr(source, 'read') else source
        self.filename = source.filename if hasattr(source, 'filename') else None
        self.lookup = [abspath(x) for x in lookup]
        self.encoding = encoding
        self.settings = self.settings.copy() # Copy from class variable
        self.settings.update(settings) # Apply
        if not self.source and self.name:
            self.filename = self.search(self.name, self.lookup)
        self.prepare(**self.settings)

    @classmethod
    def search(cls, name, lookup=[]):
        """ Search name in all directories specified in lookup.
        First without, then with common extensions. Return first hit. """
        if not lookup:
            lookup = ['.']

        if isabs(name) and isfile(name):
            return abspath(name)

        for spath in lookup:
            spath = abspath(spath) + os.sep
            fname = abspath(join(spath, name))
            if not fname.startswith(spath): continue
            if isfile(fname): return fname
            for ext in cls.extensions:
                if isfile('%s.%s' % (fname, ext)):
                    return '%s.%s' % (fname, ext)

    @classmethod
    def global_config(cls, key, *args):
        ''' This reads or sets the global settings stored in class.settings. '''
        if args:
            cls.settings = cls.settings.copy() # Make settings local to class
            cls.settings[key] = args[0]
        else:
            return cls.settings[key]

    def prepare(self, filters=None, tests=None, globals={}, **kwargs):
        from jinja2 import Environment, FunctionLoader
        if 'prefix' in kwargs: # TODO: to be removed after a while
            raise RuntimeError('The keyword argument `prefix` has been removed. '
                'Use the full jinja2 environment name line_statement_prefix instead.')
        self.env = Environment(loader=FunctionLoader(self.loader), **kwargs)
        if filters: self.env.filters.update(filters)
        if tests: self.env.tests.update(tests)
        if globals: self.env.globals.update(globals)
        if self.source:
            self.tpl = self.env.from_string(self.source)
        else:
            self.tpl = self.env.get_template(self.filename)

    def render(self, *args, **kwargs):
        for dictarg in args: kwargs.update(dictarg)
        _defaults = self.defaults.copy()
        _defaults.update(kwargs)
        return self.tpl.render(**_defaults)

    def loader(self, name):
        fname = self.search(name, self.lookup)
        if not fname: return
        with open(fname, "rb") as f:
            return f.read().decode(self.encoding)


def template(*args, **kwargs):
    """
    Get a rendered template as a string iterator.
    You can use a name, a filename or a template string as first parameter.
    Template rendering arguments can be passed as dictionaries
    or directly (as keyword arguments).
    """
    tpl = args[0] if args else None
    adapter = kwargs.pop('template_adapter', Jinja2Template)
    lookup = kwargs.pop('template_lookup', ".")
    settings = kwargs.pop('template_settings', {})

    if isinstance(tpl, adapter):
        if settings:
            tpl.prepare(**settings)
    elif "\n" in tpl or "{" in tpl or "%" in tpl or '$' in tpl:
        tpl = adapter(source=tpl, lookup=lookup, **settings)
    else:
        tpl = adapter(name=tpl, lookup=lookup, **settings)

    for dictarg in args[1:]:
        kwargs.update(dictarg)

    return tpl.render(kwargs)


class CustomCreate(startproject.Command):

    def run(self, props, spider_name):
        words = re.findall(r"([A-Za-z0-9]+)", spider_name)
        if words[0].isdigit() or (words[0] and words[0][0].isdigit()):
            print("spider name cannot start with number!")
            exit(1)
        class_name = "".join(word.capitalize() for word in words)

        templates_dir = [join(dirname(self.templates_dir), "spider")]
        current_dir = os.getcwd()
        entities = ["spider", "item"]

        def render(entity):
            if not exists(join(current_dir, "%ss"%entity)):
                self.exitcode = 1
                print("Error dir! ")
                exit(1)
            open("%ss/%s_%s.py"%(entity, class_name.lower(), entity), "w").write(template(
                "%s.py.tmpl"%entity, template_lookup=templates_dir, class_name=class_name,
                spider_name=spider_name, props=props))

        for entity in entities:
            render(entity)

        print("%sSpdier and %sItem have been created. "%(class_name, class_name))


def create():
    cmd = CustomCreate()
    cmd.settings = {}
    cmd.settings["TEMPLATES_DIR"] = join(abspath(dirname(__file__)), "templates")
    parser = ArgumentParser()
    parser.add_argument("-s", "--spider", required=True, help="spider name")
    parser.add_argument("props", nargs="+", help="prop names")
    args = parser.parse_args()
    cmd.run(args.props, args.spider)


def start():
    cmd = CustomStart()
    cmd.settings = {}
    cmd.settings["TEMPLATES_DIR"] = join(abspath(dirname(__file__)), "templates")
    parser = ArgumentParser()
    parser.add_argument("project", help="project or/and project dir")
    args = parser.parse_args()
    cmd.run(args.project)


if __name__ == "__main__":
   start()
   #create()