from pathlib import Path


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
