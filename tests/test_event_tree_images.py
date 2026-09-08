import json
from pathlib import Path

import matplotlib.image as mpimg

from iris_v2.event_tree_images import EventTreeImageService
from iris_v2.typical_scenarios import TypicalScenarioService


def test_generate_one_event_tree_as_png(tmp_path: Path) -> None:
    catalog = TypicalScenarioService().load(TypicalScenarioService.bundled_path())

    result = EventTreeImageService().generate(
        tmp_path,
        catalog=catalog,
        pairs={(0, 0)},
    )

    assert result.image_count == 1
    assert result.files[0].name == "event_tree_eq00_kind00.png"
    assert result.files[0].read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    image = mpimg.imread(result.files[0])
    assert image.shape[0] >= 600
    assert image.shape[1] >= 1600
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["image_count"] == 1
    assert manifest["items"][0]["scenario_count"] == 6
    assert manifest["items"][0]["initiator_probability_totals"] == {
        "Разрыв трубопровода на сечение": 1.0,
        "Частичная разгерметизация трубопровода": 1.0,
    }
    assert manifest["warnings"] == []
    assert manifest["items"][0]["sha256"]


def test_copy_selected_tree_to_project(tmp_path: Path, monkeypatch) -> None:
    catalog = TypicalScenarioService().load(TypicalScenarioService.bundled_path())
    bundled = tmp_path / "bundled"
    EventTreeImageService().generate(
        bundled,
        catalog=catalog,
        pairs={(0, 0)},
    )
    service = EventTreeImageService()
    monkeypatch.setattr(service, "bundled_directory", lambda: bundled)
    project = tmp_path / "project"
    project.mkdir()
    (project / "project.json").write_text("{}", encoding="utf-8")

    result = service.copy_to_project(project, pairs={(0, 0)})

    assert result.image_count == 1
    assert result.files[0] == (
        project / "output" / "event_trees" / "event_tree_eq00_kind00.png"
    )
    assert result.files[0].is_file()
