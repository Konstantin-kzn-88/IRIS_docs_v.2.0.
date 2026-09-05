import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


FILE_NAME = "typical_scenarios.json"
EXTERNAL_DIRECTORY = "typical_scenarios"


class TypicalScenarioError(Exception):
    pass


@dataclass(frozen=True)
class TypicalScenario:
    line: int
    text: str
    base_frequency: float
    event_probability: float
    frequency: float
    calc_code: int


@dataclass(frozen=True)
class TypicalScenarioCatalog:
    source_path: Path
    equipment_types: dict[int, str]
    kinds: dict[int, str]
    calculation_types: dict[int, str]
    scenarios: dict[tuple[int, int], tuple[TypicalScenario, ...]]
    forbidden_pairs: dict[tuple[int, int], str]

    @property
    def pair_count(self) -> int:
        return len(self.scenarios)

    @property
    def scenario_count(self) -> int:
        return sum(len(items) for items in self.scenarios.values())

    def scenarios_for(
        self, equipment_type: int, kind: int
    ) -> tuple[TypicalScenario, ...]:
        return self.scenarios.get((equipment_type, kind), ())

    def forbidden_reason(self, equipment_type: int, kind: int) -> str | None:
        return self.forbidden_pairs.get((equipment_type, kind))


def _mapping(raw: Any, label: str, expected: set[int]) -> dict[int, str]:
    if not isinstance(raw, dict):
        raise TypicalScenarioError(f"Раздел {label} должен быть объектом")
    result: dict[int, str] = {}
    for key, value in raw.items():
        try:
            number = int(key)
        except (TypeError, ValueError) as exc:
            raise TypicalScenarioError(f"В разделе {label} недопустимый ключ {key!r}") from exc
        if str(number) != str(key) or number not in expected:
            raise TypicalScenarioError(f"В разделе {label} недопустимый код {key!r}")
        name = str(value).strip()
        if not name:
            raise TypicalScenarioError(f"В разделе {label} не заполнено название кода {number}")
        result[number] = name
    if set(result) != expected:
        missing = ", ".join(map(str, sorted(expected - set(result))))
        raise TypicalScenarioError(f"В разделе {label} отсутствуют коды: {missing}")
    return result


