import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris_v2.hazard_factor_calculation import FILE_NAME as HAZARD_FACTOR_FILE_NAME


FILE_NAME = "toxic_results.json"
TOXIC_CALC_CODE = 4
LETHAL_COEFFICIENT = 5.0
THRESHOLD_COEFFICIENT = 15.0
MASS_POWER = 0.33
METHOD_NAME = "temporary_mass_scaling"
WARNING = (
    "Временная оценка по массе. Не является моделью рассеивания "
    "токсичного облака и должна быть заменена полноценным расчётом."
)


class ToxicCalculationError(Exception):
    pass


@dataclass(frozen=True)
class ToxicCalculationResult:
    path: Path
    case_count: int
    toxic_count: int
    results: tuple[dict[str, Any], ...]


def calculate_temporary_toxic_zones(mass_kg: float) -> tuple[int, int]:
    if (
        isinstance(mass_kg, bool)
        or not isinstance(mass_kg, (int, float))
        or not math.isfinite(float(mass_kg))
        or mass_kg <= 0
    ):
        raise ValueError("mass_kg должна быть больше нуля")
    lethal = round(LETHAL_COEFFICIENT * float(mass_kg) ** MASS_POWER)
    threshold = round(THRESHOLD_COEFFICIENT * float(mass_kg) ** MASS_POWER)
    return lethal, threshold


class ToxicCalculationService:
    def calculate(self, project_directory: Path | str) -> ToxicCalculationResult:
        project = Path(project_directory)
        if not project.is_dir():
            raise ToxicCalculationError(f"Папка проекта не найдена: {project}")
        source_path = project / HAZARD_FACTOR_FILE_NAME
        if not source_path.is_file():
            raise ToxicCalculationError(
                f"Файл не найден: {source_path.name}. "
                "Сначала рассчитайте массу поражающего фактора"
            )
        try:
            source_data = json.loads(source_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ToxicCalculationError(
                f"Не удалось прочитать {source_path.name}"
            ) from exc
        values = source_data.get("results") if isinstance(source_data, dict) else None
        if not isinstance(values, list) or not values:
            raise ToxicCalculationError(
                f"{HAZARD_FACTOR_FILE_NAME} не содержит результатов"
            )

        results: list[dict[str, Any]] = []
        case_ids: set[int] = set()
        scenario_codes: set[str] = set()
        toxic_count = 0
        for index, value in enumerate(values, start=1):
            if not isinstance(value, dict):
                raise ToxicCalculationError(
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
                raise ToxicCalculationError(
                    f"Результат {index}: недопустимый или повторяющийся id"
                )
            if not scenario_code or scenario_code in scenario_codes:
                raise ToxicCalculationError(
                    f"Результат {index}: пустой или повторяющийся scenario_code"
                )
            case_ids.add(case_id)
            scenario_codes.add(scenario_code)

            calc_code = value.get("calc_code")
            if isinstance(calc_code, bool) or not isinstance(calc_code, int):
                raise ToxicCalculationError(
                    f"Сценарий {scenario_code}: неверный calc_code"
                )
            applicable = calc_code == TOXIC_CALC_CODE
            if applicable:
                mass_t = value.get("ov_in_hazard_factor_t")
                if (
                    isinstance(mass_t, bool)
                    or not isinstance(mass_t, (int, float))
                    or not math.isfinite(float(mass_t))
                    or mass_t <= 0
                ):
                    raise ToxicCalculationError(
                        f"Сценарий {scenario_code}: ov_in_hazard_factor_t "
                        "должна быть больше нуля"
                    )
                mass_kg = float(mass_t) * 1000.0
                lethal, threshold = calculate_temporary_toxic_zones(mass_kg)
                status = "calculated_temporary"
                status_name = "Временная оценка по массе"
                toxic_count += 1
            else:
                mass_kg = None
                lethal = None
                threshold = None
                status = "not_applicable"
                status_name = "Сценарий не является токсическим поражением"

            result = dict(value)
            result.update(
                {
                    "toxic_applicable": applicable,
                    "toxic_status": status,
                    "toxic_status_name": status_name,
                    "toxic_method": METHOD_NAME if applicable else None,
                    "toxic_warning": WARNING if applicable else None,
                    "toxic_mass_kg": mass_kg,
                    "lethal_radius_m": lethal,
                    "threshold_radius_m": threshold,
                    "toxic_formula": (
                        "R_lethal=5*m^0.33; R_threshold=15*m^0.33; m, кг"
                        if applicable
                        else "не применяется"
                    ),
                }
            )
            results.append(result)

        result_data = {
            "format_version": 1,
            "method": METHOD_NAME,
            "warning": WARNING,
            "case_count": len(results),
            "toxic_count": toxic_count,
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
            raise ToxicCalculationError(f"Не удалось сохранить {path}") from exc

        return ToxicCalculationResult(
            path=path,
            case_count=len(results),
            toxic_count=toxic_count,
            results=tuple(results),
        )
