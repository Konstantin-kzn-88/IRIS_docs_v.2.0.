import json
import math
from pathlib import Path

import pytest

from iris_v2.frequency_calculation import (
    FrequencyCalculationError,
    FrequencyCalculationService,
)


def case(
    case_id: int,
    mode: str,
    multiplier: float,
    basis: float = 1000.0,
) -> dict:
    mode_names = {
        "standard": "Стандартный",
        "without_compensation": "Без КМ",
        "with_compensation": "С КМ",
    }
    return {
        "id": case_id,
        "scenario_code": f"С{case_id}",
        "equipment_id": case_id,
        "equipment_name": f"Трубопровод {case_id}",
        "hazard_component": "Участок трубопроводов",
        "frequency_mode": mode,
        "frequency_mode_name": mode_names[mode],
        "frequency_multiplier": multiplier,
        "frequency_basis": basis,
        "frequency_basis_unit": "м",
        "scenario_text": "Разрыв трубопровода → пожар пролива",
        "base_frequency": 3e-7,
        "accident_event_probability": 0.2,
        "unit_scenario_frequency": 6e-8,
    }


def write_cases(path: Path, cases: list[dict]) -> None:
    path.write_text(
        json.dumps({"format_version": 1, "cases": cases}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_old_iris_frequency_formula_is_preserved(tmp_path: Path) -> None:
    write_cases(
        tmp_path / "calculation_cases.json",
        [
            case(1, "standard", 1.0),
            case(2, "without_compensation", 1.25),
            case(3, "with_compensation", 0.6),
        ],
    )

    result = FrequencyCalculationService().calculate(tmp_path)

    frequencies = [item["scenario_frequency"] for item in result.results]
    assert frequencies == pytest.approx([6e-5, 7.5e-5, 3.6e-5])
    assert result.total_frequency == pytest.approx(1.71e-4)
    assert result.results[1]["base_frequency_with_multiplier"] == pytest.approx(
        3.75e-7
    )
    assert result.case_count == 3

    saved = json.loads(result.path.read_text(encoding="utf-8"))
    assert saved["formula"] == (
        "unit_scenario_frequency × frequency_basis × frequency_multiplier"
    )
    assert saved["results"][2]["scenario_code"] == "С3"


def test_equipment_count_is_used_without_unit_conversion(tmp_path: Path) -> None:
    apparatus = case(1, "standard", 1.0, basis=3)
    apparatus["frequency_basis_unit"] = "шт."
    write_cases(tmp_path / "calculation_cases.json", [apparatus])

    result = FrequencyCalculationService().calculate(tmp_path)

    assert result.results[0]["scenario_frequency"] == pytest.approx(1.8e-7)


def test_invalid_cases_do_not_replace_existing_result(tmp_path: Path) -> None:
    invalid = case(1, "standard", 1.0)
    invalid["unit_scenario_frequency"] = math.nan
    write_cases(tmp_path / "calculation_cases.json", [invalid])
    result_path = tmp_path / "frequency_results.json"
    result_path.write_text('{"old": true}\n', encoding="utf-8")

    with pytest.raises(FrequencyCalculationError, match="должно быть числом"):
        FrequencyCalculationService().calculate(tmp_path)

    assert result_path.read_text(encoding="utf-8") == '{"old": true}\n'


def test_missing_calculation_cases_has_clear_error(tmp_path: Path) -> None:
    with pytest.raises(FrequencyCalculationError, match="Сначала сформируйте"):
        FrequencyCalculationService().calculate(tmp_path)
