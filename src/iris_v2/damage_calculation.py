import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris_v2.calculation_config import (
    CalculationConfigError,
    CalculationConfigService,
)
from iris_v2.people_calculation import FILE_NAME as PEOPLE_FILE_NAME
from iris_v2.typical_scenarios import (
    TypicalScenarioError,
    TypicalScenarioService,
)


FILE_NAME = "damage_results.json"
DAMAGE_COEFFICIENTS = {
    1: (0.1,),
    2: (0.9, 0.1),
    6: (0.8, 1.3, 0.5, 0.25, 0.3, 0.1),
    8: (0.8, 1.3, 0.6, 0.3, 0.25, 0.2, 0.15, 0.1),
    9: (0.8, 1.3, 0.5, 0.3, 0.1, 0.2, 0.15, 0.1, 0.6),
}
LIQUIDATION_SHARE = 0.1
ENVIRONMENTAL_SHARE = 0.236
FATALITY_COST_THOUSAND_RUB = 3000.0
INJURY_COST_THOUSAND_RUB = 250.0
INDIRECT_SOCIAL_SHARE = 0.157


class DamageCalculationError(Exception):
    pass


@dataclass(frozen=True)
class DamageCalculationResult:
    path: Path
    case_count: int
    max_total_damage: float
    max_environmental_damage: float
    results: tuple[dict[str, Any], ...]


def _number(value: Any, name: str, *, positive: bool = False) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"{name} должно быть числом")
    result = float(value)
    if result < 0 or (positive and result <= 0):
        condition = "больше нуля" if positive else "не меньше нуля"
        raise ValueError(f"{name} должно быть {condition}")
    return result


def _count(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} должно быть целым числом не меньше нуля")
    return value


def approximate_equipment_cost(amount_t: float) -> float:
    """Старая кусочно-линейная оценка базовой стоимости, тыс. руб."""
    amount = _number(amount_t, "amount_t")
    if amount <= 0:
        return 0.0
    lower_amount = 0.1
    lower_cost = 100.0
    boundary_amount = 1000.0
    if amount <= boundary_amount:
        return lower_cost + amount - lower_amount
    boundary_cost = lower_cost + boundary_amount - lower_amount
    upper_slope = (25000.0 - boundary_cost) / (10000.0 - boundary_amount)
    return boundary_cost + upper_slope * (amount - boundary_amount)


def scenario_damage_coefficient(scenario_count: int, scenario_line: int) -> float:
    coefficients = DAMAGE_COEFFICIENTS.get(scenario_count)
    if coefficients is None:
        raise ValueError(
            f"для {scenario_count} сценариев коэффициенты ущерба не определены"
        )
    if (
        isinstance(scenario_line, bool)
        or not isinstance(scenario_line, int)
        or not 1 <= scenario_line <= len(coefficients)
    ):
        raise ValueError("scenario_line выходит за диапазон коэффициентов ущерба")
    return coefficients[scenario_line - 1]


def calculate_damage(
    amount_t: float,
    fatalities_count: int,
    injured_count: int,
    scenario_coefficient: float,
    damage_scale: float,
) -> dict[str, float]:
    amount = _number(amount_t, "amount_t")
    fatalities = _count(fatalities_count, "fatalities_count")
    injured = _count(injured_count, "injured_count")
    coefficient = _number(
        scenario_coefficient, "scenario_coefficient", positive=True
    )
    scale = _number(damage_scale, "damage_scale", positive=True)

    base_direct = approximate_equipment_cost(amount) * scale
    direct = base_direct * coefficient
    liquidation = base_direct * LIQUIDATION_SHARE * coefficient
    environmental = base_direct * ENVIRONMENTAL_SHARE * coefficient
    social = (
        fatalities * FATALITY_COST_THOUSAND_RUB
        + injured * INJURY_COST_THOUSAND_RUB
    )
    indirect = social * INDIRECT_SOCIAL_SHARE
    total = direct + liquidation + social + indirect + environmental
    return {
        "direct_losses": direct,
        "liquidation_costs": liquidation,
        "social_losses": social,
        "indirect_damage": indirect,
        "total_environmental_damage": environmental,
        "total_damage": total,
    }


