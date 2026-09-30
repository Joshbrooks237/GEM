import os

from env.limits import Limits
from env.runner import local_env


def test_sandbox_env_does_not_carry_api_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-key-xyz")
    monkeypatch.setenv("PEGMATITE_API_KEY", "secret-key-xyz")
    env = local_env("a0", "1577836800 +0000", tmp_path / "home")
    assert "OPENAI_API_KEY" not in env
    assert "PEGMATITE_API_KEY" not in env
    assert all("secret-key-xyz" not in value for value in env.values())
    assert "PATH" in env
    assert os.environ["OPENAI_API_KEY"] == "secret-key-xyz"
