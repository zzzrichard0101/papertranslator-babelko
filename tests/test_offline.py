import socket
import pytest
from babelko.offline import install


def test_document_stage_rejects_external_dns_and_connections(monkeypatch):
    monkeypatch.setattr(socket.socket,'connect',socket.socket.connect)
    monkeypatch.setattr(socket.socket,'connect_ex',socket.socket.connect_ex)
    monkeypatch.setattr(socket,'getaddrinfo',socket.getaddrinfo)
    install()
    with pytest.raises(OSError,match='외부 DNS'):socket.getaddrinfo('example.com',443)
    with socket.socket() as s:
        with pytest.raises(OSError,match='루프백'):s.connect(('8.8.8.8',443))
    with socket.socket() as s:
        with pytest.raises(OSError,match='루프백'):s.connect_ex(('8.8.8.8',443))
    assert socket.getaddrinfo('127.0.0.1',1234)
