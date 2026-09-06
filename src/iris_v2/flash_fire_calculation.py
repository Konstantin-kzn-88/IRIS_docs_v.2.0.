import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris_v2.hazard_factor_calculation import FILE_NAME as HAZARD_FACTOR_FILE_NAME


FILE_NAME = "flash_fire_results.json"
FLASH_FIRE_CALC_CODE = 3
GAS_KINDS = {2, 3, 7}


class FlashFireCalculationError(Exception):
    pass


@dataclass(frozen=True)
class FlashFireCalculationResult:
    path: Path
    case_count: int
    flash_fire_count: int
    results: tuple[dict[str, Any], ...]


def _number(value: Any, label: str, *, positive: bool = False) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise FlashFireCalculationError(f"{label} должно быть числом")
    result = float(value)
    if positive and result <= 0:
        raise FlashFireCalculationError(f"{label} должно быть больше нуля")
    return result


def calculate_flash_fire_radii(
    cloud_mass_kg: float,
    molar_mass_kg_mol: float | None,
    boiling_point_c: float | None,
    lel_percent: float,
    gas_density_kg_m3: float | None = None,
) -> dict[str, float]:
    """Calculate LEL and flash-fire radii using the old LCLP model."""
    for value, label in (
        (cloud_mass_kg, "Масса облака"),
        (lel_percent, "НКПР"),
    ):
        if not math.isfinite(value) or value <= 0:
            raise FlashFireCalculationError(f"{label} должно быть больше нуля")
    if lel_percent > 100:
        raise FlashFireCalculationError("НКПР не может превышать 100 % об.")

    if gas_density_kg_m3 is not None:
        if (
            not math.isfinite(gas_density_kg_m3)
            or gas_density_kg_m3 <= 0
        ):
            raise FlashFireCalculationError(
                "Плотность газа должна быть больше нуля"
            )
        vapor_density = gas_density_kg_m3
    else:
        if (
            molar_mass_kg_mol is None
            or not math.isfinite(molar_mass_kg_mol)
            or molar_mass_kg_mol <= 0
        ):
            raise FlashFireCalculationError(
                "Молярная масса должна быть больше нуля"
            )
        if boiling_point_c is None or not math.isfinite(boiling_point_c):
            raise FlashFireCalculationError(
                "Температура кипения должна быть числом"
            )
        molar_mass_kg_kmol = molar_mass_kg_mol * 1000.0
        density_denominator = 22.413 * (1.0 + 0.00367 * boiling_point_c)
        if density_denominator <= 0:
            raise FlashFireCalculationError(
                "Температура кипения даёт недопустимую плотность пара"
            )
        vapor_density = molar_mass_kg_kmol / density_denominator
        if not math.isfinite(vapor_density) or vapor_density <= 0:
            raise FlashFireCalculationError(
                "Получена недопустимая плотность пара"
            )

    lel_radius = round(
        7.8 * (cloud_mass_kg / (vapor_density * lel_percent)) ** 0.33,
        2,
    )
    flash_fire_radius = round(lel_radius * 1.2, 2)
    return {
        "vapor_density_kg_m3": vapor_density,
        "lel_radius_m": lel_radius,
        "flash_fire_radius_m": flash_fire_radius,
    }


