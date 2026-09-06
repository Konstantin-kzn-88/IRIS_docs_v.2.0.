import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris_v2.chemical_spill_calculation import (
    FILE_NAME as CHEMICAL_SPILL_FILE_NAME,
)
from iris_v2.explosion_calculation import FILE_NAME as EXPLOSION_FILE_NAME
from iris_v2.fireball_calculation import FILE_NAME as FIREBALL_FILE_NAME
from iris_v2.flash_fire_calculation import FILE_NAME as FLASH_FIRE_FILE_NAME
from iris_v2.hazard_factor_calculation import FILE_NAME as HAZARD_FACTOR_FILE_NAME
from iris_v2.jet_fire_calculation import FILE_NAME as JET_FIRE_FILE_NAME
from iris_v2.pool_fire_calculation import FILE_NAME as POOL_FIRE_FILE_NAME
from iris_v2.toxic_fake_calculation import FILE_NAME as TOXIC_FILE_NAME


FILE_NAME = "impact_zones.json"
CALCULATION_NAMES = {
    0: "Ликвидация аварии",
    1: "Пожар пролива",
    2: "Взрыв облака ТВС",
    3: "Пожар-вспышка",
    4: "Токсическое поражение",
    5: "Факельное горение",
    6: "Огненный шар",
    7: "Химически опасный пролив",
}
MODULES = {
    1: (
        POOL_FIRE_FILE_NAME,
        "pool_fire_status",
        ("q_10_5_m", "q_7_0_m", "q_4_2_m", "q_1_4_m"),
    ),
    2: (
        EXPLOSION_FILE_NAME,
        "explosion_status",
        ("p_100_m", "p_70_m", "p_28_m", "p_14_m", "p_5_m", "p_2_m"),
    ),
    3: (
        FLASH_FIRE_FILE_NAME,
        "flash_fire_status",
        ("lel_radius_m", "flash_fire_radius_m"),
    ),
    4: (
        TOXIC_FILE_NAME,
        "toxic_status",
        ("lethal_radius_m", "threshold_radius_m"),
    ),
    5: (
        JET_FIRE_FILE_NAME,
        "jet_fire_status",
        ("jet_fire_length_m", "jet_fire_diameter_m"),
    ),
    6: (
        FIREBALL_FILE_NAME,
        "fireball_status",
        ("dose_600_m", "dose_320_m", "dose_220_m", "dose_120_m"),
    ),
    7: (
        CHEMICAL_SPILL_FILE_NAME,
        "chemical_spill_status",
        ("chemical_spill_area_m2",),
    ),
}
FIELD_LABELS = {
    "q_10_5_m": "10,5 кВт/м²",
    "q_7_0_m": "7,0 кВт/м²",
    "q_4_2_m": "4,2 кВт/м²",
    "q_1_4_m": "1,4 кВт/м²",
    "p_100_m": "100 кПа",
    "p_70_m": "70 кПа",
    "p_28_m": "28 кПа",
    "p_14_m": "14 кПа",
    "p_5_m": "5 кПа",
    "p_2_m": "2 кПа",
    "lel_radius_m": "НКПР",
    "flash_fire_radius_m": "пожар-вспышка",
    "lethal_radius_m": "смертельная токсодоза",
    "threshold_radius_m": "пороговая токсодоза",
    "jet_fire_length_m": "длина факела",
    "jet_fire_diameter_m": "диаметр факела",
    "dose_600_m": "600 кДж/м²",
    "dose_320_m": "320 кДж/м²",
    "dose_220_m": "220 кДж/м²",
    "dose_120_m": "120 кДж/м²",
    "chemical_spill_area_m2": "площадь пролива",
}


class ImpactZonesError(Exception):
    pass


@dataclass(frozen=True)
class ImpactZonesResult:
    path: Path
    case_count: int
    calculated_count: int
    unavailable_count: int
    results: tuple[dict[str, Any], ...]


