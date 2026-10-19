import sys
from pathlib import Path

import keyring
import pytest
from keyring.backend import KeyringBackend

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import keystore  # noqa: E402
import llm  # noqa: E402

PROVIDER = llm.PROVIDERS["google"]


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self):
        super().__init__()
        self.store = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def delete_password(self, service, username):
        self.store.pop((service, username), None)


@pytest.fixture
def memory(monkeypatch):
    for name in PROVIDER["env"]:
        monkeypatch.delenv(name, raising=False)
    backend = MemoryKeyring()
    old = keyring.get_keyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(old)


def test_save_load_delete(memory, tmp_path):
    keystore.save("google", "AIzaTEST")
    assert keystore.load("google", PROVIDER, tmp_path) == ("AIzaTEST", None)
    assert not any(tmp_path.iterdir())  # 평문 파일을 만들지 않는다
    keystore.delete("google")
    assert keystore.load("google", PROVIDER, tmp_path) == ("", None)


def test_legacy_plaintext_file_is_migrated_and_deleted(memory, tmp_path):
    (tmp_path / PROVIDER["key_file"]).write_text("AIzaOLD\n", encoding="utf-8")
    key, notice = keystore.load("google", PROVIDER, tmp_path)
    assert key == "AIzaOLD" and "옮기고" in notice
    assert not (tmp_path / PROVIDER["key_file"]).exists()
    assert memory.store[(keystore.SERVICE, "google")] == "AIzaOLD"


def test_no_backend_refuses_to_save(monkeypatch, tmp_path):
    from keyring.backends import fail

    for name in PROVIDER["env"]:
        monkeypatch.delenv(name, raising=False)
    old = keyring.get_keyring()
    keyring.set_keyring(fail.Keyring())
    try:
        with pytest.raises(keystore.KeyStoreError):
            keystore.save("google", "AIzaX")
        (tmp_path / PROVIDER["key_file"]).write_text("AIzaOLD", encoding="utf-8")
        key, notice = keystore.load("google", PROVIDER, tmp_path)
        assert key == "AIzaOLD" and "암호화되지 않은" in notice
        keystore.delete("google")  # 오류 없이 지나가야 한다
    finally:
        keyring.set_keyring(old)
