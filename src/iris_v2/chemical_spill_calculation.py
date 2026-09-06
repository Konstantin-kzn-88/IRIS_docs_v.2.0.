import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris_v2.hazard_factor_calculation import FILE_NAME as HAZARD_FACTOR_FILE_NAME


FILE_NAME = "chemical_spill_results.json"
CHEMICAL_SPILL_CALC_CODE = 7
NON_EVAPORATING_TOXIC_LIQUID_KIND = 6


class ChemicalSpillCalculationError(Exception):
    pass


@dataclass(frozen=True)
class ChemicalSpillCalculationResult:
    path: Path
    case_count: int
    chemical_spill_count: int
    results: tuple[dict[str, Any], ...]


class ChemicalSpillCalculationService:
    def calculate(
        self, project_directory: Path | str
    ) -> ChemicalSpillCalculationResult:
        project = Path(project_directory)
        if not project.is_dir():
            raise ChemicalSpillCalculationError(
                f"Папка проекта не найдена: {project}"
            )
        source_path = project / HAZARD_FACTOR_FILE_NAME
        if not source_path.is_file():
            raise ChemicalSpillCalculationError(
                f"Файл не найден: {source_path.name}. "
                "Сначала рассчитайте массу поражающего фактора"
            )
        try:
            source_data = json.loads(source_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ChemicalSpillCalculationError(
                f"Не удалось прочитать {source_path.name}"
            ) from exc

        values = (
            source_data.get("results")
            if isinstance(source_data, dict)
            else None
        )
        if not isinstance(values, list) or not values:
            raise ChemicalSpillCalculationError(
                f"{HAZARD_FACTOR_FILE_NAME} не содержит результатов"
            )

        results: list[dict[str, Any]] = []
        case_ids: set[int] = set()
        scenario_codes: set[str] = set()
        chemical_spill_count = 0
        for index, value in enumerate(values, start=1):
            if not isinstance(value, dict):
                raise ChemicalSpillCalculationError(
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
                raise ChemicalSpillCalculationError(
                    f"Результат {index}: недопустимый или повторяющийся id"
                )
            if not scenario_code or scenario_code in scenario_codes:
                raise ChemicalSpillCalculationError(
                    f"Результат {index}: пустой или повторяющийся scenario_code"
                )
            case_ids.add(case_id)
            scenario_codes.add(scenario_code)

            calc_code = value.get("calc_code")
            if isinstance(calc_code, bool) or not isinstance(calc_code, int):
                raise ChemicalSpillCalculationError(
                    f"Сценарий {scenario_code}: неверный calc_code"
                )
            applicable = calc_code == CHEMICAL_SPILL_CALC_CODE
            if applicable:
                if value.get("kind") != NON_EVAPORATING_TOXIC_LIQUID_KIND:
                    raise ChemicalSpillCalculationError(
                        f"Сценарий {scenario_code}: химически опасный пролив "
                        "допустим только для kind=6"
                    )
                area = value.get("spill_area_m2")
                if (
                    isinstance(area, bool)
                    or not isinstance(area, (int, float))
                    or not math.isfinite(float(area))
                    or area <= 0
                ):
                    raise ChemicalSpillCalculationError(
                        f"Сценарий {scenario_code}: spill_area_m2 "
                        "должна быть больше нуля"
                    )
                area = float(area)
                status = "calculated"
                chemical_spill_count += 1
            else:
                area = None
                status = "not_applicable"

            result = dict(value)
            result.update(
                {
                    "chemical_spill_applicable": applicable,
                    "chemical_spill_status": status,
                    "chemical_spill_status_name": (
                        "Площадь пролива определена"
                        if applicable
                        else "Сценарий не является химически опасным проливом"
                    ),
                    "chemical_spill_area_m2": area,
                    "chemical_spill_formula": (
                        "spill_area_m2"
                        if applicable
                        else "не применяется"
                    ),
                }
            )
            results.append(result)

        result_data = {
            "format_version": 1,
            "case_count": len(results),
            "chemical_spill_count": chemical_spill_count,
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
            raise ChemicalSpillCalculationError(
                f"Не удалось сохранить {path}"
            ) from exc

        return ChemicalSpillCalculationResult(
            path=path,
            case_count=len(results),
            chemical_spill_count=chemical_spill_count,
            results=tuple(results),
        )
