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


FILE_NAME = "fireball_results.json"
FIREBALL_CALC_CODE = 6
THERMAL_DOSE_LEVELS_KJ_M2 = (600.0, 320.0, 220.0, 120.0)
ATMOSPHERIC_ATTENUATION_M_INV = 7e-4


class FireballCalculationError(Exception):
    pass


@dataclass(frozen=True)
class FireballCalculationResult:
    path: Path
    case_count: int
    fireball_count: int
    results: tuple[dict[str, Any], ...]


def _positive_number(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0
    ):
        raise FireballCalculationError(f"{label} должно быть больше нуля")
    return float(value)


def fireball_parameters(cloud_mass_kg: float) -> dict[str, float]:
    mass = _positive_number(cloud_mass_kg, "Масса огненного шара")
    diameter = 5.33 * mass**0.327
    return {
        "fireball_effective_diameter_m": diameter,
        "fireball_center_height_m": diameter / 2.0,
        "fireball_duration_s": 0.92 * mass**0.303,
    }


def fireball_radiation(
    cloud_mass_kg: float,
    surface_emissive_power_kw_m2: float,
    radius_m: float,
) -> tuple[float, float]:
    emissive_power = _positive_number(
        surface_emissive_power_kw_m2,
        "Плотность теплового излучения",
    )
    if (
        isinstance(radius_m, bool)
        or not isinstance(radius_m, (int, float))
        or not math.isfinite(float(radius_m))
        or radius_m < 0
    ):
        raise FireballCalculationError("Расстояние не может быть отрицательным")

    parameters = fireball_parameters(cloud_mass_kg)
    diameter = parameters["fireball_effective_diameter_m"]
    height = parameters["fireball_center_height_m"]
    duration = parameters["fireball_duration_s"]
    radius = float(radius_m)
    view_factor = (height / diameter + 0.5) / (
        4.0
        * (
            (height / diameter + 0.5) ** 2
            + (radius / diameter) ** 2
        )
        ** 1.5
    )
    transmissivity = math.exp(
        -ATMOSPHERIC_ATTENUATION_M_INV
        * (math.sqrt(radius**2 + height**2) - diameter / 2.0)
    )
    radiation = emissive_power * view_factor * transmissivity
    dose = radiation * duration
    if (
        not math.isfinite(radiation)
        or not math.isfinite(dose)
        or radiation < 0
        or dose < 0
    ):
        raise FireballCalculationError(
            "Получены недопустимые параметры теплового излучения"
        )
    return radiation, dose


def fireball_zone_radius_m(
    cloud_mass_kg: float,
    surface_emissive_power_kw_m2: float,
    target_dose_kj_m2: float,
) -> float:
    target = _positive_number(target_dose_kj_m2, "Тепловая доза")

    def dose(radius: float) -> float:
        return fireball_radiation(
            cloud_mass_kg,
            surface_emissive_power_kw_m2,
            radius,
        )[1]

    if dose(0.0) < target:
        return 0.0
    lower = 0.0
    upper = max(1.0, fireball_parameters(cloud_mass_kg)[
        "fireball_effective_diameter_m"
    ])
    for _ in range(60):
        if dose(upper) <= target:
            break
        upper *= 2.0
    else:
        raise FireballCalculationError(
            "Не удалось определить границу зоны тепловой дозы"
        )
    for _ in range(60):
        middle = (lower + upper) / 2.0
        if dose(middle) > target:
            lower = middle
        else:
            upper = middle
    return round(upper, 1)


def calculate_fireball_zones(
    cloud_mass_kg: float,
    surface_emissive_power_kw_m2: float,
) -> dict[str, float]:
    radii = [
        fireball_zone_radius_m(
            cloud_mass_kg,
            surface_emissive_power_kw_m2,
            dose,
        )
        for dose in THERMAL_DOSE_LEVELS_KJ_M2
    ]
    return dict(
        zip(
            ("dose_600_m", "dose_320_m", "dose_220_m", "dose_120_m"),
            radii,
        )
    )