class FlashFireCalculationService:
    def calculate(
        self, project_directory: Path | str
    ) -> FlashFireCalculationResult:
        project = Path(project_directory)
        if not project.is_dir():
            raise FlashFireCalculationError(
                f"Папка проекта не найдена: {project}"
            )

        hazard_path = project / HAZARD_FACTOR_FILE_NAME
        substances_path = project / "substances.json"
        for path, hint in (
            (hazard_path, "Сначала рассчитайте массу поражающего фактора"),
            (substances_path, "Сначала выберите вещества"),
        ):
            if not path.is_file():
                raise FlashFireCalculationError(
                    f"Файл не найден: {path.name}. {hint}"
                )
        try:
            hazard_data = json.loads(hazard_path.read_text(encoding="utf-8"))
            substances_data = json.loads(
                substances_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise FlashFireCalculationError(
                "Не удалось прочитать исходные JSON"
            ) from exc

        values = (
            hazard_data.get("results")
            if isinstance(hazard_data, dict)
            else None
        )
        if not isinstance(values, list) or not values:
            raise FlashFireCalculationError(
                f"{HAZARD_FACTOR_FILE_NAME} не содержит результатов"
            )
        substances = self._substances_by_id(substances_data)

        results: list[dict[str, Any]] = []
        case_ids: set[int] = set()
        scenario_codes: set[str] = set()
        flash_fire_count = 0
        for index, value in enumerate(values, start=1):
            if not isinstance(value, dict):
                raise FlashFireCalculationError(
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
                raise FlashFireCalculationError(
                    f"Результат {index}: недопустимый или повторяющийся id"
                )
            if not scenario_code or scenario_code in scenario_codes:
                raise FlashFireCalculationError(
                    f"Результат {index}: пустой или повторяющийся scenario_code"
                )
            case_ids.add(case_id)
            scenario_codes.add(scenario_code)

            substance_id = value.get("substance_id")
            substance = substances.get(substance_id)
            if substance is None:
                raise FlashFireCalculationError(
                    f"Сценарий {scenario_code}: substance_id={substance_id} "
                    "отсутствует в substances.json"
                )
            if value.get("kind") != substance.get("kind"):
                raise FlashFireCalculationError(
                    f"Сценарий {scenario_code}: устаревшие данные (kind)"
                )

            calc_code = value.get("calc_code")
            if isinstance(calc_code, bool) or not isinstance(calc_code, int):
                raise FlashFireCalculationError(
                    f"Сценарий {scenario_code}: неверный calc_code"
                )
            applicable = calc_code == FLASH_FIRE_CALC_CODE
            if applicable:
                mass_t = _number(
                    value.get("ov_in_hazard_factor_t"),
                    f"Сценарий {scenario_code}: ov_in_hazard_factor_t",
                    positive=True,
                )
                physical = substance.get("physical")
                explosion = substance.get("explosion")
                if not isinstance(physical, dict):
                    raise FlashFireCalculationError(
                        f"Сценарий {scenario_code}: physical должен быть объектом"
                    )
                if not isinstance(explosion, dict):
                    raise FlashFireCalculationError(
                        f"Сценарий {scenario_code}: explosion должен быть объектом"
                    )
                lel = _number(
                    explosion.get("lel_percent"),
                    f"Сценарий {scenario_code}: lel_percent",
                    positive=True,
                )
                if value.get("kind") in GAS_KINDS:
                    gas_density = _number(
                        physical.get("density_gas_kg_per_m3"),
                        f"Сценарий {scenario_code}: density_gas_kg_per_m3",
                        positive=True,
                    )
                    molar_mass = None
                    boiling_point = None
                    density_source = "substance_gas_density"
                else:
                    gas_density = None
                    molar_mass = _number(
                        physical.get("molar_mass_kg_per_mol"),
                        f"Сценарий {scenario_code}: molar_mass_kg_per_mol",
                        positive=True,
                    )
                    boiling_point = _number(
                        physical.get("boiling_point_C"),
                        f"Сценарий {scenario_code}: boiling_point_C",
                    )
                    density_source = "calculated_vapor_density"
                calculated = calculate_flash_fire_radii(
                    mass_t * 1000.0,
                    molar_mass,
                    boiling_point,
                    lel,
                    gas_density,
                )
                status = "calculated"
                flash_fire_count += 1
            else:
                mass_t = value.get("ov_in_hazard_factor_t")
                molar_mass = None
                boiling_point = None
                lel = None
                gas_density = None
                density_source = None
                calculated = {
                    "vapor_density_kg_m3": None,
                    "lel_radius_m": None,
                    "flash_fire_radius_m": None,
                }
                status = "not_applicable"

            result = dict(value)
            result.update(
                {
                    "flash_fire_applicable": applicable,
                    "flash_fire_status": status,
                    "flash_fire_status_name": (
                        "Зоны рассчитаны"
                        if applicable
                        else "Сценарий не является пожаром-вспышкой"
                    ),
                    "flash_fire_mass_t": mass_t,
                    "flash_fire_mass_kg": (
                        mass_t * 1000.0 if applicable else None
                    ),
                    "flash_fire_molar_mass_kg_mol": molar_mass,
                    "flash_fire_boiling_point_c": boiling_point,
                    "flash_fire_lel_percent": lel,
                    "flash_fire_gas_density_kg_m3": gas_density,
                    "flash_fire_density_source": density_source,
                    "flash_fire_formula": (
                        "Приказ МЧС России от 10.07.2009 № 404"
                        if applicable
                        else "не применяется"
                    ),
                    **calculated,
                }
            )
            results.append(result)

        result_data = {
            "format_version": 1,
            "case_count": len(results),
            "flash_fire_count": flash_fire_count,
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
            raise FlashFireCalculationError(
                f"Не удалось сохранить {path}"
            ) from exc

        return FlashFireCalculationResult(
            path=path,
            case_count=len(results),
            flash_fire_count=flash_fire_count,
            results=tuple(results),
        )

    @staticmethod
    def _substances_by_id(values: Any) -> dict[int, dict[str, Any]]:
        if not isinstance(values, list) or not values:
            raise FlashFireCalculationError(
                "Вещества должны быть непустым списком"
            )
        result: dict[int, dict[str, Any]] = {}
        for index, value in enumerate(values, start=1):
            if not isinstance(value, dict):
                raise FlashFireCalculationError(
                    f"Вещества, запись {index}: ожидается объект"
                )
            substance_id = value.get("id")
            if (
                isinstance(substance_id, bool)
                or not isinstance(substance_id, int)
                or substance_id <= 0
                or substance_id in result
            ):
                raise FlashFireCalculationError(
                    f"Вещества, запись {index}: "
                    "недопустимый или повторяющийся id"
                )
            result[substance_id] = value
        return result
