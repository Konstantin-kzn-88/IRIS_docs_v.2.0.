import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris_v2.typical_scenarios import (
    TypicalScenarioError,
    TypicalScenarioService,
)


FILE_NAME = "amount_results.json"
PIPELINE_TYPES = {0, 9}
PURE_GAS_KINDS = {2, 3, 7}


class AmountCalculationError(Exception):
    pass


@dataclass(frozen=True)
class AmountCalculationResult:
    path: Path
    equipment_count: int
    results: tuple[dict[str, Any], ...]


def _load_list(path: Path, label: str) -> list[dict[str, Any]]:
    if not path.is_file():
        raise AmountCalculationError(f"Файл не найден: {path.name}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AmountCalculationError(f"Не удалось прочитать {path.name}") from exc
    if not isinstance(data, list) or not data:
        raise AmountCalculationError(f"{label} должен быть непустым списком")
    if not all(isinstance(item, dict) for item in data):
        raise AmountCalculationError(f"{label} содержит запись неверного формата")
    return data


def _positive_number(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0
    ):
        raise AmountCalculationError(f"{label} должно быть числом больше нуля")
    return float(value)


def _density(
    physical: dict[str, Any],
    field: str,
    substance_name: str,
) -> float:
    return _positive_number(
        physical.get(field),
        f"Вещество {substance_name!r}: physical.{field}",
    )


def pipeline_internal_volume_m3(
    length_m: float,
    diameter_mm: float,
    wall_thickness_mm: float,
) -> tuple[float, float]:
    internal_diameter_mm = diameter_mm - 2.0 * wall_thickness_mm
    if internal_diameter_mm <= 0:
        raise AmountCalculationError(
            "Внутренний диаметр трубопровода должен быть больше нуля"
        )
    internal_diameter_m = internal_diameter_mm / 1000.0
    area_m2 = math.pi * internal_diameter_m**2 / 4.0
    return area_m2 * length_m, internal_diameter_mm


class AmountCalculationService:
    def calculate(
        self, project_directory: Path | str
    ) -> AmountCalculationResult:
        project = Path(project_directory)
        if not project.is_dir():
            raise AmountCalculationError(f"Папка проекта не найдена: {project}")

        substances = _load_list(project / "substances.json", "Вещества")
        equipment = _load_list(project / "equipments.json", "Оборудование")
        substance_by_id: dict[int, dict[str, Any]] = {}
        for index, substance in enumerate(substances, start=1):
            substance_id = substance.get("id")
            if (
                isinstance(substance_id, bool)
                or not isinstance(substance_id, int)
                or substance_id <= 0
                or substance_id in substance_by_id
            ):
                raise AmountCalculationError(
                    f"Вещество {index}: недопустимый или повторяющийся id"
                )
            name = str(substance.get("name", "")).strip()
            kind = substance.get("kind")
            physical = substance.get("physical")
            if not name:
                raise AmountCalculationError(f"Вещество {index}: не заполнено название")
            if isinstance(kind, bool) or not isinstance(kind, int) or kind not in range(10):
                raise AmountCalculationError(f"Вещество {index}: kind должен быть от 0 до 9")
            if not isinstance(physical, dict):
                raise AmountCalculationError(
                    f"Вещество {name!r}: physical должен быть объектом"
                )
            substance_by_id[substance_id] = substance

        try:
            catalog = TypicalScenarioService().load()
        except TypicalScenarioError as exc:
            raise AmountCalculationError(str(exc)) from exc

        results: list[dict[str, Any]] = []
        equipment_ids: set[int] = set()
        for index, item in enumerate(equipment, start=1):
            equipment_id = item.get("id")
            substance_id = item.get("substance_id")
            equipment_type = item.get("equipment_type")
            equipment_name = str(item.get("equipment_name", "")).strip()
            if (
                isinstance(equipment_id, bool)
                or not isinstance(equipment_id, int)
                or equipment_id <= 0
                or equipment_id in equipment_ids
            ):
                raise AmountCalculationError(
                    f"Оборудование {index}: недопустимый или повторяющийся id"
                )
            equipment_ids.add(equipment_id)
            if substance_id not in substance_by_id:
                raise AmountCalculationError(
                    f"Оборудование {index}: substance_id={substance_id} "
                    "отсутствует в substances.json"
                )
            if not equipment_name:
                raise AmountCalculationError(
                    f"Оборудование {index}: не заполнено название"
                )
            if (
                isinstance(equipment_type, bool)
                or not isinstance(equipment_type, int)
                or equipment_type not in catalog.equipment_types
            ):
                raise AmountCalculationError(
                    f"Оборудование {index}: equipment_type должен быть от 0 до 9"
                )

            substance = substance_by_id[substance_id]
            substance_name = str(substance["name"]).strip()
            kind = int(substance["kind"])
            if not catalog.scenarios_for(equipment_type, kind):
                reason = catalog.forbidden_reason(equipment_type, kind)
                raise AmountCalculationError(
                    f"Оборудование {index}: сочетание equipment_type={equipment_type}, "
                    f"kind={kind} недопустимо — {reason or 'сценарии отсутствуют'}"
                )
            physical = substance["physical"]

            internal_diameter_mm: float | None = None
            if equipment_type in PIPELINE_TYPES:
                length = _positive_number(
                    item.get("accident_section_length_m"),
                    f"Оборудование {index}: accident_section_length_m",
                )
                diameter = _positive_number(
                    item.get("diameter_mm"),
                    f"Оборудование {index}: diameter_mm",
                )
                wall = _positive_number(
                    item.get("wall_thickness_mm"),
                    f"Оборудование {index}: wall_thickness_mm",
                )
                volume_m3, internal_diameter_mm = pipeline_internal_volume_m3(
                    length, diameter, wall
                )
            else:
                volume_m3 = _positive_number(
                    item.get("volume_m3"),
                    f"Оборудование {index}: volume_m3",
                )

            liquid_volume_m3 = 0.0
            gas_volume_m3 = 0.0
            liquid_mass_t = 0.0
            gas_mass_t = 0.0
            if kind in PURE_GAS_KINDS:
                gas_volume_m3 = volume_m3
                gas_density = _density(
                    physical, "density_gas_kg_per_m3", substance_name
                )
                gas_mass_t = gas_volume_m3 * gas_density / 1000.0
                formula = "volume_m3 × density_gas_kg_per_m3 / 1000"
            elif equipment_type in PIPELINE_TYPES or equipment_type == 4:
                liquid_volume_m3 = volume_m3
                liquid_density = _density(
                    physical, "density_liquid_kg_per_m3", substance_name
                )
                liquid_mass_t = liquid_volume_m3 * liquid_density / 1000.0
                formula = "volume_m3 × density_liquid_kg_per_m3 / 1000"
            else:
                fill_fraction = _positive_number(
                    item.get("fill_fraction"),
                    f"Оборудование {index}: fill_fraction",
                )
                if fill_fraction > 1:
                    raise AmountCalculationError(
                        f"Оборудование {index}: fill_fraction не может быть больше 1"
                    )
                liquid_volume_m3 = volume_m3 * fill_fraction
                gas_volume_m3 = volume_m3 - liquid_volume_m3
                liquid_density = _density(
                    physical, "density_liquid_kg_per_m3", substance_name
                )
                liquid_mass_t = liquid_volume_m3 * liquid_density / 1000.0
                if gas_volume_m3 > 0:
                    gas_density = _density(
                        physical, "density_gas_kg_per_m3", substance_name
                    )
                    gas_mass_t = gas_volume_m3 * gas_density / 1000.0
                formula = (
                    "liquid_volume_m3 × density_liquid_kg_per_m3 / 1000 + "
                    "gas_volume_m3 × density_gas_kg_per_m3 / 1000"
                )

            results.append(
                {
                    "equipment_id": equipment_id,
                    "equipment_source_id": item.get("source_id"),
                    "equipment_name": equipment_name,
                    "equipment_type": equipment_type,
                    "equipment_type_name": catalog.equipment_types[equipment_type],
                    "substance_id": substance_id,
                    "substance_name": substance_name,
                    "kind": kind,
                    "kind_name": catalog.kinds[kind],
                    "hazard_component": str(
                        item.get("hazard_component", "")
                    ).strip(),
                    "volume_m3": volume_m3,
                    "internal_diameter_mm": internal_diameter_mm,
                    "liquid_volume_m3": liquid_volume_m3,
                    "gas_volume_m3": gas_volume_m3,
                    "liquid_mass_t": liquid_mass_t,
                    "gas_mass_t": gas_mass_t,
                    "amount_t": liquid_mass_t + gas_mass_t,
                    "formula": formula,
                }
            )

        result_data = {
            "format_version": 1,
            "equipment_count": len(results),
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
            raise AmountCalculationError(f"Не удалось сохранить {path}") from exc

        return AmountCalculationResult(
            path=path,
            equipment_count=len(results),
            results=tuple(results),
        )
