import net

def _resp(status):
    class R:
        def __init__(s): s.status = status
        def read(s, n=-1): return b""
        def close(s): pass
        def __enter__(s): return s
        def __exit__(s, *a): return False
    return R()

def test_classify_url():
    assert net.classify_url("https://x.com/api?wd={wd}") == "template"
    assert net.classify_url("http://127.0.0.1:9978/x") == "local"
    assert net.classify_url("http://192.168.1.5/a") == "local"
    assert net.classify_url("https://cdn.jsdelivr.net/gh/a/b.js") == "probe"

def test_probe_dns_fail():
    r = net.probe("https://nope.example/x", now="T",
                  resolver=lambda h, t: False)
    assert r["dns_ok"] == 0 and r["ok"] == 0 and r["err"].startswith("dns")

def test_probe_tls_fail():
    import ssl
    def boom(url, timeout): raise ssl.SSLError("bad cert")
    r = net.probe("https://x.com/a", now="T",
                  resolver=lambda h, t: True, opener=boom)
    assert r["tls_ok"] == 0 and r["ok"] == 0 and r["err"].startswith("tls")

def test_probe_ok_206():
    r = net.probe("https://x.com/a", now="T",
                  resolver=lambda h, t: True, opener=lambda u, t: _resp(206))
    assert r["ok"] == 1 and r["http_status"] == 206 and r["tcp_ok"] == 1

def test_probe_http_500_not_ok():
    r = net.probe("https://x.com/a", now="T",
                  resolver=lambda h, t: True, opener=lambda u, t: _resp(500))
    assert r["ok"] == 0 and r["http_status"] == 500
