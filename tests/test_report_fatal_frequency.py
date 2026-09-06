import json
from pathlib import Path

import pytest

from iris_v2.report_fatal_frequency import load_fatal_accident_frequency


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


@pytest.mark.parametrize(
    ("fatalities", "frequencies", "minimum", "maximum", "expected"),
    [
        (
            (1, 2),
            (1.0e-4, 5.0e-5),
            5.0e-5,
            1.0e-4,
            "Частота сценариев с погибшими: "
            "от 5.000E-05 до 1.000E-04 1/год.",
        ),
        (
            (0, 0),
            (1.0e-4, 5.0e-5),
            None,
            None,
            "Сценариев с погибшими нет.",
        ),
    ],
)
def test_fatal_frequency_text_variants(
    tmp_path: Path,
    fatalities: tuple[int, int],
    frequencies: tuple[float, float],
    minimum: float | None,
    maximum: float | None,
    expected: str,
) -> None:
    results = [
        {
            "scenario_code": f"С{index}",
            "fatalities_count": fatality_count,
            "scenario_frequency": frequency,
        }
        for index, (fatality_count, frequency) in enumerate(
            zip(fatalities, frequencies), start=1
        )
    ]
    write_json(tmp_path / "risk_results.json", {"results": results})
    write_json(
        tmp_path / "risk_summary.json",
        {
            "case_count": 2,
            "fatal_accident_frequency_min": minimum,
            "fatal_accident_frequency_max": maximum,
            "risk_unit": "1/год",
        },
    )

    assert load_fatal_accident_frequency(tmp_path) == expected
