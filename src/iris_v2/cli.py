import argparse
import json
import sys
from dataclasses import asdict

from iris_v2.service import CreateProjectData, ProjectError, ProjectService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="iris-v2")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="Создать проект")
    create.add_argument("path")
    create.add_argument("--name", required=True)
    create.add_argument("--code", required=True)
    create.add_argument("--organization", required=True)
    create.add_argument("--opo", required=True)
    create.add_argument("--registration-number", required=True)

    open_command = commands.add_parser("open", help="Открыть проект")
    open_command.add_argument("path")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    service = ProjectService()
    try:
        if args.command == "create":
            result = service.create(
                args.path,
                CreateProjectData(
                    name=args.name,
                    code=args.code,
                    organization_name=args.organization,
                    opo_name=args.opo,
                    opo_registration_number=args.registration_number,
                ),
            )
        else:
            result = service.open(args.path)
    except ProjectError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
