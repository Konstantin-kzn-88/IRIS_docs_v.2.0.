import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris_v2.risk_summary import FILE_NAME as SUMMARY_FILE_NAME


FN_FILE_NAME = "fn_chart.png"
FG_FILE_NAME = "fg_chart.png"


class RiskChartsError(Exception):
    pass


@dataclass(frozen=True)
class RiskChartsResult:
    directory: Path
    fn_path: Path
    fg_path: Path
    fn_point_count: int
    fg_point_count: int


def _number(value: Any, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value < 0
    ):
        raise ValueError(f"{name} должно быть числом не меньше нуля")
    return float(value)


def _read_points(path: Path) -> tuple[list[tuple[int, float]], list[tuple[float, float]]]:
    if not path.is_file():
        raise RiskChartsError(
            f"Файл не найден: {SUMMARY_FILE_NAME}. Сначала сформируйте свод риска"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RiskChartsError(f"Не удалось прочитать {SUMMARY_FILE_NAME}") from exc
    if not isinstance(data, dict):
        raise RiskChartsError(f"{SUMMARY_FILE_NAME} должен содержать объект")

    fn_source = data.get("fn_points")
    fg_source = data.get("fg_points")
    if not isinstance(fn_source, list) or not isinstance(fg_source, list):
        raise RiskChartsError(f"{SUMMARY_FILE_NAME} не содержит точек F/N и F/G")

    fn_points: list[tuple[int, float]] = []
    for index, point in enumerate(fn_source, start=1):
        try:
            if not isinstance(point, dict):
                raise ValueError("ожидается объект")
            fatalities = point.get("fatalities_count")
            if isinstance(fatalities, bool) or not isinstance(fatalities, int):
                raise ValueError("fatalities_count должно быть целым числом")
            frequency = _number(
                point.get("cumulative_frequency"), "cumulative_frequency"
            )
            if fatalities < 0 or frequency <= 0:
                raise ValueError("координаты точки должны быть больше нуля")
        except ValueError as exc:
            raise RiskChartsError(f"Точка F/N {index}: {exc}") from exc
        fn_points.append((fatalities, frequency))

    fg_points: list[tuple[float, float]] = []
    for index, point in enumerate(fg_source, start=1):
        try:
            if not isinstance(point, dict):
                raise ValueError("ожидается объект")
            damage = _number(point.get("damage_million_rub"), "damage_million_rub")
            frequency = _number(
                point.get("cumulative_frequency"), "cumulative_frequency"
            )
            if frequency <= 0:
                raise ValueError("частота должна быть больше нуля")
        except ValueError as exc:
            raise RiskChartsError(f"Точка F/G {index}: {exc}") from exc
        fg_points.append((damage, frequency))

    fn_points.sort(key=lambda point: point[0])
    fg_points.sort(key=lambda point: point[0])
    if not any(fatalities > 0 for fatalities, _ in fn_points):
        raise RiskChartsError("Для F/N нет сценариев с погибшими")
    if not any(damage > 0 for damage, _ in fg_points):
        raise RiskChartsError("Для F/G нет сценариев с положительным ущербом")
    return fn_points, fg_points


def _save_fn_chart(points: list[tuple[int, float]], path: Path) -> None:
    from matplotlib import pyplot as plt
    from matplotlib.ticker import MaxNLocator, MultipleLocator

    plot_points = [(x, y) for x, y in points if x > 0]
    people = [point[0] for point in plot_points]
    frequencies = [point[1] for point in plot_points]
    solid_x: list[float | None] = []
    solid_y: list[float | None] = []
    dashed_x: list[float] = []
    dashed_y: list[float] = []
    for fatalities, frequency in plot_points:
        solid_x.extend([max(0, fatalities - 1), fatalities, None])
        solid_y.extend([frequency, frequency, None])
    for index, (fatalities, frequency) in enumerate(plot_points):
        if index + 1 < len(plot_points):
            dashed_x.extend([fatalities, fatalities])
            dashed_y.extend([frequency, frequencies[index + 1]])

    fig, axis = plt.subplots(figsize=(8, 5))
    axis.semilogy(solid_x, solid_y, color="blue", linestyle="-", marker=".")
    axis.semilogy(dashed_x, dashed_y, color="blue", linestyle="--", marker=".")
    axis.set_title("F/N-диаграмма")
    axis.set_xlabel("Количество погибших N, чел.")
    axis.set_ylabel("Накопленная частота F(N), 1/год")
    axis.grid(True, which="both")
    axis.xaxis.set_major_locator(MultipleLocator(1))
    axis.xaxis.set_minor_locator(MaxNLocator(integer=True))
    axis.set_xticks(sorted(set(people)))
    axis.set_xlim(max(0, min(people) - 1), max(people))
    fig.tight_layout()
    fig.savefig(path, format="png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def _save_fg_chart(points: list[tuple[float, float]], path: Path) -> None:
    from matplotlib import pyplot as plt

    plot_points = [(x, y) for x, y in points if x > 0]
    damages = [point[0] for point in plot_points]
    frequencies = [point[1] for point in plot_points]
    solid_x: list[float | None] = []
    solid_y: list[float | None] = []
    dashed_x: list[float] = []
    dashed_y: list[float] = []
    previous_damage = 0.0
    for damage, frequency in plot_points:
        solid_x.extend([previous_damage, damage, None])
        solid_y.extend([frequency, frequency, None])
        previous_damage = damage
    for index, (damage, frequency) in enumerate(plot_points[:-1]):
        dashed_x.extend([damage, damage])
        dashed_y.extend([frequency, frequencies[index + 1]])

    fig, axis = plt.subplots(figsize=(8, 5))
    axis.semilogy(solid_x, solid_y, color="red", linestyle="-", marker=".")
    axis.semilogy(dashed_x, dashed_y, color="red", linestyle="--", marker=".")
    axis.set_title("F/G-диаграмма")
    axis.set_xlabel("Ущерб G, млн руб.")
    axis.set_ylabel("Накопленная частота F(G), 1/год")
    axis.grid(True, which="both")
    axis.set_xlim(0, max(damages) * 1.05)
    fig.tight_layout()
    fig.savefig(path, format="png", dpi=200, bbox_inches="tight")
    plt.close(fig)


class RiskChartsService:
    def calculate(self, project_directory: Path | str) -> RiskChartsResult:
        project = Path(project_directory)
        if not project.is_dir():
            raise RiskChartsError(f"Папка проекта не найдена: {project}")
        fn_points, fg_points = _read_points(project / SUMMARY_FILE_NAME)
        output_directory = project / "output" / "charts"
        try:
            import matplotlib

            matplotlib.use("Agg")
            output_directory.mkdir(parents=True, exist_ok=True)
            fn_path = output_directory / FN_FILE_NAME
            fg_path = output_directory / FG_FILE_NAME
            fn_temporary = output_directory / f".{FN_FILE_NAME}.tmp"
            fg_temporary = output_directory / f".{FG_FILE_NAME}.tmp"
            _save_fn_chart(fn_points, fn_temporary)
            _save_fg_chart(fg_points, fg_temporary)
            fn_temporary.replace(fn_path)
            fg_temporary.replace(fg_path)
        except ImportError as exc:
            raise RiskChartsError(
                "Не установлен matplotlib. Выполните: python -m pip install -e ."
            ) from exc
        except OSError as exc:
            raise RiskChartsError("Не удалось сохранить диаграммы риска") from exc
        except Exception as exc:
            raise RiskChartsError(f"Не удалось построить диаграммы: {exc}") from exc
        finally:
            if "fn_temporary" in locals():
                fn_temporary.unlink(missing_ok=True)
            if "fg_temporary" in locals():
                fg_temporary.unlink(missing_ok=True)

        return RiskChartsResult(
            directory=output_directory,
            fn_path=fn_path,
            fg_path=fg_path,
            fn_point_count=len(fn_points),
            fg_point_count=len(fg_points),
        )
