import json
from pathlib import Path

import pytest

from iris_v2.report_risk_matrices import prepare_risk_matrices


def write_results(path: Path, fatalities: int, damage: float) -> None:
    path.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "scenario_code": "С1",
                        "fatalities_count": fatalities,
                        "scenario_frequency": 1.0e-5,
                        "total_damage": damage,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_report_risk_matrices_are_regenerated(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    write_results(tmp_path / "risk_results.json", 1, 1000.0)

    matrices = prepare_risk_matrices(tmp_path)

    assert matrices.people_path is not None
    assert matrices.damage_path is not None
    assert matrices.people_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert matrices.damage_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_no_fatalities_uses_explanation_only_for_people_matrix(
    tmp_path: Path,
) -> None:
    pytest.importorskip("matplotlib")
    write_results(tmp_path / "risk_results.json", 0, 1000.0)

    matrices = prepare_risk_matrices(tmp_path)

    assert matrices.people_path is None
    assert matrices.damage_path is not None


def test_no_damage_uses_explanation_only_for_damage_matrix(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    write_results(tmp_path / "risk_results.json", 1, 0.0)

    matrices = prepare_risk_matrices(tmp_path)

    assert matrices.people_path is not None
    assert matrices.damage_path is None
