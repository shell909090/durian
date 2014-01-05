#!/usr/bin/python
# -*- coding: utf-8 -*-
'''
@date: 2013-12-08
@author: shell.xu
'''
import os, sys, getopt, logging
from gevent.server import StreamServer
import utils

from gevent import monkey
monkey.patch_all()

def main():
    '''
durain [-c configfile] [-h]
options:
* -c: config file
* -h: show help
    '''
    optlist, args = getopt.getopt(sys.argv[1:], 'c:f:l:h')
    optdict = dict(optlist)
    if '-h' in optdict:
        print main.__doc__
        return

    cfg = utils.getcfg(optdict.get('-c', [
        'durian.conf', '~/.durian.conf', '/etc/durian/durian.conf']))
    utils.initlog(cfg.get('log.loglevel', 'WARNING'), cfg.get('log.logfile'))
    import http
    http.connector.max_addr = int(cfg.get('pool.maxaddr', 10))
    addr = (cfg.get('main.addr', ''), int(cfg.get('main.port') or 8080))

    import proxy, manager
    p = proxy.Proxy(accesslog=cfg.get('log.access'))
    p.application = manager.setup(p)
    if cfg.get('log.verbose'):
        p.VERBOSE = True

    import midware
    if cfg.get('auth.username'):
        auth = midware.Auth()
        auth.add(cfg.get('auth.username'), cfg.get('auth.password'))
        auth.setup(p)
    elif cfg.get('auth.userfile'):
        auth = midware.Auth()
        auth.loadfile(cfg.get('auth.userfile'))
        auth.setup(p)
    if cfg.get('cache.engine'):
        store = None
        if cfg['cache.engine'] == 'memory':
            store = midware.MemoryCache(cfg.get('cache.size', 100))
        if store: midware.Cache(store).setup(p)

    try:
        StreamServer(addr, p.handler).serve_forever()
    except KeyboardInterrupt: pass

if __name__ == '__main__': main()