class FireballCalculationService:
    def calculate(
        self, project_directory: Path | str
    ) -> FireballCalculationResult:
        project = Path(project_directory)
        if not project.is_dir():
            raise FireballCalculationError(
                f"Папка проекта не найдена: {project}"
            )
        source_path = project / HAZARD_FACTOR_FILE_NAME
        if not source_path.is_file():
            raise FireballCalculationError(
                f"Файл не найден: {source_path.name}. "
                "Сначала рассчитайте массу поражающего фактора"
            )
        try:
            source_data = json.loads(source_path.read_text(encoding="utf-8"))
            config = CalculationConfigService().load(project)
        except (OSError, json.JSONDecodeError, CalculationConfigError) as exc:
            raise FireballCalculationError(
                "Не удалось прочитать исходные данные огненного шара"
            ) from exc

        emissive_power = _positive_number(
            config.get("fireball_surface_emissive_power_kw_m2"),
            "Плотность теплового излучения огненного шара",
        )
        values = (
            source_data.get("results")
            if isinstance(source_data, dict)
            else None
        )
        if not isinstance(values, list) or not values:
            raise FireballCalculationError(
                f"{HAZARD_FACTOR_FILE_NAME} не содержит результатов"
            )

        results: list[dict[str, Any]] = []
        case_ids: set[int] = set()
        scenario_codes: set[str] = set()
        fireball_count = 0
        for index, value in enumerate(values, start=1):
            if not isinstance(value, dict):
                raise FireballCalculationError(
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
                raise FireballCalculationError(
                    f"Результат {index}: недопустимый или повторяющийся id"
                )
            if not scenario_code or scenario_code in scenario_codes:
                raise FireballCalculationError(
                    f"Результат {index}: пустой или повторяющийся scenario_code"
                )
            case_ids.add(case_id)
            scenario_codes.add(scenario_code)

            calc_code = value.get("calc_code")
            if isinstance(calc_code, bool) or not isinstance(calc_code, int):
                raise FireballCalculationError(
                    f"Сценарий {scenario_code}: неверный calc_code"
                )
            applicable = calc_code == FIREBALL_CALC_CODE
            if applicable:
                mass_t = _positive_number(
                    value.get("ov_in_hazard_factor_t"),
                    f"Сценарий {scenario_code}: ov_in_hazard_factor_t",
                )
                mass_kg = mass_t * 1000.0
                parameters = fireball_parameters(mass_kg)
                zones = calculate_fireball_zones(mass_kg, emissive_power)
                peak_radiation, peak_dose = fireball_radiation(
                    mass_kg,
                    emissive_power,
                    0.0,
                )
                status = "calculated"
                fireball_count += 1
            else:
                mass_t = value.get("ov_in_hazard_factor_t")
                mass_kg = None
                parameters = {
                    "fireball_effective_diameter_m": None,
                    "fireball_center_height_m": None,
                    "fireball_duration_s": None,
                }
                zones = {
                    "dose_600_m": None,
                    "dose_320_m": None,
                    "dose_220_m": None,
                    "dose_120_m": None,
                }
                peak_radiation = None
                peak_dose = None
                status = "not_applicable"

            result = dict(value)
            result.update(
                {
                    "fireball_applicable": applicable,
                    "fireball_status": status,
                    "fireball_status_name": (
                        "Зоны рассчитаны"
                        if applicable
                        else "Сценарий не является огненным шаром"
                    ),
                    "fireball_mass_t": mass_t,
                    "fireball_mass_kg": mass_kg,
                    "fireball_surface_emissive_power_kw_m2": (
                        emissive_power if applicable else None
                    ),
                    "fireball_peak_radiation_kw_m2": peak_radiation,
                    "fireball_peak_dose_kj_m2": peak_dose,
                    "fireball_formula": (
                        "Приказ МЧС России от 10.07.2009 № 404"
                        if applicable
                        else "не применяется"
                    ),
                    **parameters,
                    **zones,
                }
            )
            results.append(result)

        result_data = {
            "format_version": 1,
            "case_count": len(results),
            "fireball_count": fireball_count,
            "thermal_dose_levels_kj_m2": list(THERMAL_DOSE_LEVELS_KJ_M2),
            "surface_emissive_power_kw_m2": emissive_power,
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
            raise FireballCalculationError(
                f"Не удалось сохранить {path}"
            ) from exc

        return FireballCalculationResult(
            path=path,
            case_count=len(results),
            fireball_count=fireball_count,
            results=tuple(results),
        )
