"""Prevent document-stage network egress; assets are prepared beforehand."""
import ipaddress,socket

def install():
    def allowed(host):
        try:return ipaddress.ip_address(host).is_loopback
        except ValueError:return host=='localhost'
    connect=socket.socket.connect;connect_ex=socket.socket.connect_ex;resolve=socket.getaddrinfo
    def guarded(self,address):
        if isinstance(address,tuple) and not allowed(address[0]):raise OSError('번역 worker는 루프백 통신만 허용합니다.')
        return connect(self,address)
    def guarded_ex(self,address):
        if isinstance(address,tuple) and not allowed(address[0]):raise OSError('번역 worker는 루프백 통신만 허용합니다.')
        return connect_ex(self,address)
    def lookup(host,*a,**kw):
        if host is not None and not allowed(host):raise OSError('번역 worker의 외부 DNS 요청을 차단했습니다.')
        return resolve(host,*a,**kw)
    socket.socket.connect=guarded;socket.socket.connect_ex=guarded_ex;socket.getaddrinfo=lookup
