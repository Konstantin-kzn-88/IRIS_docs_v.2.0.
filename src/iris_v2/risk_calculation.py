import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris_v2.damage_calculation import FILE_NAME as DAMAGE_FILE_NAME
from iris_v2.frequency_calculation import FILE_NAME as FREQUENCY_FILE_NAME
from iris_v2.service import ProjectError, ProjectService


FILE_NAME = "risk_results.json"


class RiskCalculationError(Exception):
    pass


@dataclass(frozen=True)
class RiskCalculationResult:
    path: Path
    case_count: int
    people_count: int
    total_collective_risk_fatalities: float
    total_collective_risk_injured: float
    total_expected_damage: float
    total_individual_risk_fatalities: float | None
    total_individual_risk_injured: float | None
    results: tuple[dict[str, Any], ...]


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
    if isinstance(value, bool):
        raise ValueError(f"{name} должно быть целым числом не меньше нуля")
    if isinstance(value, int):
        result = value
    elif isinstance(value, float) and value.is_integer():
        result = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        result = int(value.strip())
    else:
        raise ValueError(f"{name} должно быть целым числом не меньше нуля")
    if result < 0:
        raise ValueError(f"{name} должно быть целым числом не меньше нуля")
    return result


def calculate_risk(
    fatalities_count: int,
    injured_count: int,
    scenario_frequency: float,
    total_damage: float,
    people_count: int,
) -> dict[str, float | None]:
    fatalities = _count(fatalities_count, "fatalities_count")
    injured = _count(injured_count, "injured_count")
    frequency = _number(scenario_frequency, "scenario_frequency")
    damage = _number(total_damage, "total_damage")
    people = _count(people_count, "people_count")

    collective_fatalities = fatalities * frequency
    collective_injured = injured * frequency
    return {
        "collective_risk_fatalities": collective_fatalities,
        "collective_risk_injured": collective_injured,
        "individual_risk_fatalities": (
            collective_fatalities / people if people > 0 else None
        ),
        "individual_risk_injured": (
            collective_injured / people if people > 0 else None
        ),
        "expected_damage": damage * frequency,
    }


def _read_results(path: Path, hint: str) -> list[dict[str, Any]]:
    if not path.is_file():
        raise RiskCalculationError(f"Файл не найден: {path.name}. {hint}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RiskCalculationError(f"Не удалось прочитать {path.name}") from exc
    values = data.get("results") if isinstance(data, dict) else None
    if not isinstance(values, list) or not values:
        raise RiskCalculationError(f"{path.name} не содержит результатов")
    if not all(isinstance(value, dict) for value in values):
        raise RiskCalculationError(f"{path.name} содержит неверный результат")
    return values


def _by_id(values: list[dict[str, Any]], file_name: str) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for index, value in enumerate(values, start=1):
        case_id = value.get("id")
        if (
            isinstance(case_id, bool)
            or not isinstance(case_id, int)
            or case_id <= 0
            or case_id in result
        ):
            raise RiskCalculationError(
                f"{file_name}, результат {index}: "
                "недопустимый или повторяющийся id"
            )
        result[case_id] = value
    return result


class RiskCalculationService:
    def calculate(self, project_directory: Path | str) -> RiskCalculationResult:
        project = Path(project_directory)
        if not project.is_dir():
            raise RiskCalculationError(f"Папка проекта не найдена: {project}")
        damage_values = _read_results(
            project / DAMAGE_FILE_NAME,
            "Сначала рассчитайте ущерб",
        )
        frequency_values = _read_results(
            project / FREQUENCY_FILE_NAME,
            "Сначала рассчитайте частоты сценариев",
        )
        damage_by_id = _by_id(damage_values, DAMAGE_FILE_NAME)
        frequency_by_id = _by_id(frequency_values, FREQUENCY_FILE_NAME)
        if damage_by_id.keys() != frequency_by_id.keys():
            raise RiskCalculationError(
                "Наборы сценариев в расчёте ущерба и частот не совпадают"
            )

        try:
            project_info = ProjectService().open(project)
            personnel = project_info.opo_snapshot.get("personnel", {})
            if not isinstance(personnel, dict):
                raise ValueError("opo_snapshot.personnel должен быть объектом")
            employees = _count(
                personnel.get("employees_count", 0),
                "employees_count",
            )
            other_employees = _count(
                personnel.get("employees_other_opo_count", 0),
                "employees_other_opo_count",
            )
        except (ProjectError, ValueError) as exc:
            raise RiskCalculationError(str(exc)) from exc
        people_count = employees + other_employees

        results: list[dict[str, Any]] = []
        for case_id, damage_item in damage_by_id.items():
            scenario_code = str(damage_item.get("scenario_code", "")).strip()
            frequency_item = frequency_by_id[case_id]
            if not scenario_code or frequency_item.get("scenario_code") != scenario_code:
                raise RiskCalculationError(
                    f"Сценарий id={case_id}: данные частоты устарели"
                )
            try:
                risk = calculate_risk(
                    damage_item.get("fatalities_count"),
                    damage_item.get("injured_count"),
                    frequency_item.get("scenario_frequency"),
                    damage_item.get("total_damage"),
                    people_count,
                )
            except ValueError as exc:
                raise RiskCalculationError(
                    f"Сценарий {scenario_code}: {exc}"
                ) from exc
            result = dict(damage_item)
            result.update(
                {
                    "scenario_frequency": float(
                        frequency_item["scenario_frequency"]
                    ),
                    "risk_people_count": people_count,
                    "individual_risk_status": (
                        "calculated" if people_count > 0 else "no_people"
                    ),
                    **risk,
                }
            )
            results.append(result)

        total_collective_fatalities = sum(
            item["collective_risk_fatalities"] for item in results
        )
        total_collective_injured = sum(
            item["collective_risk_injured"] for item in results
        )
        total_expected_damage = sum(item["expected_damage"] for item in results)
        total_individual_fatalities = (
            total_collective_fatalities / people_count
            if people_count > 0
            else None
        )
        total_individual_injured = (
            total_collective_injured / people_count
            if people_count > 0
            else None
        )
        result_data = {
            "format_version": 1,
            "case_count": len(results),
            "employees_count": employees,
            "employees_other_opo_count": other_employees,
            "risk_people_count": people_count,
            "individual_risk_status": (
                "calculated" if people_count > 0 else "no_people"
            ),
            "total_collective_risk_fatalities": total_collective_fatalities,
            "total_collective_risk_injured": total_collective_injured,
            "total_individual_risk_fatalities": total_individual_fatalities,
            "total_individual_risk_injured": total_individual_injured,
            "total_expected_damage": total_expected_damage,
            "expected_damage_unit": "тыс. руб./год",
            "results": results,
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
            raise RiskCalculationError(f"Не удалось сохранить {path}") from exc

        return RiskCalculationResult(
            path=path,
            case_count=len(results),
            people_count=people_count,
            total_collective_risk_fatalities=total_collective_fatalities,
            total_collective_risk_injured=total_collective_injured,
            total_expected_damage=total_expected_damage,
            total_individual_risk_fatalities=total_individual_fatalities,
            total_individual_risk_injured=total_individual_injured,
            results=tuple(results),
        )
