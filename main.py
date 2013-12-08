#!/usr/bin/python
# -*- coding: utf-8 -*-
'''
@date: 2013-12-08
@author: shell.xu
'''
import os, sys, getopt, logging
from gevent.server import StreamServer

def initlog(lv, logfile=None):
    if isinstance(lv, basestring): lv = getattr(logging, lv)
    rootlog = logging.getLogger()
    if logfile: handler = logging.FileHandler(logfile)
    else: handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            '%(asctime)s,%(msecs)03d (%(process)d)[%(levelname)s]%(name)s(%(filename)s:%(lineno)d): %(message)s',
            '%Y-%m-%d %H:%M:%S'))
    rootlog.addHandler(handler)
    rootlog.setLevel(lv)

def main():
    '''
durain [-a accessfile] [-l loglevel] [-h] [-p port]
options:
* -a: accessfile
* -l: loglevel, DEBUG, INFO, WARNING, ERROR
* -h: show help
* -p: port
    '''
    optlist, args = getopt.getopt(sys.argv[1:], 'a:l:hp:')
    optdict = dict(optlist)
    if '-h' in optdict:
        print main.__doc__
        return

    import proxy
    initlog(optdict.get('-l', 'WARNING'))
    p = proxy.Proxy(accesslog=optdict.get('-a'))
    p.application = __import__('manager').setup(p)

    try:
        StreamServer(
            ('', int(optdict.get('-p', 8080))),
            p.handler).serve_forever()
    except KeyboardInterrupt: pass

if __name__ == '__main__': main()
