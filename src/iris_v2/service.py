import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from iris_v2.database import create_database_engine, upgrade_database
from iris_v2.models import Project
from iris_v2.template_catalog import TemplateCatalogError, TemplateCatalogService


DATABASE_NAME = "project.sqlite3"
MANIFEST_NAME = "project.json"


class ProjectError(Exception):
    pass


@dataclass(frozen=True)
class CreateProjectData:
    name: str
    code: str
    organization_name: str
    opo_name: str
    opo_registration_number: str
    organization_snapshot: dict | None = None
    opo_snapshot: dict | None = None

    def validate(self) -> None:
        for field_name in (
            "name",
            "code",
            "organization_name",
            "opo_name",
            "opo_registration_number",
        ):
            value = getattr(self, field_name)
            if not value.strip():
                raise ProjectError(f"Не заполнено поле: {field_name}")


@dataclass(frozen=True)
class ProjectInfo:
    id: str
    name: str
    code: str
    organization_name: str
    opo_name: str
    opo_registration_number: str
    created_at: str
    organization_snapshot: dict
    opo_snapshot: dict


class ProjectService:
    def create(self, project_directory: Path | str, data: CreateProjectData) -> ProjectInfo:
        data.validate()
        target = Path(project_directory).resolve()
        if target.exists():
            raise ProjectError(f"Папка уже существует: {target}")

        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent))
        try:
            (temporary / "input").mkdir()
            (temporary / "output").mkdir()

            project_id = str(uuid4())
            created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            organization_snapshot = data.organization_snapshot or {
                "short_name": data.organization_name.strip()
            }
            opo_snapshot = data.opo_snapshot or {
                "name": data.opo_name.strip(),
                "registration_number": data.opo_registration_number.strip(),
            }
            database_path = temporary / DATABASE_NAME
            upgrade_database(database_path)

            engine = create_database_engine(database_path)
            try:
                with Session(engine) as session, session.begin():
                    session.add(
                        Project(
                            id=project_id,
                            name=data.name.strip(),
                            code=data.code.strip(),
                            organization_name=data.organization_name.strip(),
                            opo_name=data.opo_name.strip(),
                            opo_registration_number=data.opo_registration_number.strip(),
                            organization_snapshot_json=json.dumps(
                                organization_snapshot, ensure_ascii=False
                            ),
                            opo_snapshot_json=json.dumps(
                                opo_snapshot, ensure_ascii=False
                            ),
                            created_at=created_at,
                        )
                    )
            finally:
                engine.dispose()

            manifest = {"format_version": 1, "project_id": project_id}
            (temporary / MANIFEST_NAME).write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            try:
                TemplateCatalogService().select(temporary, "default")
            except TemplateCatalogError as exc:
                raise ProjectError(
                    f"Не удалось добавить шаблон default: {exc}"
                ) from exc
            temporary.replace(target)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise

        return self.open(target)

    def open(self, project_directory: Path | str) -> ProjectInfo:
        root = Path(project_directory).resolve()
        database_path = root / DATABASE_NAME
        manifest_path = root / MANIFEST_NAME
        if not database_path.is_file() or not manifest_path.is_file():
            raise ProjectError("Это не папка проекта IRIS v2")

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProjectError("Файл project.json повреждён") from exc

        upgrade_database(database_path)
        engine = create_database_engine(database_path)
        try:
            with Session(engine) as session:
                project = session.scalar(select(Project))
                if project is None or project.id != manifest.get("project_id"):
                    raise ProjectError("Данные проекта повреждены")
                return ProjectInfo(
                    id=project.id,
                    name=project.name,
                    code=project.code,
                    organization_name=project.organization_name,
                    opo_name=project.opo_name,
                    opo_registration_number=project.opo_registration_number,
                    created_at=project.created_at,
                    organization_snapshot=json.loads(
                        project.organization_snapshot_json
                    ),
                    opo_snapshot=json.loads(project.opo_snapshot_json),
                )
        finally:
            engine.dispose()

    def update_personnel(
        self,
        project_directory: Path | str,
        employees_count: int,
        employees_other_opo_count: int,
        presence_probability: float = 1.0,
    ) -> ProjectInfo:
        for value, label in (
            (employees_count, "Численность работников ОПО"),
            (employees_other_opo_count, "Численность людей на соседних ОПО"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ProjectError(f"{label} должна быть целым числом не меньше нуля")
        if (
            isinstance(presence_probability, bool)
            or not isinstance(presence_probability, (int, float))
            or not 0 <= float(presence_probability) <= 1
        ):
            raise ProjectError("Вероятность присутствия должна быть от 0 до 1")

        root = Path(project_directory).resolve()
        database_path = root / DATABASE_NAME
        if not database_path.is_file():
            raise ProjectError(f"База проекта не найдена: {database_path}")

        upgrade_database(database_path)
        engine = create_database_engine(database_path)
        try:
            with Session(engine) as session, session.begin():
                project = session.scalar(select(Project))
                if project is None:
                    raise ProjectError("Данные проекта повреждены")
                try:
                    opo_snapshot = json.loads(project.opo_snapshot_json)
                except json.JSONDecodeError as exc:
                    raise ProjectError("Снимок ОПО в базе проекта повреждён") from exc
                if not isinstance(opo_snapshot, dict):
                    raise ProjectError("Снимок ОПО в базе проекта должен быть объектом")
                personnel = opo_snapshot.get("personnel", {})
                if not isinstance(personnel, dict):
                    personnel = {}
                personnel.update(
                    {
                        "employees_count": employees_count,
                        "employees_other_opo_count": employees_other_opo_count,
                        "presence_probability": float(presence_probability),
                    }
                )
                opo_snapshot["personnel"] = personnel
                project.opo_snapshot_json = json.dumps(
                    opo_snapshot, ensure_ascii=False
                )
        finally:
            engine.dispose()
        return self.open(root)
