from ponyo_source_manager.discovery.path_resolver import (
    resolve_asset_url,
    resolve_source_assets,
)


def test_resolves_relative_assets_against_config_directory():
    origin = "https://raw.example/box/config/main.json"
    result = resolve_source_assets(
        origin, "./libs/drpy2.min.js",
        {"rule": "../js/儿童.js", "host": "https://vod.example"},
        "./jar/spider.jar",
    )
    assert result["status"] == "resolved"
    assert result["effective_api"] == "https://raw.example/box/config/libs/drpy2.min.js"
    assert result["effective_ext"]["rule"] == "https://raw.example/box/js/儿童.js"
    assert result["effective_ext"]["host"] == "https://vod.example"
    assert result["effective_jar"] == "https://raw.example/box/config/jar/spider.jar"


def test_local_drpy_password_is_inherited_but_remote_query_is_not():
    local, status = resolve_asset_url(
        "http://127.0.0.1:5757/config/1?pwd=secret", "../js/rule.js"
    )
    remote, _ = resolve_asset_url(
        "https://cdn.example/config/a.json?token=secret", "./rule.js"
    )
    assert status == "resolved"
    assert local == "http://127.0.0.1:5757/js/rule.js?pwd=secret"
    assert remote == "https://cdn.example/config/rule.js"


def test_rejects_unsafe_or_unresolvable_relative_assets():
    escaped, escaped_status = resolve_asset_url(
        "https://trusted.example/config.json", "//evil.example/rule.js"
    )
    missing, missing_status = resolve_asset_url("ponyo.json", "./rule.js")
    assert escaped is None
    assert escaped_status == "rejected_scheme_relative"
    assert missing is None
    assert missing_status == "invalid_origin"
