import hashlib
import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path


CONFIG_FILE_NAME = "report_config.json"


class TemplateCatalogError(Exception):
    pass


@dataclass(frozen=True)
class TemplateDocument:
    name: str
    path: Path
    size: int
    sha256: str


@dataclass(frozen=True)
class TemplateProfile:
    name: str
    directory: Path
    documents: tuple[TemplateDocument, ...]


@dataclass(frozen=True)
class TemplateSelectionResult:
    config_path: Path
    snapshot_directory: Path
    profile_name: str
    documents: tuple[TemplateDocument, ...]


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _document(path: Path) -> TemplateDocument:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise TemplateCatalogError(f"Не удалось прочитать шаблон: {path}") from exc
    if size <= 0 or not zipfile.is_zipfile(path):
        raise TemplateCatalogError(f"Файл не является документом DOCX: {path}")
    try:
        with zipfile.ZipFile(path) as archive:
            if "word/document.xml" not in archive.namelist():
                raise TemplateCatalogError(
                    f"Файл не является документом DOCX: {path}"
                )
        checksum = _hash_file(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise TemplateCatalogError(f"Не удалось прочитать шаблон: {path}") from exc
    return TemplateDocument(
        name=path.name,
        path=path,
        size=size,
        sha256=checksum,
    )


class TemplateCatalogService:
    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else Path.cwd() / "templates"

    def ensure_root(self) -> Path:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise TemplateCatalogError(
                f"Не удалось создать папку шаблонов: {self.root}"
            ) from exc
        return self.root

    def load(self) -> tuple[TemplateProfile, ...]:
        root = self.ensure_root()
        profiles: list[TemplateProfile] = []
        for directory in sorted(
            (item for item in root.iterdir() if item.is_dir()),
            key=lambda item: item.name.casefold(),
        ):
            paths = sorted(
                (
                    item
                    for item in directory.iterdir()
                    if item.is_file() and item.suffix.casefold() == ".docx"
                ),
                key=lambda item: item.name.casefold(),
            )
            if not paths:
                continue
            names = [path.name.casefold() for path in paths]
            if len(names) != len(set(names)):
                raise TemplateCatalogError(
                    f"В варианте {directory.name} повторяются имена документов"
                )
            profiles.append(
                TemplateProfile(
                    name=directory.name,
                    directory=directory,
                    documents=tuple(_document(path) for path in paths),
                )
            )
        return tuple(profiles)

    def select(
        self,
        project_directory: Path | str,
        profile_name: str,
    ) -> TemplateSelectionResult:
        project = Path(project_directory)
        if not project.is_dir() or not (project / "project.json").is_file():
            raise TemplateCatalogError(f"Это не папка проекта IRIS v2: {project}")
        selected = next(
            (profile for profile in self.load() if profile.name == profile_name),
            None,
        )
        if selected is None:
            raise TemplateCatalogError(f"Вариант шаблонов не найден: {profile_name}")

        templates_directory = project / "input" / "templates"
        snapshot_directory = templates_directory / "selected"
        staging_directory = templates_directory / ".selected.tmp"
        try:
            templates_directory.mkdir(parents=True, exist_ok=True)
            shutil.rmtree(staging_directory, ignore_errors=True)
            staging_directory.mkdir()
            for document in selected.documents:
                shutil.copy2(document.path, staging_directory / document.name)

            config = {
                "format_version": 1,
                "template_profile": selected.name,
                "documents": [
                    {
                        "name": document.name,
                        "path": f"input/templates/selected/{document.name}",
                        "size": document.size,
                        "sha256": document.sha256,
                    }
                    for document in selected.documents
                ],
            }
            config_path = project / CONFIG_FILE_NAME
            temporary_config = project / f".{CONFIG_FILE_NAME}.tmp"
            temporary_config.write_text(
                json.dumps(config, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            shutil.rmtree(snapshot_directory, ignore_errors=True)
            staging_directory.replace(snapshot_directory)
            temporary_config.replace(config_path)
        except OSError as exc:
            shutil.rmtree(staging_directory, ignore_errors=True)
            if "temporary_config" in locals():
                temporary_config.unlink(missing_ok=True)
            raise TemplateCatalogError(
                "Не удалось сохранить выбранный комплект шаблонов"
            ) from exc

        snapshot_documents = tuple(
            TemplateDocument(
                name=document.name,
                path=snapshot_directory / document.name,
                size=document.size,
                sha256=document.sha256,
            )
            for document in selected.documents
        )
        return TemplateSelectionResult(
            config_path=config_path,
            snapshot_directory=snapshot_directory,
            profile_name=selected.name,
            documents=snapshot_documents,
        )
