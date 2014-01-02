#!/usr/bin/python
# -*- coding: utf-8 -*-
'''
@date: 2013-12-08
@author: shell.xu
'''
import base64, logging
import http

class Auth(object):

    def __init__(self): self.users = {}

    def loadfile(self, filapath):
        with open(filepath, 'r') as fi:
            for line in fi:
                if line.startswith('#'): continue
                user, passwd = line.rstrip('\n').split(':')
                self.add(user, passwd)

    def add(self, name, passwd):
        self.users[name] = passwd

    def setup(self, proxy):
        http_handler = proxy.http_handler
        def inner(req):
            res = self.auth(req)
            return http_handler(req) if res is None else res
        proxy.http_handler = inner

    def auth(self, req):
        auth = req.get('Proxy-Authorization')
        if auth:
            if auth.startswith('Basic '): auth = auth[6:]
            user, passwd = base64.b64decode(auth).split(':', 1)
            if self.users.get(user) == passwd:
                del req['Proxy-Authorization']
                return
            else: logging.warning('login failed with %s:%s' % (user, passwd))
        res = http.response_http(
            407, headers={'Proxy-Authenticate': 'Basic realm="durian"'},
            body='Authorization needed')
        res.sendto(req.stream)
        return res

# TODO: cache
class Cache(object):

    def __init__(self):
        pass

    def pre(self, req):
        pass

    def post(self, req, resp):
        pass
