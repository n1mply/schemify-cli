"""config.json: данные студента и настройки генерации."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

OUTPUT_FORMATS = ("png", "svg", "drawio")


@dataclass
class Student:
    full_name: str = ""      # «Иванов И.И.»
    subject: str = ""
    group: str = ""

    def is_complete(self) -> bool:
        return bool(self.full_name and self.subject and self.group)


@dataclass
class Config:
    student: Student = field(default_factory=Student)
    output_format: str = "png"          # png | svg | drawio
    humanize: bool = True               # очеловечивать подписи узлов
    inputs_dir: str = "inputs"
    output_dir: str = "output"
    path: Path = field(default=Path("config.json"), repr=False)

    # ------------------------------------------------------------------ io
    @classmethod
    def load(cls, path: Path) -> "Config":
        cfg = cls(path=path)
        if not path.is_file():
            cfg.save()                  # первый запуск: кладём конфиг с дефолтами
            return cfg
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict):
                raise ValueError("корень должен быть объектом")
        except (OSError, ValueError) as error:
            print(f"! Не удалось прочитать {path.name} ({error}), использую значения по умолчанию.")
            return cfg

        st = data.get("student") if isinstance(data.get("student"), dict) else {}
        cfg.student = Student(
            full_name=str(st.get("full_name", "")).strip(),
            subject=str(st.get("subject", "")).strip(),
            group=str(st.get("group", "")).strip(),
        )
        fmt = str(data.get("output_format", "png")).strip().lower().lstrip(".")
        if fmt not in OUTPUT_FORMATS:
            print(f"! В конфиге неизвестный output_format {fmt!r} "
                  f"(допустимо: {', '.join(OUTPUT_FORMATS)}), использую png.")
            fmt = "png"
        cfg.output_format = fmt
        if isinstance(data.get("humanize"), bool):
            cfg.humanize = data["humanize"]
        for key in ("inputs_dir", "output_dir"):
            if isinstance(data.get(key), str) and data[key].strip():
                setattr(cfg, key, data[key].strip())
        return cfg

    def save(self) -> None:
        data = {
            "student": {
                "full_name": self.student.full_name,
                "subject": self.student.subject,
                "group": self.student.group,
            },
            "output_format": self.output_format,
            "humanize": self.humanize,
            "inputs_dir": self.inputs_dir,
            "output_dir": self.output_dir,
        }
        try:
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
        except OSError as error:
            print(f"! Не удалось сохранить {self.path.name}: {error}")

    # ------------------------------------------------------------- helpers
    def resolve(self, root: Path, name: str) -> Path:
        p = Path(getattr(self, name))
        return p if p.is_absolute() else root / p
