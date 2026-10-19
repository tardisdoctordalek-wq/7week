"""API 키를 Windows 자격 증명 관리자에 암호화해 저장한다.

Windows 자격 증명 관리자는 키를 Windows 사용자 계정 기준으로 암호화(DPAPI)한다.
이전 버전이 앱 폴더에 평문으로 저장한 키 파일이 있으면 자격 증명 관리자로 옮기고 파일을 지운다.
"""

import os
from pathlib import Path

import keyring
from keyring.errors import KeyringError

SERVICE = "7week-sogyeonseo"


class KeyStoreError(Exception):
    """사용자에게 그대로 보여줄 수 있는 오류."""


def load(provider_id: str, provider: dict, app_dir: Path) -> tuple[str, str | None]:
    """(키, 안내 메시지)를 돌려준다. 저장된 키가 없으면 빈 문자열."""
    for name in provider["env"]:
        if os.environ.get(name):
            return os.environ[name], None
    try:
        key = keyring.get_password(SERVICE, provider_id)
    except KeyringError:
        key = None
    if key:
        return key, None

    legacy = app_dir / provider["key_file"]
    if not legacy.exists():
        return "", None
    key = legacy.read_text(encoding="utf-8").strip()
    try:
        save(provider_id, key)
    except KeyStoreError:
        return key, f"{legacy.name}에 키가 암호화되지 않은 채 저장되어 있습니다. 파일을 지워 주세요."
    legacy.unlink()
    return key, f"{legacy.name}에 있던 키를 Windows 자격 증명 관리자로 옮기고(암호화) 파일은 지웠습니다."


def save(provider_id: str, key: str) -> None:
    try:
        keyring.set_password(SERVICE, provider_id, key)
    except KeyringError as e:
        raise KeyStoreError(f"이 PC에서는 키를 암호화해 저장할 수 없습니다 ({e}). 키는 매번 입력해 주세요.")


def delete(provider_id: str) -> None:
    try:
        keyring.delete_password(SERVICE, provider_id)
    except KeyringError:
        pass  # 저장된 키가 없으면 지울 것도 없다
