from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Options:
    # --- внешний вид схемы -------------------------------------------------
    # Как рисовать for: "hexagon" (символ «подготовка», i = 0; i < n; i++ внутри)
    # или "diamond" (init - процесс, условие - ромб, update - процесс в конце тела)
    for_style: str = "hexagon"

    # Не рисовать декоративный вывод: printf("=======\\n"), printf("== ИТОГ ==\\n")
    skip_decorative: bool = True

    # --- подписи (язык диаграммы) -------------------------------------------
    yes_label: str = "Да"
    no_label: str = "Нет"
    default_label: str = "default"
    start_text: str = "Начало"
    end_text: str = "Конец"
    input_prefix: str = "Ввод"
    output_prefix: str = "Вывод"
    # Для функций, отличных от main, в блоке начала пишем сигнатуру: fact(int n)
    signature_in_start: bool = True

    # --- шрифт --------------------------------------------------------------
    font_family: str = "Times New Roman, Liberation Serif, DejaVu Serif, serif"
    font_size: int = 14
    line_height: int = 18
    # Запас на ширину шрифта. 1.15 - безопасно и для Times, и для DejaVu Serif,
    # которым cairosvg/браузер подменяют Times на Linux без шрифтов Microsoft.
    text_scale: float = 1.15

    # --- поля ---------------------------------------------------------------
    margin: int = 30
    stroke_width: float = 1.5