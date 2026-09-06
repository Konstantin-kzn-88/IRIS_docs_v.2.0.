import json
from pathlib import Path

import pytest

from iris_v2.report_collective_risk import (
    ReportCollectiveRiskError,
    load_collective_risk_rows,
)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def risk_row(code: str, component: str, fatalities: float, injured: float) -> dict:
    return {
        "scenario_code": code,
        "hazard_component": component,
        "collective_risk_fatalities": fatalities,
        "collective_risk_injured": injured,
    }


def test_collective_risk_is_grouped_and_totalled(tmp_path: Path) -> None:
    results = [
        risk_row("С1", "Трубопроводы", 1.0e-5, 2.0e-5),
        risk_row("С2", "Резервуарный парк", 3.0e-5, 4.0e-5),
        risk_row("С3", "Трубопроводы", 5.0e-5, 6.0e-5),
    ]
    write_json(tmp_path / "risk_results.json", {"results": results})
    write_json(
        tmp_path / "risk_summary.json",
        {
            "case_count": 3,
            "component_count": 2,
            "risk_unit": "1/год",
            "total_collective_risk_fatalities": 9.0e-5,
            "total_collective_risk_injured": 1.2e-4,
            "components": [
                {
                    "hazard_component": "Трубопроводы",
                    "scenario_count": 2,
                    "collective_risk_fatalities": 6.0e-5,
                    "collective_risk_injured": 8.0e-5,
                },
                {
                    "hazard_component": "Резервуарный парк",
                    "scenario_count": 1,
                    "collective_risk_fatalities": 3.0e-5,
                    "collective_risk_injured": 4.0e-5,
                },
            ],
        },
    )

    assert load_collective_risk_rows(tmp_path) == (
        {
            "component": "Трубопроводы",
            "fatalities": "6.000E-05",
            "injured": "8.000E-05",
        },
        {
            "component": "Резервуарный парк",
            "fatalities": "3.000E-05",
            "injured": "4.000E-05",
        },
        {
            "component": "Итого по ОПО",
            "fatalities": "9.000E-05",
            "injured": "1.200E-04",
        },
    )


def test_stale_collective_risk_is_rejected(tmp_path: Path) -> None:
    write_json(
        tmp_path / "risk_results.json",
        {"results": [risk_row("С1", "Трубопроводы", 1.0e-5, 2.0e-5)]},
    )
    write_json(
        tmp_path / "risk_summary.json",
        {
            "case_count": 1,
            "component_count": 1,
            "risk_unit": "1/год",
            "total_collective_risk_fatalities": 2.0e-5,
            "total_collective_risk_injured": 2.0e-5,
            "components": [
                {
                    "hazard_component": "Трубопроводы",
                    "scenario_count": 1,
                    "collective_risk_fatalities": 1.0e-5,
                    "collective_risk_injured": 2.0e-5,
                }
            ],
        },
    )

    with pytest.raises(ReportCollectiveRiskError, match="итоговый коллективный риск"):
        load_collective_risk_rows(tmp_path)