def _number(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise TypicalScenarioError(f"{label} должно быть числом")
    return float(value)


class TypicalScenarioService:
    @staticmethod
    def bundled_path() -> Path:
        return Path(__file__).parent / "data" / FILE_NAME

    @staticmethod
    def external_path() -> Path:
        return Path.cwd() / EXTERNAL_DIRECTORY / FILE_NAME

    def load(self, path: Path | str | None = None) -> TypicalScenarioCatalog:
        if path is None:
            external = self.external_path()
            source = external if external.is_file() else self.bundled_path()
        else:
            source = Path(path)
            if source.is_dir():
                source = source / FILE_NAME
        if not source.is_file():
            raise TypicalScenarioError(f"Файл не найден: {source}")
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TypicalScenarioError(f"Не удалось прочитать {source}: {exc}") from exc
        return self._validate(raw, source)

    @staticmethod
    def _validate(raw: Any, source: Path) -> TypicalScenarioCatalog:
        if not isinstance(raw, dict):
            raise TypicalScenarioError("Корневой элемент должен быть объектом")
        meta = raw.get("meta")
        scenarios_raw = raw.get("scenarios")
        if not isinstance(meta, dict) or not isinstance(scenarios_raw, dict):
            raise TypicalScenarioError("Обязательны разделы meta и scenarios")

        equipment_types = _mapping(
            meta.get("equipment_type_mapping"), "equipment_type_mapping", set(range(10))
        )
        kinds = _mapping(meta.get("kind_mapping"), "kind_mapping", set(range(10)))
        calculation_types = _mapping(
            meta.get("calc_code_mapping"), "calc_code_mapping", set(range(8))
        )

        forbidden_pairs: dict[tuple[int, int], str] = {}
        allowed_pairs = meta.get("allowed_pairs", {})
        if not isinstance(allowed_pairs, dict):
            raise TypicalScenarioError("Раздел allowed_pairs должен быть объектом")
        for equipment_key, kinds_raw in allowed_pairs.items():
            try:
                equipment_type = int(equipment_key)
            except (TypeError, ValueError) as exc:
                raise TypicalScenarioError("Недопустимый equipment_type в allowed_pairs") from exc
            if equipment_type not in equipment_types or not isinstance(kinds_raw, dict):
                raise TypicalScenarioError("Недопустимая запись в allowed_pairs")
            for kind_key, rule in kinds_raw.items():
                try:
                    kind = int(kind_key)
                except (TypeError, ValueError) as exc:
                    raise TypicalScenarioError("Недопустимый kind в allowed_pairs") from exc
                if kind not in kinds or not isinstance(rule, dict):
                    raise TypicalScenarioError("Недопустимая запись в allowed_pairs")
                if rule.get("allowed") is not False:
                    raise TypicalScenarioError(
                        "allowed_pairs должен содержать только явные запреты"
                    )
                reason = str(rule.get("reason", "")).strip()
                if not reason:
                    raise TypicalScenarioError("Для запрещённой пары не указана причина")
                forbidden_pairs[(equipment_type, kind)] = reason

        scenarios: dict[tuple[int, int], tuple[TypicalScenario, ...]] = {}
        for equipment_key, kinds_raw in scenarios_raw.items():
            try:
                equipment_type = int(equipment_key)
            except (TypeError, ValueError) as exc:
                raise TypicalScenarioError("Недопустимый equipment_type в scenarios") from exc
            if equipment_type not in equipment_types or not isinstance(kinds_raw, dict):
                raise TypicalScenarioError("Недопустимая запись в scenarios")
            for kind_key, items_raw in kinds_raw.items():
                try:
                    kind = int(kind_key)
                except (TypeError, ValueError) as exc:
                    raise TypicalScenarioError("Недопустимый kind в scenarios") from exc
                pair = (equipment_type, kind)
                if kind not in kinds or not isinstance(items_raw, list) or not items_raw:
                    raise TypicalScenarioError(f"Для пары {pair} отсутствуют сценарии")
                if pair in forbidden_pairs:
                    raise TypicalScenarioError(f"Запрещённая пара {pair} содержит сценарии")
                items: list[TypicalScenario] = []
                for index, item in enumerate(items_raw, start=1):
                    label = f"Сценарий {equipment_type}/{kind}/{index}"
                    if not isinstance(item, dict):
                        raise TypicalScenarioError(f"{label} должен быть объектом")
                    line = item.get("scenario_line")
                    if isinstance(line, bool) or not isinstance(line, int) or line != index:
                        raise TypicalScenarioError(f"{label}: scenario_line должен быть равен {index}")
                    text = str(item.get("scenario_text", "")).strip()
                    if not text:
                        raise TypicalScenarioError(f"{label}: не заполнен scenario_text")
                    base = _number(item.get("base_frequency"), f"{label}: base_frequency")
                    probability = _number(
                        item.get("accident_event_probability"),
                        f"{label}: accident_event_probability",
                    )
                    frequency = _number(
                        item.get("scenario_frequency"), f"{label}: scenario_frequency"
                    )
                    calc_code = item.get("calc_code")
                    if base <= 0 or not 0 <= probability <= 1 or frequency < 0:
                        raise TypicalScenarioError(f"{label}: недопустимые частота или вероятность")
                    if (
                        isinstance(calc_code, bool)
                        or not isinstance(calc_code, int)
                        or calc_code not in calculation_types
                    ):
                        raise TypicalScenarioError(f"{label}: недопустимый calc_code")
                    if not math.isclose(
                        frequency, base * probability, rel_tol=1e-9, abs_tol=1e-18
                    ):
                        raise TypicalScenarioError(
                            f"{label}: scenario_frequency не равна base_frequency × probability"
                        )
                    items.append(
                        TypicalScenario(line, text, base, probability, frequency, calc_code)
                    )
                scenarios[pair] = tuple(items)

        all_pairs = {
            (equipment_type, kind)
            for equipment_type in equipment_types
            for kind in kinds
        }
        classified = set(scenarios) | set(forbidden_pairs)
        if classified != all_pairs:
            missing = sorted(all_pairs - classified)
            raise TypicalScenarioError(f"Не описаны сочетания equipment_type/kind: {missing}")

        return TypicalScenarioCatalog(
            source.resolve(),
            equipment_types,
            kinds,
            calculation_types,
            scenarios,
            forbidden_pairs,
        )
