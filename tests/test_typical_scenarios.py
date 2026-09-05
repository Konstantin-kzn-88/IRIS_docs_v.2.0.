import json
from pathlib import Path

import pytest

from iris_v2.typical_scenarios import TypicalScenarioError, TypicalScenarioService


def test_bundled_catalog_is_complete() -> None:
    catalog = TypicalScenarioService().load(TypicalScenarioService.bundled_path())

    assert len(catalog.equipment_types) == 10
    assert len(catalog.kinds) == 10
    assert catalog.pair_count == 62
    assert len(catalog.forbidden_pairs) == 38
    assert catalog.scenario_count == 370
    assert catalog.scenarios_for(0, 0)[0].calc_code == 1


def test_forbidden_pair_has_reason() -> None:
    catalog = TypicalScenarioService().load(TypicalScenarioService.bundled_path())

    assert catalog.scenarios_for(1, 2) == ()
    assert "РВС" in catalog.forbidden_reason(1, 2)


def test_external_catalog_has_priority(tmp_path: Path, monkeypatch) -> None:
    source = TypicalScenarioService.bundled_path()
    data = json.loads(source.read_text(encoding="utf-8"))
    data["scenarios"]["0"]["0"][0]["scenario_text"] = "Локальный сценарий"
    directory = tmp_path / "typical_scenarios"
    directory.mkdir()
    (directory / "typical_scenarios.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    catalog = TypicalScenarioService().load()

    assert catalog.scenarios_for(0, 0)[0].text == "Локальный сценарий"


def test_wrong_calculated_frequency_is_rejected(tmp_path: Path) -> None:
    data = json.loads(
        TypicalScenarioService.bundled_path().read_text(encoding="utf-8")
    )
    data["scenarios"]["0"]["0"][0]["scenario_frequency"] = 999
    path = tmp_path / "typical_scenarios.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(TypicalScenarioError, match="scenario_frequency"):
        TypicalScenarioService().load(path)
