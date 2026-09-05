import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris_v2.calculation_config import (
    CalculationConfigError,
    CalculationConfigService,
)
from iris_v2.spill_calculation import FILE_NAME as SPILL_FILE_NAME


FILE_NAME = "evaporation_results.json"
EVAPORATING_KINDS = {0, 1, 8}
REFERENCE_PRESSURE_PA = 101_325.0
UNIVERSAL_GAS_CONSTANT = 8.314462618
KG_TO_T = 0.001
STATUS_NAMES = {
    "calculated": "Испарение рассчитано",
    "no_spill": "Жидкий пролив отсутствует",
    "method_not_applicable": "Модель испарения не применяется",
}


class EvaporationCalculationError(Exception):
    pass


@dataclass(frozen=True)
class EvaporationCalculationResult:
    path: Path
    case_count: int
    evaporation_count: int
    results: tuple[dict[str, Any], ...]


def _read_json(path: Path, missing_hint: str) -> Any:
    if not path.is_file():
        raise EvaporationCalculationError(
            f"Файл не найден: {path.name}. {missing_hint}"
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaporationCalculationError(
            f"Не удалось прочитать {path.name}"
        ) from exc


def _objects_by_id(values: Any, label: str) -> dict[int, dict[str, Any]]:
    if not isinstance(values, list) or not values:
        raise EvaporationCalculationError(f"{label} должен быть непустым списком")
    result: dict[int, dict[str, Any]] = {}
    for index, value in enumerate(values, start=1):
        if not isinstance(value, dict):
            raise EvaporationCalculationError(
                f"{label}, запись {index}: ожидается объект"
            )
        object_id = value.get("id")
        if (
            isinstance(object_id, bool)
            or not isinstance(object_id, int)
            or object_id <= 0
            or object_id in result
        ):
            raise EvaporationCalculationError(
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
        raise EvaporationCalculationError(f"{label} должно быть числом")
    result = float(value)
    if positive and result <= 0:
        raise EvaporationCalculationError(f"{label} должно быть больше нуля")
    if non_negative and result < 0:
        raise EvaporationCalculationError(f"{label} не может быть отрицательным")
    return result


def saturated_vapor_pressure_pa(
    current_temperature_c: float,
    boiling_point_c: float,
    evaporation_heat_j_kg: float,
    molar_mass_kg_mol: float,
    reference_pressure_pa: float = REFERENCE_PRESSURE_PA,
) -> float:
    current_temperature_k = current_temperature_c + 273.15
    boiling_temperature_k = boiling_point_c + 273.15
    if current_temperature_k <= 0 or boiling_temperature_k <= 0:
        raise EvaporationCalculationError(
            "Температуры должны быть выше абсолютного нуля"
        )
    if evaporation_heat_j_kg <= 0 or molar_mass_kg_mol <= 0:
        raise EvaporationCalculationError(
            "Теплота испарения и молярная масса должны быть больше нуля"
        )
    if reference_pressure_pa <= 0:
        raise EvaporationCalculationError(
            "Опорное давление должно быть больше нуля"
        )
    molar_evaporation_heat = evaporation_heat_j_kg * molar_mass_kg_mol
    exponent = -(
        molar_evaporation_heat / UNIVERSAL_GAS_CONSTANT
    ) * (1.0 / current_temperature_k - 1.0 / boiling_temperature_k)
    try:
        pressure = reference_pressure_pa * math.exp(exponent)
    except OverflowError as exc:
        raise EvaporationCalculationError(
            "Не удалось рассчитать давление насыщенного пара: переполнение"
        ) from exc
    if not math.isfinite(pressure) or pressure < 0:
        raise EvaporationCalculationError(
            "Получено недопустимое давление насыщенного пара"
        )
    return pressure


def evaporation_intensity_kg_m2_s(
    saturated_pressure_pa: float,
    molar_mass_kg_mol: float,
    coefficient: float = 1.0,
) -> float:
    if saturated_pressure_pa < 0:
        raise EvaporationCalculationError(
            "Давление насыщенного пара не может быть отрицательным"
        )
    if molar_mass_kg_mol <= 0 or coefficient <= 0:
        raise EvaporationCalculationError(
            "Молярная масса и коэффициент испарения должны быть больше нуля"
        )
    pressure_kpa = saturated_pressure_pa / 1000.0
    molar_mass_g_mol = molar_mass_kg_mol * 1000.0
    return 1e-6 * coefficient * pressure_kpa * math.sqrt(molar_mass_g_mol)


def evaporation_is_applicable(kind: int, spill_applicable: bool) -> bool:
    return spill_applicable and kind in EVAPORATING_KINDS


class EvaporationCalculationService:
    def calculate(
        self, project_directory: Path | str
    ) -> EvaporationCalculationResult:
        project = Path(project_directory)
        if not project.is_dir():
            raise EvaporationCalculationError(
                f"Папка проекта не найдена: {project}"
            )

        equipment = _objects_by_id(
            _read_json(
                project / "equipments.json",
                "Сначала импортируйте оборудование",
            ),
            "Оборудование",
        )
        substances = _objects_by_id(
            _read_json(
                project / "substances.json",
                "Сначала выберите вещества",
            ),
            "Вещества",
        )
        spill_data = _read_json(
            project / SPILL_FILE_NAME,
            "Сначала рассчитайте площадь пролива",
        )
        spills = (
            spill_data.get("results") if isinstance(spill_data, dict) else None
        )
        if not isinstance(spills, list) or not spills:
            raise EvaporationCalculationError(
                f"{SPILL_FILE_NAME} не содержит результатов"
            )
        try:
            config = CalculationConfigService().load(project)
        except CalculationConfigError as exc:
            raise EvaporationCalculationError(str(exc)) from exc
        coefficient = _number(
            config.get("evaporation_coefficient"),
            "evaporation_coefficient",
            positive=True,
        )

        results: list[dict[str, Any]] = []
        case_ids: set[int] = set()
        scenario_codes: set[str] = set()
        evaporation_count = 0
        for index, spill in enumerate(spills, start=1):
            if not isinstance(spill, dict):
                raise EvaporationCalculationError(
                    f"Результат пролива {index}: ожидается объект"
                )
            case_id = spill.get("id")
            scenario_code = str(spill.get("scenario_code", "")).strip()
            if (
                isinstance(case_id, bool)
                or not isinstance(case_id, int)
                or case_id <= 0
                or case_id in case_ids
            ):
                raise EvaporationCalculationError(
                    f"Результат пролива {index}: "
                    "недопустимый или повторяющийся id"
                )
            if not scenario_code or scenario_code in scenario_codes:
                raise EvaporationCalculationError(
                    f"Результат пролива {index}: "
                    "пустой или повторяющийся scenario_code"
                )
            case_ids.add(case_id)
            scenario_codes.add(scenario_code)

            equipment_id = spill.get("equipment_id")
            item = equipment.get(equipment_id)
            if item is None:
                raise EvaporationCalculationError(
                    f"Сценарий {scenario_code}: equipment_id={equipment_id} "
                    "отсутствует в equipments.json"
                )
            substance_id = item.get("substance_id")
            substance = substances.get(substance_id)
            if substance is None:
                raise EvaporationCalculationError(
                    f"Сценарий {scenario_code}: substance_id={substance_id} "
                    "отсутствует в substances.json"
                )
            equipment_type = item.get("equipment_type")
            kind = substance.get("kind")
            for actual, expected, label in (
                (spill.get("substance_id"), substance_id, "substance_id"),
                (spill.get("equipment_type"), equipment_type, "equipment_type"),
                (spill.get("kind"), kind, "kind"),
            ):
                if actual != expected:
                    raise EvaporationCalculationError(
                        f"Сценарий {scenario_code}: устаревшие данные ({label}). "
                        "Повторите предыдущие расчёты"
                    )
            if (
                isinstance(kind, bool)
                or not isinstance(kind, int)
                or kind not in range(10)
            ):
                raise EvaporationCalculationError(
                    f"Сценарий {scenario_code}: kind должен быть от 0 до 9"
                )
            spill_applicable = spill.get("spill_applicable")
            if not isinstance(spill_applicable, bool):
                raise EvaporationCalculationError(
                    f"Сценарий {scenario_code}: spill_applicable должен быть "
                    "логическим значением"
                )
            applicable = evaporation_is_applicable(kind, spill_applicable)

            pressure_pa = None
            intensity = None
            evaporation_rate = None
            evaporation_time = None
            calculated_mass = None
            evaporated_mass = None
            limited_by_release = None
            if applicable:
                spill_area = _number(
                    spill.get("spill_area_m2"),
                    f"Сценарий {scenario_code}: spill_area_m2",
                    positive=True,
                )
                released_mass = _number(
                    spill.get("ov_in_accident_t"),
                    f"Сценарий {scenario_code}: ov_in_accident_t",
                    positive=True,
                )
                evaporation_time = _number(
                    item.get("evaporation_time_s"),
                    f"Сценарий {scenario_code}: evaporation_time_s",
                    non_negative=True,
                )
                current_temperature = _number(
                    item.get("substance_temperature_c"),
                    f"Сценарий {scenario_code}: substance_temperature_c",
                )
                physical = substance.get("physical")
                if not isinstance(physical, dict):
                    raise EvaporationCalculationError(
                        f"Сценарий {scenario_code}: physical должен быть объектом"
                    )
                boiling_point = _number(
                    physical.get("boiling_point_C"),
                    f"Сценарий {scenario_code}: boiling_point_C",
                )
                evaporation_heat = _number(
                    physical.get("evaporation_heat_J_per_kg"),
                    f"Сценарий {scenario_code}: evaporation_heat_J_per_kg",
                    positive=True,
                )
                molar_mass = _number(
                    physical.get("molar_mass_kg_per_mol"),
                    f"Сценарий {scenario_code}: molar_mass_kg_per_mol",
                    positive=True,
                )
                pressure_pa = saturated_vapor_pressure_pa(
                    current_temperature,
                    boiling_point,
                    evaporation_heat,
                    molar_mass,
                )
                intensity = evaporation_intensity_kg_m2_s(
                    pressure_pa,
                    molar_mass,
                    coefficient,
                )
                evaporation_rate = intensity * spill_area
                calculated_mass = evaporation_rate * evaporation_time * KG_TO_T
                if not math.isfinite(calculated_mass):
                    raise EvaporationCalculationError(
                        f"Сценарий {scenario_code}: получена недопустимая "
                        "испарившаяся масса"
                    )
                evaporated_mass = min(calculated_mass, released_mass)
                limited_by_release = calculated_mass > released_mass
                status = "calculated"
                evaporation_count += 1
            elif not spill_applicable:
                status = "no_spill"
            else:
                status = "method_not_applicable"

            result = dict(spill)
            result.update(
                {
                    "evaporation_applicable": applicable,
                    "evaporation_status": status,
                    "evaporation_status_name": STATUS_NAMES[status],
                    "evaporation_coefficient": coefficient,
                    "reference_pressure_pa": REFERENCE_PRESSURE_PA,
                    "saturated_vapor_pressure_pa": pressure_pa,
                    "saturated_vapor_pressure_kpa": (
                        None if pressure_pa is None else pressure_pa / 1000.0
                    ),
                    "evaporation_intensity_kg_m2_s": intensity,
                    "evaporation_rate_kg_s": evaporation_rate,
                    "evaporation_time_s": evaporation_time,
                    "calculated_evaporated_mass_t": calculated_mass,
                    "evaporated_mass_t": evaporated_mass,
                    "limited_by_release_mass": limited_by_release,
                    "evaporation_formula": (
                        "min(evaporation_intensity_kg_m2_s × spill_area_m2 "
                        "× evaporation_time_s / 1000, ov_in_accident_t)"
                        if applicable
                        else "не применяется"
                    ),
                }
            )
            results.append(result)

        result_data = {
            "format_version": 1,
            "case_count": len(results),
            "evaporation_count": evaporation_count,
            "constants": {
                "reference_pressure_pa": REFERENCE_PRESSURE_PA,
                "universal_gas_constant": UNIVERSAL_GAS_CONSTANT,
                "evaporation_coefficient": coefficient,
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
            raise EvaporationCalculationError(
                f"Не удалось сохранить {path}"
            ) from exc

        return EvaporationCalculationResult(
            path=path,
            case_count=len(results),
            evaporation_count=evaporation_count,
            results=tuple(results),
        )
