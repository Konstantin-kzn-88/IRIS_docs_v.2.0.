import json
import math
from pathlib import Path
from typing import Any

from docx.document import Document as DocumentType
from docx.oxml.ns import qn
from docx.shared import Pt

from iris_v2.risk_calculation import FILE_NAME as RISK_FILE_NAME
from iris_v2.risk_summary import FILE_NAME as SUMMARY_FILE_NAME


MARKER = "{{FATAL_ACCIDENT_FREQUENCY}}"


class ReportFatalFrequencyError(Exception):
    pass


def _load_object(path: Path, missing_message: str) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReportFatalFrequencyError(missing_message) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportFatalFrequencyError(
            f"Не удалось прочитать {path.name}"
        ) from exc
    if not isinstance(raw, dict):
        raise ReportFatalFrequencyError(
            f"Файл {path.name} повреждён: ожидается объект"
        )
    return raw


def _number(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0
    ):
        raise ReportFatalFrequencyError(
            f"{label} должно быть числом не меньше нуля"
        )
    return float(value)


def _optional_number(value: Any, label: str) -> float | None:
    return None if value is None else _number(value, label)


def _same_optional(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return left is right
    return math.isclose(left, right, rel_tol=1e-12, abs_tol=0.0)


def load_fatal_accident_frequency(project_directory: Path | str) -> str:
    project = Path(project_directory)
    risk = _load_object(
        project / RISK_FILE_NAME,
        "Риски не рассчитаны. Сначала выполните модуль «Расчёт риска»",
    )
    summary = _load_object(
        project / SUMMARY_FILE_NAME,
        "Сводные показатели риска не рассчитаны. "
        "Сначала выполните модуль «Сводные показатели риска»",
    )
    results = risk.get("results")
    if not isinstance(results, list) or not results:
        raise ReportFatalFrequencyError(
            f"Файл {RISK_FILE_NAME} повреждён: results должен быть непустым списком"
        )

    codes: set[str] = set()
    fatal_frequencies: list[float] = []
    for index, item in enumerate(results, start=1):
        if not isinstance(item, dict):
            raise ReportFatalFrequencyError(
                f"{RISK_FILE_NAME}, запись {index}: ожидается объект"
            )
        code = str(item.get("scenario_code", "")).strip()
        if not code or code in codes:
            raise ReportFatalFrequencyError(
                f"{RISK_FILE_NAME}, запись {index}: "
                "пустой или повторяющийся scenario_code"
            )
        codes.add(code)
        fatalities = item.get("fatalities_count")
        if (
            isinstance(fatalities, bool)
            or not isinstance(fatalities, int)
            or fatalities < 0
        ):
            raise ReportFatalFrequencyError(
                f"Сценарий {code}: fatalities_count должно быть "
                "целым числом не меньше нуля"
            )
        frequency = _number(
            item.get("scenario_frequency"),
            f"Сценарий {code}: scenario_frequency",
        )
        if fatalities >= 1:
            fatal_frequencies.append(frequency)

    case_count = summary.get("case_count")
    if (
        isinstance(case_count, bool)
        or not isinstance(case_count, int)
        or case_count != len(results)
    ):
        raise ReportFatalFrequencyError(
            f"Файл {SUMMARY_FILE_NAME} устарел: не совпадает case_count"
        )
    if summary.get("risk_unit") != "1/год":
        raise ReportFatalFrequencyError(
            f"Файл {SUMMARY_FILE_NAME} содержит неизвестную единицу частоты"
        )

    expected_min = min(fatal_frequencies) if fatal_frequencies else None
    expected_max = max(fatal_frequencies) if fatal_frequencies else None
    stored_min = _optional_number(
        summary.get("fatal_accident_frequency_min"),
        "fatal_accident_frequency_min",
    )
    stored_max = _optional_number(
        summary.get("fatal_accident_frequency_max"),
        "fatal_accident_frequency_max",
    )
    if not _same_optional(stored_min, expected_min) or not _same_optional(
        stored_max, expected_max
    ):
        raise ReportFatalFrequencyError(
            f"Файл {SUMMARY_FILE_NAME} устарел: частоты сценариев с погибшими "
            f"не совпадают с {RISK_FILE_NAME}"
        )

    if stored_min is None:
        return "Сценариев с погибшими нет."
    if math.isclose(stored_min, stored_max, rel_tol=1e-12, abs_tol=0.0):
        return f"Частота сценариев с погибшими: {stored_min:.3E} 1/год."
    return (
        "Частота сценариев с погибшими: "
        f"от {stored_min:.3E} до {stored_max:.3E} 1/год."
    )


def render_fatal_accident_frequency(
    document: DocumentType,
    value: str,
) -> bool:
    marker_paragraph = next(
        (paragraph for paragraph in document.paragraphs if MARKER in paragraph.text),
        None,
    )
    if marker_paragraph is None:
        return False

    marker_paragraph.clear()
    run = marker_paragraph.add_run(value)
    run.font.name = "Times New Roman"
    run.font.size = Pt(12)
    fonts = run._element.get_or_add_rPr().get_or_add_rFonts()
    for name in ("ascii", "hAnsi", "eastAsia"):
        fonts.set(qn(f"w:{name}"), "Times New Roman")
    return True
