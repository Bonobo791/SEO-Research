from pathlib import Path

from pathlib import Path

from seo_rank.domain_blocklist import DomainBlocklist


def test_tests_do_not_use_the_committed_domain_blocklist() -> None:
    tests_dir = Path(__file__).parents[1]
    offenders = [
        path
        for path in tests_dir.rglob("test_*.py")
        if path != Path(__file__) and (
            "domain_blocklist.txt" in path.read_text(encoding="utf-8")
            or "DomainBlocklist.load()" in path.read_text(encoding="utf-8")
        )
    ]

    assert offenders == []


def test_implicit_blocklist_path_is_test_local(tmp_path: Path) -> None:
    blocklist = DomainBlocklist.load()

    blocklist.record(
        "https://unavailable.example/path",
        keyword="test keyword",
        reason="test",
    )

    assert blocklist.path == tmp_path / "blocklist.txt"
    assert blocklist.path.read_text(encoding="utf-8").endswith(
        'unavailable.example  # keyword="test keyword" reason=test\n'
    )
