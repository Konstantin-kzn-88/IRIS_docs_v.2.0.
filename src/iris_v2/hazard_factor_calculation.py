import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris_v2.calculation_config import (
    CalculationConfigError,
    CalculationConfigService,
)
from iris_v2.evaporation_calculation import FILE_NAME as EVAPORATION_FILE_NAME


FILE_NAME = "hazard_factor_results.json"
PURE_GAS_KINDS = {2, 3}
CALC_CODE_NAMES = {
    0: "ликвидация аварии",
    1: "пожар пролива",
    2: "взрыв облака",
    3: "пожар-вспышка",
    4: "токсическое поражение",
    5: "факельное горение",
    6: "огненный шар",
    7: "химически опасный пролив",
}
SOURCE_NAMES = {
    "none": "Поражающий фактор отсутствует",
    "accident_mass": "Вся масса вещества в аварии",
    "evaporated_mass": "Вся испарившаяся масса",
    "cloud_from_accident": "Доля вышедшей массы в облаке",
    "cloud_from_evaporation": "Доля испарившейся массы в облаке",
    "bleve_mass": "Доля массы, участвующая в BLEVE",
}


class HazardFactorCalculationError(Exception):
    pass


@dataclass(frozen=True)
class HazardFactorCalculationResult:
    path: Path
    case_count: int
    active_count: int
    results: tuple[dict[str, Any], ...]


