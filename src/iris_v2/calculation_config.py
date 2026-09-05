import copy
import json
import math
from pathlib import Path
from typing import Any


FILE_NAME = "calculation_config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "partial_release_fraction": 0.125,
    "flammable_cloud_fraction": 0.1,
    "bleve_fraction": 0.15,
    "partial_spill_fraction": 0.12,
    "wind_speed_m_s": 1.0,
    "evaporation_coefficient": 1.0,
    "liquid_leak_hole_diameter_mm": 20.0,
    "gas_leak_hole_diameter_mm": 20.0,
    "damage_scale": 30.3,
    "frequency_multipliers": {
        "standard": 1.0,
        "without_compensation": 1.25,
        "with_compensation": 0.6,
    },
}


class CalculationConfigError(Exception):
    pass


def new_calculation_config() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_CONFIG)


def _number(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise CalculationConfigError(f"Поле «{label}» должно быть числом")
    return float(value)


class CalculationConfigService:
    def load(self, project_directory: Path | str) -> dict[str, Any]:
        path = Path(project_directory) / FILE_NAME
        if not path.is_file():
            return new_calculation_config()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CalculationConfigError(f"Не удалось прочитать {path}") from exc
        if not isinstance(raw, dict):
            raise CalculationConfigError(
                "Корневой элемент calculation_config.json должен быть объектом"
            )

        result = new_calculation_config()
        result.update(raw)
        multipliers = dict(DEFAULT_CONFIG["frequency_multipliers"])
        raw_multipliers = raw.get("frequency_multipliers", {})
        if not isinstance(raw_multipliers, dict):
            raise CalculationConfigError(
                "Поле frequency_multipliers должно быть объектом"
            )
        multipliers.update(raw_multipliers)
        result["frequency_multipliers"] = multipliers
        self.validate(result)
        return result

    def save(
        self, project_directory: Path | str, data: dict[str, Any]
    ) -> Path:
        self.validate(data)
        directory = Path(project_directory)
        if not directory.is_dir():
            raise CalculationConfigError(f"Папка проекта не найдена: {directory}")
        path = directory / FILE_NAME
        temporary_path = directory / f".{FILE_NAME}.tmp"
        try:
            temporary_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary_path.replace(path)
        except OSError as exc:
            raise CalculationConfigError(f"Не удалось сохранить {path}") from exc
        return path

    @staticmethod
    def validate(data: dict[str, Any]) -> None:
        if not isinstance(data, dict):
            raise CalculationConfigError("Настройки расчёта должны быть объектом")

        for key, label in (
            ("partial_release_fraction", "Доля частичной разгерметизации"),
            ("flammable_cloud_fraction", "Доля вещества в облаке"),
            ("bleve_fraction", "Доля вещества в огненном шаре"),
            ("partial_spill_fraction", "Доля частичного пролива"),
        ):
            value = _number(data.get(key), label)
            if not 0 < value <= 1:
                raise CalculationConfigError(
                    f"Поле «{label}» должно быть больше 0 и не больше 1"
                )

        for key, label in (
            ("wind_speed_m_s", "Скорость ветра"),
            ("evaporation_coefficient", "Коэффициент испарения"),
            ("liquid_leak_hole_diameter_mm", "Отверстие истечения жидкости"),
            ("gas_leak_hole_diameter_mm", "Отверстие истечения газа"),
            ("damage_scale", "Масштаб ущерба"),
        ):
            if _number(data.get(key), label) <= 0:
                raise CalculationConfigError(
                    f"Поле «{label}» должно быть больше нуля"
                )

        multipliers = data.get("frequency_multipliers")
        if not isinstance(multipliers, dict):
            raise CalculationConfigError(
                "Поле frequency_multipliers должно быть объектом"
            )
        standard = _number(multipliers.get("standard"), "Стандартный множитель")
        if standard != 1.0:
            raise CalculationConfigError(
                "Стандартный множитель должен быть равен 1"
            )
        for key, label in (
            ("without_compensation", "Множитель без КМ"),
            ("with_compensation", "Множитель с КМ"),
        ):
            if _number(multipliers.get(key), label) <= 0:
                raise CalculationConfigError(
                    f"Поле «{label}» должно быть больше нуля"
                )
