import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris_v2.calculation_cases import FILE_NAME as CASES_FILE_NAME


FILE_NAME = "frequency_results.json"


class FrequencyCalculationError(Exception):
    pass


@dataclass(frozen=True)
class FrequencyCalculationResult:
    path: Path
    case_count: int
    total_frequency: float
    results: tuple[dict[str, Any], ...]


def _number(value: Any, label: str, *, positive: bool = False) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise FrequencyCalculationError(f"{label} должно быть числом")
    result = float(value)
    if positive and result <= 0:
        raise FrequencyCalculationError(f"{label} должно быть больше нуля")
    return result


class FrequencyCalculationService:
    def calculate(
        self, project_directory: Path | str
    ) -> FrequencyCalculationResult:
        project = Path(project_directory)
        if not project.is_dir():
            raise FrequencyCalculationError(f"Папка проекта не найдена: {project}")

        source = project / CASES_FILE_NAME
        if not source.is_file():
            raise FrequencyCalculationError(
                f"Файл не найден: {CASES_FILE_NAME}. "
                "Сначала сформируйте расчётные сценарии"
            )
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FrequencyCalculationError(
                f"Не удалось прочитать {CASES_FILE_NAME}"
            ) from exc
        cases = data.get("cases") if isinstance(data, dict) else None
        if not isinstance(cases, list) or not cases:
            raise FrequencyCalculationError(
                f"{CASES_FILE_NAME} не содержит расчётных сценариев"
            )

        results: list[dict[str, Any]] = []
        case_ids: set[int] = set()
        scenario_codes: set[str] = set()
        for index, case in enumerate(cases, start=1):
            if not isinstance(case, dict):
                raise FrequencyCalculationError(
                    f"Сценарий {index}: ожидается объект"
                )
            case_id = case.get("id")
            scenario_code = str(case.get("scenario_code", "")).strip()
            if (
                isinstance(case_id, bool)
                or not isinstance(case_id, int)
                or case_id <= 0
                or case_id in case_ids
            ):
                raise FrequencyCalculationError(
                    f"Сценарий {index}: недопустимый или повторяющийся id"
                )
            if not scenario_code or scenario_code in scenario_codes:
                raise FrequencyCalculationError(
                    f"Сценарий {index}: пустой или повторяющийся scenario_code"
                )
            case_ids.add(case_id)
            scenario_codes.add(scenario_code)

            base_frequency = _number(
                case.get("base_frequency"),
                f"Сценарий {scenario_code}: base_frequency",
                positive=True,
            )
            probability = _number(
                case.get("accident_event_probability"),
                f"Сценарий {scenario_code}: accident_event_probability",
            )
            if not 0 <= probability <= 1:
                raise FrequencyCalculationError(
                    f"Сценарий {scenario_code}: accident_event_probability "
                    "должна быть от 0 до 1"
                )
            unit_frequency = _number(
                case.get("unit_scenario_frequency"),
                f"Сценарий {scenario_code}: unit_scenario_frequency",
            )
            if unit_frequency < 0 or not math.isclose(
                unit_frequency,
                base_frequency * probability,
                rel_tol=1e-9,
                abs_tol=1e-18,
            ):
                raise FrequencyCalculationError(
                    f"Сценарий {scenario_code}: unit_scenario_frequency "
                    "не равна base_frequency × accident_event_probability"
                )
            frequency_basis = _number(
                case.get("frequency_basis"),
                f"Сценарий {scenario_code}: frequency_basis",
                positive=True,
            )
            frequency_multiplier = _number(
                case.get("frequency_multiplier"),
                f"Сценарий {scenario_code}: frequency_multiplier",
                positive=True,
            )
            basis_unit = str(case.get("frequency_basis_unit", "")).strip()
            if basis_unit not in {"м", "шт."}:
                raise FrequencyCalculationError(
                    f"Сценарий {scenario_code}: frequency_basis_unit "
                    "должна быть «м» или «шт.»"
                )

            result = dict(case)
            result["base_frequency_with_multiplier"] = (
                base_frequency * frequency_multiplier
            )
            result["scenario_frequency"] = (
                unit_frequency * frequency_basis * frequency_multiplier
            )
            results.append(result)

        total_frequency = sum(item["scenario_frequency"] for item in results)
        result_data = {
            "format_version": 1,
            "formula": (
                "unit_scenario_frequency × frequency_basis × "
                "frequency_multiplier"
            ),
            "case_count": len(results),
            "total_frequency": total_frequency,
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
            raise FrequencyCalculationError(f"Не удалось сохранить {path}") from exc

        return FrequencyCalculationResult(
            path=path,
            case_count=len(results),
            total_frequency=total_frequency,
            results=tuple(results),
        )
