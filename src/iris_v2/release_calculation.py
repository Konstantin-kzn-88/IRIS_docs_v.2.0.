import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris_v2.amount_calculation import FILE_NAME as AMOUNT_FILE_NAME
from iris_v2.calculation_cases import FILE_NAME as CASES_FILE_NAME
from iris_v2.calculation_config import (
    CalculationConfigError,
    CalculationConfigService,
)


FILE_NAME = "release_results.json"
PIPELINE_TYPES = {0, 9}
STORAGE_TYPES = {1, 7}
PRESSURE_EQUIPMENT_TYPES = {2, 3, 6, 8}
PURE_GAS_KINDS = {2, 3, 7}
DISCHARGE_COEFFICIENT = 0.62
UNIVERSAL_GAS_CONSTANT = 8.314462618
ADIABATIC_INDEX = 1.3
KG_TO_T = 0.001

RELEASE_MODE_NAMES = {
    "inventory_full": "Полное разрушение — вся масса в оборудовании",
    "inventory_partial": "Частичное разрушение — доля массы",
    "pipeline_liquid_full": "Разрыв трубопровода — масса участка и приток жидкости",
    "pipeline_liquid_partial": "Частичная разгерметизация трубопровода",
    "gas_supply_full": "Полный выброс газа — масса в оборудовании и приток",
    "gas_supply_partial": "Частичный выброс газа — масса в оборудовании и приток",
    "liquid_phase_leak": "Истечение ниже уровня жидкости",
    "gas_phase_leak": "Истечение выше уровня жидкости",
    "pump_release": "Разрушение отводящего трубопровода насоса",
}


class ReleaseCalculationError(Exception):
    pass


@dataclass(frozen=True)
class ReleaseCalculationResult:
    path: Path
    case_count: int
    results: tuple[dict[str, Any], ...]


