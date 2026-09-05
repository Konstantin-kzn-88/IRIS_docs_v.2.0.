import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris_v2.hazard_factor_calculation import FILE_NAME as HAZARD_FACTOR_FILE_NAME


FILE_NAME = "explosion_results.json"
EXPLOSION_CALC_CODE = 2
PRESSURE_LEVELS_KPA = (70.0, 28.0, 14.0, 5.0, 2.0)
ATMOSPHERIC_PRESSURE_KPA = 101.3
ATMOSPHERIC_PRESSURE_PA = 101_325.0
SOUND_SPEED_M_S = 340.0
ENERGY_SCALE_PRESSURE_PA = 101_300.0
MINIMUM_SCALED_DISTANCE = 0.34


class ExplosionCalculationError(Exception):
    pass


@dataclass(frozen=True)
class ExplosionCalculationResult:
    path: Path
    case_count: int
    explosion_count: int
    results: tuple[dict[str, Any], ...]


def _number(value: Any, label: str, *, positive: bool = False) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ExplosionCalculationError(f"{label} должно быть числом")
    result = float(value)
    if positive and result <= 0:
        raise ExplosionCalculationError(f"{label} должно быть больше нуля")
    return result


def flame_speed_m_s(
    explosion_hazard_class: int,
    clutter_degree: int,
    cloud_mass_kg: float,
) -> float:
    if explosion_hazard_class not in range(1, 5):
        raise ExplosionCalculationError(
            "Класс взрывоопасности должен быть от 1 до 4"
        )
    if clutter_degree not in range(1, 5):
        raise ExplosionCalculationError(
            "Степень загромождённости должна быть от 1 до 4"
        )
    if not math.isfinite(cloud_mass_kg) or cloud_mass_kg <= 0:
        raise ExplosionCalculationError("Масса облака должна быть больше нуля")

    mass_factor = cloud_mass_kg ** (1.0 / 6.0)
    values = (
        (500.0, 500.0, 300.0, 200.0),
        (500.0, 300.0, 200.0, 150.0),
        (300.0, 200.0, 150.0, 43.0 * mass_factor),
        (200.0, 150.0, 43.0 * mass_factor, 26.0 * mass_factor),
    )
    return values[explosion_hazard_class - 1][clutter_degree - 1]


def explosion_pressure_impulse(
    explosion_hazard_class: int,
    clutter_degree: int,
    cloud_mass_kg: float,
    heat_of_combustion_kj_kg: float,
    expansion_degree: float,
    energy_reserve_factor: float,
    radius_m: float,
) -> tuple[float, float]:
    for value, label in (
        (heat_of_combustion_kj_kg, "Теплота сгорания"),
        (energy_reserve_factor, "Коэффициент запаса энергии"),
        (radius_m, "Расстояние"),
    ):
        if not math.isfinite(value) or value <= 0:
            raise ExplosionCalculationError(f"{label} должно быть больше нуля")
    if not math.isfinite(expansion_degree) or expansion_degree <= 1:
        raise ExplosionCalculationError(
            "Степень расширения должна быть больше единицы"
        )

    speed = flame_speed_m_s(
        explosion_hazard_class,
        clutter_degree,
        cloud_mass_kg,
    )
    energy_j = (
        cloud_mass_kg
        * heat_of_combustion_kj_kg
        * energy_reserve_factor
        * 1000.0
    )
    scaled_distance = radius_m / (
        energy_j / ENERGY_SCALE_PRESSURE_PA
    ) ** (1.0 / 3.0)
    scaled_distance = max(scaled_distance, MINIMUM_SCALED_DISTANCE)
    mixture_factor = (expansion_degree - 1.0) / expansion_degree
    speed_factor = speed / SOUND_SPEED_M_S

    pressure_kpa = (
        speed_factor**2
        * mixture_factor
        * (
            0.83 / scaled_distance
            - 0.14 / scaled_distance**2
        )
        * ATMOSPHERIC_PRESSURE_KPA
    )
    impulse_pa_s = (
        speed_factor
        * mixture_factor
        * (1.0 - 0.4 * speed_factor * mixture_factor)
        * (
            0.06 / scaled_distance
            + 0.01 / scaled_distance**2
            - 0.0025 / scaled_distance**3
        )
        * ATMOSPHERIC_PRESSURE_PA ** (2.0 / 3.0)
        * energy_j ** (1.0 / 3.0)
        / SOUND_SPEED_M_S
    )
    if (
        not math.isfinite(pressure_kpa)
        or not math.isfinite(impulse_pa_s)
        or pressure_kpa < 0
        or impulse_pa_s < 0
    ):
        raise ExplosionCalculationError(
            "Получены недопустимые параметры воздушной ударной волны"
        )
    return pressure_kpa, impulse_pa_s


