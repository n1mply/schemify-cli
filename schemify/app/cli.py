"""Диалог с пользователем и сценарии «вся лаба» / «одна схема»."""
from __future__ import annotations

import sys
from pathlib import Path

from schemify.app.config import Config, Student
from schemify.app.pipeline import FlowchartGenerator, scan_inputs
from schemify.app.prompts import ask, ask_choice, ask_yes_no
from schemify.renderers.svg import WatermarkInfo


class App:
    def __init__(self, root: Path, cfg: Config) -> None:
        self.root = root
        self.cfg = cfg
        self.inputs_dir = cfg.resolve(root, "inputs_dir")
        self.output_dir = cfg.resolve(root, "output_dir")
        self.generator = FlowchartGenerator(cfg, self.output_dir)

    # ----------------------------------------------------------------- run
    def run(self) -> None:
        print("=" * 52)
        print("  Schemify - блок-схемы по ГОСТ из кода на C")
        print("=" * 52)
        self._print_settings()
        while True:
            mode = ask_choice("\nЧто генерируем?", {"1": "Вся лаба", "2": "Одна схема"})
            if mode == "1":
                self.whole_lab()
            else:
                self.single()
            if not ask_yes_no("\nСделать ещё одну генерацию?", default=False):
                break
        print("Готово.")

    def _print_settings(self) -> None:
        c = self.cfg
        print(f"Формат: {c.output_format} | очеловечивание: {'вкл' if c.humanize else 'выкл'} "
              f"(меняется в {c.path.name})")
        if c.humanize and not self.generator.has_api_key:
            print("! LLM_API_KEY не найден в .env - сложные узлы ИИ обработаны не будут, "
                  "только локальные правила.")

    # ------------------------------------------------------------ scenarios
    def whole_lab(self) -> None:
        student, variant, lab_num = None, "", ""
        if ask_yes_no("Нужен штамп студента?", default=True):
            student, variant, lab_num = self._ask_stamp(with_task=False)

        out_dir = self.output_dir / (f"lab_{lab_num}" if lab_num else "lab")
        self.generator.output_dir = out_dir

        scan = self._wait_for_inputs()
        if scan is None:
            return

        print(f"\nГенерация ({self.cfg.output_format}) -> {out_dir}")
        done, failed = 0, 0
        for task in scan.tasks:
            print(f"  Задание {task.number} ({task.path.name})")
            watermark = None
            if student:
                watermark = _watermark(student, variant, lab_num, str(task.number))
            if self._generate_one(task.path, f"task{task.number}", watermark):
                done += 1
            else:
                failed += 1
        print(f"\nГотово: {done} из {len(scan.tasks)}"
              + (f", с ошибками: {failed}" if failed else "") + f". Папка: {out_dir}")

    def single(self) -> None:
        watermark = None
        student = None
        if ask_yes_no("Нужен штамп студента?", default=True):
            student, variant, lab_num, task_num = self._ask_stamp(with_task=True)
            watermark = _watermark(student, variant, lab_num, task_num)

        path = self._ask_source_file()
        self.generator.output_dir = self.output_dir
        print(f"\nГенерация ({self.cfg.output_format}) -> {self.output_dir}")
        self._generate_one(path, path.stem, watermark)

    # -------------------------------------------------------------- helpers
    def _generate_one(self, path: Path, base_name: str,
                      watermark: WatermarkInfo | None) -> bool:
        try:
            files, warnings = self.generator.generate(path, base_name, watermark)
        except ImportError as error:
            print(f"    Ошибка: не хватает зависимости ({error}). "
                  "Выполните: pip install -r requirements.txt")
            return False
        except Exception as error:
            print(f"    Ошибка: {error}")
            return False
        for w in warnings:
            print(f"    ! {w}")
        for f in files:
            print(f"    + {f.name}")
        return True

    def _wait_for_inputs(self):
        self.inputs_dir.mkdir(parents=True, exist_ok=True)
        print(f"\nПоложите файлы с кодом в папку:\n  {self.inputs_dir}")
        print("Имя файла должно заканчиваться номером задания: task1.c, task2.c ...")
        while True:
            answer = input("Когда закончите - нажмите Enter (q - отмена): ").strip().lower()
            if answer in {"q", "й", "quit", "exit"}:
                return None
            scan = scan_inputs(self.inputs_dir)
            if scan.duplicates:
                print("  ! Несколько файлов с одним номером задания:")
                for number, paths in scan.duplicates:
                    print(f"    №{number}: " + ", ".join(p.name for p in paths))
                print("  Будет использован первый по алфавиту, остальные пропущены.")
            if scan.ignored:
                print("  ! Пропущены (нет номера в конце имени): "
                      + ", ".join(p.name for p in scan.ignored))
            if not scan.tasks:
                print("  В папке нет подходящих .c файлов. Добавьте их и нажмите Enter.")
                continue
            print("  Найдено: " + ", ".join(f"{t.path.name} (задание {t.number})"
                                              for t in scan.tasks))
            return scan

    def _ask_source_file(self) -> Path:
        print(f"\nУкажите .c файл (полный путь или имя файла из {self.inputs_dir.name}/).")
        while True:
            raw = ask("Файл").strip().strip('"').strip("'")
            for candidate in (Path(raw).expanduser(), self.inputs_dir / raw, self.root / raw):
                if candidate.is_file():
                    return candidate
            print("  Файл не найден, попробуйте ещё раз.")

    def _ask_stamp(self, with_task: bool):
        """Спрашивает данные штампа, сохраняет предмет/ФИО/группу в конфиг."""
        saved = self.cfg.student
        student = saved
        use_saved = False
        if saved.is_complete():
            print(f"\nСохранённые данные: {saved.subject}, {saved.full_name}, {saved.group}")
            use_saved = ask_yes_no("Использовать их?", default=True)
        if not use_saved:
            student = Student(
                full_name=ask("Фамилия и инициалы (Иванов И.И.)", saved.full_name),
                subject=ask("Предмет", saved.subject),
                group=ask("Группа", saved.group),
            )
            self.cfg.student = student
            self.cfg.save()
            print(f"  Данные сохранены в {self.cfg.path.name}")
        variant = ask("Вариант")
        lab_num = ask("Номер лабораторной")
        if with_task:
            return student, variant, lab_num, ask("Номер задания")
        return student, variant, lab_num


def _watermark(student: Student, variant: str, lab_num: str, task_num: str) -> WatermarkInfo:
    return WatermarkInfo(subject=student.subject, full_name=student.full_name,
                         group=student.group, variant=variant,
                         lab_num=lab_num, task_num=task_num)
