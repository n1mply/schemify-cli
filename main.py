"""Точка входа: python main.py"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        print("! python-dotenv не установлен, .env не прочитан "
              "(pip install -r requirements.txt)")

    logging.basicConfig(level=logging.WARNING, format="  ! %(message)s")

    from schemify.app.cli import App
    from schemify.app.config import Config

    cfg = Config.load(ROOT / "config.json")
    try:
        App(ROOT, cfg).run()
    except (KeyboardInterrupt, EOFError):
        print("\nВыход.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