def _number(
    value: Any,
    label: str,
    *,
    non_negative: bool = False,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise HazardFactorCalculationError(f"{label} должно быть числом")
    result = float(value)
    if non_negative and result < 0:
        raise HazardFactorCalculationError(f"{label} не может быть отрицательным")
    return result


def calculate_hazard_factor_mass(
    calc_code: int,
    kind: int,
    accident_mass_t: float,
    evaporated_mass_t: float | None,
    flammable_cloud_fraction: float,
    bleve_fraction: float,
) -> tuple[float, str, str]:
    """Return mass, source code and formula for one calculation scenario."""
    if calc_code == 0:
        return 0.0, "none", "0"
    if calc_code in {1, 5, 7}:
        return accident_mass_t, "accident_mass", "ov_in_accident_t"
    if calc_code == 2:
        if evaporated_mass_t is not None:
            return (
                evaporated_mass_t * flammable_cloud_fraction,
                "cloud_from_evaporation",
                "evaporated_mass_t × flammable_cloud_fraction",
            )
        return (
            accident_mass_t * flammable_cloud_fraction,
            "cloud_from_accident",
            "ov_in_accident_t × flammable_cloud_fraction",
        )
    if calc_code == 3:
        if evaporated_mass_t is not None:
            return (
                evaporated_mass_t,
                "evaporated_mass",
                "evaporated_mass_t",
            )
        if kind in PURE_GAS_KINDS:
            return accident_mass_t, "accident_mass", "ov_in_accident_t"
        return (
            accident_mass_t * flammable_cloud_fraction,
            "cloud_from_accident",
            "ov_in_accident_t × flammable_cloud_fraction",
        )
    if calc_code == 4:
        if evaporated_mass_t is not None:
            return (
                evaporated_mass_t,
                "evaporated_mass",
                "evaporated_mass_t",
            )
        return accident_mass_t, "accident_mass", "ov_in_accident_t"
    if calc_code == 6:
        return (
            accident_mass_t * bleve_fraction,
            "bleve_mass",
            "ov_in_accident_t × bleve_fraction",
        )
    raise HazardFactorCalculationError(
        f"Не задано правило для calc_code={calc_code}"
    )


class HazardFactorCalculationService:
    def calculate(
        self, project_directory: Path | str
    ) -> HazardFactorCalculationResult:
        project = Path(project_directory)
        if not project.is_dir():
            raise HazardFactorCalculationError(
                f"Папка проекта не найдена: {project}"
            )

        source_path = project / EVAPORATION_FILE_NAME
        if not source_path.is_file():
            raise HazardFactorCalculationError(
                f"Файл не найден: {EVAPORATION_FILE_NAME}. "
                "Сначала рассчитайте испарение"
            )
        try:
            source_data = json.loads(source_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HazardFactorCalculationError(
                f"Не удалось прочитать {EVAPORATION_FILE_NAME}"
            ) from exc
        values = (
            source_data.get("results")
            if isinstance(source_data, dict)
            else None
        )
        if not isinstance(values, list) or not values:
            raise HazardFactorCalculationError(
                f"{EVAPORATION_FILE_NAME} не содержит результатов"
            )

        try:
            config = CalculationConfigService().load(project)
        except CalculationConfigError as exc:
            raise HazardFactorCalculationError(str(exc)) from exc
        cloud_fraction = _number(
            config.get("flammable_cloud_fraction"),
            "flammable_cloud_fraction",
            non_negative=True,
        )
        bleve_fraction = _number(
            config.get("bleve_fraction"),
            "bleve_fraction",
            non_negative=True,
        )
        if not 0 < cloud_fraction <= 1 or not 0 < bleve_fraction <= 1:
            raise HazardFactorCalculationError(
                "Доли облака и BLEVE должны быть больше 0 и не больше 1"
            )

        results: list[dict[str, Any]] = []
        case_ids: set[int] = set()
        scenario_codes: set[str] = set()
        active_count = 0
        for index, value in enumerate(values, start=1):
            if not isinstance(value, dict):
                raise HazardFactorCalculationError(
                    f"Результат испарения {index}: ожидается объект"
                )
            case_id = value.get("id")
            scenario_code = str(value.get("scenario_code", "")).strip()
            if (
                isinstance(case_id, bool)
                or not isinstance(case_id, int)
                or case_id <= 0
                or case_id in case_ids
            ):
                raise HazardFactorCalculationError(
                    f"Результат испарения {index}: "
                    "недопустимый или повторяющийся id"
                )
            if not scenario_code or scenario_code in scenario_codes:
                raise HazardFactorCalculationError(
                    f"Результат испарения {index}: "
                    "пустой или повторяющийся scenario_code"
                )
            case_ids.add(case_id)
            scenario_codes.add(scenario_code)

            calc_code = value.get("calc_code")
            kind = value.get("kind")
            if (
                isinstance(calc_code, bool)
                or not isinstance(calc_code, int)
                or calc_code not in CALC_CODE_NAMES
            ):
                raise HazardFactorCalculationError(
                    f"Сценарий {scenario_code}: calc_code должен быть от 0 до 7"
                )
            if (
                isinstance(kind, bool)
                or not isinstance(kind, int)
                or kind not in range(10)
            ):
                raise HazardFactorCalculationError(
                    f"Сценарий {scenario_code}: kind должен быть от 0 до 9"
                )

            accident_mass = _number(
                value.get("ov_in_accident_t"),
                f"Сценарий {scenario_code}: ov_in_accident_t",
                non_negative=True,
            )
            evaporation_applicable = value.get("evaporation_applicable")
            if not isinstance(evaporation_applicable, bool):
                raise HazardFactorCalculationError(
                    f"Сценарий {scenario_code}: evaporation_applicable должен "
                    "быть логическим значением"
                )
            evaporated_raw = value.get("evaporated_mass_t")
            if evaporation_applicable:
                evaporated_mass = _number(
                    evaporated_raw,
                    f"Сценарий {scenario_code}: evaporated_mass_t",
                    non_negative=True,
                )
                if evaporated_mass > accident_mass:
                    raise HazardFactorCalculationError(
                        f"Сценарий {scenario_code}: испарившаяся масса не может "
                        "превышать массу вещества в аварии"
                    )
            else:
                if evaporated_raw is not None:
                    raise HazardFactorCalculationError(
                        f"Сценарий {scenario_code}: устаревший результат "
                        "испарения. Повторите предыдущий расчёт"
                    )
                evaporated_mass = None

            mass, source, formula = calculate_hazard_factor_mass(
                calc_code,
                kind,
                accident_mass,
                evaporated_mass,
                cloud_fraction,
                bleve_fraction,
            )
            if not math.isfinite(mass) or mass < 0:
                raise HazardFactorCalculationError(
                    f"Сценарий {scenario_code}: получена недопустимая масса"
                )

            factor_flow = None
            if calc_code == 5:
                factor_flow = _number(
                    value.get("flow_kg_s"),
                    f"Сценарий {scenario_code}: flow_kg_s",
                    non_negative=True,
                )
                if factor_flow <= 0:
                    raise HazardFactorCalculationError(
                        f"Сценарий {scenario_code}: для факельного горения "
                        "flow_kg_s должен быть больше нуля"
                    )

            active = calc_code != 0
            if active:
                active_count += 1
            result = dict(value)
            result.update(
                {
                    "hazard_factor_applicable": active,
                    "hazard_factor_status": "calculated" if active else "none",
                    "hazard_factor_status_name": (
                        "Масса рассчитана"
                        if active
                        else "Поражающий фактор отсутствует"
                    ),
                    "hazard_factor_source": source,
                    "hazard_factor_source_name": SOURCE_NAMES[source],
                    "flammable_cloud_fraction": cloud_fraction,
                    "bleve_fraction": bleve_fraction,
                    "ov_in_hazard_factor_t": mass,
                    "hazard_factor_flow_kg_s": factor_flow,
                    "hazard_factor_formula": formula,
                }
            )
            results.append(result)

        result_data = {
            "format_version": 1,
            "case_count": len(results),
            "active_count": active_count,
            "constants": {
                "flammable_cloud_fraction": cloud_fraction,
                "bleve_fraction": bleve_fraction,
            },
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
            raise HazardFactorCalculationError(
                f"Не удалось сохранить {path}"
            ) from exc

        return HazardFactorCalculationResult(
            path=path,
            case_count=len(results),
            active_count=active_count,
            results=tuple(results),
        )
