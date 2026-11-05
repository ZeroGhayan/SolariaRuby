import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path, monkeypatch):
    """Cache e logs dos testes ficam num diretório temporário."""
    monkeypatch.chdir(tmp_path)
