import json
from pathlib import Path

import pytest

from iris_v2.risk_charts import RiskChartsError, RiskChartsService


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def summary() -> dict:
    return {
        "fn_points": [
            {"fatalities_count": 0, "cumulative_frequency": 1.8e-4},
            {"fatalities_count": 1, "cumulative_frequency": 1.8e-4},
            {"fatalities_count": 2, "cumulative_frequency": 5e-5},
        ],
        "fg_points": [
            {"damage_million_rub": 0.0, "cumulative_frequency": 1.7e-4},
            {"damage_million_rub": 1.0, "cumulative_frequency": 1.7e-4},
            {"damage_million_rub": 2.5, "cumulative_frequency": 2e-5},
        ],
    }


def test_service_creates_two_png_files(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    write_json(tmp_path / "risk_summary.json", summary())

    result = RiskChartsService().calculate(tmp_path)

    assert result.fn_path == tmp_path / "output" / "charts" / "fn_chart.png"
    assert result.fg_path == tmp_path / "output" / "charts" / "fg_chart.png"
    assert result.fn_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert result.fg_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert result.fn_point_count == 3
    assert result.fg_point_count == 3


def test_missing_summary_has_clear_error(tmp_path: Path) -> None:
    with pytest.raises(RiskChartsError, match="Сначала сформируйте свод риска"):
        RiskChartsService().calculate(tmp_path)


def test_fn_requires_scenario_with_fatalities(tmp_path: Path) -> None:
    value = summary()
    value["fn_points"] = [
        {"fatalities_count": 0, "cumulative_frequency": 1e-4}
    ]
    write_json(tmp_path / "risk_summary.json", value)

    with pytest.raises(RiskChartsError, match="нет сценариев с погибшими"):
        RiskChartsService().calculate(tmp_path)
