import json
from pathlib import Path

import pytest

from iris_v2.substances import SubstanceError, SubstanceService


def substance_data(identifier: int, name: str, kind: int) -> dict:
    return {
        "id": identifier,
        "name": name,
        "kind": kind,
        "formula": "",
        "composition": {"components": []},
        "notes": "",
        "physical": {},
        "explosion": {},
        "toxicity": {},
        "reactivity": "",
        "odor": "",
        "corrosiveness": "",
        "precautions": "",
        "impact": "",
        "protection": "",
        "neutralization_methods": "",
        "first_aid": "",
    }


def test_archive_is_loaded_recursively_and_project_ids_are_created(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    for group, data in (
        ("DNS", substance_data(26, "Нефть", 0)),
        ("NPZ", substance_data(2, "Аммиак", 5)),
    ):
        directory = archive / group
        directory.mkdir(parents=True)
        (directory / f"{data['name']}.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

    service = SubstanceService()
    substances = service.load_archive(archive)
    service.save_project(tmp_path, reversed(substances))
    result = service.load_project(tmp_path)

    assert len(substances) == 2
    assert {item.group for item in substances} == {"DNS", "NPZ"}
    assert [item["id"] for item in result] == [1, 2]
    assert [item["name"] for item in result] == ["Аммиак", "Нефть"]
    assert (tmp_path / "info.txt").read_text(encoding="utf-8") == (
        "id\tname\tkind\n"
        "1\tАммиак\t5\n"
        "2\tНефть\t0\n"
    )


def test_empty_selection_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(SubstanceError):
        SubstanceService().save_project(tmp_path, [])


def test_identical_substances_cannot_be_selected_twice(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    data = substance_data(1, "Нефть", 0)
    first = archive / "first.json"
    second = archive / "second.json"
    first.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    data["id"] = 2
    second.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    substances = SubstanceService().load_archive(archive)

    with pytest.raises(SubstanceError):
        SubstanceService().save_project(tmp_path, substances)
