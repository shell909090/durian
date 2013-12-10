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

class Proxy(object):
    VERBOSE = False
    # Actually, 'Transfer-Encoding' should included.
    hopHeaders = [
        'Connection', 'Keep-Alive', 'Proxy-Authenticate', 'Proxy-Authorization',
        'Te', 'Trailers', 'Upgrade']

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
            if hasattr(res, 'length'):
                length = res.length
            else: length = res.get_header('Content-Length', '-')
            code = res.code
        else: length, code = '-', 500
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
        for k in self.hopHeaders:
            if msgx.has_header(k): msgx.del_header(k)
        return msgx

    def forward_msg(self, msg, stream, msgx, streamx, hasbody=False):
        if self.VERBOSE: msgx.debug()
        msgx.send_header(streamx)
        source = msg.read_chunk(stream, hasbody=hasbody)
        if msg.get_header('Transfer-Encoding', 'identity') != 'identity':
            source = http.chunked(source)
        msg.length = 0
        # FIXME: wrong! chunk size counted.
        for c in source:
            # TODO: cache?
            # self.do_plugins('data', msg, c)
            msg.length += len(c)
            streamx.write(c)
        streamx.flush()

    def do_http(self, req, addr):
        host, port, uri = http.parseurl(req.uri)

        if self.VERBOSE: req.debug()
        reqx = self.clone_msg(req)
        reqx.uri = uri

        sock = connector.connect((host, port))
        if sock is None:
            res = http.response_to(req, 502)
            self.accesslog(addr, req, res)
            return
        stream = sock.makefile()

        res = None
        req.start_time = datetime.now()
        self.in_query.append(req)

        try:
            # TODO: persistent connection
            reqx.add_header('Connection', 'close')
            self.forward_msg(req, req.stream, reqx, stream)

            res = http.Response.recv_msg(stream)
            if self.VERBOSE: res.debug()

            resx = self.clone_msg(res)
            hasbody = req.method.upper() != 'HEAD' and res.code not in http.CODE_NOBODY
            self.forward_msg(res, stream, resx, req.stream, hasbody)

        except Exception, err:
            if res is None:
                res = http.response_to(req, 502)
            self.accesslog(addr, req, res)
            raise

        finally:
            self.in_query.remove(req)
            connector.close(sock)

        res.connection = not res.isclose(hasbody)
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
        except Exception, err:
            if not res.header_sent:
                res.send_header(req.stream)
                req.stream.flush()
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
