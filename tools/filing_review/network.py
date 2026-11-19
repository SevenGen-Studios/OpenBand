"""Bounded public HTTP access; redirects and robots are checked at every hop.

Only explicitly approved hostnames are reachable. Administrators must confirm
terms/permissions when registering a source. No browser challenges are bypassed.
"""
from __future__ import annotations
import http.client
import ipaddress
import socket
import ssl
import time
from urllib.parse import urlsplit, urljoin, quote
from urllib.robotparser import RobotFileParser

class HTTPStatusError(RuntimeError):
    def __init__(self,status,retry_after=None):
        super().__init__(f'HTTP {status}; source not retrieved')
        self.status=status
        self.retry_after=None
        if retry_after:
            try:self.retry_after=max(0,int(retry_after))
            except ValueError:
                try:
                    from email.utils import parsedate_to_datetime
                    from datetime import datetime,timezone
                    self.retry_after=max(0,(parsedate_to_datetime(retry_after)-datetime.now(timezone.utc)).total_seconds())
                except (ValueError,TypeError,OverflowError):pass

AGENT='OpenBandFilingReview/1.0 (+https://openband.ca)'
GOV_HOSTS={'services.sac-isc.gc.ca','fnp-ppn.aadnc-aandc.gc.ca','www.sac-isc.gc.ca','www.canada.ca'}

class PublicHTTP:
    def __init__(self, hosts=(), interval=2):
        self.hosts=GOV_HOSTS | set(hosts)
        self.interval=max(1,interval)
        self.last={}
        self.robots={}

    def validate(self,url):
        p=urlsplit(url)
        if p.scheme!='https' or p.username or p.password or p.port not in (None,443) or p.hostname not in self.hosts:
            raise ValueError('Source must be HTTPS on an explicitly approved hostname')
        addresses=socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError('Private or reserved network address blocked')
        return p,addresses[0][4][0]

    def raw(self,url,limit):
        p,address=self.validate(url)
        pause=self.last.get(p.hostname,0)+self.interval-time.monotonic()
        if pause>0: time.sleep(pause)
        self.last[p.hostname]=time.monotonic()
        # Pin the validated IP, while TLS still verifies the original hostname.
        connection=http.client.HTTPSConnection(p.hostname,timeout=30,context=ssl.create_default_context())
        sock=socket.create_connection((address,443),timeout=30)
        connection.sock=connection._context.wrap_socket(sock,server_hostname=p.hostname)
        try:
            connection.request('GET',quote(p.path,safe='/%:@')+('?' + quote(p.query,safe='=&%/:?+,@') if p.query else ''),headers={'User-Agent':AGENT,'Accept-Encoding':'identity'})
            response=connection.getresponse()
            headers=dict((k.lower(),v) for k,v in response.getheaders())
            if int(headers.get('content-length','0'))>limit: raise ValueError('Response exceeds size limit')
            body=response.read(limit+1)
            if len(body)>limit: raise ValueError('Response exceeds size limit')
            return response.status,headers,body
        finally: connection.close()

    def permitted(self,url):
        p,_=self.validate(url)
        origin='https://'+p.hostname
        if origin not in self.robots:
            status,headers,body=self.raw(origin+'/robots.txt',512_000)
            robot=RobotFileParser()
            if status==404: robot.parse([])
            elif status==200: robot.parse(body.decode('utf-8','replace').splitlines())
            else: raise RuntimeError(f'robots.txt unavailable ({status}); source deferred')
            self.robots[origin]=robot
        robot=self.robots[origin]
        self.interval=max(self.interval,robot.crawl_delay(AGENT) or robot.crawl_delay('*') or 0)
        if not robot.can_fetch(AGENT,url): raise PermissionError('robots.txt disallows this URL')

    def get(self,url,limit=40_000_000):
        for _ in range(5):
            self.permitted(url)
            status,headers,body=self.raw(url,limit)
            if status in (301,302,303,307,308):
                url=urljoin(url,headers.get('location',''))
                continue
            if status!=200: raise HTTPStatusError(status,headers.get('retry-after'))
            if 'captcha' in body[:20000].decode('utf-8','ignore').lower() and not body.startswith(b'%PDF-'):
                raise PermissionError('Access challenge; manual source review required')
            return body,url
        raise RuntimeError('Redirect limit exceeded')
