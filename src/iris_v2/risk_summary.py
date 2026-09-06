import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris_v2.risk_calculation import FILE_NAME as RISK_FILE_NAME


FILE_NAME = "risk_summary.json"


class RiskSummaryError(Exception):
    pass


@dataclass(frozen=True)
class RiskSummaryResult:
    path: Path
    case_count: int
    component_count: int
    fatal_accident_frequency_min: float | None
    fatal_accident_frequency_max: float | None
    total_collective_risk_fatalities: float
    total_collective_risk_injured: float
    total_expected_damage: float
    components: tuple[dict[str, Any], ...]
    fn_points: tuple[dict[str, float | int], ...]
    fg_points: tuple[dict[str, float], ...]


def _number(value: Any, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value < 0
    ):
        raise ValueError(f"{name} должно быть числом не меньше нуля")
    return float(value)


def _count(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} должно быть целым числом не меньше нуля")
    return value


def build_fn_points(rows: list[dict[str, Any]]) -> list[dict[str, float | int]]:
    """Точки F/N: F(N) = сумма частот сценариев с числом погибших >= N."""
    frequency_by_count: dict[int, float] = {}
    for index, row in enumerate(rows, start=1):
        fatalities = _count(row.get("fatalities_count"), f"строка {index}: fatalities_count")
        frequency = _number(
            row.get("scenario_frequency"),
            f"строка {index}: scenario_frequency",
        )
        frequency_by_count[fatalities] = (
            frequency_by_count.get(fatalities, 0.0) + frequency
        )

    points = [
        {
            "fatalities_count": fatalities,
            "cumulative_frequency": sum(
                frequency
                for count, frequency in frequency_by_count.items()
                if count >= fatalities
            ),
        }
        for fatalities in sorted(frequency_by_count)
    ]
    if points and points[0]["fatalities_count"] > 0:
        points.insert(
            0,
            {
                "fatalities_count": 0,
                "cumulative_frequency": points[0]["cumulative_frequency"],
            },
        )
    return [point for point in points if point["cumulative_frequency"] > 0]


def build_fg_points(rows: list[dict[str, Any]]) -> list[dict[str, float]]:
    """Точки F/G: G в млн руб., исходный total_damage задан в тыс. руб."""
    frequency_by_damage: dict[float, float] = {}
    for index, row in enumerate(rows, start=1):
        damage = _number(row.get("total_damage"), f"строка {index}: total_damage")
        frequency = _number(
            row.get("scenario_frequency"),
            f"строка {index}: scenario_frequency",
        )
        damage_million = round(damage / 1000.0, 6)
        frequency_by_damage[damage_million] = (
            frequency_by_damage.get(damage_million, 0.0) + frequency
        )

    points = [
        {
            "damage_million_rub": damage,
            "cumulative_frequency": sum(
                frequency
                for value, frequency in frequency_by_damage.items()
                if value >= damage
            ),
        }
        for damage in sorted(frequency_by_damage)
    ]
    if points and points[0]["damage_million_rub"] > 0:
        points.insert(
            0,
            {
                "damage_million_rub": 0.0,
                "cumulative_frequency": points[0]["cumulative_frequency"],
            },
        )
    return [point for point in points if point["cumulative_frequency"] > 0]


