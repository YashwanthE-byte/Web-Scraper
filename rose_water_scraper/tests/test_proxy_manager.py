"""
tests/test_proxy_manager.py
---------------------------
Unit tests for ProxyManager configuration and formatting.
"""

from utils.proxy_manager import ProxyManager

def test_proxy_manager_disabled():
    pm = ProxyManager(use_proxies=False)
    assert pm.is_enabled() is False
    assert pm.get_requests_proxies() is None
    assert pm.get_playwright_proxy() is None

def test_webshare_rotating_formatting():
    pm = ProxyManager(
        use_proxies=True,
        username="myuser",
        password="mypassword",
        gateway="p.webshare.io",
        port=80,
        mode="rotating"
    )
    assert pm.is_enabled() is True
    assert pm.get_webshare_auth_user() == "myuser-rotate"
    
    req_proxies = pm.get_requests_proxies()
    assert req_proxies is not None
    assert req_proxies["http"] == "http://myuser-rotate:mypassword@p.webshare.io:80"
    assert req_proxies["https"] == "http://myuser-rotate:mypassword@p.webshare.io:80"

    pw_proxy = pm.get_playwright_proxy()
    assert pw_proxy is not None
    assert pw_proxy["server"] == "http://p.webshare.io:80"
    assert pw_proxy["username"] == "myuser-rotate"
    assert pw_proxy["password"] == "mypassword"

def test_webshare_direct_mode():
    pm = ProxyManager(
        use_proxies=True,
        username="myuser",
        password="mypassword",
        gateway="p.webshare.io",
        port=80,
        mode="direct"
    )
    assert pm.get_webshare_auth_user() == "myuser"
    assert "myuser:" in pm.get_requests_proxies()["http"]
