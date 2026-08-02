from app.core.rate_limit.identity import _client_ip, _map_audience


def test_map_audience():
    assert _map_audience("platform") == "platform"
    assert _map_audience("tenant:acme") == "tenant"
    assert _map_audience("member:acme") == "member"


def test_map_audience_unknown_falls_back_to_anonymous():
    assert _map_audience("bogus") == "anonymous"
    assert _map_audience("") == "anonymous"


def test_client_ip_prefers_xff_when_trusted():
    class R:
        headers = {"x-forwarded-for": "9.9.9.9, 10.0.0.1"}

        class client:
            host = "172.17.0.1"

    assert _client_ip(R(), trusted_proxy=True) == "9.9.9.9"
    assert _client_ip(R(), trusted_proxy=False) == "172.17.0.1"


def test_client_ip_falls_back_when_no_xff_header():
    class R:
        headers: dict[str, str] = {}

        class client:
            host = "172.17.0.1"

    assert _client_ip(R(), trusted_proxy=True) == "172.17.0.1"