def _sum_optional(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [row[field] for row in rows if row[field] is not None]
    return sum(values) if values else None


def _component_summary(name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    fatal_frequencies = [
        row["scenario_frequency"] for row in rows if row["fatalities_count"] >= 1
    ]
    return {
        "hazard_component": name,
        "scenario_count": len(rows),
        "collective_risk_fatalities": sum(
            row["collective_risk_fatalities"] for row in rows
        ),
        "collective_risk_injured": sum(
            row["collective_risk_injured"] for row in rows
        ),
        "individual_risk_fatalities": _sum_optional(
            rows, "individual_risk_fatalities"
        ),
        "individual_risk_injured": _sum_optional(
            rows, "individual_risk_injured"
        ),
        "expected_damage": sum(row["expected_damage"] for row in rows),
        "fatal_accident_frequency": sum(fatal_frequencies),
        "fatal_accident_frequency_min": (
            min(fatal_frequencies) if fatal_frequencies else None
        ),
        "fatal_accident_frequency_max": (
            max(fatal_frequencies) if fatal_frequencies else None
        ),
        "max_direct_losses": max(row["direct_losses"] for row in rows),
        "max_total_environmental_damage": max(
            row["total_environmental_damage"] for row in rows
        ),
        "max_total_damage": max(row["total_damage"] for row in rows),
    }


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise RiskSummaryError(
            f"Файл не найден: {RISK_FILE_NAME}. Сначала рассчитайте риски"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RiskSummaryError(f"Не удалось прочитать {RISK_FILE_NAME}") from exc
    values = data.get("results") if isinstance(data, dict) else None
    if not isinstance(values, list) or not values:
        raise RiskSummaryError(f"{RISK_FILE_NAME} не содержит результатов")

    rows: list[dict[str, Any]] = []
    ids: set[int] = set()
    for index, value in enumerate(values, start=1):
        if not isinstance(value, dict):
            raise RiskSummaryError(f"Результат {index}: ожидается объект")
        try:
            case_id = value.get("id")
            if (
                isinstance(case_id, bool)
                or not isinstance(case_id, int)
                or case_id <= 0
                or case_id in ids
            ):
                raise ValueError("недопустимый или повторяющийся id")
            ids.add(case_id)
            component = str(value.get("hazard_component", "")).strip()
            if not component:
                raise ValueError("hazard_component не заполнено")
            row = dict(value)
            row["hazard_component"] = component
            row["fatalities_count"] = _count(
                value.get("fatalities_count"), "fatalities_count"
            )
            for field in (
                "scenario_frequency",
                "collective_risk_fatalities",
                "collective_risk_injured",
                "expected_damage",
                "direct_losses",
                "total_environmental_damage",
                "total_damage",
            ):
                row[field] = _number(value.get(field), field)
            for field in (
                "individual_risk_fatalities",
                "individual_risk_injured",
            ):
                row[field] = (
                    None if value.get(field) is None else _number(value.get(field), field)
                )
        except ValueError as exc:
            code = str(value.get("scenario_code", index))
            raise RiskSummaryError(f"Сценарий {code}: {exc}") from exc
        rows.append(row)
    return rows


class RiskSummaryService:
    def calculate(self, project_directory: Path | str) -> RiskSummaryResult:
        project = Path(project_directory)
        if not project.is_dir():
            raise RiskSummaryError(f"Папка проекта не найдена: {project}")
        rows = _read_rows(project / RISK_FILE_NAME)

        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(row["hazard_component"], []).append(row)
        components = [
            _component_summary(name, component_rows)
            for name, component_rows in grouped.items()
        ]
        fatal_frequencies = [
            row["scenario_frequency"] for row in rows if row["fatalities_count"] >= 1
        ]
        fn_points = build_fn_points(rows)
        fg_points = build_fg_points(rows)
        result_data = {
            "format_version": 1,
            "case_count": len(rows),
            "component_count": len(components),
            "fatal_accident_frequency_min": (
                min(fatal_frequencies) if fatal_frequencies else None
            ),
            "fatal_accident_frequency_max": (
                max(fatal_frequencies) if fatal_frequencies else None
            ),
            "total_collective_risk_fatalities": sum(
                row["collective_risk_fatalities"] for row in rows
            ),
            "total_collective_risk_injured": sum(
                row["collective_risk_injured"] for row in rows
            ),
            "total_individual_risk_fatalities": _sum_optional(
                rows, "individual_risk_fatalities"
            ),
            "total_individual_risk_injured": _sum_optional(
                rows, "individual_risk_injured"
            ),
            "total_expected_damage": sum(row["expected_damage"] for row in rows),
            "risk_unit": "1/год",
            "expected_damage_unit": "тыс. руб./год",
            "damage_unit": "тыс. руб.",
            "fg_damage_unit": "млн руб.",
            "components": components,
            "fn_points": fn_points,
            "fg_points": fg_points,
        }
        path = project / FILE_NAME
        temporary = project / f".{FILE_NAME}.tmp"
        try:
            temporary.write_text(
                json.dumps(result_data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(path)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise RiskSummaryError(f"Не удалось сохранить {path}") from exc

        return RiskSummaryResult(
            path=path,
            case_count=len(rows),
            component_count=len(components),
            fatal_accident_frequency_min=result_data[
                "fatal_accident_frequency_min"
            ],
            fatal_accident_frequency_max=result_data[
                "fatal_accident_frequency_max"
            ],
            total_collective_risk_fatalities=result_data[
                "total_collective_risk_fatalities"
            ],
            total_collective_risk_injured=result_data[
                "total_collective_risk_injured"
            ],
            total_expected_damage=result_data["total_expected_damage"],
            components=tuple(components),
            fn_points=tuple(fn_points),
            fg_points=tuple(fg_points),
        )
