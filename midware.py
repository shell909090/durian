#!/usr/bin/python
# -*- coding: utf-8 -*-
'''
@date: 2013-12-08
@author: shell.xu
'''
import base64

logger = logging.getLogger()

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

    def pre(self, req):
        auth = req.get_header('Proxy-Authorization')
        if auth:
            user, passwd = base64.b64decode(auth).split(':', 1)
            if self.users.get(user) == passwd:
                req.del_header('Proxy-Authorization')
                return
        res = http.response_http(407)
        res.add_header('Proxy-Authenticate', 'durian')
        res.sendto(req.stream)
        req.stream.flush()
        return res

    def post(self, req, resp):
        pass

# TODO: cache
class Cache(object):

    def __init__(self):
        pass

    def pre(self, req):
        pass

    def post(self, req, resp):
        pass
