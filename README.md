# Durain #

Durain is a full stack proxy server written by python. It's based on gevent.

It support GET and CONNECT, and have http service in same port.

# Usage #

Run `python main.py -p port` to start.

use -a to setup accesslog.

run `python main -h` show more help.

# Files #

* http.py: httputils.
* main.py: mainfile.
* manager.py: manage service written by webpy.
* midware.py: midwares.
* proxy.py: proxy server.

# Code #

Use proxy.Proxy to make a instance of proxy. It have two parameters, application and accesslog. application is the WSGI application object of http service. And accesslog is the file to write accesslog. As default, it use a manager system of proxy written by webpy.

# License #

This software is public under BSD.

	Copyright (c) 2013 Shell.Xu<shell909090@gmail.com>
	All rights reserved.
	 
	Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
	 
	1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
	 
	2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
	 
	THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

