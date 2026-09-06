import json
from pathlib import Path

import pytest

from iris_v2.report_max_damage import ReportMaxDamageError, load_max_damage_rows


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def risk_row(
    code: str,
    component: str,
    direct: float,
    environmental: float,
    total: float,
) -> dict:
    return {
        "scenario_code": code,
        "hazard_component": component,
        "damage_unit": "тыс. руб.",
        "direct_losses": direct,
        "total_environmental_damage": environmental,
        "total_damage": total,
    }


def component(
    name: str,
    count: int,
    direct: float,
    environmental: float,
    total: float,
) -> dict:
    return {
        "hazard_component": name,
        "scenario_count": count,
        "max_direct_losses": direct,
        "max_total_environmental_damage": environmental,
        "max_total_damage": total,
    }


def test_maximum_damage_is_grouped_without_summing(tmp_path: Path) -> None:
    results = [
        risk_row("С1", "Трубопроводы", 100.0, 50.0, 500.0),
        risk_row("С2", "Резервуарный парк", 800.0, 20.0, 1000.0),
        risk_row("С3", "Трубопроводы", 200.0, 70.0, 600.0),
    ]
    write_json(tmp_path / "risk_results.json", {"results": results})
    write_json(
        tmp_path / "risk_summary.json",
        {
            "case_count": 3,
            "component_count": 2,
            "damage_unit": "тыс. руб.",
            "components": [
                component("Трубопроводы", 2, 200.0, 70.0, 600.0),
                component("Резервуарный парк", 1, 800.0, 20.0, 1000.0),
            ],
        },
    )

    assert load_max_damage_rows(tmp_path) == (
        {
            "component": "Трубопроводы",
            "direct": "200,0",
            "environmental": "70,0",
            "total": "600,0",
        },
        {
            "component": "Резервуарный парк",
            "direct": "800,0",
            "environmental": "20,0",
            "total": "1000,0",
        },
        {
            "component": "Максимум по ОПО",
            "direct": "800,0",
            "environmental": "70,0",
            "total": "1000,0",
        },
    )


def test_stale_maximum_damage_is_rejected(tmp_path: Path) -> None:
    write_json(
        tmp_path / "risk_results.json",
        {"results": [risk_row("С1", "Трубопроводы", 100.0, 50.0, 500.0)]},
    )
    write_json(
        tmp_path / "risk_summary.json",
        {
            "case_count": 1,
            "component_count": 1,
            "damage_unit": "тыс. руб.",
            "components": [component("Трубопроводы", 1, 100.0, 50.0, 600.0)],
        },
    )

    with pytest.raises(ReportMaxDamageError, match="не совпадает"):
        load_max_damage_rows(tmp_path)
