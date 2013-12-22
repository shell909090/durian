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

logger = logging.getLogger()

def fdcopy(fd1, fd2):
    fdlist = [fd1, fd2]
    while True:
        for rfd in select.select(fdlist, [], [])[0]:
            try: d = os.read(rfd, http.BUFSIZE)
            except OSError: d = ''
            if not d: raise EOFError()
            try: os.write(fd2 if rfd == fd1 else fd1, d)
            except OSError: raise EOFError()

class RequestFile(object):

    def __init__(self, req):
        self.it, self.buf = req.read_chunk(req.stream), ''

    def read(self, size):
        try:
            while len(self.buf) < size:
                self.buf += self.it.next()
        except StopIteration:
            size = len(self.buf)
        r, self.buf = self.buf[:size], self.buf[size:]
        return r

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

class Proxy(object):
    VERBOSE = True
    hopHeaders = ['Connection', 'Keep-Alive', 'Te', 'Trailers', 'Upgrade']

    def __init__(self, application=None, accesslog=None):
        self.plugins, self.in_query = [], []
        self.application = application
        if accesslog is None:
            self.accesslogfile = None
        elif accesslog == '':
            self.accesslogfile = sys.stdout
        else: self.accesslogfile = open(accesslog, 'w')

    def accesslog(self, addr, req, res):
        if self.accesslogfile is None: return
        if res is not None:
            code = res.code
            length = res.get_header('Content-Length')
            if length is None and hasattr(res, 'length'):
                length = str(res.length)
            if length is None: length = '-'
        else: code, length = 500, '-'
        self.accesslogfile.write('%s:%d - - [%s] "%s" %d %s "-" %s\n' % (
            addr[0], addr[1], datetime.now().isoformat(),
            req.get_startline(), code, length, req.get_header('User-Agent')))

    def do_connect(self, req, addr):
        r = req.uri.split(':', 1)
        host = r[0]
        port = int(r[1]) if len(r) > 1 else 80

        sock = connector.connect((host, port))
        if sock is None:
            res = http.response_to(req, 502)
            self.accesslog(addr, req, res)
            return

        res = None
        req.start_time = datetime.now()
        self.in_query.append(req)

        try:
            res = http.response_to(req, 200)
            self.accesslog(addr, req, res)
            fdcopy(req.stream.fileno(), sock.fileno())

        finally:
            self.in_query.remove(req)
            connector.close(sock)

    def clone_msg(self, msg):
        msgx = copy.copy(msg)
        msgx.headers = msg.headers.copy()
        for k, v in msg.headers.iteritems():
            if k.startswith('Proxy-'): msgx.del_header(k)
        for k in self.hopHeaders:
            if msgx.has_header(k): msgx.del_header(k)
        return msgx

    def round_trip(self, reqx, keepalive):
        sock = connector.connect(reqx.addr)
        if sock is None:
            res = http.response_to(reqx, 502)
            return res
        streamx = sock.makefile()

        try:
            # TODO: persistent connection
            reqx.add_header('Connection', 'close')
            if self.VERBOSE: reqx.debug()
            reqx.sendto(streamx)

            resx = http.Response.recv_msg(streamx)
            if self.VERBOSE: resx.debug()

            hasbody = reqx.method.upper() != 'HEAD' and resx.code not in http.CODE_NOBODY

            res = self.clone_msg(resx)
            m = Meter(resx.read_chunk(streamx, hasbody))
            res.body = m
            if resx.get_header('Transfer-Encoding', 'identity') != 'identity':
                res.body = http.chunked(res.body)

            if all((resx.get_header('Transfer-Encoding', 'identity') == 'identity',
                    not resx.has_header('Content-Length'), hasbody)):
                keepalive = False

            res.connection = keepalive
            res.set_header('Connection', 'keep-alive' if keepalive else 'close')

            if self.VERBOSE: res.debug()
            res.sendto(reqx.stream)
            res.length = m.counter

        finally:
            connector.close(sock)

        return res

    def do_http(self, req, addr):
        host, port, uri = http.parseurl(req.uri)

        if self.VERBOSE: req.debug()
        reqx = self.clone_msg(req)
        reqx.uri = uri
        reqx.addr = (host, port)
        reqx.body = req.read_chunk(req.stream)
        if req.get_header('Transfer-Encoding', 'identity') != 'identity':
            reqx.body = http.chunked(reqx.body)
        reqx.set_header('Host', host)

        # keepalive = False
        if req.version == 'HTTP/1.1':
            keepalive = not any((
                req.get_header('Connection', '').lower() == 'close',
                req.get_header('Proxy-Connection', '').lower() == 'close'))
        else:
            keepalive = any((
                req.get_header('Connection', '').lower() == 'keep-alive',
                req.get_header('Proxy-Connection', '').lower() == 'keep-alive',
                req.has_header('Keep-Alive')))

        res = None
        req.start_time = datetime.now()
        self.in_query.append(req)

        try:
            res = self.round_trip(reqx, keepalive)

        finally:
            self.in_query.remove(req)

        self.accesslog(addr, req, res)
        return res

    def req2env(self, req):
        u = urlparse.urlparse(req.uri)
        env = dict(('HTTP_' + k.upper(), v) for k, v in req.iter_headers())
        env['REQUEST_METHOD'] = req.method
        env['SCRIPT_NAME'] = ''
        env['PATH_INFO'] = u.path
        env['QUERY_STRING'] = u.query
        env['CONTENT_TYPE'] = req.get_header('Content-Type')
        env['CONTENT_LENGTH'] = req.get_header('Content-Length')
        env['SERVER_PROTOCOL'] = req.version
        if req.method in set(['POST', 'PUT']):
            env['wsgi.input'] = RequestFile(req)
        return env

    def do_service(self, req, addr):
        env = self.req2env(req)

        res = http.response_http(500)
        res.header_sent = False
        def start_response(status, res_headers):
            r = status.split(' ', 1)
            res.code = int(r[0])
            if len(r) > 1: res.phrase = r[1]
            else: res.phrase = http.DEFAULT_PAGES[resp.code][0]
            for k, v in res_headers: res.add_header(k, v)
            res.add_header('Transfer-Encoding', 'chunked')
            res.send_header(req.stream)
            res.header_sent = True

        try:
            for b in http.chunked(self.application(env, start_response)):
                req.stream.write(b)
            req.stream.flush()
        except Exception, err:
            if not res.header_sent:
                res.send_header(req.stream)
            self.accesslog(addr, req, res)
            raise

        self.accesslog(addr, req, res)
        return res

    def do_plugins(self, name, *p):
        for p in self.plugins:
            f = getattr(p, name)
            if not f: continue
            res = f(*p)
            if res: return

    def do(self, req, addr):
        res = self.do_plugins('pre', req)
        if res is not None:
            self.accesslog(addr, req, res)
            return
        if req.method.upper() == 'CONNECT':
            return self.do_connect(req, addr)
        u = urlparse.urlparse(req.uri)
        if not u.netloc:
            return self.do_service(req, addr)
        res = self.do_http(req, addr)
        return res

    def handler(self, sock, addr):
        stream = sock.makefile()
        try:
            while self.do(http.Request.recv_msg(stream), addr):
                pass
        except (EOFError, socket.error): logger.debug('network error')
        except Exception, err: logger.exception('unknown')
        finally:
            sock.close()
            logger.debug('connection closed')
