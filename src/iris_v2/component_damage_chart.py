import json
import math
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris_v2.risk_summary import FILE_NAME as SUMMARY_FILE_NAME


FILE_NAME = "damage_by_component.png"


class ComponentDamageChartError(Exception):
    pass


@dataclass(frozen=True)
class ComponentDamageChartResult:
    path: Path
    component_count: int


def _number(value: Any, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value < 0
    ):
        raise ValueError(f"{name} должно быть числом не меньше нуля")
    return float(value)


def _read_components(path: Path) -> list[tuple[str, float, float]]:
    if not path.is_file():
        raise ComponentDamageChartError(
            f"Файл не найден: {SUMMARY_FILE_NAME}. Сначала сформируйте свод риска"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ComponentDamageChartError(
            f"Не удалось прочитать {SUMMARY_FILE_NAME}"
        ) from exc
    values = data.get("components") if isinstance(data, dict) else None
    if not isinstance(values, list) or not values:
        raise ComponentDamageChartError(
            f"{SUMMARY_FILE_NAME} не содержит составляющих ОПО"
        )

    result: list[tuple[str, float, float]] = []
    names: set[str] = set()
    for index, value in enumerate(values, start=1):
        if not isinstance(value, dict):
            raise ComponentDamageChartError(
                f"Составляющая {index}: ожидается объект"
            )
        try:
            name = str(value.get("hazard_component", "")).strip()
            if not name or name in names:
                raise ValueError("пустое или повторяющееся название")
            names.add(name)
            direct = _number(value.get("max_direct_losses"), "max_direct_losses")
            environmental = _number(
                value.get("max_total_environmental_damage"),
                "max_total_environmental_damage",
            )
        except ValueError as exc:
            raise ComponentDamageChartError(
                f"Составляющая {index}: {exc}"
            ) from exc
        if direct + environmental > 0:
            result.append((name, direct, environmental))
    if not result:
        raise ComponentDamageChartError(
            "Нет составляющих ОПО с положительным ущербом"
        )
    result.sort(key=lambda item: item[1] + item[2], reverse=True)
    return result


def _save_chart(rows: list[tuple[str, float, float]], path: Path) -> None:
    from matplotlib import pyplot as plt

    labels = [textwrap.fill(row[0], width=28) for row in rows]
    direct_values = [row[1] for row in rows]
    environmental_values = [row[2] for row in rows]
    minimum_for_log_scale = 1e-6
    direct_plot = [
        value if value > 0 else minimum_for_log_scale for value in direct_values
    ]
    environmental_plot = [
        value if value > 0 else minimum_for_log_scale
        for value in environmental_values
    ]

    positions = list(range(len(rows)))
    bar_height = 0.35
    figure_height = max(4.5, 0.55 * len(rows))
    figure, axis = plt.subplots(figsize=(14, figure_height))
    axis.barh(
        [position - bar_height / 2 for position in positions],
        direct_plot,
        height=bar_height,
        label="Прямой ущерб",
    )
    axis.barh(
        [position + bar_height / 2 for position in positions],
        environmental_plot,
        height=bar_height,
        label="Экологический ущерб",
    )
    axis.set_xscale("log")
    axis.set_yticks(positions)
    axis.set_yticklabels(labels)
    axis.invert_yaxis()
    axis.set_xlabel("Ущерб, тыс. руб. (логарифмическая шкала)")
    axis.set_ylabel("Составляющая ОПО")
    axis.set_title("Распределение ущерба по составляющим ОПО")
    axis.grid(True, axis="x", which="both")
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, format="png", dpi=300, bbox_inches="tight")
    plt.close(figure)


class ComponentDamageChartService:
    def calculate(
        self, project_directory: Path | str
    ) -> ComponentDamageChartResult:
        project = Path(project_directory)
        if not project.is_dir():
            raise ComponentDamageChartError(
                f"Папка проекта не найдена: {project}"
            )
        rows = _read_components(project / SUMMARY_FILE_NAME)
        output_directory = project / "output" / "charts"
        try:
            import matplotlib

            matplotlib.use("Agg")
            output_directory.mkdir(parents=True, exist_ok=True)
            path = output_directory / FILE_NAME
            temporary = output_directory / f".{FILE_NAME}.tmp"
            _save_chart(rows, temporary)
            temporary.replace(path)
        except ImportError as exc:
            raise ComponentDamageChartError(
                "Не установлен matplotlib. Выполните: python -m pip install -e ."
            ) from exc
        except OSError as exc:
            raise ComponentDamageChartError(
                "Не удалось сохранить диаграмму ущерба"
            ) from exc
        except Exception as exc:
            raise ComponentDamageChartError(
                f"Не удалось построить диаграмму ущерба: {exc}"
            ) from exc
        finally:
            if "temporary" in locals():
                temporary.unlink(missing_ok=True)

        return ComponentDamageChartResult(
            path=path,
            component_count=len(rows),
        )
