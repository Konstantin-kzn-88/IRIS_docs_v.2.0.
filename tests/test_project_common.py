import json
from pathlib import Path

import pytest

from iris_v2.project_common import ProjectCommonError, ProjectCommonService


def test_create_and_edit_project_common(tmp_path: Path) -> None:
    service = ProjectCommonService()
    data = service.load(tmp_path, "Название", "CODE-001")
    data["dpb_code"] = "CODE-001-ДПБ"
    data["executor"]["name"] = "ООО Проектировщик"

    path = service.save(tmp_path, data)
    loaded = service.load(tmp_path)

    assert path == tmp_path / "project_common.json"
    assert loaded["project_name"] == "Название"
    assert loaded["dpb_code"] == "CODE-001-ДПБ"
    assert loaded["executor"]["name"] == "ООО Проектировщик"


def test_unknown_fields_are_preserved(tmp_path: Path) -> None:
    source = {
        "year": 2026,
        "project_name": "Проект",
        "project_code": "CODE",
        "future_field": {"value": 10},
        "executor": {"name": "Разработчик", "future_executor_field": "текст"},
    }
    (tmp_path / "project_common.json").write_text(
        json.dumps(source, ensure_ascii=False), encoding="utf-8"
    )

    service = ProjectCommonService()
    data = service.load(tmp_path)
    service.save(tmp_path, data)
    loaded = json.loads(
        (tmp_path / "project_common.json").read_text(encoding="utf-8")
    )

    assert loaded["future_field"] == {"value": 10}
    assert loaded["executor"]["future_executor_field"] == "текст"


def test_invalid_year_is_rejected(tmp_path: Path) -> None:
    data = ProjectCommonService().load(tmp_path, "Проект", "CODE")
    data["year"] = 1999

    with pytest.raises(ProjectCommonError):
        ProjectCommonService().save(tmp_path, data)
