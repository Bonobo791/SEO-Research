from seo_rank.domain_blocklist import (
    DomainBlocklist,
    registrable_domain,
)


def test_registrable_domain_strips_scheme_www_port_path():
    assert registrable_domain("https://www.Example.com:443/path?q=1") == "example.com"
    assert registrable_domain("sub.example.com") == "sub.example.com"
    assert registrable_domain("http://user@host.example.com/") == "host.example.com"
    assert registrable_domain("") is None


def test_load_ignores_comments_and_blanks(tmp_path):
    path = tmp_path / "bl.txt"
    path.write_text(
        "# header\n\n"
        "Bad.com  # keyword=\"x\" reason=timeout\n"
        "www.other.com\n"
        "https://www.zillow.com/\n",  # hand-pasted URL form
        encoding="utf-8",
    )
    bl = DomainBlocklist.load(path)
    assert bl.is_blocked("https://bad.com/page")
    assert bl.is_blocked("https://other.com/")  # www. stripped on load
    assert bl.is_blocked("https://zillow.com/homes")  # URL-form entry normalized


def test_load_missing_file_is_empty(tmp_path):
    bl = DomainBlocklist.load(tmp_path / "nope.txt")
    assert not bl.is_blocked("https://anything.com")


def test_is_blocked_matches_subdomains_not_lookalikes(tmp_path):
    path = tmp_path / "blocklist.txt"
    path.write_text("example.com\n", encoding="utf-8")
    bl = DomainBlocklist.load(path)
    assert bl.is_blocked("https://example.com/a")
    assert bl.is_blocked("https://www.example.com/a")
    assert bl.is_blocked("https://blog.sub.example.com/a")
    assert not bl.is_blocked("https://notexample.com/a")
    assert not bl.is_blocked("https://example.com.evil.com/a")


def test_filter_results_drops_only_blocked(tmp_path):
    path = tmp_path / "blocklist.txt"
    path.write_text("dead.com\n", encoding="utf-8")
    bl = DomainBlocklist.load(path)
    rows = [
        {"url": "https://dead.com/x", "rank": 1},
        {"url": "https://live.com/y", "rank": 2},
    ]
    kept = bl.filter_results(rows, keyword="kw")
    assert [r["url"] for r in kept] == ["https://live.com/y"]


def test_record_appends_new_domain_with_header_and_dedups(tmp_path):
    path = tmp_path / "blocklist.txt"
    bl = DomainBlocklist.load(path)  # file does not exist yet
    bl.record("https://dead.com/x", keyword='he said "hi"', reason="timeout")
    bl.record("https://dead.com/y", keyword="again", reason="timeout")  # same domain
    bl.record("https://also-dead.com/z", keyword="k2", reason="onpage-50402")

    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Domains that failed to load")
    assert text.count("dead.com") == 2  # dead.com once + also-dead.com once
    lines = [ln for ln in text.splitlines() if not ln.startswith("#")]
    assert lines[0].split()[0] == "dead.com"
    assert lines[1].split()[0] == "also-dead.com"
    # recorded domain is now blocked for the rest of the run
    assert bl.is_blocked("https://dead.com/other")
    # a fresh load sees the persisted lines
    assert DomainBlocklist.load(path).is_blocked("https://also-dead.com/q")
