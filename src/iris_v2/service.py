import json
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from iris_v2.database import create_database_engine, upgrade_database
from iris_v2.models import Project


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

    def validate(self) -> None:
        for field_name, value in asdict(self).items():
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
                            created_at=created_at,
                        )
                    )
            finally:
                engine.dispose()

            manifest = {"format_version": 1, "project_id": project_id}
            (temporary / MANIFEST_NAME).write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
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
                )
        finally:
            engine.dispose()

