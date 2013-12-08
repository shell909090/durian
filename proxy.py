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

class Proxy(object):
    VERBOSE = False

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
            length = res.get_header('Content-Length', '-')
            code = res.code
        else: length, code = '-', 500
        self.accesslogfile.write('%s:%d - - [%s] "%s" %d %s "-" %s\n' % (
            addr[0], addr[1], datetime.now().isoformat(),
            req.get_startline(), code, length, req.get_header('User-Agent')))

    def do_http(self, req):
        host, port, uri = http.parseurl(req.uri)

        reqx = copy.copy(req)
        reqx.uri = uri
        reqx.headers = {}
        for k, v in req.iter_headers():
            if k.startswith('Proxy'): continue
            reqx.add_header(k, v)
        if self.VERBOSE: req.debug()

        sock = socket.socket()
        req.start_time = datetime.now()
        self.in_query.append(req)
        try:
            sock.connect((host, port))
            stream = sock.makefile()

            reqx.send_header(stream)
            for c in reqx.read_chunk(reqx.stream, raw=True):
                stream.write(c)
            stream.flush()

            res = http.Response.recv_msg(stream)
            if self.VERBOSE: res.debug()
            res.send_header(req.stream)

            hasbody = req.method.upper() != 'HEAD' and \
                      res.code not in http.CODE_NOBODY
            for c in res.read_chunk(stream, hasbody=hasbody, raw=True):
                req.stream.write(c)
            req.stream.flush()
        finally:
            self.in_query.remove(req)
            sock.close()

        res.connection = req.get_header('Proxy-Connection', '').lower() == 'keep-alive' and res.get_header('Connection', 'close').lower() != 'close'
        return res

    def do_connect(self, req, addr):
        r = req.uri.split(':', 1)
        if len(r) > 1:
            port = int(r[1])
        else: port = 80
        host = r[0]

        header_sent = False
        sock = socket.socket()
        req.start_time = datetime.now()
        self.in_query.append(req)
        try:
            sock.connect((host, port))

            res = http.Response(req.version, 200, 'OK')
            res.send_header(req.stream)
            req.stream.flush()
            self.accesslog(addr, req, res)
            header_sent = True

            fdcopy(req.stream.fileno(), sock.fileno())
        except Exception, err:
            if not header_sent:
                res = http.Response(req.version, 502, 'Bad Gateway')
                res.send_header(req.stream)
                req.stream.flush()
                self.accesslog(addr, req, res)
            raise
        finally:
            self.in_query.remove(req)
            sock.close()

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
        # TODO: wsgi.input
        return env

    def do_service(self, req):
        env = self.req2env(req)

        res = http.response_http(200)
        def start_response(status, res_headers):
            r = status.split(' ', 1)
            res.code = int(r[0])
            if len(r) > 1: res.phrase = r[1]
            else: res.phrase = http.DEFAULT_PAGES[resp.code][0]
            for k, v in res_headers: res.add_header(k, v)
            res.add_header('Transfer-Encoding', 'chunked')
            res.send_header(req.stream)

        for b in http.chunked(self.application(env, start_response)):
            req.stream.write(b)
        return res

    def do(self, req, addr):
        for p in self.plugins:
            res = p.pre(req)
            if res is not None:
                self.accesslog(addr, req, res)
                return

        if req.method.upper() == 'CONNECT':
            return self.do_connect(req, addr)

        u = urlparse.urlparse(req.uri)
        if not u.netloc:
            res = self.do_service(req)
        else: res = self.do_http(req)
        for p in self.plugins:
            p.post(req, res)
        self.accesslog(addr, req, res)
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
            logger.debug('browser connection closed')