def _read_results(path: Path, hint: str) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ImpactZonesError(f"Файл не найден: {path.name}. {hint}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ImpactZonesError(f"Не удалось прочитать {path.name}") from exc
    values = data.get("results") if isinstance(data, dict) else None
    if not isinstance(values, list) or not values:
        raise ImpactZonesError(f"{path.name} не содержит результатов")
    if not all(isinstance(value, dict) for value in values):
        raise ImpactZonesError(f"{path.name} содержит неверный результат")
    return values


def _results_by_id(
    values: list[dict[str, Any]],
    file_name: str,
) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for index, value in enumerate(values, start=1):
        case_id = value.get("id")
        if (
            isinstance(case_id, bool)
            or not isinstance(case_id, int)
            or case_id <= 0
            or case_id in result
        ):
            raise ImpactZonesError(
                f"{file_name}, результат {index}: "
                "недопустимый или повторяющийся id"
            )
        result[case_id] = value
    return result


def _summary(values: dict[str, Any]) -> str:
    parts = []
    for key, value in values.items():
        if value is None:
            continue
        unit = "м²" if key == "chemical_spill_area_m2" else "м"
        parts.append(f"{FIELD_LABELS[key]}: {float(value):.6g} {unit}")
    return "; ".join(parts)


class ImpactZonesService:
    def calculate(self, project_directory: Path | str) -> ImpactZonesResult:
        project = Path(project_directory)
        if not project.is_dir():
            raise ImpactZonesError(f"Папка проекта не найдена: {project}")
        source_values = _read_results(
            project / HAZARD_FACTOR_FILE_NAME,
            "Сначала рассчитайте массу поражающего фактора",
        )

        required_codes = {
            value.get("calc_code")
            for value in source_values
            if isinstance(value.get("calc_code"), int)
        }
        module_results: dict[int, dict[int, dict[str, Any]]] = {}
        for calc_code, (file_name, _, _) in MODULES.items():
            if calc_code not in required_codes:
                continue
            values = _read_results(
                project / file_name,
                f"Сначала выполните расчёт «{CALCULATION_NAMES[calc_code]}»",
            )
            module_results[calc_code] = _results_by_id(values, file_name)

        results: list[dict[str, Any]] = []
        case_ids: set[int] = set()
        scenario_codes: set[str] = set()
        calculated_count = 0
        unavailable_count = 0
        for index, source in enumerate(source_values, start=1):
            case_id = source.get("id")
            scenario_code = str(source.get("scenario_code", "")).strip()
            calc_code = source.get("calc_code")
            if (
                isinstance(case_id, bool)
                or not isinstance(case_id, int)
                or case_id <= 0
                or case_id in case_ids
            ):
                raise ImpactZonesError(
                    f"Исходный результат {index}: "
                    "недопустимый или повторяющийся id"
                )
            if not scenario_code or scenario_code in scenario_codes:
                raise ImpactZonesError(
                    f"Исходный результат {index}: "
                    "пустой или повторяющийся scenario_code"
                )
            if (
                isinstance(calc_code, bool)
                or not isinstance(calc_code, int)
                or calc_code not in CALCULATION_NAMES
            ):
                raise ImpactZonesError(
                    f"Сценарий {scenario_code}: calc_code должен быть от 0 до 7"
                )
            case_ids.add(case_id)
            scenario_codes.add(scenario_code)

            if calc_code == 0:
                status = "none"
                status_name = "Поражающий фактор отсутствует"
                impact_values: dict[str, Any] = {}
            else:
                file_name, status_field, fields = MODULES[calc_code]
                module_item = module_results[calc_code].get(case_id)
                if module_item is None:
                    raise ImpactZonesError(
                        f"Сценарий {scenario_code} отсутствует в {file_name}"
                    )
                if module_item.get("scenario_code") != scenario_code:
                    raise ImpactZonesError(
                        f"Сценарий {scenario_code}: устаревшие данные в {file_name}"
                    )
                expected_status = (
                    "calculated_temporary" if calc_code == 4 else "calculated"
                )
                if module_item.get(status_field) != expected_status:
                    raise ImpactZonesError(
                        f"Сценарий {scenario_code} не рассчитан в {file_name}"
                    )
                impact_values = {field: module_item.get(field) for field in fields}
                if any(value is None for value in impact_values.values()):
                    raise ImpactZonesError(
                        f"Сценарий {scenario_code}: неполные зоны в {file_name}"
                    )
                status = (
                    "calculated_temporary" if calc_code == 4 else "calculated"
                )
                status_name = (
                    "Временная оценка по массе"
                    if calc_code == 4
                    else "Результат рассчитан"
                )
                calculated_count += 1

            result = dict(source)
            result.update(
                {
                    "impact_type": CALCULATION_NAMES[calc_code],
                    "impact_status": status,
                    "impact_status_name": status_name,
                    "impact_values": impact_values,
                    "impact_summary": _summary(impact_values),
                }
            )
            results.append(result)

        result_data = {
            "format_version": 1,
            "case_count": len(results),
            "calculated_count": calculated_count,
            "unavailable_count": unavailable_count,
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
            raise ImpactZonesError(f"Не удалось сохранить {path}") from exc

        return ImpactZonesResult(
            path=path,
            case_count=len(results),
            calculated_count=calculated_count,
            unavailable_count=unavailable_count,
            results=tuple(results),
        )