def explosion_zone_radius_m(
    explosion_hazard_class: int,
    clutter_degree: int,
    cloud_mass_kg: float,
    heat_of_combustion_kj_kg: float,
    expansion_degree: float,
    energy_reserve_factor: float,
    target_pressure_kpa: float,
) -> float:
    if target_pressure_kpa <= 0:
        raise ExplosionCalculationError(
            "Порог избыточного давления должен быть больше нуля"
        )

    def pressure(radius: float) -> float:
        return explosion_pressure_impulse(
            explosion_hazard_class,
            clutter_degree,
            cloud_mass_kg,
            heat_of_combustion_kj_kg,
            expansion_degree,
            energy_reserve_factor,
            radius,
        )[0]

    if pressure(1e-9) < target_pressure_kpa:
        return 0.0
    lower = 1e-9
    upper = 1.0
    for _ in range(80):
        if pressure(upper) <= target_pressure_kpa:
            break
        upper *= 2.0
    else:
        raise ExplosionCalculationError(
            "Не удалось определить границу зоны избыточного давления"
        )
    for _ in range(60):
        middle = (lower + upper) / 2.0
        if pressure(middle) > target_pressure_kpa:
            lower = middle
        else:
            upper = middle
    return round(upper, 1)


def calculate_explosion_zones(
    explosion_hazard_class: int,
    clutter_degree: int,
    cloud_mass_kg: float,
    heat_of_combustion_kj_kg: float,
    expansion_degree: float,
    energy_reserve_factor: float,
) -> dict[str, float]:
    radii = [
        explosion_zone_radius_m(
            explosion_hazard_class,
            clutter_degree,
            cloud_mass_kg,
            heat_of_combustion_kj_kg,
            expansion_degree,
            energy_reserve_factor,
            level,
        )
        for level in PRESSURE_LEVELS_KPA
    ]
    return dict(
        zip(
            ("p_70_m", "p_28_m", "p_14_m", "p_5_m", "p_2_m"),
            radii,
        )
    )


