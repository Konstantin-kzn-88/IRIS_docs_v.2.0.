import hashlib
import json
import math
import shutil
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from iris_v2.typical_scenarios import (
    TypicalScenario,
    TypicalScenarioCatalog,
    TypicalScenarioService,
)


DIRECTORY_NAME = "event_trees"
MANIFEST_FILE_NAME = "manifest.json"


class EventTreeImageError(Exception):
    pass


@dataclass
class _TreeNode:
    label: str
    children: dict[str, "_TreeNode"] = field(default_factory=dict)
    probability: float | None = None
    y: float = 0.0


@dataclass(frozen=True)
class EventTreeImageResult:
    directory: Path
    manifest_path: Path
    image_count: int
    files: tuple[Path, ...]


def _number(value: float) -> str:
    if math.isclose(value, round(value), abs_tol=1e-12):
        result = str(int(round(value)))
    else:
        result = f"{value:.6f}".rstrip("0").rstrip(".")
    return result.replace(".", ",")


def _wrapped(value: str, width: int = 27) -> str:
    return "\n".join(
        textwrap.wrap(
            value,
            width=width,
            break_long_words=False,
            break_on_hyphens=False,
        )
    )


def _tree(scenarios: tuple[TypicalScenario, ...]) -> _TreeNode:
    root = _TreeNode("Инициирующее событие")
    for scenario in scenarios:
        parts = [part.strip() for part in scenario.text.split("→") if part.strip()]
        if len(parts) < 2:
            raise EventTreeImageError(
                f"Сценарий {scenario.line} не образует ветвь дерева: {scenario.text}"
            )
        node = root
        for part in parts:
            node = node.children.setdefault(part, _TreeNode(part))
        if node.probability is not None:
            raise EventTreeImageError(
                f"Повторяется конечная ветвь сценария: {scenario.text}"
            )
        node.probability = scenario.event_probability
    return root


def _initiator_totals(
    scenarios: tuple[TypicalScenario, ...],
) -> dict[str, float]:
    totals: dict[str, float] = {}
    for scenario in scenarios:
        initiator = scenario.text.split("→", maxsplit=1)[0].strip()
        totals[initiator] = totals.get(initiator, 0.0) + scenario.event_probability
    return totals


def _depth(node: _TreeNode) -> int:
    if not node.children:
        return 0
    return 1 + max(_depth(child) for child in node.children.values())


def _place(node: _TreeNode, next_y: list[float]) -> None:
    if not node.children:
        node.y = next_y[0]
        next_y[0] += 1.0
        return
    for child in node.children.values():
        _place(child, next_y)
    values = [child.y for child in node.children.values()]
    node.y = (min(values) + max(values)) / 2.0


def _draw_node(
    axes: plt.Axes,
    node: _TreeNode,
    x: float,
    *,
    terminal: bool,
) -> None:
    width = 0.76
    height = 0.52 if terminal else 0.46
    facecolor = "#f3f3f3" if terminal else "white"
    box = FancyBboxPatch(
        (x - width / 2, node.y - height / 2),
        width,
        height,
        boxstyle="round,pad=0.025,rounding_size=0.025",
        linewidth=0.8,
        edgecolor="black",
        facecolor=facecolor,
        zorder=3,
    )
    axes.add_patch(box)
    label = _wrapped(node.label)
    if terminal:
        label += f"\nPитог = {_number(node.probability or 0.0)}"
    axes.text(
        x,
        node.y,
        label,
        ha="center",
        va="center",
        fontsize=7.3 if terminal else 7.0,
        linespacing=1.12,
        zorder=4,
    )


def _draw_tree(axes: plt.Axes, node: _TreeNode, x: int = 0) -> None:
    _draw_node(axes, node, float(x), terminal=not node.children)
    for child in node.children.values():
        start_x = x + 0.38
        end_x = x + 0.62
        middle_x = (start_x + end_x) / 2
        axes.plot(
            [start_x, middle_x, middle_x, end_x],
            [node.y, node.y, child.y, child.y],
            color="black",
            linewidth=0.8,
            zorder=1,
        )
        _draw_tree(axes, child, x + 1)


