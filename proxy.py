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

import threading
lp = threading.Lock()

def fdcopy(fd1, fd2):
    fdlist = [fd1, fd2]
    while True:
        for rfd in select.select(fdlist, [], [])[0]:
            try: d = os.read(rfd, http.BUFSIZE)
            except OSError: d = ''
            if not d: raise EOFError()
            try: os.write(fd2 if rfd == fd1 else fd1, d)
            except OSError: raise EOFError()

class Connector(object):

    def connect(self, addr):
        sock = socket.socket()
        try: sock.connect(addr)
        except IOError:
            sock.close()
            return
        return sock

    def close(self, sock):
        sock.close()

connector = Connector()

class Meter(object):

    def __init__(self, src, init=0):
        self.counter, self.src = init, src

    def __iter__(self):
        for c in self.src:
            self.counter += len(c)
            yield c

class Proxy(http.WSGIServer):
    VERBOSE = True
    hopHeaders = ['Connection', 'Keep-Alive', 'Te', 'Trailers', 'Upgrade']

    def __init__(self, application=None, accesslog=None):
        super(Proxy, self).__init__(application, accesslog)
        self.plugins, self.in_query = [], []

    def http_handler(self, req):
        with lp:
            res = self.do_plugins('pre', req)
            if res is not None:
                return
            if req.method.upper() == 'CONNECT':
                return self.connect_handler(req)
            u = urlparse.urlparse(req.uri)
            if not u.netloc:
                return http.WSGIServer.http_handler(self, req)
            res = self.do_http(req)
            return res

    def connect_handler(self, req):
        r = req.uri.split(':', 1)
        host = r[0]
        port = int(r[1]) if len(r) > 1 else 80

        sock = connector.connect((host, port))
        if sock is None:
            return http.response_to(req, 502)

        res = None
        req.start_time = datetime.now()
        self.in_query.append(req)

        try:
            res = http.response_to(req, 200)
            fdcopy(req.stream.fileno(), sock.fileno())

        finally:
            self.in_query.remove(req)
            connector.close(sock)
        return None
            
    def clone_msg(self, msg):
        msgx = copy.copy(msg)
        msgx.headers = msg.headers.copy()
        for k in msg.headers.iterkeys():
            if k.startswith('Proxy'): del msgx[k]
        for k in self.hopHeaders:
            if k in msgx: del msgx[k]
        return msgx

    def round_trip(self, reqx, keepalive):
        sock = connector.connect(reqx.remote)
        if sock is None:
            res = http.response_to(reqx, 502)
            return res
        streamx = sock.makefile()

        try:
            # TODO: persistent connection
            reqx.add('Connection', 'close')
            if self.VERBOSE: reqx.debug()
            reqx.sendto(streamx)

            resx = http.Response.recvfrom(streamx)
            if self.VERBOSE: resx.debug()

            hasbody = reqx.method.upper() != 'HEAD'

            res = self.clone_msg(resx)
            if not hasbody or resx.body is None: m = None
            else: m = Meter(resx.body)
            res.body = m

            if all((resx.get('Transfer-Encoding', 'identity') == 'identity',
                    'Content-Length' not in resx, hasbody)):
                keepalive = False

            res.connection = keepalive
            res['Connection'] = 'keep-alive' if keepalive else 'close'

            if self.VERBOSE: res.debug()
            res.sendto(reqx.stream)
            res.length = 0 if m is None else m.counter

        finally:
            connector.close(sock)

        return res

    def do_http(self, req):
        host, port, uri = http.parseurl(req.uri)

        if self.VERBOSE: req.debug()
        reqx = self.clone_msg(req)
        reqx.uri = uri
        reqx.remote = (host, port)
        reqx['Host'] = host if port == 80 else '%s:%d' % (host, port)

        # keepalive = False
        if req.version == 'HTTP/1.1':
            keepalive = not any((
                req.get('Connection', '').lower() == 'close',
                req.get('Proxy-Connection', '').lower() == 'close'))
        else:
            keepalive = any((
                req.get('Connection', '').lower() == 'keep-alive',
                req.get('Proxy-Connection', '').lower() == 'keep-alive',
                'Keep-Alive' in req))

        res = None
        req.start_time = datetime.now()
        self.in_query.append(req)

        try:
            res = self.round_trip(reqx, keepalive)
        finally: self.in_query.remove(req)
        return res

    def do_plugins(self, name, *p):
        for p in self.plugins:
            f = getattr(p, name)
            if not f: continue
            res = f(*p)
            if res: return
