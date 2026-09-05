import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris_v2.calculation_config import (
    CalculationConfigError,
    CalculationConfigService,
)
from iris_v2.release_calculation import (
    FILE_NAME as RELEASE_FILE_NAME,
    RELEASE_MODE_NAMES,
)


FILE_NAME = "spill_results.json"
SPILL_RELEASE_MODES = {
    "inventory_full",
    "inventory_partial",
    "pipeline_liquid_full",
    "pipeline_liquid_partial",
    "liquid_phase_leak",
    "pump_release",
}
FULL_SPILL_MODES = {
    "inventory_full",
    "pipeline_liquid_full",
    "pump_release",
}
SPILL_SOURCE_NAMES = {
    "calculated": "Расчёт по коэффициенту",
    "specified_full": "Заданная полная площадь",
    "specified_partial": "Доля заданной площади",
    "not_applicable": "Пролив отсутствует",
}


class SpillCalculationError(Exception):
    pass


@dataclass(frozen=True)
class SpillCalculationResult:
    path: Path
    case_count: int
    spill_count: int
    results: tuple[dict[str, Any], ...]


def _read_json(path: Path, missing_hint: str) -> Any:
    if not path.is_file():
        raise SpillCalculationError(f"Файл не найден: {path.name}. {missing_hint}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpillCalculationError(f"Не удалось прочитать {path.name}") from exc


def _objects_by_id(values: Any, label: str) -> dict[int, dict[str, Any]]:
    if not isinstance(values, list) or not values:
        raise SpillCalculationError(f"{label} должен быть непустым списком")
    result: dict[int, dict[str, Any]] = {}
    for index, value in enumerate(values, start=1):
        if not isinstance(value, dict):
            raise SpillCalculationError(f"{label}, запись {index}: ожидается объект")
        object_id = value.get("id")
        if (
            isinstance(object_id, bool)
            or not isinstance(object_id, int)
            or object_id <= 0
            or object_id in result
        ):
            raise SpillCalculationError(
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
        raise SpillCalculationError(f"{label} должно быть числом")
    result = float(value)
    if positive and result <= 0:
        raise SpillCalculationError(f"{label} должно быть больше нуля")
    if non_negative and result < 0:
        raise SpillCalculationError(f"{label} не может быть отрицательным")
    return result


def spill_is_applicable(release_mode: str) -> bool:
    return release_mode in SPILL_RELEASE_MODES


def calculate_spill_area_m2(
    released_mass_t: float,
    spill_coefficient: float,
    specified_area_m2: float | None,
    *,
    is_full_spill: bool,
    partial_spill_fraction: float,
) -> tuple[float, str, str]:
    if specified_area_m2 is None or specified_area_m2 == 0:
        return (
            released_mass_t * spill_coefficient,
            "calculated",
            "ov_in_accident_t × spill_coefficient",
        )
    if is_full_spill:
        return specified_area_m2, "specified_full", "spill_area_m2"
    return (
        specified_area_m2 * partial_spill_fraction,
        "specified_partial",
        "spill_area_m2 × partial_spill_fraction",
    )


class SpillCalculationService:
    def calculate(
        self, project_directory: Path | str
    ) -> SpillCalculationResult:
        project = Path(project_directory)
        if not project.is_dir():
            raise SpillCalculationError(f"Папка проекта не найдена: {project}")

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
        release_data = _read_json(
            project / RELEASE_FILE_NAME,
            "Сначала рассчитайте массу вещества в аварии",
        )
        releases = (
            release_data.get("results")
            if isinstance(release_data, dict)
            else None
        )
        if not isinstance(releases, list) or not releases:
            raise SpillCalculationError(
                f"{RELEASE_FILE_NAME} не содержит результатов"
            )
        try:
            config = CalculationConfigService().load(project)
        except CalculationConfigError as exc:
            raise SpillCalculationError(str(exc)) from exc
        partial_fraction = _number(
            config.get("partial_spill_fraction"),
            "partial_spill_fraction",
            positive=True,
        )
        if partial_fraction > 1:
            raise SpillCalculationError(
                "partial_spill_fraction не может быть больше 1"
            )

        results: list[dict[str, Any]] = []
        case_ids: set[int] = set()
        scenario_codes: set[str] = set()
        spill_count = 0
        for index, release in enumerate(releases, start=1):
            if not isinstance(release, dict):
                raise SpillCalculationError(
                    f"Результат выброса {index}: ожидается объект"
                )
            case_id = release.get("id")
            scenario_code = str(release.get("scenario_code", "")).strip()
            if (
                isinstance(case_id, bool)
                or not isinstance(case_id, int)
                or case_id <= 0
                or case_id in case_ids
            ):
                raise SpillCalculationError(
                    f"Результат выброса {index}: "
                    "недопустимый или повторяющийся id"
                )
            if not scenario_code or scenario_code in scenario_codes:
                raise SpillCalculationError(
                    f"Результат выброса {index}: "
                    "пустой или повторяющийся scenario_code"
                )
            case_ids.add(case_id)
            scenario_codes.add(scenario_code)

            equipment_id = release.get("equipment_id")
            item = equipment.get(equipment_id)
            if item is None:
                raise SpillCalculationError(
                    f"Сценарий {scenario_code}: equipment_id={equipment_id} "
                    "отсутствует в equipments.json"
                )
            substance_id = item.get("substance_id")
            substance = substances.get(substance_id)
            if substance is None:
                raise SpillCalculationError(
                    f"Сценарий {scenario_code}: substance_id={substance_id} "
                    "отсутствует в substances.json"
                )
            for actual, expected, label in (
                (release.get("substance_id"), substance_id, "substance_id"),
                (
                    release.get("equipment_type"),
                    item.get("equipment_type"),
                    "equipment_type",
                ),
                (release.get("kind"), substance.get("kind"), "kind"),
            ):
                if actual != expected:
                    raise SpillCalculationError(
                        f"Сценарий {scenario_code}: устаревшие данные ({label}). "
                        "Повторите предыдущие расчёты"
                    )

            release_mode = str(release.get("release_mode", "")).strip()
            if release_mode not in RELEASE_MODE_NAMES:
                raise SpillCalculationError(
                    f"Сценарий {scenario_code}: неизвестный release_mode "
                    f"{release_mode!r}. Повторите расчёт массы в аварии"
                )
            released_mass = _number(
                release.get("ov_in_accident_t"),
                f"Сценарий {scenario_code}: ov_in_accident_t",
                non_negative=True,
            )
            applicable = spill_is_applicable(release_mode)
            specified_raw = item.get("spill_area_m2")
            specified_area = (
                None
                if specified_raw is None
                else _number(
                    specified_raw,
                    f"Сценарий {scenario_code}: spill_area_m2",
                    non_negative=True,
                )
            )

            if applicable:
                if released_mass <= 0:
                    raise SpillCalculationError(
                        f"Сценарий {scenario_code}: масса пролива должна быть "
                        "больше нуля"
                    )
                coefficient = _number(
                    item.get("spill_coefficient"),
                    f"Сценарий {scenario_code}: spill_coefficient",
                    non_negative=True,
                )
                if (specified_area is None or specified_area == 0) and coefficient <= 0:
                    raise SpillCalculationError(
                        f"Сценарий {scenario_code}: при незаданной площади "
                        "spill_coefficient должен быть больше нуля"
                    )
                is_full_spill = release_mode in FULL_SPILL_MODES
                area, source, formula = calculate_spill_area_m2(
                    released_mass,
                    coefficient,
                    specified_area,
                    is_full_spill=is_full_spill,
                    partial_spill_fraction=partial_fraction,
                )
                spill_count += 1
            else:
                coefficient = item.get("spill_coefficient")
                is_full_spill = None
                area = None
                source = "not_applicable"
                formula = "не применяется для газовой фазы"

            result = dict(release)
            result.update(
                {
                    "spill_applicable": applicable,
                    "spill_source": source,
                    "spill_source_name": SPILL_SOURCE_NAMES[source],
                    "is_full_spill": is_full_spill,
                    "spill_coefficient": coefficient,
                    "specified_spill_area_m2": specified_area,
                    "partial_spill_fraction": partial_fraction,
                    "spill_area_m2": area,
                    "spill_formula": formula,
                }
            )
            results.append(result)

        result_data = {
            "format_version": 1,
            "case_count": len(results),
            "spill_count": spill_count,
            "partial_spill_fraction": partial_fraction,
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
            raise SpillCalculationError(f"Не удалось сохранить {path}") from exc

        return SpillCalculationResult(
            path=path,
            case_count=len(results),
            spill_count=spill_count,
            results=tuple(results),
        )
