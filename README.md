# IRIS v2 — минимальное ядро

Поддерживается Python 3.10.

## Установка

```powershell
python -m pip install -e ".[dev]"
```

## Создание проекта

```powershell
iris-v2 create "D:\IRIS_projects\Test" `
  --name "Тестовый проект" `
  --code "TEST-001" `
  --organization "АО Пример" `
  --opo "Тестовый ОПО" `
  --registration-number "А00-00000-0000"
```

## Открытие проекта

```powershell
iris-v2 open "D:\IRIS_projects\Test"
```

Папка проекта содержит `project.sqlite3`, `project.json`, `input` и `output`.

## Окно программы

```powershell
python main.py
```

Также окно можно запустить командой `iris-v2-gui`.
