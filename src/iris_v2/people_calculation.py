import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris_v2.impact_zones import FILE_NAME as IMPACT_ZONES_FILE_NAME


FILE_NAME = "people_results.json"


class PeopleCalculationError(Exception):
    pass


@dataclass(frozen=True)
class PeopleCalculationResult:
    path: Path
    case_count: int
    max_fatalities: int
    max_injured: int
    results: tuple[dict[str, Any], ...]


def _non_negative_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} должно быть целым числом не меньше нуля")
    return value


def calculate_people_damage(
    equipment_type: int,
    kind: int,
    scenario_line: int,
    calc_code: int,
    possible_dead: int,
    possible_injured: int,
) -> tuple[int, int, str]:
    """Возвращает погибших, пострадавших и код применённого правила."""
    for value, name, valid_range in (
        (equipment_type, "equipment_type", range(10)),
        (kind, "kind", range(10)),
        (calc_code, "calc_code", range(8)),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value not in valid_range:
            raise ValueError(f"{name} имеет недопустимое значение")
    if (
        isinstance(scenario_line, bool)
        or not isinstance(scenario_line, int)
        or scenario_line <= 0
    ):
        raise ValueError("scenario_line должно быть целым числом больше нуля")
    possible_dead = _non_negative_integer(possible_dead, "possible_dead")
    possible_injured = _non_negative_integer(
        possible_injured, "possible_injured"
    )

    if calc_code == 0:
        return 0, 0, "no_impact"

    # В старой модели токсическое поражение, огненный шар и химически
    # опасный пролив всегда давали одного пострадавшего без погибших.
    if calc_code in {4, 6, 7}:
        return 0, 1, "one_injured"

    # Насосы/арматура имели отдельные правила в старом _calc_people.py.
    if equipment_type == 4:
        if scenario_line == 2 and calc_code == 1:
            return (
                max(0, possible_dead - 3),
                max(0, possible_injured - 4),
                "pump_cloud_fire",
            )
        if kind == 4 and scenario_line == 5 and calc_code == 2:
            return (
                max(0, possible_dead - 2),
                max(0, possible_injured - 3),
                "pump_explosion",
            )
        if kind in {0, 1, 4, 5}:
            return 1, 1, "pump_local_impact"
        return 0, 1, "pump_limited_impact"

    if calc_code == 2:
        if equipment_type in {0, 9} and kind in {4, 5} and scenario_line == 6:
            return 0, 1, "pipeline_lpg_partial_explosion"
        if scenario_line == 2:
            return possible_dead, possible_injured, "full_explosion"
        return 1, 1, "partial_explosion"

    if calc_code == 1:
        if scenario_line == 1 or (kind == 9 and scenario_line == 2):
            return (
                max(0, possible_dead - 1),
                max(0, possible_injured - 1),
                "full_pool_fire",
            )
        return 0, 1, "partial_pool_fire"

    if calc_code in {3, 5}:
        if scenario_line == 1:
            return (
                max(0, possible_dead - 1),
                max(0, possible_injured - 1),
                "full_flash_or_jet_fire",
            )
        if kind in {2, 3}:
            return 1, 1, "gas_local_impact"
        return 0, 1, "liquid_local_impact"

    raise ValueError("Для сочетания не определено правило расчёта людей")


def _read_json(path: Path, label: str) -> Any:
    if not path.is_file():
        raise PeopleCalculationError(f"Файл не найден: {path.name}. {label}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PeopleCalculationError(f"Не удалось прочитать {path.name}") from exc


class PeopleCalculationService:
    def calculate(self, project_directory: Path | str) -> PeopleCalculationResult:
        project = Path(project_directory)
        if not project.is_dir():
            raise PeopleCalculationError(f"Папка проекта не найдена: {project}")

        impact_data = _read_json(
            project / IMPACT_ZONES_FILE_NAME,
            "Сначала сформируйте свод зон поражения",
        )
        impact_values = (
            impact_data.get("results") if isinstance(impact_data, dict) else None
        )
        if not isinstance(impact_values, list) or not impact_values:
            raise PeopleCalculationError(
                f"{IMPACT_ZONES_FILE_NAME} не содержит результатов"
            )

        equipment_values = _read_json(
            project / "equipments.json",
            "Сначала импортируйте оборудование",
        )
        if not isinstance(equipment_values, list) or not equipment_values:
            raise PeopleCalculationError("equipments.json должен быть непустым списком")
        equipment_by_id: dict[int, dict[str, Any]] = {}
        for index, item in enumerate(equipment_values, start=1):
            if not isinstance(item, dict):
                raise PeopleCalculationError(
                    f"Оборудование {index}: ожидается объект"
                )
            equipment_id = item.get("id")
            if (
                isinstance(equipment_id, bool)
                or not isinstance(equipment_id, int)
                or equipment_id <= 0
                or equipment_id in equipment_by_id
            ):
                raise PeopleCalculationError(
                    f"Оборудование {index}: недопустимый или повторяющийся id"
                )
            equipment_by_id[equipment_id] = item

        results: list[dict[str, Any]] = []
        case_ids: set[int] = set()
        scenario_codes: set[str] = set()
        for index, value in enumerate(impact_values, start=1):
            if not isinstance(value, dict):
                raise PeopleCalculationError(
                    f"Результат зон {index}: ожидается объект"
                )
            case_id = value.get("id")
            scenario_code = str(value.get("scenario_code", "")).strip()
            if (
                isinstance(case_id, bool)
                or not isinstance(case_id, int)
                or case_id <= 0
                or case_id in case_ids
            ):
                raise PeopleCalculationError(
                    f"Результат {index}: недопустимый или повторяющийся id"
                )
            if not scenario_code or scenario_code in scenario_codes:
                raise PeopleCalculationError(
                    f"Результат {index}: пустой или повторяющийся scenario_code"
                )
            case_ids.add(case_id)
            scenario_codes.add(scenario_code)

            equipment_id = value.get("equipment_id")
            equipment = equipment_by_id.get(equipment_id)
            if equipment is None:
                raise PeopleCalculationError(
                    f"Сценарий {scenario_code}: equipment_id={equipment_id} "
                    "отсутствует в equipments.json"
                )
            if equipment.get("equipment_type") != value.get("equipment_type"):
                raise PeopleCalculationError(
                    f"Сценарий {scenario_code}: equipment_type не совпадает "
                    "с equipments.json"
                )
            calc_code = value.get("calc_code")
            expected_status = {
                0: "none",
                4: "calculated_temporary",
            }.get(calc_code, "calculated")
            if value.get("impact_status") != expected_status:
                raise PeopleCalculationError(
                    f"Сценарий {scenario_code}: свод зон не рассчитан"
                )

            try:
                possible_dead = _non_negative_integer(
                    equipment.get("possible_dead"), "possible_dead"
                )
                possible_injured = _non_negative_integer(
                    equipment.get("possible_injured"), "possible_injured"
                )
                fatalities, injured, rule = calculate_people_damage(
                    value.get("equipment_type"),
                    value.get("kind"),
                    value.get("typical_scenario_line"),
                    calc_code,
                    possible_dead,
                    possible_injured,
                )
            except ValueError as exc:
                raise PeopleCalculationError(
                    f"Сценарий {scenario_code}: {exc}"
                ) from exc

            result = dict(value)
            result.update(
                {
                    "possible_dead": possible_dead,
                    "possible_injured": possible_injured,
                    "fatalities_count": fatalities,
                    "injured_count": injured,
                    "people_rule": rule,
                }
            )
            results.append(result)

        max_fatalities = max(item["fatalities_count"] for item in results)
        max_injured = max(item["injured_count"] for item in results)
        result_data = {
            "format_version": 1,
            "case_count": len(results),
            "max_fatalities": max_fatalities,
            "max_injured": max_injured,
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
            raise PeopleCalculationError(f"Не удалось сохранить {path}") from exc

        return PeopleCalculationResult(
            path=path,
            case_count=len(results),
            max_fatalities=max_fatalities,
            max_injured=max_injured,
            results=tuple(results),
        )
