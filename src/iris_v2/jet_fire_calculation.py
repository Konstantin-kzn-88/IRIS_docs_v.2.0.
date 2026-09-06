import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris_v2.hazard_factor_calculation import FILE_NAME as HAZARD_FACTOR_FILE_NAME


FILE_NAME = "jet_fire_results.json"
JET_FIRE_CALC_CODE = 5
LPG_KINDS = {4, 5, 8}
GAS_RELEASE_MODES = {
    "gas_supply_full",
    "gas_supply_partial",
    "gas_phase_leak",
}
JET_TYPE_COEFFICIENTS = (12.5, 13.5, 15.0)
JET_TYPE_NAMES = (
    "Газовый факел",
    "Газовый факел СУГ",
    "Жидкостный факел / факел СУГ",
)


class JetFireCalculationError(Exception):
    pass


@dataclass(frozen=True)
class JetFireCalculationResult:
    path: Path
    case_count: int
    jet_fire_count: int
    results: tuple[dict[str, Any], ...]


def jet_fire_type(kind: int, release_mode: str) -> int:
    if isinstance(kind, bool) or not isinstance(kind, int) or kind not in range(10):
        raise JetFireCalculationError("Вид вещества должен быть от 0 до 9")
    if not isinstance(release_mode, str) or not release_mode.strip():
        raise JetFireCalculationError("Не задан режим истечения")
    if release_mode in GAS_RELEASE_MODES:
        return 1 if kind in LPG_KINDS else 0
    return 2


def calculate_jet_fire_size(
    mass_flow_kg_s: float,
    jet_type: int,
) -> tuple[int, int]:
    if (
        isinstance(mass_flow_kg_s, bool)
        or not isinstance(mass_flow_kg_s, (int, float))
        or not math.isfinite(float(mass_flow_kg_s))
        or mass_flow_kg_s <= 0
    ):
        raise JetFireCalculationError("Расход должен быть больше нуля")
    if isinstance(jet_type, bool) or jet_type not in range(3):
        raise JetFireCalculationError("Тип факела должен быть от 0 до 2")

    length_m = int(
        JET_TYPE_COEFFICIENTS[jet_type] * float(mass_flow_kg_s) ** 0.4
    )
    diameter_m = math.ceil(0.15 * length_m)
    return length_m, diameter_m


class JetFireCalculationService:
    def calculate(
        self, project_directory: Path | str
    ) -> JetFireCalculationResult:
        project = Path(project_directory)
        if not project.is_dir():
            raise JetFireCalculationError(
                f"Папка проекта не найдена: {project}"
            )
        source_path = project / HAZARD_FACTOR_FILE_NAME
        if not source_path.is_file():
            raise JetFireCalculationError(
                f"Файл не найден: {source_path.name}. "
                "Сначала рассчитайте массу поражающего фактора"
            )
        try:
            source_data = json.loads(source_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise JetFireCalculationError(
                f"Не удалось прочитать {source_path.name}"
            ) from exc

        values = (
            source_data.get("results")
            if isinstance(source_data, dict)
            else None
        )
        if not isinstance(values, list) or not values:
            raise JetFireCalculationError(
                f"{HAZARD_FACTOR_FILE_NAME} не содержит результатов"
            )

        results: list[dict[str, Any]] = []
        case_ids: set[int] = set()
        scenario_codes: set[str] = set()
        jet_fire_count = 0
        for index, value in enumerate(values, start=1):
            if not isinstance(value, dict):
                raise JetFireCalculationError(
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
                raise JetFireCalculationError(
                    f"Результат {index}: недопустимый или повторяющийся id"
                )
            if not scenario_code or scenario_code in scenario_codes:
                raise JetFireCalculationError(
                    f"Результат {index}: пустой или повторяющийся scenario_code"
                )
            case_ids.add(case_id)
            scenario_codes.add(scenario_code)

            calc_code = value.get("calc_code")
            if isinstance(calc_code, bool) or not isinstance(calc_code, int):
                raise JetFireCalculationError(
                    f"Сценарий {scenario_code}: неверный calc_code"
                )
            applicable = calc_code == JET_FIRE_CALC_CODE
            if applicable:
                flow = value.get("hazard_factor_flow_kg_s")
                if (
                    isinstance(flow, bool)
                    or not isinstance(flow, (int, float))
                    or not math.isfinite(float(flow))
                    or flow <= 0
                ):
                    raise JetFireCalculationError(
                        f"Сценарий {scenario_code}: "
                        "hazard_factor_flow_kg_s должен быть больше нуля"
                    )
                kind = value.get("kind")
                release_mode = value.get("release_mode")
                type_code = jet_fire_type(kind, release_mode)
                length_m, diameter_m = calculate_jet_fire_size(
                    float(flow),
                    type_code,
                )
                status = "calculated"
                jet_fire_count += 1
            else:
                flow = value.get("hazard_factor_flow_kg_s")
                release_mode = value.get("release_mode")
                type_code = None
                length_m = None
                diameter_m = None
                status = "not_applicable"

            result = dict(value)
            result.update(
                {
                    "jet_fire_applicable": applicable,
                    "jet_fire_status": status,
                    "jet_fire_status_name": (
                        "Размеры факела рассчитаны"
                        if applicable
                        else "Сценарий не является факельным горением"
                    ),
                    "jet_fire_flow_kg_s": (
                        float(flow) if applicable else None
                    ),
                    "jet_fire_release_mode": (
                        release_mode if applicable else None
                    ),
                    "jet_fire_type": type_code,
                    "jet_fire_type_name": (
                        JET_TYPE_NAMES[type_code]
                        if type_code is not None
                        else None
                    ),
                    "jet_fire_length_m": length_m,
                    "jet_fire_diameter_m": diameter_m,
                    "jet_fire_formula": (
                        "Приказ МЧС России от 10.07.2009 № 404, "
                        "формулы П3.71–П3.72"
                        if applicable
                        else "не применяется"
                    ),
                }
            )
            results.append(result)

        result_data = {
            "format_version": 1,
            "case_count": len(results),
            "jet_fire_count": jet_fire_count,
            "jet_type_coefficients": list(JET_TYPE_COEFFICIENTS),
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
            raise JetFireCalculationError(
                f"Не удалось сохранить {path}"
            ) from exc

        return JetFireCalculationResult(
            path=path,
            case_count=len(results),
            jet_fire_count=jet_fire_count,
            results=tuple(results),
        )
