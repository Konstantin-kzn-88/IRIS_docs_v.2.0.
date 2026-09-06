import json
from pathlib import Path

import pytest

from iris_v2.risk_matrices import RiskMatricesError, RiskMatricesService


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def risk_row(
    number: int,
    fatalities: int,
    frequency: float,
    damage_thousand_rub: float,
) -> dict:
    return {
        "scenario_code": f"С{number}",
        "fatalities_count": fatalities,
        "scenario_frequency": frequency,
        "total_damage": damage_thousand_rub,
    }


def test_service_creates_two_risk_matrices(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    write_json(
        tmp_path / "risk_results.json",
        {
            "results": [
                risk_row(1, 1, 1e-4, 1000.0),
                risk_row(2, 3, 5e-5, 2500.0),
                risk_row(3, 0, 2e-4, 500.0),
            ]
        },
    )

    result = RiskMatricesService().calculate(tmp_path)

    assert result.people_path.name == "risk_matrix.png"
    assert result.damage_path.name == "risk_matrix_damage.png"
    assert result.people_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert result.damage_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert result.people_point_count == 2
    assert result.damage_point_count == 3


def test_people_matrix_requires_fatalities(tmp_path: Path) -> None:
    write_json(
        tmp_path / "risk_results.json",
        {"results": [risk_row(1, 0, 1e-4, 1000.0)]},
    )

    with pytest.raises(RiskMatricesError, match="Нет сценариев с погибшими"):
        RiskMatricesService().calculate(tmp_path)


def test_duplicate_scenario_code_is_rejected(tmp_path: Path) -> None:
    first = risk_row(1, 1, 1e-4, 1000.0)
    second = risk_row(2, 2, 2e-5, 2000.0)
    second["scenario_code"] = first["scenario_code"]
    write_json(tmp_path / "risk_results.json", {"results": [first, second]})

    with pytest.raises(RiskMatricesError, match="повторяющийся scenario_code"):
        RiskMatricesService().calculate(tmp_path)
