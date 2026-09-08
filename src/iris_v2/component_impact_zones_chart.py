import json
import math
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any


FILE_NAME = "max_impact_zones_by_component.png"
ZONE_SPECS = (
    (1, "q_1_4_m", "Пожар пролива: q=1,4 кВт/м²"),
    (2, "p_2_m", "Взрыв ТВС: P=2 кПа"),
    (3, "flash_fire_radius_m", "Пожар-вспышка: Rвсп"),
    (4, "threshold_radius_m", "Токсическое поражение: PD"),
)


class ComponentImpactZonesChartError(Exception):
    pass


@dataclass(frozen=True)
class ComponentImpactZonesChartResult:
    path: Path
    component_count: int


def _number(value: Any, label: str) -> float | None:
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0
    ):
        raise ComponentImpactZonesChartError(
            f"{label} должно быть числом не меньше нуля"
        )
    return float(value)


def read_component_zone_maxima(path: Path) -> list[tuple[str, tuple[float, ...]]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ComponentImpactZonesChartError(
            "Зоны поражающих факторов не рассчитаны"
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ComponentImpactZonesChartError(
            "Не удалось прочитать impact_zones.json"
        ) from exc
    results = raw.get("results") if isinstance(raw, dict) else None
    if not isinstance(results, list) or not results:
        raise ComponentImpactZonesChartError(
            "impact_zones.json не содержит результатов"
        )
    grouped: dict[str, list[float]] = {}
    for index, item in enumerate(results, start=1):
        if not isinstance(item, dict):
            raise ComponentImpactZonesChartError(
                f"Результат {index}: ожидается объект"
            )
        component = str(item.get("hazard_component", "")).strip()
        calc_code = item.get("calc_code")
        values = item.get("impact_values")
        if (
            not component
            or isinstance(calc_code, bool)
            or not isinstance(calc_code, int)
            or not isinstance(values, dict)
        ):
            raise ComponentImpactZonesChartError(
                f"Результат {index}: неверные данные составляющей или зон"
            )
        maxima = grouped.setdefault(component, [0.0] * len(ZONE_SPECS))
        for position, (required_code, field, _) in enumerate(ZONE_SPECS):
            if calc_code == required_code:
                value = _number(values.get(field), f"Результат {index}: {field}")
                if value is not None:
                    maxima[position] = max(maxima[position], value)
    rows = [(name, tuple(values)) for name, values in grouped.items()]
    return [row for row in rows if any(value > 0 for value in row[1])]


def _save_chart(rows: list[tuple[str, tuple[float, ...]]], path: Path) -> None:
    from matplotlib import pyplot as plt

    labels = [textwrap.fill(name, width=28) for name, _ in rows]
    positions = list(range(len(rows)))
    height = max(7.0, 0.55 * len(rows) + 3.0)
    figure, axes = plt.subplots(2, 2, figsize=(14, height), sharey=True)
    for axis, position, (_, _, title) in zip(axes.flat, range(4), ZONE_SPECS):
        values = [row[1][position] for row in rows]
        bars = axis.barh(positions, values, color="#4472C4")
        axis.set_title(title)
        axis.set_xlabel("Максимальный радиус, м")
        if any(value > 0 for value in values):
            axis.grid(True, axis="x", alpha=0.35)
            axis.margins(x=0.15)
        else:
            axis.set_xlim(0, 1)
            axis.set_xticks([])
            axis.text(
                0.5,
                0.5,
                "Нет данных",
                ha="center",
                va="center",
                transform=axis.transAxes,
                color="#666666",
            )
        axis.bar_label(
            bars,
            labels=[f"{value:.1f}" if value > 0 else "" for value in values],
            padding=3,
            fontsize=8,
        )
    for axis in axes[:, 0]:
        axis.set_yticks(positions)
        axis.set_yticklabels(labels)
    axes[0, 0].invert_yaxis()
    figure.suptitle("Максимальные зоны поражающих факторов по составляющим ОПО")
    figure.tight_layout()
    figure.savefig(path, format="png", dpi=300, bbox_inches="tight")
    plt.close(figure)


class ComponentImpactZonesChartService:
    def calculate(
        self, project_directory: Path | str
    ) -> ComponentImpactZonesChartResult:
        project = Path(project_directory)
        rows = read_component_zone_maxima(project / "impact_zones.json")
        if not rows:
            raise ComponentImpactZonesChartError(
                "Нет положительных радиусов зон для диаграммы"
            )
        output_directory = project / "output" / "charts"
        path = output_directory / FILE_NAME
        temporary = output_directory / f".{FILE_NAME}.tmp"
        try:
            import matplotlib

            matplotlib.use("Agg")
            output_directory.mkdir(parents=True, exist_ok=True)
            _save_chart(rows, temporary)
            temporary.replace(path)
        except ImportError as exc:
            raise ComponentImpactZonesChartError(
                "Не установлен matplotlib. Выполните: python -m pip install -e ."
            ) from exc
        except Exception as exc:
            raise ComponentImpactZonesChartError(
                f"Не удалось построить диаграмму зон: {exc}"
            ) from exc
        finally:
            temporary.unlink(missing_ok=True)
        return ComponentImpactZonesChartResult(path=path, component_count=len(rows))


__all__ = [
    "ComponentImpactZonesChartError",
    "ComponentImpactZonesChartResult",
    "ComponentImpactZonesChartService",
    "FILE_NAME",
    "ZONE_SPECS",
    "read_component_zone_maxima",
]
