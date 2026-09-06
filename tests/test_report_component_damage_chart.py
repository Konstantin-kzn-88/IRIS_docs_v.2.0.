import json
from pathlib import Path

import pytest

from iris_v2.report_component_damage_chart import prepare_component_damage_chart
from iris_v2.report_max_damage import ReportMaxDamageError
from iris_v2.risk_summary import RiskSummaryService


def write_risk_results(project: Path, direct: float, environmental: float) -> None:
    row = {
        "id": 1,
        "scenario_code": "С1",
        "hazard_component": "Участок трубопроводов",
        "fatalities_count": 1,
        "scenario_frequency": 1.0e-5,
        "collective_risk_fatalities": 1.0e-5,
        "collective_risk_injured": 2.0e-5,
        "individual_risk_fatalities": 1.0e-6,
        "individual_risk_injured": 2.0e-6,
        "expected_damage": 0.1,
        "direct_losses": direct,
        "total_environmental_damage": environmental,
        "total_damage": direct + environmental,
        "damage_unit": "тыс. руб.",
    }
    (project / "risk_results.json").write_text(
        json.dumps({"results": [row]}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_report_component_damage_chart_is_regenerated(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    write_risk_results(tmp_path, 100.0, 20.0)
    RiskSummaryService().calculate(tmp_path)

    path = prepare_component_damage_chart(tmp_path)

    assert path is not None
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_zero_damage_uses_explanation(tmp_path: Path) -> None:
    write_risk_results(tmp_path, 0.0, 0.0)
    RiskSummaryService().calculate(tmp_path)

    assert prepare_component_damage_chart(tmp_path) is None


def test_stale_summary_is_rejected(tmp_path: Path) -> None:
    write_risk_results(tmp_path, 100.0, 20.0)
    RiskSummaryService().calculate(tmp_path)
    write_risk_results(tmp_path, 200.0, 20.0)

    with pytest.raises(ReportMaxDamageError, match="устарел"):
        prepare_component_damage_chart(tmp_path)
