"""Регрессия на произвольное чтение файловой системы.

`POST /api/won-tenders/import` принимал `folder_path` из тела запроса и
открывал его как есть, без авторизации. Запросом можно было указать любой
каталог на сервере и вытащить его содержимое через импорт.

Теперь путь трактуется как имя подпапки внутри `won_tenders/`, а выход за
пределы этого каталога отклоняется.
"""

import pytest
from fastapi import HTTPException

from web.routers.won_tenders import _resolve_import_folder

ESCAPING_PATHS = [
    "../../etc",
    "..\\..\\Windows",
    "/etc/passwd",
    "C:\\Windows\\System32",
    "won_tenders/../../secrets",
]


@pytest.mark.parametrize("raw_path", ESCAPING_PATHS)
def test_paths_outside_root_are_rejected(raw_path):
    with pytest.raises(HTTPException) as exc:
        _resolve_import_folder(raw_path)

    # 400 — путь недопустим, 404 — внутрь корня он не попал.
    assert exc.value.status_code in (400, 404)


def test_missing_subfolder_is_404():
    with pytest.raises(HTTPException) as exc:
        _resolve_import_folder("no-such-folder")

    assert exc.value.status_code == 404


def test_existing_subfolder_resolves_inside_root(tmp_path, monkeypatch):
    from web.routers import won_tenders as module

    root = tmp_path / "won_tenders"
    (root / "0356500005626000011").mkdir(parents=True)
    monkeypatch.setattr(module, "WON_TENDERS_ROOT", root)

    resolved = module._resolve_import_folder("0356500005626000011")

    assert resolved == (root / "0356500005626000011").resolve()


async def test_import_requires_authentication(client):
    response = await client.post(
        "/api/won-tenders/import",
        json={"folder_path": "/etc"},
    )

    assert response.status_code == 401
