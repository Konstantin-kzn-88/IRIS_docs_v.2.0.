import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris_v2.risk_calculation import FILE_NAME as RISK_FILE_NAME


PEOPLE_FILE_NAME = "risk_matrix.png"
DAMAGE_FILE_NAME = "risk_matrix_damage.png"


class RiskMatricesError(Exception):
    pass


@dataclass(frozen=True)
class RiskMatricesResult:
    directory: Path
    people_path: Path
    damage_path: Path
    people_point_count: int
    damage_point_count: int


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
        raise RiskMatricesError(
            f"Файл не найден: {RISK_FILE_NAME}. Сначала рассчитайте риски"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RiskMatricesError(f"Не удалось прочитать {RISK_FILE_NAME}") from exc
    values = data.get("results") if isinstance(data, dict) else None
    if not isinstance(values, list) or not values:
        raise RiskMatricesError(f"{RISK_FILE_NAME} не содержит результатов")

    rows: list[dict[str, Any]] = []
    scenario_codes: set[str] = set()
    for index, value in enumerate(values, start=1):
        if not isinstance(value, dict):
            raise RiskMatricesError(f"Результат {index}: ожидается объект")
        try:
            scenario_code = str(value.get("scenario_code", "")).strip()
            if not scenario_code or scenario_code in scenario_codes:
                raise ValueError("пустой или повторяющийся scenario_code")
            scenario_codes.add(scenario_code)
            fatalities = value.get("fatalities_count")
            if (
                isinstance(fatalities, bool)
                or not isinstance(fatalities, int)
                or fatalities < 0
            ):
                raise ValueError(
                    "fatalities_count должно быть целым числом не меньше нуля"
                )
            rows.append(
                {
                    "scenario_code": scenario_code,
                    "fatalities_count": fatalities,
                    "scenario_frequency": _number(
                        value.get("scenario_frequency"), "scenario_frequency"
                    ),
                    "total_damage_million_rub": _number(
                        value.get("total_damage"), "total_damage"
                    )
                    / 1000.0,
                }
            )
        except ValueError as exc:
            code = str(value.get("scenario_code", index))
            raise RiskMatricesError(f"Сценарий {code}: {exc}") from exc
    return rows


def _point_sizes(frequencies: list[float]) -> list[float]:
    minimum = min(frequencies)
    maximum = max(frequencies)
    denominator = math.log10(maximum) - math.log10(minimum)
    if denominator <= 0:
        return [55.0] * len(frequencies)
    return [
        25.0
        + 60.0
        * (math.log10(frequency) - math.log10(minimum))
        / denominator
        for frequency in frequencies
    ]


def _label_codes(
    points: list[tuple[float, float, str]],
) -> set[str]:
    most_probable = sorted(points, key=lambda point: point[1], reverse=True)[:5]
    most_dangerous = sorted(
        points, key=lambda point: (point[0], point[1]), reverse=True
    )[:5]
    return {point[2] for point in most_probable + most_dangerous}


def _add_labels(axis: Any, points: list[tuple[float, float, str]]) -> None:
    codes = _label_codes(points)
    offsets = ((4, 3), (4, -10), (12, 6), (12, -14))
    number = 0
    for x, y, code in points:
        if code not in codes:
            continue
        axis.annotate(
            code,
            (x, y),
            textcoords="offset points",
            xytext=offsets[number % len(offsets)],
            fontsize=9,
        )
        number += 1


def _save_people_matrix(
    points: list[tuple[float, float, str]], path: Path
) -> None:
    from matplotlib import pyplot as plt
    from matplotlib.ticker import MultipleLocator

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    figure, axis = plt.subplots(figsize=(10, 5.5))
    axis.set_yscale("log")
    for frequency in (1e-1, 1e-2, 1e-3, 1e-4, 1e-5, 1e-6):
        color = "green" if frequency == 1e-6 else "red" if frequency == 1e-4 else "gray"
        axis.axhline(frequency, color=color, linestyle="--", linewidth=1.2)
    for fatalities in (1, 3, 10):
        axis.axvline(fatalities, color="gray", linewidth=1)
    axis.scatter(xs, ys, s=_point_sizes(ys))
    _add_labels(axis, points)
    axis.set_title("Матрица риска (частота – последствия)")
    axis.set_xlabel("Последствия: число погибших, чел.")
    axis.set_ylabel("Частота сценария, 1/год")
    axis.set_xlim(left=0, right=max(xs) + 1)
    axis.set_ylim(bottom=min(ys) / 2, top=max(ys) * 2)
    axis.xaxis.set_major_locator(MultipleLocator(1))
    axis.grid(True, which="both")
    figure.tight_layout()
    figure.savefig(path, format="png", dpi=200, bbox_inches="tight")
    plt.close(figure)


def _save_damage_matrix(
    points: list[tuple[float, float, str]], path: Path
) -> None:
    from matplotlib import pyplot as plt

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    figure, axis = plt.subplots(figsize=(10, 5.5))
    axis.set_yscale("log")
    axis.scatter(xs, ys, s=_point_sizes(ys))
    _add_labels(axis, points)
    axis.set_title("Матрица риска (частота – ущерб)")
    axis.set_xlabel("Последствия: суммарный ущерб, млн руб.")
    axis.set_ylabel("Частота сценария, 1/год")
    axis.set_xlim(left=0, right=max(xs) * 1.05)
    axis.set_ylim(bottom=min(ys) / 2, top=max(ys) * 2)
    axis.grid(True, which="both")
    figure.tight_layout()
    figure.savefig(path, format="png", dpi=200, bbox_inches="tight")
    plt.close(figure)


class RiskMatricesService:
    def calculate(self, project_directory: Path | str) -> RiskMatricesResult:
        project = Path(project_directory)
        if not project.is_dir():
            raise RiskMatricesError(f"Папка проекта не найдена: {project}")
        rows = _read_rows(project / RISK_FILE_NAME)
        people_points = [
            (
                float(row["fatalities_count"]),
                row["scenario_frequency"],
                row["scenario_code"],
            )
            for row in rows
            if row["fatalities_count"] >= 1 and row["scenario_frequency"] > 0
        ]
        damage_points = [
            (
                row["total_damage_million_rub"],
                row["scenario_frequency"],
                row["scenario_code"],
            )
            for row in rows
            if row["total_damage_million_rub"] > 0
            and row["scenario_frequency"] > 0
        ]
        if not people_points:
            raise RiskMatricesError("Нет сценариев с погибшими для матрицы риска")
        if not damage_points:
            raise RiskMatricesError("Нет сценариев с ущербом для матрицы риска")

        output_directory = project / "output" / "charts"
        try:
            import matplotlib

            matplotlib.use("Agg")
            output_directory.mkdir(parents=True, exist_ok=True)
            people_path = output_directory / PEOPLE_FILE_NAME
            damage_path = output_directory / DAMAGE_FILE_NAME
            people_temporary = output_directory / f".{PEOPLE_FILE_NAME}.tmp"
            damage_temporary = output_directory / f".{DAMAGE_FILE_NAME}.tmp"
            _save_people_matrix(people_points, people_temporary)
            _save_damage_matrix(damage_points, damage_temporary)
            people_temporary.replace(people_path)
            damage_temporary.replace(damage_path)
        except ImportError as exc:
            raise RiskMatricesError(
                "Не установлен matplotlib. Выполните: python -m pip install -e ."
            ) from exc
        except OSError as exc:
            raise RiskMatricesError("Не удалось сохранить матрицы риска") from exc
        except Exception as exc:
            raise RiskMatricesError(f"Не удалось построить матрицы риска: {exc}") from exc
        finally:
            if "people_temporary" in locals():
                people_temporary.unlink(missing_ok=True)
            if "damage_temporary" in locals():
                damage_temporary.unlink(missing_ok=True)

        return RiskMatricesResult(
            directory=output_directory,
            people_path=people_path,
            damage_path=damage_path,
            people_point_count=len(people_points),
            damage_point_count=len(damage_points),
        )
