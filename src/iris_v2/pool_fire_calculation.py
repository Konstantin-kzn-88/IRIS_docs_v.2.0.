import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris_v2.calculation_config import (
    CalculationConfigError,
    CalculationConfigService,
)
from iris_v2.hazard_factor_calculation import FILE_NAME as HAZARD_FACTOR_FILE_NAME


FILE_NAME = "pool_fire_results.json"
POOL_FIRE_CALC_CODE = 1
THERMAL_LEVELS_KW_M2 = (10.5, 7.0, 4.2, 1.4)
SURFACE_EMISSIVE_POWER_KW_M2 = 25.0
ATMOSPHERIC_ATTENUATION_M_INV = 7e-4
AIR_DENSITY_KG_M3 = 1.15
GRAVITY_M_S2 = 9.81
U_STAR_GRAVITY_M_S2 = 9.8


class PoolFireCalculationError(Exception):
    pass


@dataclass(frozen=True)
class PoolFireCalculationResult:
    path: Path
    case_count: int
    pool_fire_count: int
    results: tuple[dict[str, Any], ...]


def _number(
    value: Any,
    label: str,
    *,
    positive: bool = False,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise PoolFireCalculationError(f"{label} должно быть числом")
    result = float(value)
    if positive and result <= 0:
        raise PoolFireCalculationError(f"{label} должно быть больше нуля")
    return result


def thermal_radiation_kw_m2(
    spill_area_m2: float,
    burning_rate_kg_m2_s: float,
    molar_mass_kg_mol: float,
    boiling_point_c: float,
    wind_speed_m_s: float,
    radius_m: float,
) -> float:
    """Thermal radiation from the old Strait_fire model in explicit SI units."""
    for value, label in (
        (spill_area_m2, "Площадь пролива"),
        (burning_rate_kg_m2_s, "Скорость выгорания"),
        (molar_mass_kg_mol, "Молярная масса"),
        (wind_speed_m_s, "Скорость ветра"),
        (radius_m, "Расстояние"),
    ):
        if not math.isfinite(value) or value <= 0:
            raise PoolFireCalculationError(f"{label} должно быть больше нуля")

    effective_diameter = math.sqrt(4.0 * spill_area_m2 / math.pi)
    pool_edge = effective_diameter / 2.0 + 0.1
    radius = max(radius_m, pool_edge)

    molar_mass_kg_kmol = molar_mass_kg_mol * 1000.0
    vapor_density_denominator = 22.413 * (1.0 + 0.00367 * boiling_point_c)
    if vapor_density_denominator <= 0:
        raise PoolFireCalculationError(
            "Температура кипения даёт недопустимую плотность пара"
        )
    vapor_density = molar_mass_kg_kmol / vapor_density_denominator
    if not math.isfinite(vapor_density) or vapor_density <= 0:
        raise PoolFireCalculationError("Получена недопустимая плотность пара")

    u_star = wind_speed_m_s / (
        burning_rate_kg_m2_s
        * U_STAR_GRAVITY_M_S2
        * effective_diameter
        / vapor_density
    ) ** (1.0 / 3.0)
    if u_star >= 1.0:
        flame_length = (
            55.0
            * effective_diameter
            * (
                burning_rate_kg_m2_s
                / (AIR_DENSITY_KG_M3 * math.sqrt(GRAVITY_M_S2 * effective_diameter))
            )
            ** 0.67
            * u_star**0.21
        )
        cosine = u_star**-0.5
    else:
        flame_length = (
            42.0
            * effective_diameter
            * (
                burning_rate_kg_m2_s
                / (AIR_DENSITY_KG_M3 * math.sqrt(GRAVITY_M_S2 * effective_diameter))
            )
            ** 0.61
        )
        cosine = 1.0

    theta = math.acos(min(1.0, max(-1.0, cosine)))
    a = 2.0 * flame_length / effective_diameter
    b = 2.0 * radius / effective_diameter
    big_a = math.sqrt(a * a + (b + 1.0) ** 2 - 2.0 * a * (b + 1.0) * math.sin(theta))
    big_b = math.sqrt(a * a + (b - 1.0) ** 2 - 2.0 * a * (b - 1.0) * math.sin(theta))
    c = math.sqrt(1.0 + (b * b - 1.0) * math.cos(theta) ** 2)
    d = math.sqrt((b - 1.0) / (b + 1.0))
    e = a * math.cos(theta) / (b - a * math.sin(theta))
    f = math.sqrt(b * b - 1.0)

    common_angle = math.atan(
        (a * b - f * f * math.sin(theta)) / (f * c)
    ) + math.atan(f * f * math.sin(theta) / (f * c))
    vertical = (1.0 / math.pi) * (
        -e * math.atan(d)
        + e
        * (
            a * a
            + (b + 1.0) ** 2
            - 2.0 * b * (1.0 + a * math.sin(theta))
        )
        / (big_a * big_b)
        * math.atan(big_a * d / big_b)
        + math.cos(theta) / c * common_angle
    )
    horizontal = (1.0 / math.pi) * (
        math.atan(1.0 / d)
        + math.sin(theta) / c * common_angle
        - (
            a * a
            + (b + 1.0) ** 2
            - 2.0 * (b + 1.0 + a * b * math.sin(theta))
        )
        / (big_a * big_b)
        * math.atan(big_a * d / big_b)
    )
    view_factor = math.sqrt(vertical**2 + horizontal**2)
    transmissivity = math.exp(
        -ATMOSPHERIC_ATTENUATION_M_INV
        * (radius - 0.5 * effective_diameter)
    )
    radiation = view_factor * transmissivity * SURFACE_EMISSIVE_POWER_KW_M2
    if not math.isfinite(radiation) or radiation < 0:
        raise PoolFireCalculationError(
            "Получена недопустимая интенсивность теплового излучения"
        )
    return radiation


def thermal_zone_radius_m(
    spill_area_m2: float,
    burning_rate_kg_m2_s: float,
    molar_mass_kg_mol: float,
    boiling_point_c: float,
    wind_speed_m_s: float,
    target_kw_m2: float,
) -> float:
    if target_kw_m2 <= 0:
        raise PoolFireCalculationError(
            "Порог теплового излучения должен быть больше нуля"
        )
    effective_diameter = math.sqrt(4.0 * spill_area_m2 / math.pi)
    lower = effective_diameter / 2.0 + 0.1

    def radiation(radius: float) -> float:
        return thermal_radiation_kw_m2(
            spill_area_m2,
            burning_rate_kg_m2_s,
            molar_mass_kg_mol,
            boiling_point_c,
            wind_speed_m_s,
            radius,
        )

    if radiation(lower) <= target_kw_m2:
        return round(lower, 1)
    upper = max(lower + 1.0, lower * 2.0)
    for _ in range(60):
        if radiation(upper) <= target_kw_m2:
            break
        upper *= 2.0
    else:
        raise PoolFireCalculationError(
            "Не удалось определить границу зоны теплового излучения"
        )
    for _ in range(60):
        middle = (lower + upper) / 2.0
        if radiation(middle) > target_kw_m2:
            lower = middle
        else:
            upper = middle
    return round(upper, 1)


def calculate_pool_fire_zones(
    spill_area_m2: float,
    burning_rate_kg_m2_s: float,
    molar_mass_kg_mol: float,
    boiling_point_c: float,
    wind_speed_m_s: float,
) -> dict[str, float]:
    radii = [
        thermal_zone_radius_m(
            spill_area_m2,
            burning_rate_kg_m2_s,
            molar_mass_kg_mol,
            boiling_point_c,
            wind_speed_m_s,
            level,
        )
        for level in THERMAL_LEVELS_KW_M2
    ]
    return dict(zip(("q_10_5_m", "q_7_0_m", "q_4_2_m", "q_1_4_m"), radii))


class PoolFireCalculationService:
    def calculate(
        self, project_directory: Path | str
    ) -> PoolFireCalculationResult:
        project = Path(project_directory)
        if not project.is_dir():
            raise PoolFireCalculationError(f"Папка проекта не найдена: {project}")

        hazard_path = project / HAZARD_FACTOR_FILE_NAME
        substances_path = project / "substances.json"
        if not hazard_path.is_file():
            raise PoolFireCalculationError(
                f"Файл не найден: {HAZARD_FACTOR_FILE_NAME}. "
                "Сначала рассчитайте массу поражающего фактора"
            )
        if not substances_path.is_file():
            raise PoolFireCalculationError("Файл не найден: substances.json")
        try:
            hazard_data = json.loads(hazard_path.read_text(encoding="utf-8"))
            substances_data = json.loads(substances_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PoolFireCalculationError("Не удалось прочитать исходные JSON") from exc

        values = hazard_data.get("results") if isinstance(hazard_data, dict) else None
        if not isinstance(values, list) or not values:
            raise PoolFireCalculationError(
                f"{HAZARD_FACTOR_FILE_NAME} не содержит результатов"
            )
        if not isinstance(substances_data, list) or not substances_data:
            raise PoolFireCalculationError("substances.json должен быть непустым списком")
        substances: dict[int, dict[str, Any]] = {}
        for index, substance in enumerate(substances_data, start=1):
            if not isinstance(substance, dict):
                raise PoolFireCalculationError(
                    f"Вещество {index}: ожидается объект"
                )
            substance_id = substance.get("id")
            if (
                isinstance(substance_id, bool)
                or not isinstance(substance_id, int)
                or substance_id <= 0
                or substance_id in substances
            ):
                raise PoolFireCalculationError(
                    f"Вещество {index}: недопустимый или повторяющийся id"
                )
            substances[substance_id] = substance

        try:
            config = CalculationConfigService().load(project)
        except CalculationConfigError as exc:
            raise PoolFireCalculationError(str(exc)) from exc
        wind_speed = _number(
            config.get("wind_speed_m_s"),
            "wind_speed_m_s",
            positive=True,
        )

        results: list[dict[str, Any]] = []
        case_ids: set[int] = set()
        scenario_codes: set[str] = set()
        pool_fire_count = 0
        for index, value in enumerate(values, start=1):
            if not isinstance(value, dict):
                raise PoolFireCalculationError(
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
                raise PoolFireCalculationError(
                    f"Результат {index}: недопустимый или повторяющийся id"
                )
            if not scenario_code or scenario_code in scenario_codes:
                raise PoolFireCalculationError(
                    f"Результат {index}: пустой или повторяющийся scenario_code"
                )
            case_ids.add(case_id)
            scenario_codes.add(scenario_code)

            substance_id = value.get("substance_id")
            substance = substances.get(substance_id)
            if substance is None:
                raise PoolFireCalculationError(
                    f"Сценарий {scenario_code}: substance_id={substance_id} "
                    "отсутствует в substances.json"
                )
            if value.get("kind") != substance.get("kind"):
                raise PoolFireCalculationError(
                    f"Сценарий {scenario_code}: устаревшие данные вещества"
                )
            calc_code = value.get("calc_code")
            if isinstance(calc_code, bool) or not isinstance(calc_code, int):
                raise PoolFireCalculationError(
                    f"Сценарий {scenario_code}: неверный calc_code"
                )

            applicable = calc_code == POOL_FIRE_CALC_CODE
            if applicable:
                spill_area = _number(
                    value.get("spill_area_m2"),
                    f"Сценарий {scenario_code}: spill_area_m2",
                    positive=True,
                )
                physical = substance.get("physical")
                explosion = substance.get("explosion")
                if not isinstance(physical, dict) or not isinstance(explosion, dict):
                    raise PoolFireCalculationError(
                        f"Сценарий {scenario_code}: свойства вещества повреждены"
                    )
                molar_mass = _number(
                    physical.get("molar_mass_kg_per_mol"),
                    f"Сценарий {scenario_code}: molar_mass_kg_per_mol",
                    positive=True,
                )
                boiling_point = _number(
                    physical.get("boiling_point_C"),
                    f"Сценарий {scenario_code}: boiling_point_C",
                )
                burning_rate = _number(
                    explosion.get("burning_rate_kg_per_s_m2"),
                    f"Сценарий {scenario_code}: burning_rate_kg_per_s_m2",
                    positive=True,
                )
                zones = calculate_pool_fire_zones(
                    spill_area,
                    burning_rate,
                    molar_mass,
                    boiling_point,
                    wind_speed,
                )
                pool_fire_count += 1
                status = "calculated"
            else:
                spill_area = value.get("spill_area_m2")
                molar_mass = None
                boiling_point = None
                burning_rate = None
                zones = {
                    "q_10_5_m": None,
                    "q_7_0_m": None,
                    "q_4_2_m": None,
                    "q_1_4_m": None,
                }
                status = "not_applicable"

            result = dict(value)
            result.update(
                {
                    "pool_fire_applicable": applicable,
                    "pool_fire_status": status,
                    "pool_fire_status_name": (
                        "Зоны рассчитаны"
                        if applicable
                        else "Сценарий не является пожаром пролива"
                    ),
                    "pool_fire_spill_area_m2": spill_area,
                    "pool_fire_burning_rate_kg_m2_s": burning_rate,
                    "pool_fire_molar_mass_kg_mol": molar_mass,
                    "pool_fire_boiling_point_c": boiling_point,
                    "pool_fire_wind_speed_m_s": wind_speed,
                    "pool_fire_formula": (
                        "Приказ МЧС России от 10.07.2009 № 404"
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
            "pool_fire_count": pool_fire_count,
            "constants": {
                "thermal_levels_kw_m2": list(THERMAL_LEVELS_KW_M2),
                "surface_emissive_power_kw_m2": SURFACE_EMISSIVE_POWER_KW_M2,
                "atmospheric_attenuation_m_inv": ATMOSPHERIC_ATTENUATION_M_INV,
                "air_density_kg_m3": AIR_DENSITY_KG_M3,
                "gravity_m_s2": GRAVITY_M_S2,
                "u_star_gravity_m_s2": U_STAR_GRAVITY_M_S2,
                "wind_speed_m_s": wind_speed,
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
            raise PoolFireCalculationError(f"Не удалось сохранить {path}") from exc

        return PoolFireCalculationResult(
            path=path,
            case_count=len(results),
            pool_fire_count=pool_fire_count,
            results=tuple(results),
        )
