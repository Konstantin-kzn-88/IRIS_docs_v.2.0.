import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris_v2.calculation_config import (
    CalculationConfigError,
    CalculationConfigService,
)
from iris_v2.typical_scenarios import (
    TypicalScenarioError,
    TypicalScenarioService,
)


FILE_NAME = "calculation_cases.json"
PIPELINE_TYPES = {0, 9}
FREQUENCY_MODE_LABELS = {
    "standard": "Стандартный",
    "without_compensation": "Без КМ",
    "with_compensation": "С КМ",
}


class CalculationCasesError(Exception):
    pass


@dataclass(frozen=True)
class CalculationCasesResult:
    path: Path
    equipment_count: int
    case_count: int
    cases: tuple[dict[str, Any], ...]


def _load_list(path: Path, label: str) -> list[dict[str, Any]]:
    if not path.is_file():
        raise CalculationCasesError(f"Файл не найден: {path.name}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CalculationCasesError(f"Не удалось прочитать {path.name}") from exc
    if not isinstance(data, list) or not data:
        raise CalculationCasesError(f"{label} должен быть непустым списком")
    if not all(isinstance(item, dict) for item in data):
        raise CalculationCasesError(f"{label} содержит запись неверного формата")
    return data


def _frequency_mode(hazard_component: str) -> str:
    has_without = "(без КМ)" in hazard_component
    has_with = "(с КМ)" in hazard_component
    if has_without and has_with:
        raise CalculationCasesError(
            f"{hazard_component!r}: одновременно указаны (без КМ) и (с КМ)"
        )
    if has_without:
        if not hazard_component.endswith("(без КМ)"):
            raise CalculationCasesError(
                f"{hazard_component!r}: отметка (без КМ) должна быть в конце"
            )
        return "without_compensation"
    if has_with:
        if not hazard_component.endswith("(с КМ)"):
            raise CalculationCasesError(
                f"{hazard_component!r}: отметка (с КМ) должна быть в конце"
            )
        return "with_compensation"
    return "standard"


class CalculationCasesService:
    def generate(
        self, project_directory: Path | str
    ) -> CalculationCasesResult:
        project = Path(project_directory)
        if not project.is_dir():
            raise CalculationCasesError(f"Папка проекта не найдена: {project}")

        substances = _load_list(project / "substances.json", "Вещества")
        equipment = _load_list(project / "equipments.json", "Оборудование")
        substance_by_id: dict[int, dict[str, Any]] = {}
        for index, substance in enumerate(substances, start=1):
            substance_id = substance.get("id")
            kind = substance.get("kind")
            name = str(substance.get("name", "")).strip()
            if (
                isinstance(substance_id, bool)
                or not isinstance(substance_id, int)
                or substance_id <= 0
                or substance_id in substance_by_id
            ):
                raise CalculationCasesError(
                    f"Вещество {index}: недопустимый или повторяющийся id"
                )
            if not name:
                raise CalculationCasesError(f"Вещество {index}: не заполнено название")
            if isinstance(kind, bool) or not isinstance(kind, int) or kind not in range(10):
                raise CalculationCasesError(f"Вещество {index}: kind должен быть от 0 до 9")
            substance_by_id[substance_id] = substance

        try:
            catalog = TypicalScenarioService().load()
        except TypicalScenarioError as exc:
            raise CalculationCasesError(str(exc)) from exc
        try:
            config = CalculationConfigService().load(project)
        except CalculationConfigError as exc:
            raise CalculationCasesError(str(exc)) from exc
        multipliers = config["frequency_multipliers"]

        cases: list[dict[str, Any]] = []
        equipment_ids: set[int] = set()
        for equipment_index, item in enumerate(equipment, start=1):
            equipment_id = item.get("id")
            substance_id = item.get("substance_id")
            equipment_type = item.get("equipment_type")
            equipment_name = str(item.get("equipment_name", "")).strip()
            hazard_component = str(item.get("hazard_component", "")).strip()

            if (
                isinstance(equipment_id, bool)
                or not isinstance(equipment_id, int)
                or equipment_id <= 0
                or equipment_id in equipment_ids
            ):
                raise CalculationCasesError(
                    f"Оборудование {equipment_index}: недопустимый или повторяющийся id"
                )
            equipment_ids.add(equipment_id)
            if substance_id not in substance_by_id:
                raise CalculationCasesError(
                    f"Оборудование {equipment_index}: substance_id={substance_id} "
                    "отсутствует в substances.json"
                )
            if not equipment_name:
                raise CalculationCasesError(
                    f"Оборудование {equipment_index}: не заполнено название"
                )
            if (
                isinstance(equipment_type, bool)
                or not isinstance(equipment_type, int)
                or equipment_type not in catalog.equipment_types
            ):
                raise CalculationCasesError(
                    f"Оборудование {equipment_index}: equipment_type должен быть от 0 до 9"
                )
            if not hazard_component:
                raise CalculationCasesError(
                    f"Оборудование {equipment_index}: не заполнено hazard_component"
                )

            substance = substance_by_id[substance_id]
            kind = substance["kind"]
            scenarios = catalog.scenarios_for(equipment_type, kind)
            if not scenarios:
                reason = catalog.forbidden_reason(equipment_type, kind)
                message = reason or "типовые сценарии отсутствуют"
                raise CalculationCasesError(
                    f"Оборудование {equipment_index}: сочетание "
                    f"equipment_type={equipment_type}, kind={kind} недопустимо — {message}"
                )

            mode = _frequency_mode(hazard_component)
            frequency_basis = (
                item.get("total_length_m")
                if equipment_type in PIPELINE_TYPES
                else item.get("equipment_count")
            )
            frequency_basis_unit = "м" if equipment_type in PIPELINE_TYPES else "шт."
            if (
                isinstance(frequency_basis, bool)
                or not isinstance(frequency_basis, (int, float))
                or not math.isfinite(float(frequency_basis))
                or float(frequency_basis) <= 0
            ):
                field = (
                    "total_length_m"
                    if equipment_type in PIPELINE_TYPES
                    else "equipment_count"
                )
                raise CalculationCasesError(
                    f"Оборудование {equipment_index}: {field} должно быть "
                    "числом больше нуля"
                )
            for scenario in scenarios:
                case_number = len(cases) + 1
                cases.append(
                    {
                        "id": case_number,
                        "scenario_code": f"С{case_number}",
                        "equipment_id": equipment_id,
                        "equipment_source_id": item.get("source_id"),
                        "equipment_name": equipment_name,
                        "equipment_type": equipment_type,
                        "equipment_type_name": catalog.equipment_types[equipment_type],
                        "substance_id": substance_id,
                        "substance_name": str(substance["name"]).strip(),
                        "kind": kind,
                        "kind_name": catalog.kinds[kind],
                        "hazard_component": hazard_component,
                        "frequency_mode": mode,
                        "frequency_mode_name": FREQUENCY_MODE_LABELS[mode],
                        "frequency_multiplier": float(multipliers[mode]),
                        "frequency_basis": float(frequency_basis),
                        "frequency_basis_unit": frequency_basis_unit,
                        "typical_scenario_line": scenario.line,
                        "scenario_text": scenario.text,
                        "base_frequency": scenario.base_frequency,
                        "accident_event_probability": scenario.event_probability,
                        "unit_scenario_frequency": scenario.frequency,
                        "calc_code": scenario.calc_code,
                        "calc_name": catalog.calculation_types[scenario.calc_code],
                    }
                )

        result_data = {
            "format_version": 1,
            "equipment_count": len(equipment),
            "case_count": len(cases),
            "cases": cases,
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
            raise CalculationCasesError(f"Не удалось сохранить {path}") from exc

        return CalculationCasesResult(
            path=path,
            equipment_count=len(equipment),
            case_count=len(cases),
            cases=tuple(cases),
        )
