#!/usr/bin/python
# -*- coding: utf-8 -*-
'''
@date: 2013-12-08
@author: shell.xu
'''
import time, heapq, base64, logging, datetime, cStringIO
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
        def new_http_handler(req):
            res = self.auth(req)
            return http_handler(req) if res is None else res
        proxy.http_handler = new_http_handler

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

class CacheableFile(object):

    def __init__(self, src, maxlength=0):
        self.src, self.maxlength = src, maxlength
        self.buf = cStringIO.StringIO()

    def __iter__(self):
        for c in self.src:
            self.buf.write(c)
            yield c

class Cache(object):

    CACHE_METHOD = set(['GET', 'HEAD'])
    INVALIDATE_METHOD = set(['PUT', 'DELETE', 'POST'])

    def __init__(self, store):
        self.store = store

    def hitcache(self, req, res):
        logging.debug('cache hit: %s' % req.uri)
        self.proxy.iskeepalive(req)

        hasbody = req.method.upper() != 'HEAD'
        res.keepalive = req.keepalive
        if all((res.get('Transfer-Encoding', 'identity') == 'identity',
                'Content-Length' not in res, hasbody)):
            res.keepalive = False

        if self.proxy.VERBOSE: res.debug()
        res.sendto(req.stream)
        return res

    def setupcache(self, req, res):
        cres = self.proxy.clone_msg(res)
        cres['Cache-Control'] = 'max-age=%d' % cres.cache
        cres.body = cres.cachebody.buf.getvalue()
        self.store.set_data(req.uri, cres, res.cache)
        logging.debug('cache setup: %s' % req.uri)
        return cres

    def new_do_http(self, req):
        if req.method in self.CACHE_METHOD and \
           req.get('Cache-Control') != 'no-cache':
            res = self.store.get_data(req.uri)
            if res is not None:
                return self.hitcache(req, res)

        res = self.do_http(req)
        if res is None or not res.cache:
            return res
        return self.setupcache(req, res)

    def reqdone(self, req, res):
        if req.method in self.CACHE_METHOD and res.code / 100 == 2:
            if 'Expires' in res:
                df = http.HttpDate2Time(res['Expires']) - datetime.datetime.now()
                res.cache = df.total_seconds()
            if 'Age' in res: res.cache = int(res['Age'])
            if 'Cache-Control' in res:
                for i in res['Cache-Control'].split(':'):
                    if i.startswith('max-age'):
                        res.cache = int(i.split('=', 1)[1])
                    elif i.startswith('no-cache'):
                        res.cache = 0
            if res.cache:
                res.cachebody = res.body = CacheableFile(res.body)
        elif req.method in self.INVALIDATE_METHOD:
            self.store.del_data(req.uri)

    def setup(self, proxy):
        self.proxy = proxy
        proxy.reqdone = self.reqdone
        self.do_http = proxy.do_http
        proxy.do_http = self.new_do_http

class ObjHeap(object):
    ''' 使用lru算法的对象缓存容器，感谢Evan Prodromou <evan@bad.dynu.ca>。
    thx for Evan Prodromou <evan@bad.dynu.ca>. '''

    class __node(object):
        def __init__(self, k, v, f): self.k, self.v, self.f = k, v, f
        def __cmp__(self, o): return self.f > o.f

    def __init__(self, size):
        self.size, self.f = size, 0
        self.__dict, self.__heap = {}, []

    def __len__(self): return len(self.__dict)
    def __contains__(self, k): return self.__dict.has_key(k)
    def __setitem__(self, k, v):
        if self.__dict.has_key(k):
            n = self.__dict[k]
            n.v = v
            self.f += 1
            n.f = self.f
            heapq.heapify(self.__heap)
        else:
            while len(self.__heap) >= self.size:
                del self.__dict[heapq.heappop(self.__heap).k]
                self.f = 0
                for n in self.__heap: n.f = 0
            n = self.__node(k, v, self.f)
            self.__dict[k] = n
            heapq.heappush(self.__heap, n)
    def __getitem__(self, k):
        n = self.__dict[k]
        self.f += 1
        n.f = self.f
        heapq.heapify(self.__heap)
        return n.v
    def __delitem__(self, k):
        n = self.__dict[k]
        del self.__dict[k]
        self.__heap.remove(n)
        heapq.heapify(self.__heap)
        return n.v
    def __iter__(self):
        c = self.__heap[:]
        while len(c): yield heapq.heappop(c).k
        raise StopIteration
    
class MemoryCache(object):

    def __init__(self, size):
        self.oh = ObjHeap(size)

    def get_data(self, k):
        try: o = self.oh[k]
        except KeyError: return None
        if o[1] >= time.time(): return o[0]
        del self.oh[k]
        return None

    def set_data(self, k, v, exp):
        self.oh[k] = (v, time.time() + exp)

    def del_data(self, k):
        del self.oh[k]