class EventTreeImageService:
    @staticmethod
    def bundled_directory() -> Path:
        return Path(__file__).parent / "data" / DIRECTORY_NAME

    def generate(
        self,
        output_directory: Path | str | None = None,
        *,
        catalog: TypicalScenarioCatalog | None = None,
        pairs: set[tuple[int, int]] | None = None,
    ) -> EventTreeImageResult:
        selected_catalog = catalog or TypicalScenarioService().load()
        directory = (
            Path(output_directory)
            if output_directory is not None
            else self.bundled_directory()
        )
        selected_pairs = sorted(
            pair
            for pair in selected_catalog.scenarios
            if pairs is None or pair in pairs
        )
        if not selected_pairs:
            raise EventTreeImageError("Не выбрано ни одного дерева событий")
        unknown = (pairs or set()) - set(selected_catalog.scenarios)
        if unknown:
            raise EventTreeImageError(
                f"Нет сценариев для сочетаний: {sorted(unknown)}"
            )

        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise EventTreeImageError(
                f"Не удалось создать папку изображений: {directory}"
            ) from exc

        files: list[Path] = []
        manifest_items: list[dict[str, object]] = []
        warnings: list[str] = []
        for equipment_type, kind in selected_pairs:
            scenarios = selected_catalog.scenarios[(equipment_type, kind)]
            initiator_totals = _initiator_totals(scenarios)
            for initiator, total in initiator_totals.items():
                if not math.isclose(total, 1.0, rel_tol=1e-9, abs_tol=1e-9):
                    warnings.append(
                        f"equipment_type={equipment_type}, kind={kind}, "
                        f"инициирующее событие «{initiator}»: "
                        f"сумма Pитог = {_number(total)}, а не 1"
                    )
            tree = _tree(scenarios)
            _place(tree, [0.0])
            leaf_count = len(scenarios)
            max_depth = _depth(tree)
            figure, axes = plt.subplots(
                figsize=(max(10.0, (max_depth + 1) * 2.55), max(4.2, leaf_count * 0.72 + 1.8)),
                dpi=180,
            )
            _draw_tree(axes, tree)
            axes.set_xlim(-0.48, max_depth + 0.48)
            axes.set_ylim(leaf_count - 0.35, -1.05)
            axes.axis("off")
            axes.set_title(
                f"Дерево событий: {selected_catalog.equipment_types[equipment_type]}\n"
                f"{selected_catalog.kinds[kind]}",
                fontsize=11,
                pad=10,
            )
            filename = f"event_tree_eq{equipment_type:02d}_kind{kind:02d}.png"
            path = directory / filename
            temporary = directory / f".{filename}.tmp.png"
            try:
                figure.savefig(
                    temporary,
                    format="png",
                    dpi=180,
                    facecolor="white",
                    bbox_inches="tight",
                    pad_inches=0.12,
                )
                temporary.replace(path)
            except OSError as exc:
                temporary.unlink(missing_ok=True)
                raise EventTreeImageError(
                    f"Не удалось сохранить изображение: {path}"
                ) from exc
            finally:
                plt.close(figure)
            files.append(path)
            manifest_items.append(
                {
                    "equipment_type": equipment_type,
                    "equipment_name": selected_catalog.equipment_types[equipment_type],
                    "kind": kind,
                    "kind_name": selected_catalog.kinds[kind],
                    "file": filename,
                    "scenario_count": len(scenarios),
                    "initiator_probability_totals": initiator_totals,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )

        manifest = {
            "format_version": 1,
            "source": selected_catalog.source_path.name,
            "image_format": "PNG",
            "probability_note": (
                "Pитог — accident_event_probability из typical_scenarios.json"
            ),
            "image_count": len(files),
            "warnings": warnings,
            "items": manifest_items,
        }
        manifest_path = directory / MANIFEST_FILE_NAME
        temporary_manifest = directory / f".{MANIFEST_FILE_NAME}.tmp"
        try:
            temporary_manifest.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary_manifest.replace(manifest_path)
        except OSError as exc:
            temporary_manifest.unlink(missing_ok=True)
            raise EventTreeImageError(
                f"Не удалось сохранить описание изображений: {manifest_path}"
            ) from exc
        return EventTreeImageResult(
            directory=directory,
            manifest_path=manifest_path,
            image_count=len(files),
            files=tuple(files),
        )

    def copy_to_project(
        self,
        project_directory: Path | str,
        *,
        pairs: set[tuple[int, int]] | None = None,
    ) -> EventTreeImageResult:
        project = Path(project_directory)
        if not project.is_dir() or not (project / "project.json").is_file():
            raise EventTreeImageError(f"Это не папка проекта IRIS v2: {project}")
        source = self.bundled_directory()
        manifest_path = source / MANIFEST_FILE_NAME
        if not manifest_path.is_file():
            raise EventTreeImageError("Комплект PNG-деревьев событий не найден")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EventTreeImageError("Не удалось прочитать комплект деревьев") from exc
        items = manifest.get("items") if isinstance(manifest, dict) else None
        if not isinstance(items, list):
            raise EventTreeImageError("Некорректный файл описания деревьев")

        destination = project / "output" / DIRECTORY_NAME
        destination.mkdir(parents=True, exist_ok=True)
        copied: list[Path] = []
        selected_items: list[dict[str, object]] = []
        for item in items:
            pair = (item.get("equipment_type"), item.get("kind"))
            if pairs is not None and pair not in pairs:
                continue
            filename = str(item.get("file", ""))
            source_path = source / filename
            if not filename or not source_path.is_file():
                raise EventTreeImageError(f"Не найден файл дерева: {filename}")
            target = destination / filename
            shutil.copy2(source_path, target)
            copied.append(target)
            selected_items.append(item)
        if pairs is not None and len(selected_items) != len(pairs):
            raise EventTreeImageError("Не для всех сочетаний найдены PNG-деревья")
        project_manifest = dict(manifest)
        project_manifest["image_count"] = len(selected_items)
        project_manifest["items"] = selected_items
        result_manifest = destination / MANIFEST_FILE_NAME
        result_manifest.write_text(
            json.dumps(project_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return EventTreeImageResult(
            directory=destination,
            manifest_path=result_manifest,
            image_count=len(copied),
            files=tuple(copied),
        )


def main() -> None:
    result = EventTreeImageService().generate()
    print(f"Сформировано PNG-деревьев: {result.image_count}")
    print(result.directory)


if __name__ == "__main__":
    main()