class DamageCalculationService:
    def calculate(self, project_directory: Path | str) -> DamageCalculationResult:
        project = Path(project_directory)
        if not project.is_dir():
            raise DamageCalculationError(f"Папка проекта не найдена: {project}")
        source_path = project / PEOPLE_FILE_NAME
        if not source_path.is_file():
            raise DamageCalculationError(
                f"Файл не найден: {PEOPLE_FILE_NAME}. "
                "Сначала рассчитайте число погибших и пострадавших"
            )
        try:
            source_data = json.loads(source_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DamageCalculationError(
                f"Не удалось прочитать {PEOPLE_FILE_NAME}"
            ) from exc
        values = source_data.get("results") if isinstance(source_data, dict) else None
        if not isinstance(values, list) or not values:
            raise DamageCalculationError(f"{PEOPLE_FILE_NAME} не содержит результатов")
        try:
            config = CalculationConfigService().load(project)
            catalog = TypicalScenarioService().load()
        except (CalculationConfigError, TypicalScenarioError) as exc:
            raise DamageCalculationError(str(exc)) from exc
        damage_scale = float(config["damage_scale"])

        results: list[dict[str, Any]] = []
        case_ids: set[int] = set()
        scenario_codes: set[str] = set()
        for index, value in enumerate(values, start=1):
            if not isinstance(value, dict):
                raise DamageCalculationError(
                    f"Результат по людям {index}: ожидается объект"
                )
            case_id = value.get("id")
            scenario_code = str(value.get("scenario_code", "")).strip()
            if (
                isinstance(case_id, bool)
                or not isinstance(case_id, int)
                or case_id <= 0
                or case_id in case_ids
            ):
                raise DamageCalculationError(
                    f"Результат {index}: недопустимый или повторяющийся id"
                )
            if not scenario_code or scenario_code in scenario_codes:
                raise DamageCalculationError(
                    f"Результат {index}: пустой или повторяющийся scenario_code"
                )
            case_ids.add(case_id)
            scenario_codes.add(scenario_code)

            equipment_type = value.get("equipment_type")
            kind = value.get("kind")
            scenario_line = value.get("typical_scenario_line")
            try:
                scenarios = catalog.scenarios_for(equipment_type, kind)
                if not scenarios:
                    raise ValueError(
                        "для сочетания equipment_type и kind отсутствуют сценарии"
                    )
                coefficient = scenario_damage_coefficient(
                    len(scenarios), scenario_line
                )
                damage = calculate_damage(
                    value.get("amount_t"),
                    value.get("fatalities_count"),
                    value.get("injured_count"),
                    coefficient,
                    damage_scale,
                )
            except (TypeError, ValueError) as exc:
                raise DamageCalculationError(
                    f"Сценарий {scenario_code}: {exc}"
                ) from exc

            result = dict(value)
            result.update(
                {
                    "damage_unit": "тыс. руб.",
                    "damage_scale": damage_scale,
                    "damage_scenario_coefficient": coefficient,
                    **damage,
                }
            )
            results.append(result)

        max_total = max(item["total_damage"] for item in results)
        max_environmental = max(
            item["total_environmental_damage"] for item in results
        )
        result_data = {
            "format_version": 1,
            "unit": "тыс. руб.",
            "case_count": len(results),
            "max_total_damage": max_total,
            "max_environmental_damage": max_environmental,
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
            raise DamageCalculationError(f"Не удалось сохранить {path}") from exc

        return DamageCalculationResult(
            path=path,
            case_count=len(results),
            max_total_damage=max_total,
            max_environmental_damage=max_environmental,
            results=tuple(results),
        )
