import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris_v2.risk_calculation import FILE_NAME as RISK_FILE_NAME


FILE_NAME = "key_scenarios.json"


class KeyScenariosError(Exception):
    pass


@dataclass(frozen=True)
class KeyScenariosResult:
    path: Path
    component_count: int
    row_count: int
    rows: tuple[dict[str, Any], ...]


def _number(value: Any, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value < 0
    ):
        raise ValueError(f"{name} должно быть числом не меньше нуля")
    return float(value)


def _count(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} должно быть целым числом не меньше нуля")
    return value


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise KeyScenariosError(
            f"Файл не найден: {RISK_FILE_NAME}. Сначала рассчитайте риски"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KeyScenariosError(f"Не удалось прочитать {RISK_FILE_NAME}") from exc
    values = data.get("results") if isinstance(data, dict) else None
    if not isinstance(values, list) or not values:
        raise KeyScenariosError(f"{RISK_FILE_NAME} не содержит результатов")

    rows: list[dict[str, Any]] = []
    codes: set[str] = set()
    for index, value in enumerate(values, start=1):
        if not isinstance(value, dict):
            raise KeyScenariosError(f"Результат {index}: ожидается объект")
        try:
            code = str(value.get("scenario_code", "")).strip()
            component = str(value.get("hazard_component", "")).strip()
            equipment = str(value.get("equipment_name", "")).strip()
            scenario_text = str(value.get("scenario_text", "")).strip()
            if not code or code in codes:
                raise ValueError("пустой или повторяющийся scenario_code")
            if not component:
                raise ValueError("hazard_component не заполнено")
            if not equipment:
                raise ValueError("equipment_name не заполнено")
            if not scenario_text:
                raise ValueError("scenario_text не заполнено")
            codes.add(code)
            rows.append(
                {
                    "hazard_component": component,
                    "scenario_code": code,
                    "equipment_name": equipment,
                    "fatalities_count": _count(
                        value.get("fatalities_count"), "fatalities_count"
                    ),
                    "injured_count": _count(
                        value.get("injured_count"), "injured_count"
                    ),
                    "total_damage": _number(
                        value.get("total_damage"), "total_damage"
                    ),
                    "scenario_frequency": _number(
                        value.get("scenario_frequency"), "scenario_frequency"
                    ),
                    "scenario_text": scenario_text,
                }
            )
        except ValueError as exc:
            code = str(value.get("scenario_code", index))
            raise KeyScenariosError(f"Сценарий {code}: {exc}") from exc
    return rows


def select_key_scenarios(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        component = row["hazard_component"]
        if component not in selected:
            selected[component] = {"dangerous": row, "probable": row}
            continue

        dangerous = selected[component]["dangerous"]
        if row["fatalities_count"] > dangerous["fatalities_count"] or (
            row["fatalities_count"] == dangerous["fatalities_count"]
            and row["total_damage"] > dangerous["total_damage"]
        ):
            selected[component]["dangerous"] = row

        probable = selected[component]["probable"]
        if row["scenario_frequency"] > probable["scenario_frequency"]:
            selected[component]["probable"] = row

    result: list[dict[str, Any]] = []
    for component in sorted(selected):
        for scenario_type, type_name in (
            ("dangerous", "Наиболее опасный"),
            ("probable", "Наиболее вероятный"),
        ):
            row = dict(selected[component][scenario_type])
            row["scenario_type"] = scenario_type
            row["scenario_type_name"] = type_name
            result.append(row)
    return result


class KeyScenariosService:
    def calculate(self, project_directory: Path | str) -> KeyScenariosResult:
        project = Path(project_directory)
        if not project.is_dir():
            raise KeyScenariosError(f"Папка проекта не найдена: {project}")
        source_rows = _read_rows(project / RISK_FILE_NAME)
        rows = select_key_scenarios(source_rows)
        result_data = {
            "format_version": 1,
            "component_count": len(rows) // 2,
            "row_count": len(rows),
            "damage_unit": "тыс. руб.",
            "frequency_unit": "1/год",
            "selection_rules": {
                "dangerous": "максимум погибших, затем максимум ущерба",
                "probable": "максимум частоты сценария",
            },
            "rows": rows,
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
            raise KeyScenariosError(f"Не удалось сохранить {path}") from exc

        return KeyScenariosResult(
            path=path,
            component_count=len(rows) // 2,
            row_count=len(rows),
            rows=tuple(rows),
        )
