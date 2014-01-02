#!/usr/bin/python
# -*- coding: utf-8 -*-
'''
@date: 2013-12-08
@author: shell.xu
'''
import os, sys
from datetime import datetime
import web

class List(object):
    tmplstr = '''$def with (in_query)
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd">
<html>
  <head>
    <title>list requests</title>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
  </head>
  <body>
  <table>
    <tr>
      <th>method</th><th>uri</th><th>time</th>
    </tr>
    $ now = datetime.now()
    $for req in in_query:
    <tr>
      <td>$req.method</td><td>$req.uri</td><td>$(now-req.start_time)</td>
    </tr>
  </table>
  </body>
</html>
    '''
    tmpl = web.template.Template(
        tmplstr, globals={'datetime': datetime})

    def GET(self):
        return self.tmpl(web.config.proxy.in_query)

def setup(proxy):
    web.config.proxy = proxy
    urls = (
        '.*', List)
    return web.application(urls).wsgifunc()