class ExplosionCalculationService:
    def calculate(
        self, project_directory: Path | str
    ) -> ExplosionCalculationResult:
        project = Path(project_directory)
        if not project.is_dir():
            raise ExplosionCalculationError(
                f"Папка проекта не найдена: {project}"
            )

        hazard_path = project / HAZARD_FACTOR_FILE_NAME
        equipment_path = project / "equipments.json"
        substances_path = project / "substances.json"
        for path, hint in (
            (
                hazard_path,
                "Сначала рассчитайте массу поражающего фактора",
            ),
            (equipment_path, "Сначала импортируйте оборудование"),
            (substances_path, "Сначала выберите вещества"),
        ):
            if not path.is_file():
                raise ExplosionCalculationError(
                    f"Файл не найден: {path.name}. {hint}"
                )
        try:
            hazard_data = json.loads(hazard_path.read_text(encoding="utf-8"))
            equipment_data = json.loads(equipment_path.read_text(encoding="utf-8"))
            substances_data = json.loads(substances_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ExplosionCalculationError(
                "Не удалось прочитать исходные JSON"
            ) from exc

        values = (
            hazard_data.get("results")
            if isinstance(hazard_data, dict)
            else None
        )
        if not isinstance(values, list) or not values:
            raise ExplosionCalculationError(
                f"{HAZARD_FACTOR_FILE_NAME} не содержит результатов"
            )

        equipment = self._objects_by_id(equipment_data, "Оборудование")
        substances = self._objects_by_id(substances_data, "Вещества")
        results: list[dict[str, Any]] = []
        case_ids: set[int] = set()
        scenario_codes: set[str] = set()
        explosion_count = 0
        for index, value in enumerate(values, start=1):
            if not isinstance(value, dict):
                raise ExplosionCalculationError(
                    f"Результат поражающего фактора {index}: ожидается объект"
                )
            case_id = value.get("id")
            scenario_code = str(value.get("scenario_code", "")).strip()
            if (
                isinstance(case_id, bool)
                or not isinstance(case_id, int)
                or case_id <= 0
                or case_id in case_ids
            ):
                raise ExplosionCalculationError(
                    f"Результат {index}: недопустимый или повторяющийся id"
                )
            if not scenario_code or scenario_code in scenario_codes:
                raise ExplosionCalculationError(
                    f"Результат {index}: пустой или повторяющийся scenario_code"
                )
            case_ids.add(case_id)
            scenario_codes.add(scenario_code)

            equipment_id = value.get("equipment_id")
            substance_id = value.get("substance_id")
            item = equipment.get(equipment_id)
            substance = substances.get(substance_id)
            if item is None:
                raise ExplosionCalculationError(
                    f"Сценарий {scenario_code}: equipment_id={equipment_id} "
                    "отсутствует в equipments.json"
                )
            if substance is None:
                raise ExplosionCalculationError(
                    f"Сценарий {scenario_code}: substance_id={substance_id} "
                    "отсутствует в substances.json"
                )
            for actual, expected, label in (
                (item.get("substance_id"), substance_id, "substance_id оборудования"),
                (value.get("kind"), substance.get("kind"), "kind"),
                (value.get("equipment_type"), item.get("equipment_type"), "equipment_type"),
            ):
                if actual != expected:
                    raise ExplosionCalculationError(
                        f"Сценарий {scenario_code}: устаревшие данные ({label})"
                    )

            calc_code = value.get("calc_code")
            if isinstance(calc_code, bool) or not isinstance(calc_code, int):
                raise ExplosionCalculationError(
                    f"Сценарий {scenario_code}: неверный calc_code"
                )
            applicable = calc_code == EXPLOSION_CALC_CODE
            if applicable:
                mass_t = _number(
                    value.get("ov_in_hazard_factor_t"),
                    f"Сценарий {scenario_code}: ov_in_hazard_factor_t",
                    positive=True,
                )
                explosion = substance.get("explosion")
                if not isinstance(explosion, dict):
                    raise ExplosionCalculationError(
                        f"Сценарий {scenario_code}: explosion должен быть объектом"
                    )
                hazard_class = self._integer_in_range(
                    explosion.get("explosion_hazard_class"),
                    f"Сценарий {scenario_code}: explosion_hazard_class",
                    1,
                    4,
                )
                clutter = self._integer_in_range(
                    item.get("clutter_degree"),
                    f"Сценарий {scenario_code}: clutter_degree",
                    1,
                    4,
                )
                heat = _number(
                    explosion.get("heat_of_combustion_kJ_per_kg"),
                    f"Сценарий {scenario_code}: heat_of_combustion_kJ_per_kg",
                    positive=True,
                )
                expansion = _number(
                    explosion.get("expansion_degree"),
                    f"Сценарий {scenario_code}: expansion_degree",
                    positive=True,
                )
                if expansion <= 1:
                    raise ExplosionCalculationError(
                        f"Сценарий {scenario_code}: expansion_degree должен "
                        "быть больше 1"
                    )
                energy_factor = _number(
                    explosion.get("energy_reserve_factor"),
                    f"Сценарий {scenario_code}: energy_reserve_factor",
                    positive=True,
                )
                mass_kg = mass_t * 1000.0
                speed = flame_speed_m_s(hazard_class, clutter, mass_kg)
                zones = calculate_explosion_zones(
                    hazard_class,
                    clutter,
                    mass_kg,
                    heat,
                    expansion,
                    energy_factor,
                )
                peak_pressure, peak_impulse = explosion_pressure_impulse(
                    hazard_class,
                    clutter,
                    mass_kg,
                    heat,
                    expansion,
                    energy_factor,
                    1e-9,
                )
                explosion_count += 1
                status = "calculated"
            else:
                mass_t = value.get("ov_in_hazard_factor_t")
                mass_kg = None
                hazard_class = None
                clutter = None
                heat = None
                expansion = None
                energy_factor = None
                speed = None
                peak_pressure = None
                peak_impulse = None
                zones = {
                    "p_70_m": None,
                    "p_28_m": None,
                    "p_14_m": None,
                    "p_5_m": None,
                    "p_2_m": None,
                }
                status = "not_applicable"

            result = dict(value)
            result.update(
                {
                    "explosion_applicable": applicable,
                    "explosion_status": status,
                    "explosion_status_name": (
                        "Зоны рассчитаны"
                        if applicable
                        else "Сценарий не является взрывом облака"
                    ),
                    "explosion_mass_t": mass_t,
                    "explosion_mass_kg": mass_kg,
                    "explosion_hazard_class": hazard_class,
                    "explosion_clutter_degree": clutter,
                    "explosion_heat_of_combustion_kj_kg": heat,
                    "explosion_expansion_degree": expansion,
                    "explosion_energy_reserve_factor": energy_factor,
                    "explosion_flame_speed_m_s": speed,
                    "explosion_peak_pressure_kpa": peak_pressure,
                    "explosion_peak_impulse_pa_s": peak_impulse,
                    "explosion_formula": (
                        "СП 12.13130.2009"
                        if applicable
                        else "не применяется"
                    ),
                    **zones,
                }
            )
            results.append(result)

        result_data = {
            "format_version": 1,
            "case_count": len(results),
            "explosion_count": explosion_count,
            "pressure_levels_kpa": list(PRESSURE_LEVELS_KPA),
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
            raise ExplosionCalculationError(
                f"Не удалось сохранить {path}"
            ) from exc

        return ExplosionCalculationResult(
            path=path,
            case_count=len(results),
            explosion_count=explosion_count,
            results=tuple(results),
        )

    @staticmethod
    def _objects_by_id(values: Any, label: str) -> dict[int, dict[str, Any]]:
        if not isinstance(values, list) or not values:
            raise ExplosionCalculationError(
                f"{label} должен быть непустым списком"
            )
        result: dict[int, dict[str, Any]] = {}
        for index, value in enumerate(values, start=1):
            if not isinstance(value, dict):
                raise ExplosionCalculationError(
                    f"{label}, запись {index}: ожидается объект"
                )
            object_id = value.get("id")
            if (
                isinstance(object_id, bool)
                or not isinstance(object_id, int)
                or object_id <= 0
                or object_id in result
            ):
                raise ExplosionCalculationError(
                    f"{label}, запись {index}: "
                    "недопустимый или повторяющийся id"
                )
            result[object_id] = value
        return result

    @staticmethod
    def _integer_in_range(
        value: Any,
        label: str,
        minimum: int,
        maximum: int,
    ) -> int:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value not in range(minimum, maximum + 1)
        ):
            raise ExplosionCalculationError(
                f"{label} должен быть от {minimum} до {maximum}"
            )
        return value
