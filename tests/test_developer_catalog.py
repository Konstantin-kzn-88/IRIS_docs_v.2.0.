import json
from pathlib import Path

import pytest

from iris_v2.developer_catalog import DeveloperCatalogError, load_developers


def test_developers_are_loaded_from_separate_files(tmp_path: Path) -> None:
    developers_directory = tmp_path / "developers"
    for folder, name in (("first", "ООО Первый"), ("second", "ООО Второй")):
        directory = developers_directory / folder
        directory.mkdir(parents=True)
        (directory / "developer.json").write_text(
            json.dumps(
                {"name": name, "inn": "123", "future_field": folder},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    developers = load_developers(developers_directory)

    assert [developer.name for developer in developers] == ["ООО Первый", "ООО Второй"]
    assert developers[1].snapshot()["future_field"] == "second"


def test_developer_without_name_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "developer.json"
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(DeveloperCatalogError):
        load_developers(path)