def _read_json(path: Path, label: str) -> Any:
    if not path.is_file():
        raise ReleaseCalculationError(f"Файл не найден: {path.name}. {label}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseCalculationError(f"Не удалось прочитать {path.name}") from exc


def _objects_by_id(
    values: Any,
    label: str,
) -> dict[int, dict[str, Any]]:
    if not isinstance(values, list) or not values:
        raise ReleaseCalculationError(f"{label} должен быть непустым списком")
    result: dict[int, dict[str, Any]] = {}
    for index, value in enumerate(values, start=1):
        if not isinstance(value, dict):
            raise ReleaseCalculationError(f"{label}, запись {index}: ожидается объект")
        object_id = value.get("id")
        if (
            isinstance(object_id, bool)
            or not isinstance(object_id, int)
            or object_id <= 0
            or object_id in result
        ):
            raise ReleaseCalculationError(
                f"{label}, запись {index}: недопустимый или повторяющийся id"
            )
        result[object_id] = value
    return result


def _number(
    value: Any,
    label: str,
    *,
    positive: bool = False,
    non_negative: bool = False,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ReleaseCalculationError(f"{label} должно быть числом")
    result = float(value)
    if positive and result <= 0:
        raise ReleaseCalculationError(f"{label} должно быть больше нуля")
    if non_negative and result < 0:
        raise ReleaseCalculationError(f"{label} не может быть отрицательным")
    return result


def liquid_leak_mass_flow_kg_s(
    pressure_mpa: float,
    hole_diameter_mm: float,
    density_kg_m3: float,
) -> float:
    pressure_pa = pressure_mpa * 1_000_000.0
    hole_diameter_m = hole_diameter_mm / 1000.0
    area_m2 = math.pi * hole_diameter_m**2 / 4.0
    return (
        DISCHARGE_COEFFICIENT
        * area_m2
        * math.sqrt(2.0 * density_kg_m3 * pressure_pa)
    )


def gas_leak_mass_flow_kg_s(
    pressure_mpa: float,
    hole_diameter_mm: float,
    temperature_c: float,
    molar_mass_kg_mol: float,
) -> float:
    temperature_k = temperature_c + 273.15
    if temperature_k <= 0:
        raise ReleaseCalculationError(
            "Температура вещества должна быть выше абсолютного нуля"
        )
    pressure_pa = pressure_mpa * 1_000_000.0
    hole_diameter_m = hole_diameter_mm / 1000.0
    area_m2 = math.pi * hole_diameter_m**2 / 4.0
    specific_gas_constant = UNIVERSAL_GAS_CONSTANT / molar_mass_kg_mol
    critical_factor = (
        2.0 / (ADIABATIC_INDEX + 1.0)
    ) ** ((ADIABATIC_INDEX + 1.0) / (ADIABATIC_INDEX - 1.0))
    return (
        DISCHARGE_COEFFICIENT
        * area_m2
        * pressure_pa
        * math.sqrt(
            ADIABATIC_INDEX
            / (specific_gas_constant * temperature_k)
            * critical_factor
        )
    )


def release_mode(equipment_type: int, kind: int, scenario_line: int) -> str:
    """Return the old IRIS release rule without equipment/kind modules."""
    if equipment_type in PIPELINE_TYPES:
        if kind in PURE_GAS_KINDS:
            full = {1, 2, 3, 4} if kind in {2, 3} else {1}
            partial = {5, 6, 7, 8} if kind in {2, 3} else {2}
            if scenario_line in full:
                return "gas_supply_full"
            if scenario_line in partial:
                return "gas_supply_partial"
        else:
            if kind in {0, 1, 9}:
                full, partial = {1, 2, 3}, {4, 5, 6}
            elif kind in {4, 5}:
                full, partial = {1, 2, 3, 4}, {5, 6, 7, 8}
            else:
                full, partial = {1}, {2}
            if scenario_line in full:
                return "pipeline_liquid_full"
            if scenario_line in partial:
                return "pipeline_liquid_partial"

    elif equipment_type in STORAGE_TYPES:
        if kind in {0, 1, 9}:
            full, partial = {1, 2, 3}, {4, 5, 6}
        else:
            full, partial = {1}, {2}
        if scenario_line in full:
            return "inventory_full"
        if scenario_line in partial:
            return "inventory_partial"

    elif equipment_type in PRESSURE_EQUIPMENT_TYPES:
        if kind in {2, 3}:
            if scenario_line in {1, 2, 3, 4}:
                return "gas_supply_full"
            if scenario_line in {5, 6, 7, 8}:
                return "gas_supply_partial"
        elif kind == 7:
            if scenario_line == 1:
                return "gas_supply_full"
            if scenario_line == 2:
                return "gas_supply_partial"
        elif kind == 8:
            if scenario_line == 1:
                return "inventory_full"
            if scenario_line == 2:
                return "inventory_partial"
        else:
            if scenario_line in {1, 2, 3} or (
                kind == 0 and scenario_line == 9
            ):
                return "inventory_full"
            if scenario_line in {4, 5}:
                return "liquid_phase_leak"
            if scenario_line in {6, 7, 8}:
                return "gas_phase_leak"

    elif equipment_type == 4:
        return "pump_release"

    elif equipment_type == 5 and kind in PURE_GAS_KINDS:
        full = {1, 2, 3, 4} if kind in {2, 3} else {1}
        partial = {5, 6, 7, 8} if kind in {2, 3} else {2}
        if scenario_line in full:
            return "gas_supply_full"
        if scenario_line in partial:
            return "gas_supply_partial"

    raise ReleaseCalculationError(
        "Не задано правило массы выброса для "
        f"equipment_type={equipment_type}, kind={kind}, "
        f"scenario_line={scenario_line}"
    )


class ReleaseCalculationService:
    def calculate(
        self, project_directory: Path | str
    ) -> ReleaseCalculationResult:
        project = Path(project_directory)
        if not project.is_dir():
            raise ReleaseCalculationError(f"Папка проекта не найдена: {project}")

        equipment = _objects_by_id(
            _read_json(project / "equipments.json", "Сначала импортируйте оборудование"),
            "Оборудование",
        )
        substances = _objects_by_id(
            _read_json(project / "substances.json", "Сначала выберите вещества"),
            "Вещества",
        )
        amount_data = _read_json(
            project / AMOUNT_FILE_NAME,
            "Сначала рассчитайте количество ОВ",
        )
        amount_values = (
            amount_data.get("results") if isinstance(amount_data, dict) else None
        )
        if not isinstance(amount_values, list) or not amount_values:
            raise ReleaseCalculationError(
                f"{AMOUNT_FILE_NAME} не содержит результатов"
            )
        amount_by_equipment: dict[int, dict[str, Any]] = {}
        for index, value in enumerate(amount_values, start=1):
            if not isinstance(value, dict):
                raise ReleaseCalculationError(
                    f"{AMOUNT_FILE_NAME}, запись {index}: ожидается объект"
                )
            equipment_id = value.get("equipment_id")
            if (
                isinstance(equipment_id, bool)
                or not isinstance(equipment_id, int)
                or equipment_id in amount_by_equipment
            ):
                raise ReleaseCalculationError(
                    f"{AMOUNT_FILE_NAME}, запись {index}: "
                    "недопустимый или повторяющийся equipment_id"
                )
            amount_by_equipment[equipment_id] = value

        cases_data = _read_json(
            project / CASES_FILE_NAME,
            "Сначала сформируйте расчётные сценарии",
        )
        cases = cases_data.get("cases") if isinstance(cases_data, dict) else None
        if not isinstance(cases, list) or not cases:
            raise ReleaseCalculationError(
                f"{CASES_FILE_NAME} не содержит расчётных сценариев"
            )
        try:
            config = CalculationConfigService().load(project)
        except CalculationConfigError as exc:
            raise ReleaseCalculationError(str(exc)) from exc
        partial_fraction = _number(
            config.get("partial_release_fraction"),
            "partial_release_fraction",
            positive=True,
        )
        liquid_hole = _number(
            config.get("liquid_leak_hole_diameter_mm"),
            "liquid_leak_hole_diameter_mm",
            positive=True,
        )
        gas_hole = _number(
            config.get("gas_leak_hole_diameter_mm"),
            "gas_leak_hole_diameter_mm",
            positive=True,
        )

        results: list[dict[str, Any]] = []
        case_ids: set[int] = set()
        scenario_codes: set[str] = set()
        for index, case in enumerate(cases, start=1):
            if not isinstance(case, dict):
                raise ReleaseCalculationError(f"Сценарий {index}: ожидается объект")
            case_id = case.get("id")
            scenario_code = str(case.get("scenario_code", "")).strip()
            if (
                isinstance(case_id, bool)
                or not isinstance(case_id, int)
                or case_id <= 0
                or case_id in case_ids
            ):
                raise ReleaseCalculationError(
                    f"Сценарий {index}: недопустимый или повторяющийся id"
                )
            if not scenario_code or scenario_code in scenario_codes:
                raise ReleaseCalculationError(
                    f"Сценарий {index}: пустой или повторяющийся scenario_code"
                )
            case_ids.add(case_id)
            scenario_codes.add(scenario_code)

            equipment_id = case.get("equipment_id")
            item = equipment.get(equipment_id)
            amount = amount_by_equipment.get(equipment_id)
            if item is None:
                raise ReleaseCalculationError(
                    f"Сценарий {scenario_code}: equipment_id={equipment_id} "
                    "отсутствует в equipments.json"
                )
            if amount is None:
                raise ReleaseCalculationError(
                    f"Сценарий {scenario_code}: equipment_id={equipment_id} "
                    f"отсутствует в {AMOUNT_FILE_NAME}. Пересчитайте количество ОВ"
                )
            substance_id = item.get("substance_id")
            substance = substances.get(substance_id)
            if substance is None:
                raise ReleaseCalculationError(
                    f"Сценарий {scenario_code}: substance_id={substance_id} "
                    "отсутствует в substances.json"
                )
            equipment_type = item.get("equipment_type")
            kind = substance.get("kind")
            scenario_line = case.get("typical_scenario_line")
            for actual, expected, label in (
                (case.get("equipment_type"), equipment_type, "equipment_type"),
                (case.get("substance_id"), substance_id, "substance_id"),
                (case.get("kind"), kind, "kind"),
                (amount.get("equipment_type"), equipment_type, "amount equipment_type"),
                (amount.get("substance_id"), substance_id, "amount substance_id"),
                (amount.get("kind"), kind, "amount kind"),
            ):
                if actual != expected:
                    raise ReleaseCalculationError(
                        f"Сценарий {scenario_code}: устаревшие данные ({label}). "
                        "Повторите формирование исходных результатов"
                    )
            if (
                isinstance(equipment_type, bool)
                or not isinstance(equipment_type, int)
                or isinstance(kind, bool)
                or not isinstance(kind, int)
                or isinstance(scenario_line, bool)
                or not isinstance(scenario_line, int)
            ):
                raise ReleaseCalculationError(
                    f"Сценарий {scenario_code}: неверные коды исходных данных"
                )

            mode = release_mode(equipment_type, kind, scenario_line)
            amount_t = _number(
                amount.get("amount_t"),
                f"Сценарий {scenario_code}: amount_t",
                positive=True,
            )
            pressure = _number(
                item.get("pressure_mpa"),
                f"Сценарий {scenario_code}: pressure_mpa",
                positive=True,
            )
            shutdown_time = _number(
                item.get("shutdown_time_s"),
                f"Сценарий {scenario_code}: shutdown_time_s",
                non_negative=True,
            )
            physical = substance.get("physical")
            if not isinstance(physical, dict):
                raise ReleaseCalculationError(
                    f"Сценарий {scenario_code}: physical вещества должен быть объектом"
                )

            flow_kg_s = 0.0
            flow_mass_t = 0.0
            if mode in {
                "pipeline_liquid_full",
                "pipeline_liquid_partial",
                "liquid_phase_leak",
                "pump_release",
            }:
                density = _number(
                    physical.get("density_liquid_kg_per_m3"),
                    f"Сценарий {scenario_code}: density_liquid_kg_per_m3",
                    positive=True,
                )
                diameter = (
                    _number(
                        item.get("diameter_mm"),
                        f"Сценарий {scenario_code}: diameter_mm",
                        positive=True,
                    )
                    if mode.startswith("pipeline_liquid")
                    else liquid_hole
                )
                flow_kg_s = liquid_leak_mass_flow_kg_s(
                    pressure, diameter, density
                )
                if mode == "pipeline_liquid_partial":
                    flow_kg_s *= partial_fraction
                flow_mass_t = flow_kg_s * shutdown_time * KG_TO_T
            elif mode in {"gas_supply_full", "gas_supply_partial", "gas_phase_leak"}:
                temperature = _number(
                    item.get("substance_temperature_c"),
                    f"Сценарий {scenario_code}: substance_temperature_c",
                )
                molar_mass = _number(
                    physical.get("molar_mass_kg_per_mol"),
                    f"Сценарий {scenario_code}: molar_mass_kg_per_mol",
                    positive=True,
                )
                flow_kg_s = gas_leak_mass_flow_kg_s(
                    pressure, gas_hole, temperature, molar_mass
                )
                if mode == "gas_supply_partial":
                    flow_kg_s *= partial_fraction
                flow_mass_t = flow_kg_s * shutdown_time * KG_TO_T

            if mode in {
                "inventory_full",
                "pipeline_liquid_full",
                "gas_supply_full",
                "gas_supply_partial",
                "pump_release",
            }:
                inventory_release_t = amount_t
            elif mode in {"inventory_partial", "pipeline_liquid_partial"}:
                inventory_release_t = amount_t * partial_fraction
            else:
                inventory_release_t = 0.0
            released_t = inventory_release_t + flow_mass_t

            result = dict(case)
            result.update(
                {
                    "release_mode": mode,
                    "release_mode_name": RELEASE_MODE_NAMES[mode],
                    "amount_t": amount_t,
                    "inventory_release_t": inventory_release_t,
                    "flow_kg_s": flow_kg_s,
                    "flow_mass_t": flow_mass_t,
                    "ov_in_accident_t": released_t,
                }
            )
            results.append(result)

        result_data = {
            "format_version": 1,
            "case_count": len(results),
            "constants": {
                "discharge_coefficient": DISCHARGE_COEFFICIENT,
                "universal_gas_constant": UNIVERSAL_GAS_CONSTANT,
                "adiabatic_index": ADIABATIC_INDEX,
                "partial_release_fraction": partial_fraction,
                "liquid_leak_hole_diameter_mm": liquid_hole,
                "gas_leak_hole_diameter_mm": gas_hole,
            },
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
            raise ReleaseCalculationError(f"Не удалось сохранить {path}") from exc

        return ReleaseCalculationResult(
            path=path,
            case_count=len(results),
            results=tuple(results),
        )
