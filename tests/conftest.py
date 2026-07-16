from pathlib import Path

import pytest

from seo_rank.domain_blocklist import DomainBlocklist
from seo_rank.env import ensure_project_env_loaded

ensure_project_env_loaded()


@pytest.fixture(autouse=True)
def isolate_implicit_domain_blocklist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Keep implicit blocklist writes out of the committed production file."""
    original_load = DomainBlocklist.load.__func__

    def load_test_blocklist(
        cls: type[DomainBlocklist], path: Path | str | None = None
    ) -> DomainBlocklist:
        return original_load(cls, tmp_path / "blocklist.txt" if path is None else path)

    monkeypatch.setattr(DomainBlocklist, "load", classmethod(load_test_blocklist))
