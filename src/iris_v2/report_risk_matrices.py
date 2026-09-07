from dataclasses import dataclass
from pathlib import Path

from iris_v2.risk_calculation import FILE_NAME as RISK_FILE_NAME
from iris_v2.risk_matrices import (
    DAMAGE_FILE_NAME,
    PEOPLE_FILE_NAME,
    RiskMatricesError,
    _read_rows,
    _save_damage_matrix,
    _save_people_matrix,
)


PEOPLE_MARKER = "{{RISK_MATRIX_CHART}}"
DAMAGE_MARKER = "{{RISK_MATRIX_DAMAGE_CHART}}"
PEOPLE_EMPTY_TEXT = (
    "Матрица риска по числу погибших не построена: "
    "сценарии с погибшими отсутствуют."
)
DAMAGE_EMPTY_TEXT = (
    "Матрица риска по ущербу не построена: "
    "сценарии с положительным ущербом отсутствуют."
)


@dataclass(frozen=True)
class ReportRiskMatrices:
    people_path: Path | None
    damage_path: Path | None


def prepare_risk_matrices(project_directory: Path | str) -> ReportRiskMatrices:
    project = Path(project_directory)
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
    output_directory = project / "output" / "charts"
    people_path = output_directory / PEOPLE_FILE_NAME if people_points else None
    damage_path = output_directory / DAMAGE_FILE_NAME if damage_points else None
    people_temporary = output_directory / f".{PEOPLE_FILE_NAME}.report.tmp"
    damage_temporary = output_directory / f".{DAMAGE_FILE_NAME}.report.tmp"
    try:
        if people_points or damage_points:
            import matplotlib

            matplotlib.use("Agg")
            output_directory.mkdir(parents=True, exist_ok=True)
        if people_points:
            _save_people_matrix(people_points, people_temporary)
        if damage_points:
            _save_damage_matrix(damage_points, damage_temporary)
        if people_points:
            people_temporary.replace(people_path)
        if damage_points:
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
        people_temporary.unlink(missing_ok=True)
        damage_temporary.unlink(missing_ok=True)
    return ReportRiskMatrices(
        people_path=people_path,
        damage_path=damage_path,
    )


__all__ = [
    "DAMAGE_EMPTY_TEXT",
    "DAMAGE_MARKER",
    "PEOPLE_EMPTY_TEXT",
    "PEOPLE_MARKER",
    "ReportRiskMatrices",
    "RiskMatricesError",
    "prepare_risk_matrices",
]
