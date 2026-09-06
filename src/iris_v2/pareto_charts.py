import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris_v2.risk_calculation import FILE_NAME as RISK_FILE_NAME


CHARTS = (
    (
        "collective_risk_fatalities",
        "pareto_fatalities.png",
        "Pareto-диаграмма сценариев по коллективному риску гибели",
        "Коллективный риск гибели, чел./год",
    ),
    (
        "collective_risk_injured",
        "pareto_injured.png",
        "Pareto-диаграмма сценариев по коллективному риску травмирования",
        "Коллективный риск травмирования, чел./год",
    ),
    (
        "total_damage",
        "pareto_damage.png",
        "Pareto-диаграмма сценариев по суммарному ущербу",
        "Суммарный ущерб, тыс. руб.",
    ),
    (
        "total_environmental_damage",
        "pareto_environmental_damage.png",
        "Pareto-диаграмма сценариев по экологическому ущербу",
        "Экологический ущерб, тыс. руб.",
    ),
)


class ParetoChartsError(Exception):
    pass


@dataclass(frozen=True)
class ParetoChartsResult:
    directory: Path
    fatalities_path: Path
    injured_path: Path
    damage_path: Path
    environmental_damage_path: Path
    scenario_count: int


def _number(value: Any, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value < 0
    ):
        raise ValueError(f"{name} должно быть числом не меньше нуля")
    return float(value)


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ParetoChartsError(
            f"Файл не найден: {RISK_FILE_NAME}. Сначала рассчитайте риски"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ParetoChartsError(f"Не удалось прочитать {RISK_FILE_NAME}") from exc
    values = data.get("results") if isinstance(data, dict) else None
    if not isinstance(values, list) or not values:
        raise ParetoChartsError(f"{RISK_FILE_NAME} не содержит результатов")

    rows: list[dict[str, Any]] = []
    codes: set[str] = set()
    fields = tuple(chart[0] for chart in CHARTS)
    for index, value in enumerate(values, start=1):
        if not isinstance(value, dict):
            raise ParetoChartsError(f"Результат {index}: ожидается объект")
        try:
            code = str(value.get("scenario_code", "")).strip()
            equipment = str(value.get("equipment_name", "")).strip()
            if not code or code in codes:
                raise ValueError("пустой или повторяющийся scenario_code")
            if not equipment:
                raise ValueError("equipment_name не заполнено")
            codes.add(code)
            row = {"scenario_code": code, "equipment_name": equipment}
            for field in fields:
                row[field] = _number(value.get(field), field)
        except ValueError as exc:
            code = str(value.get("scenario_code", index))
            raise ParetoChartsError(f"Сценарий {code}: {exc}") from exc
        rows.append(row)
    return rows


def build_pareto_series(
    rows: list[dict[str, Any]], value_key: str
) -> list[tuple[str, float]]:
    series = [
        (
            f"{row['equipment_name']} / {row['scenario_code']}",
            float(row[value_key]),
        )
        for row in rows
    ]
    series.sort(key=lambda item: item[1], reverse=True)
    return series


def limit_pareto_series(
    series: list[tuple[str, float]], top_n: int = 20
) -> list[tuple[str, float]]:
    if len(series) <= top_n:
        return list(series)
    result = list(series[:top_n])
    other_sum = sum(value for _, value in series[top_n:])
    if other_sum > 0:
        result.append(("Прочие", other_sum))
    return result


def _save_chart(
    series: list[tuple[str, float]],
    path: Path,
    title: str,
    ylabel: str,
) -> None:
    from matplotlib import pyplot as plt

    limited = limit_pareto_series(series)
    if limited and limited[-1][0] == "Прочие":
        drawn = limited[:-1]
    else:
        drawn = limited
    labels = [label for label, _ in drawn]
    values = [value for _, value in drawn]
    total = sum(value for _, value in series)
    cumulative: list[float] = []
    running = 0.0
    for value in values:
        running += value
        cumulative.append(100.0 * running / total if total > 0 else 0.0)

    positions = list(range(len(values)))
    figure, axis = plt.subplots(figsize=(12, 6))
    axis.bar(positions, values)
    axis.set_ylabel(ylabel)
    axis.set_title(title)
    axis.set_xticks(positions)
    axis.set_xticklabels(labels, rotation=90, fontsize=7)
    axis.grid(True, axis="y")

    share_axis = axis.twinx()
    share_axis.plot(
        positions,
        cumulative,
        color="orange",
        marker="o",
        linewidth=2,
    )
    share_axis.set_ylabel("Накопленная доля, %")
    share_axis.set_ylim(0, 105)
    share_axis.axhline(80, color="red", linestyle="--", linewidth=1.5)
    figure.tight_layout()
    figure.savefig(path, format="png", dpi=200, bbox_inches="tight")
    plt.close(figure)


class ParetoChartsService:
    def calculate(self, project_directory: Path | str) -> ParetoChartsResult:
        project = Path(project_directory)
        if not project.is_dir():
            raise ParetoChartsError(f"Папка проекта не найдена: {project}")
        rows = _read_rows(project / RISK_FILE_NAME)
        output_directory = project / "output" / "charts"
        temporary_paths: list[Path] = []
        final_paths: dict[str, Path] = {}
        try:
            import matplotlib

            matplotlib.use("Agg")
            output_directory.mkdir(parents=True, exist_ok=True)
            for field, file_name, title, ylabel in CHARTS:
                final_path = output_directory / file_name
                temporary_path = output_directory / f".{file_name}.tmp"
                temporary_paths.append(temporary_path)
                _save_chart(
                    build_pareto_series(rows, field),
                    temporary_path,
                    title,
                    ylabel,
                )
                final_paths[field] = final_path
            for field, file_name, _, _ in CHARTS:
                temporary = output_directory / f".{file_name}.tmp"
                temporary.replace(final_paths[field])
        except ImportError as exc:
            raise ParetoChartsError(
                "Не установлен matplotlib. Выполните: python -m pip install -e ."
            ) from exc
        except OSError as exc:
            raise ParetoChartsError("Не удалось сохранить диаграммы Парето") from exc
        except Exception as exc:
            raise ParetoChartsError(
                f"Не удалось построить диаграммы Парето: {exc}"
            ) from exc
        finally:
            for path in temporary_paths:
                path.unlink(missing_ok=True)

        return ParetoChartsResult(
            directory=output_directory,
            fatalities_path=final_paths["collective_risk_fatalities"],
            injured_path=final_paths["collective_risk_injured"],
            damage_path=final_paths["total_damage"],
            environmental_damage_path=final_paths[
                "total_environmental_damage"
            ],
            scenario_count=len(rows),
        )
