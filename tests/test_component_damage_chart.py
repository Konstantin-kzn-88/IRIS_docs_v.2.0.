import json
from pathlib import Path

import pytest

from iris_v2.component_damage_chart import (
    ComponentDamageChartError,
    ComponentDamageChartService,
    _read_components,
)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def component(name: str, direct: float, environmental: float) -> dict:
    return {
        "hazard_component": name,
        "max_direct_losses": direct,
        "max_total_environmental_damage": environmental,
    }


def test_components_are_sorted_by_combined_damage(tmp_path: Path) -> None:
    path = tmp_path / "risk_summary.json"
    write_json(
        path,
        {
            "components": [
                component("Участок А", 100.0, 50.0),
                component("Участок Б", 500.0, 100.0),
                component("Без ущерба", 0.0, 0.0),
            ]
        },
    )

    rows = _read_components(path)

    assert rows == [
        ("Участок Б", 500.0, 100.0),
        ("Участок А", 100.0, 50.0),
    ]


def test_service_creates_png(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    write_json(
        tmp_path / "risk_summary.json",
        {
            "components": [
                component("Участок А", 100.0, 50.0),
                component("Участок Б", 500.0, 100.0),
            ]
        },
    )

    result = ComponentDamageChartService().calculate(tmp_path)

    assert result.path == tmp_path / "output" / "charts" / "damage_by_component.png"
    assert result.path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert result.component_count == 2


def test_missing_summary_has_clear_error(tmp_path: Path) -> None:
    with pytest.raises(
        ComponentDamageChartError,
        match="Сначала сформируйте свод риска",
    ):
        ComponentDamageChartService().calculate(tmp_path)


def test_duplicate_component_is_rejected(tmp_path: Path) -> None:
    write_json(
        tmp_path / "risk_summary.json",
        {
            "components": [
                component("Участок А", 100.0, 50.0),
                component("Участок А", 200.0, 60.0),
            ]
        },
    )

    with pytest.raises(ComponentDamageChartError, match="повторяющееся"):
        ComponentDamageChartService().calculate(tmp_path)
