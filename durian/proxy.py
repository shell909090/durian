#!/usr/bin/python
# -*- coding: utf-8 -*-
'''
@date: 2013-12-08
@author: shell.xu
'''
import os, sys, copy, logging, urlparse
import http
from datetime import datetime
from gevent import socket, select

def fdcopy(fd1, fd2):
    fdlist = [fd1, fd2]
    while True:
        for rfd in select.select(fdlist, [], [])[0]:
            try: d = os.read(rfd, http.BUFSIZE)
            except OSError: d = ''
            if not d: raise EOFError()
            try: os.write(fd2 if rfd == fd1 else fd1, d)
            except OSError: raise EOFError()

class Meter(object):

    def __init__(self, src, init=0):
        self.counter, self.src = init, src

    def __iter__(self):
        for c in self.src:
            self.counter += len(c)
            yield c

class Proxy(http.WSGIServer):
    VERBOSE = False
    hopHeaders = ['Connection', 'Keep-Alive', 'Te', 'Trailers', 'Upgrade']

    def __init__(self, application=None, accesslog=None):
        super(Proxy, self).__init__(application, accesslog)
        self.in_query = []

    def http_handler(self, req):
        if req.method.upper() == 'CONNECT':
            return self.connect_handler(req)
        u = urlparse.urlparse(req.uri)
        if u.netloc: return self.do_http(req)
        return http.WSGIServer.http_handler(self, req)

    def connect_handler(self, req):
        r = req.uri.split(':', 1)
        host = r[0]
        port = int(r[1]) if len(r) > 1 else 80

        try: sock = http.connector.connect((host, port))
        except IOError: return http.response_to(req, 502)

        req.start_time = datetime.now()
        self.in_query.append(req)

        try:
            res = http.response_to(req, 200)
            fdcopy(req.stream.fileno(), sock.fileno())

        finally:
            self.in_query.remove(req)
            sock.close()
        return None
            
    def clone_msg(self, msg):
        msgx = copy.copy(msg)
        msgx.headers = msg.headers.copy()
        for k in msg.headers.iterkeys():
            if k.startswith('Proxy'): del msgx[k]
        for k in self.hopHeaders:
            if k in msgx: del msgx[k]
        return msgx

    def do_http(self, req):
        host, port, uri = http.parseurl(req.uri)

        if self.VERBOSE: req.debug()
        reqx = self.clone_msg(req)
        reqx.remote, reqx.uri = (host, port), uri
        reqx['Host'] = host if port == 80 else '%s:%d' % (host, port)
        if self.VERBOSE: reqx.debug()

        if req.version == 'HTTP/1.1':
            keepalive = not any((
                req.get('Connection', '').lower() == 'close',
                req.get('Proxy-Connection', '').lower() == 'close'))
        else:
            keepalive = any((
                req.get('Connection', '').lower() == 'keep-alive',
                req.get('Proxy-Connection', '').lower() == 'keep-alive',
                'Keep-Alive' in req))

        req.start_time = datetime.now()
        self.in_query.append(req)

        try:
            res, resx = None, http.round_trip(reqx)

            try:
                if self.VERBOSE: resx.debug()
                res = self.clone_msg(resx)

                hasbody = reqx.method.upper() != 'HEAD'
                if not hasbody or resx.body is None: m = None
                else: m = Meter(resx.body)
                res.body = m

                if all((resx.get('Transfer-Encoding', 'identity') == 'identity',
                        'Content-Length' not in resx, hasbody)):
                    keepalive = False
                res.connection = keepalive
                res['Connection'] = 'keep-alive' if keepalive else 'close'

                if self.VERBOSE: res.debug()
                res.sendto(req.stream)
                res.length = 0 if m is None else m.counter

            finally: resx.close()
        finally: self.in_query.remove(req)
        return res
