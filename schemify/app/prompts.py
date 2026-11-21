"""Мелкие помощники для диалога в консоли."""
from __future__ import annotations

YES = {"y", "yes", "д", "да", "1"}
NO = {"n", "no", "н", "нет", "0"}


def ask(question: str, default: str = "") -> str:
    """Спрашивает строку; пустой ввод = default. Пустой ответ без default не принимается."""
    suffix = f" [{default}]" if default else ""
    while True:
        answer = input(f"{question}{suffix}: ").strip()
        if answer:
            return answer
        if default:
            return default
        print("  Поле не может быть пустым.")


def ask_yes_no(question: str, default: bool | None = None) -> bool:
    hint = {True: "Y/n", False: "y/N", None: "y/n"}[default]
    while True:
        answer = input(f"{question} ({hint}): ").strip().lower()
        if not answer and default is not None:
            return default
        if answer in YES:
            return True
        if answer in NO:
            return False
        print("  Введите y (да) или n (нет).")


def ask_choice(question: str, options: dict[str, str]) -> str:
    """options: {'1': 'описание', ...}; возвращает выбранный ключ."""
    print(question)
    for key, label in options.items():
        print(f"  {key} - {label}")
    while True:
        answer = input("> ").strip()
        if answer in options:
            return answer
        print(f"  Введите одно из: {', '.join(options)}.")
