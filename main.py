#!/usr/bin/python
# -*- coding: utf-8 -*-
'''
@date: 2013-12-08
@author: shell.xu
'''
import os, sys, getopt, logging
from gevent.server import StreamServer
import utils

def main():
    '''
durain [-a accessfile] [-c configfile] [-f logfile] [-l loglevel] [-h] [-p port]
options:
* -a: accessfile
* -c: config file
* -f: logfile
* -l: loglevel, DEBUG, INFO, WARNING, ERROR
* -h: show help
* -p: port
    '''
    optlist, args = getopt.getopt(sys.argv[1:], 'a:c:f:l:hp:')
    optdict = dict(optlist)
    if '-h' in optdict:
        print main.__doc__
        return

    cfg = utils.getcfg(optdict.get('-c', [
        'durian.conf', '~/.durian.conf', '/etc/durian/config']))
    utils.initlog(
        optdict.get('-l') or cfg.get('log.loglevel') or 'WARNING',
        optdict.get('-c') or cfg.get('log.logfile'))
    addr = (cfg.get('main.addr', ''),
            int(optdict.get('-p') or cfg.get('main.port') or 8080))

    import proxy, manager
    p = proxy.Proxy(accesslog=optdict.get('-a') or cfg.get('log.access'))
    p.application = manager.setup(p)

    try:
        StreamServer(addr, p.handler).serve_forever()
    except KeyboardInterrupt: pass

if __name__ == '__main__': main()
