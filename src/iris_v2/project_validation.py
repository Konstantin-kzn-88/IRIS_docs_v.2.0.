import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris_v2.calculation_config import (
    FILE_NAME as CALCULATION_CONFIG_FILE_NAME,
    CalculationConfigError,
    CalculationConfigService,
)
from iris_v2.service import ProjectInfo
from iris_v2.typical_scenarios import (
    TypicalScenarioError,
    TypicalScenarioService,
)


PHASE_STATES = {"ж.ф.", "г.ф.", "ж.ф.+г.ф."}
PIPELINE_TYPES = {0, 9}


@dataclass(frozen=True)
class ValidationItem:
    section: str
    ok: bool
    message: str
    path: Path | None = None


@dataclass(frozen=True)
class ValidationReport:
    items: tuple[ValidationItem, ...]

    @property
    def ready(self) -> bool:
        return all(item.ok for item in self.items)


def _read_json(path: Path) -> tuple[Any, str | None]:
    if not path.is_file():
        return None, f"Файл не найден: {path.name}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"Не удалось прочитать {path.name}: {exc}"


def _number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _positive(value: Any) -> bool:
    return _number(value) and float(value) > 0


def _message(errors: list[str], success: str) -> str:
    return "; ".join(errors) if errors else success


class ProjectValidationService:
    def check(
        self, project_directory: Path | str, project: ProjectInfo
    ) -> ValidationReport:
        root = Path(project_directory)
        project_item = self._check_project(project)
        common_item = self._check_project_common(root / "project_common.json")
        substances_item, substance_ids = self._check_substances(
            root / "substances.json"
        )
        equipment_item = self._check_equipment(
            root / "equipments.json", substance_ids
        )
        typical_scenarios_item = self._check_typical_scenarios(
            root / "equipments.json", root / "substances.json"
        )
        calculation_config_item = self._check_calculation_config(
            root / CALCULATION_CONFIG_FILE_NAME
        )
        return ValidationReport(
            (
                project_item,
                common_item,
                substances_item,
                equipment_item,
                typical_scenarios_item,
                calculation_config_item,
            )
        )

    @staticmethod
    def _check_typical_scenarios(
        equipment_path: Path, substances_path: Path
    ) -> ValidationItem:
        errors: list[str] = []
        service = TypicalScenarioService()
        catalog = None
        source_path = (
            service.external_path()
            if service.external_path().is_file()
            else service.bundled_path()
        )
        try:
            catalog = service.load()
            source_path = catalog.source_path
        except TypicalScenarioError as exc:
            errors.append(str(exc))

        substances, substances_error = _read_json(substances_path)
        equipment, equipment_error = _read_json(equipment_path)
        if substances_error:
            errors.append(substances_error)
        if equipment_error:
            errors.append(equipment_error)

        checked = 0
        if (
            catalog is not None
            and isinstance(substances, list)
            and isinstance(equipment, list)
        ):
            substance_kinds = {
                item.get("id"): item.get("kind")
                for item in substances
                if isinstance(item, dict)
                and isinstance(item.get("id"), int)
                and isinstance(item.get("kind"), int)
            }
            for index, item in enumerate(equipment, start=1):
                if not isinstance(item, dict):
                    continue
                equipment_type = item.get("equipment_type")
                kind = substance_kinds.get(item.get("substance_id"))
                if (
                    isinstance(equipment_type, int)
                    and equipment_type in catalog.equipment_types
                    and isinstance(kind, int)
                    and kind in catalog.kinds
                ):
                    checked += 1
                    reason = catalog.forbidden_reason(equipment_type, kind)
                    if reason is not None:
                        errors.append(
                            f"оборудование {index}: сочетание "
                            f"equipment_type={equipment_type}, kind={kind} запрещено — {reason}"
                        )
                    elif not catalog.scenarios_for(equipment_type, kind):
                        errors.append(
                            f"оборудование {index}: отсутствуют типовые сценарии "
                            f"для equipment_type={equipment_type}, kind={kind}"
                        )

        success = (
            f"Справочник: {catalog.pair_count} сочетания, "
            f"{catalog.scenario_count} сценариев; проверено строк: {checked}"
            if catalog is not None
            else ""
        )
        return ValidationItem(
            "Типовые сценарии",
            not errors,
            _message(errors, success),
            source_path,
        )

    @staticmethod
    def _check_calculation_config(path: Path) -> ValidationItem:
        errors: list[str] = []
        if not path.is_file():
            errors.append(f"Файл не найден: {path.name}")
        else:
            try:
                CalculationConfigService().load(path.parent)
            except CalculationConfigError as exc:
                errors.append(str(exc))
        return ValidationItem(
            "Настройки расчёта",
            not errors,
            _message(errors, "Настройки расчёта заполнены"),
            path,
        )

    @staticmethod
    def _check_project(project: ProjectInfo) -> ValidationItem:
        errors: list[str] = []
        for value, label in (
            (project.organization_name, "организация"),
            (project.opo_name, "ОПО"),
            (project.opo_registration_number, "регистрационный номер ОПО"),
        ):
            if not str(value).strip():
                errors.append(f"не заполнено поле «{label}»")
        if not isinstance(project.organization_snapshot, dict) or not project.organization_snapshot:
            errors.append("отсутствует снимок организации")
        if not isinstance(project.opo_snapshot, dict) or not project.opo_snapshot:
            errors.append("отсутствует снимок ОПО")
        return ValidationItem(
            "Организация и ОПО",
            not errors,
            _message(errors, "Организация и ОПО выбраны"),
        )

    @staticmethod
    def _check_project_common(path: Path) -> ValidationItem:
        data, read_error = _read_json(path)
        errors = [read_error] if read_error else []
        if read_error is None:
            if not isinstance(data, dict):
                errors.append("корневой элемент должен быть объектом")
            else:
                for key, label in (
                    ("project_name", "название проекта"),
                    ("project_code", "шифр проекта"),
                ):
                    if not str(data.get(key, "")).strip():
                        errors.append(f"не заполнено поле «{label}»")
                executor = data.get("executor")
                if not isinstance(executor, dict):
                    errors.append("поле executor должно быть объектом")
                elif not str(executor.get("name", "")).strip():
                    errors.append("не заполнено наименование разработчика")
        return ValidationItem(
            "Данные проекта",
            not errors,
            _message(errors, "Данные проекта заполнены"),
            path,
        )

    @staticmethod
    def _check_substances(path: Path) -> tuple[ValidationItem, set[int]]:
        data, read_error = _read_json(path)
        errors = [read_error] if read_error else []
        ids: set[int] = set()
        if read_error is None:
            if not isinstance(data, list) or not data:
                errors.append("список веществ должен быть непустым массивом")
            else:
                for index, substance in enumerate(data, start=1):
                    prefix = f"вещество {index}"
                    if not isinstance(substance, dict):
                        errors.append(f"{prefix}: ожидается объект")
                        continue
                    substance_id = substance.get("id")
                    if isinstance(substance_id, bool) or not isinstance(substance_id, int) or substance_id <= 0:
                        errors.append(f"{prefix}: id должен быть положительным целым")
                    elif substance_id in ids:
                        errors.append(f"{prefix}: id {substance_id} повторяется")
                    else:
                        ids.add(substance_id)
                    if not str(substance.get("name", "")).strip():
                        errors.append(f"{prefix}: не заполнено название")
                    kind = substance.get("kind")
                    if isinstance(kind, bool) or not isinstance(kind, int) or kind not in range(10):
                        errors.append(f"{prefix}: kind должен быть от 0 до 9")
        item = ValidationItem(
            "Вещества",
            not errors,
            _message(
                errors,
                f"Проверено веществ: {len(data) if isinstance(data, list) else 0}",
            ),
            path,
        )
        return item, ids

    @staticmethod
    def _check_equipment(path: Path, substance_ids: set[int]) -> ValidationItem:
        data, read_error = _read_json(path)
        errors = [read_error] if read_error else []
        if read_error is None:
            if not isinstance(data, list) or not data:
                errors.append("список оборудования должен быть непустым массивом")
            else:
                for index, equipment in enumerate(data, start=1):
                    prefix = f"оборудование {index}"
                    if not isinstance(equipment, dict):
                        errors.append(f"{prefix}: ожидается объект")
                        continue
                    equipment_type = equipment.get("equipment_type")
                    if isinstance(equipment_type, bool) or not isinstance(equipment_type, int) or equipment_type not in range(10):
                        errors.append(f"{prefix}: equipment_type должен быть от 0 до 9")
                    substance_id = equipment.get("substance_id")
                    if not substance_ids:
                        errors.append(f"{prefix}: невозможно проверить substance_id — вещества не готовы")
                    elif substance_id not in substance_ids:
                        errors.append(f"{prefix}: substance_id {substance_id!r} отсутствует в substances.json")
                    hazard_component = str(
                        equipment.get("hazard_component", "")
                    ).strip()
                    if not hazard_component:
                        errors.append(f"{prefix}: не заполнена составляющая ОПО")
                    has_without = "(без КМ)" in hazard_component
                    has_with = "(с КМ)" in hazard_component
                    if has_without and has_with:
                        errors.append(
                            f"{prefix}: одновременно указаны (без КМ) и (с КМ)"
                        )
                    elif has_without and not hazard_component.endswith("(без КМ)"):
                        errors.append(f"{prefix}: отметка (без КМ) должна быть в конце")
                    elif has_with and not hazard_component.endswith("(с КМ)"):
                        errors.append(f"{prefix}: отметка (с КМ) должна быть в конце")
                    if equipment.get("phase_state") not in PHASE_STATES:
                        errors.append(f"{prefix}: недопустимое phase_state")
                    pressure = equipment.get("pressure_mpa")
                    if not _number(pressure) or float(pressure) < 0.1:
                        errors.append(f"{prefix}: pressure_mpa должен быть не меньше 0,1")
                    coord_type = equipment.get("coord_type")
                    if isinstance(coord_type, bool) or not isinstance(coord_type, int) or coord_type not in (0, 1, 2):
                        errors.append(f"{prefix}: coord_type должен быть 0, 1 или 2")
                    coordinates = equipment.get("coordinates")
                    if (
                        not isinstance(coordinates, list)
                        or len(coordinates) < 2
                        or any(not _number(value) for value in coordinates)
                    ):
                        errors.append(f"{prefix}: coordinates должен иметь формат [0, 0, ...]")
                    fill_fraction = equipment.get("fill_fraction")
                    if not _number(fill_fraction) or not 0 < float(fill_fraction) <= 1:
                        errors.append(f"{prefix}: fill_fraction должен быть больше 0 и не больше 1")
                    clutter_degree = equipment.get("clutter_degree")
                    if isinstance(clutter_degree, bool) or not isinstance(clutter_degree, int) or clutter_degree not in range(1, 5):
                        errors.append(f"{prefix}: clutter_degree должен быть от 1 до 4")
                    if equipment_type in PIPELINE_TYPES:
                        total = equipment.get("total_length_m")
                        accident = equipment.get("accident_section_length_m")
                        diameter = equipment.get("diameter_mm")
                        wall = equipment.get("wall_thickness_mm")
                        for value, field in (
                            (total, "total_length_m"),
                            (accident, "accident_section_length_m"),
                            (diameter, "diameter_mm"),
                            (wall, "wall_thickness_mm"),
                        ):
                            if not _positive(value):
                                errors.append(f"{prefix}: {field} должен быть больше нуля")
                        if _number(total) and _number(accident) and float(accident) > float(total):
                            errors.append(f"{prefix}: аварийный участок больше полной длины")
                        if _number(diameter) and _number(wall) and float(wall) * 2 >= float(diameter):
                            errors.append(f"{prefix}: толщина стенки недопустима")
                    elif isinstance(equipment_type, int) and equipment_type in range(1, 9):
                        if not _positive(equipment.get("equipment_count")):
                            errors.append(f"{prefix}: equipment_count должен быть больше нуля")
                        if not _positive(equipment.get("volume_m3")):
                            errors.append(f"{prefix}: volume_m3 должен быть больше нуля")
        return ValidationItem(
            "Оборудование",
            not errors,
            _message(
                errors,
                "Проверено единиц/участков: "
                f"{len(data) if isinstance(data, list) else 0}",
            ),
            path,
        )
