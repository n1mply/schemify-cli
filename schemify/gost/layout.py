"""Движок раскладки блок-схемы.

Идея: программа на C структурна (if/циклы/switch вложены друг в друга), поэтому
вместо общей раскладки графа каждая конструкция строится как *фрагмент* (Frag):
прямоугольная область с вертикальной осью x = 0. Вход фрагмента - точка (0, 0),
выход - точка (0, height). Фрагменты складываются друг под другом (seq), а
составные конструкции (if, while, switch ...) сами собирают из вложенных
фрагментов линии со слиянием стрелок, как требует ГОСТ 19.701-90.

Переходы break / continue / return не имеют своего места в потоке: фрагмент
запоминает точку, откуда переход уходит (Jump), а ближайшая охватывающая
конструкция (цикл, switch, функция) позже прокладывает линию по боковой
«полосе» снаружи и сливает её с нужной линией. Так пересечений блоков нет.

Все координаты относительные: ось x = 0, y растёт вниз.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from .options import Options

# --- геометрические константы ----------------------------------------------
G = 28          # вертикальный зазор между соседними блоками
JD = 24         # от точки входа цикла до его заголовка
SIDE = 32       # боковой зазор между блоком и вертикальной линией
LANE = 26       # расстояние между соседними боковыми полосами
MERGE = 24      # запас на слияние линий под ветвями
GB = 22         # запас под телом цикла для обратной стрелки
CG = 40         # зазор между столбцами switch
DROP = 36       # длина линии от шины switch до первого блока


@dataclass
class Shape:
    kind: str       # terminator | process | predefined | io | decision | hexagon
    x: float        # центр
    y: float
    w: float
    h: float
    lines: list[str]


@dataclass
class Edge:
    pts: list[tuple[float, float]]
    arrow: bool = False


@dataclass
class Label:
    x: float
    y: float
    text: str
    anchor: str = "start"       # start | end | middle


@dataclass
class Jump:
    kind: str       # break | continue | return
    x: float
    y: float


@dataclass
class Frag:
    shapes: list[Shape] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)
    jumps: list[Jump] = field(default_factory=list)
    left: float = 0.0           # вылет влево от оси (>= 0)
    right: float = 0.0          # вылет вправо от оси (>= 0)
    height: float = 0.0
    falls: bool = True          # достижим ли выход (поток идёт дальше)
    entry_junction: bool = False    # вход - точка слияния (стрелку рисует сам фрагмент)
    pure_jump: Jump | None = None   # фрагмент - только переход, без блоков

    def add(self, other: "Frag", dx: float, dy: float) -> None:
        """Переносит геометрию другого фрагмента в этот со сдвигом (dx, dy)."""
        for s in other.shapes:
            self.shapes.append(replace(s, x=s.x + dx, y=s.y + dy))
        for e in other.edges:
            self.edges.append(Edge([(x + dx, y + dy) for x, y in e.pts], e.arrow))
        for lb in other.labels:
            self.labels.append(replace(lb, x=lb.x + dx, y=lb.y + dy))
        for j in other.jumps:
            self.jumps.append(Jump(j.kind, j.x + dx, j.y + dy))
        self.left = max(self.left, other.left - dx)
        self.right = max(self.right, other.right + dx)

    def edge(self, *pts: tuple[float, float], arrow: bool = False) -> None:
        self.edges.append(Edge(_clean(list(pts)), arrow))


def _clean(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for p in pts:
        if not out or abs(out[-1][0] - p[0]) > 1e-6 or abs(out[-1][1] - p[1]) > 1e-6:
            out.append(p)
    return out


def clear_y(dw: float, dh: float, dist: float) -> float:
    """Минимальный y, ниже которого блок, ближний край которого на расстоянии
    dist от оси, уже не задевает нижние грани ромба (ширина dw, высота dh)."""
    half = dw / 2
    avail = dist - 8
    if avail >= half:
        return dh / 2
    return dh / 2 + (dh / 2) * (1 - max(avail, 0) / half)


# Заголовок блока: (вид, ширина, высота, строки)
Head = tuple[str, float, float, list[str]]


def block(kind: str, w: float, h: float, lines: list[str]) -> Frag:
    f = Frag()
    f.shapes.append(Shape(kind, 0, h / 2, w, h, lines))
    f.left = f.right = w / 2
    f.height = h
    return f


def jump_frag(kind: str) -> Frag:
    f = Frag()
    j = Jump(kind, 0.0, 0.0)
    f.jumps.append(j)
    f.pure_jump = j
    f.falls = False
    f.entry_junction = True
    return f


# ---------------------------------------------------------------------------
# Последовательность
# ---------------------------------------------------------------------------
def seq(frags: list[Frag]) -> Frag | None:
    frags = [f for f in frags if f is not None]
    if not frags:
        return None
    out = Frag()
    y = 0.0
    for i, f in enumerate(frags):
        if i == 0:
            out.add(f, 0, 0)
            out.entry_junction = f.entry_junction
            out.pure_jump = f.pure_jump
            top = 0.0
        else:
            top = y + G
            out.add(f, 0, top)
            out.edge((0, y), (0, top), arrow=not f.entry_junction)
            out.pure_jump = None
        y = top + f.height
        if not f.falls:
            out.falls = False
            break
    out.height = y
    return out


# ---------------------------------------------------------------------------
# if
# ---------------------------------------------------------------------------
def make_if(head: Head, T: Frag | None, E: Frag | None, o: Options) -> Frag:
    kind, dw, dh, lines = head
    out = Frag()
    out.shapes.append(Shape(kind, 0, dh / 2, dw, dh, lines))
    out.left = out.right = dw / 2
    cy = dh / 2
    yes, no = o.yes_label, o.no_label

    # --- режим 1: if без else, ветка «Да» идёт вниз по оси -------------------
    if E is None and T is not None and T.falls:
        ty = dh + G
        out.add(T, 0, ty)
        out.edge((0, dh), (0, ty), arrow=not T.entry_junction)
        out.labels.append(Label(6, dh + 17, yes))
        xn = max(dw / 2, T.right) + SIDE
        h = ty + T.height + MERGE
        out.edge((0, ty + T.height), (0, h))
        out.edge((dw / 2, cy), (xn, cy), (xn, h), (0, h))
        out.labels.append(Label(dw / 2 + 6, cy - 6, no))
        out.right = max(out.right, xn)
        out.height = h
        return out

    # --- режим 2: if без else, ветка «Да» не возвращается (break/return ...) --
    # Поток «Нет» идёт вниз по оси, «Да» уходит вправо из угла ромба.
    if E is None and T is not None:
        if T.pure_jump is not None:
            out.jumps.append(Jump(T.pure_jump.kind, dw / 2, cy))
            h = dh
        else:
            xt = max(dw / 2 + SIDE, T.left + SIDE)
            ty = max(cy + G, clear_y(dw, dh, xt - T.left))
            out.add(T, xt, ty)
            out.edge((dw / 2, cy), (xt, cy), (xt, ty), arrow=not T.entry_junction)
            h = max(dh, ty + T.height)
            if h > dh:
                out.edge((0, dh), (0, h))
        out.labels.append(Label(dw / 2 + 6, cy - 6, yes))
        out.labels.append(Label(6, dh + 17, no))
        out.height = h
        out.falls = True
        return out

    # --- режим 3: есть else (или обе ветки пусты) ----------------------------
    xl = -max(dw / 2 + SIDE, (T.right if T else 0.0) + SIDE / 2)
    xr = max(dw / 2 + SIDE, (E.left if E else 0.0) + SIDE / 2)
    by = cy + G
    if T is not None and T.pure_jump is None:
        by = max(by, clear_y(dw, dh, -xl - T.right))
    if E is not None and E.pure_jump is None:
        by = max(by, clear_y(dw, dh, xr - E.left))
    bottoms = [dh]
    falling: list[tuple[float, float]] = []      # (x ветки, y выхода)
    any_falls = False

    for br, x, sign in ((T, xl, -1), (E, xr, 1)):
        corner = (sign * dw / 2, cy)
        if br is None:
            continue
        if br.pure_jump is not None:
            out.jumps.append(Jump(br.pure_jump.kind, corner[0], cy))
            continue
        out.add(br, x, by)
        out.edge(corner, (x, cy), (x, by), arrow=not br.entry_junction)
        bottoms.append(by + br.height)
        if br.falls:
            falling.append((x, by + br.height))
            any_falls = True

    h = max(bottoms) + MERGE
    for x, yb in falling:
        out.edge((x, yb), (x, h), (0, h))
    for br, x, sign in ((T, xl, -1), (E, xr, 1)):
        if br is None:
            xs = sign * (dw / 2 + SIDE)
            out.edge((sign * dw / 2, cy), (xs, cy), (xs, h), (0, h))
            out.left = max(out.left, -xs if sign < 0 else 0)
            out.right = max(out.right, xs if sign > 0 else 0)
            any_falls = True

    out.labels.append(Label(-dw / 2 - 6, cy - 6, yes, "end"))
    out.labels.append(Label(dw / 2 + 6, cy - 6, no))
    out.height = h
    out.falls = any_falls
    return out


# ---------------------------------------------------------------------------
# Циклы
# ---------------------------------------------------------------------------
class _Lanes:
    """Боковые вертикальные полосы с одной стороны структуры.

    start - x первой полосы, step - шаг до следующей (знак задаёт сторону).
    """

    def __init__(self, start: float, step: float):
        self.start, self.step, self.n = start, step, 0

    def alloc(self) -> float:
        x = self.start + self.step * self.n
        self.n += 1
        return x

    @property
    def extent(self) -> float:
        """Вылет от оси до самой дальней занятой полосы (0, если полос нет)."""
        return abs(self.start + self.step * (self.n - 1)) if self.n else 0.0


def _stagger(out: Frag) -> None:
    """Разводит по глубине переходы, стартующие на одной высоте, чтобы их
    горизонтальные участки не сливались: дальняя от оси линия идёт ниже."""
    groups: dict[int, list[Jump]] = {}
    for j in out.jumps:
        groups.setdefault(round(j.y / 4), []).append(j)
    for grp in groups.values():
        for side in (True, False):
            part = [j for j in grp if (j.x >= 0) == side]
            part.sort(key=lambda j: -abs(j.x))      # дальний от оси - глубже
            n = len(part)
            for rank, j in enumerate(part):
                d = min(10 * (n - 1 - rank), 30)
                if d:
                    out.edge((j.x, j.y), (j.x, j.y + d))
                    j.y += d


def make_while(head: Head, body: Frag | None, post: Frag | None, o: Options,
               labels: bool = True) -> Frag:
    """Цикл с проверкой в начале (while, for).

    post - блок «обновление» (только for в стиле diamond): выполняется в конце
    каждой итерации, и именно туда ведёт continue.
    """
    kind, hw, hh, lines = head
    out = Frag()
    out.entry_junction = True
    cy = JD + hh / 2
    out.shapes.append(Shape(kind, 0, cy, hw, hh, lines))
    out.edge((0, 0), (0, JD), arrow=True)
    out.left = out.right = hw / 2

    head_bottom = JD + hh
    y_end = head_bottom                      # где заканчивается итерация
    falls = True
    if body is not None:
        by = head_bottom + G
        out.add(body, 0, by)
        out.edge((0, head_bottom), (0, by), arrow=not body.entry_junction)
        y_end = by + body.height
        falls = body.falls
    if labels:
        out.labels.append(Label(6, head_bottom + 17, o.yes_label))

    cont_y = None                            # точка слияния перед post (цель continue)
    if post is not None:
        py = y_end + G
        cont_y = y_end + G / 2
        out.add(post, 0, py)
        out.edge((0, y_end if falls else cont_y), (0, py), arrow=True)
        y_end = py + post.height
        falls = post.falls

    _stagger(out)
    brks = [j for j in out.jumps if j.kind == "break"]
    conts = [j for j in out.jumps if j.kind == "continue"]
    out.jumps = [j for j in out.jumps if j.kind == "return"]

    # цель continue: заголовок (post нет) или точка перед post
    to_head_l = [j for j in conts if cont_y is None and j.x <= 0]
    to_head_r = [j for j in conts if cont_y is None and j.x > 0]
    to_post = [j for j in conts if cont_y is not None]
    need_back = falls or bool(to_head_l)

    right = _Lanes(out.right + SIDE, LANE)       # первая полоса = линия «Нет»
    left = _Lanes(-(out.left + SIDE), -LANE)     # первая полоса = обратная стрелка
    nx = right.alloc()
    ye = (y_end + GB + 22) if falls else max(y_end, head_bottom) + MERGE
    if need_back:
        xb = left.alloc()
        if falls:
            out.edge((0, y_end), (0, y_end + GB), (xb, y_end + GB), (xb, JD / 2), (0, JD / 2))
        else:
            out.edge((xb, max(j.y for j in to_head_l)), (xb, JD / 2), (0, JD / 2))

    out.edge((hw / 2, cy), (nx, cy), (nx, ye), (0, ye))     # линия «Нет»
    if labels:
        out.labels.append(Label(hw / 2 + 6, cy - 6, o.no_label))

    # break: вправо - сливается с линией «Нет», влево - своя полоса
    lb = left.alloc() if any(j.x < 0 for j in brks) else None
    for j in brks:
        lane = nx if j.x >= 0 else lb
        out.edge((j.x, j.y), (lane, j.y), (lane, ye), (0, ye))

    # continue к заголовку: слева - сливается с обратной стрелкой
    for j in to_head_l:
        out.edge((j.x, j.y), (xb, j.y))
    rc = right.alloc() if to_head_r else None
    for j in to_head_r:
        out.edge((j.x, j.y), (rc, j.y), (rc, JD / 2), (0, JD / 2))

    # continue к блоку обновления for: свои полосы
    lc = left.alloc() if any(j.x <= 0 for j in to_post) else None
    rp = right.alloc() if any(j.x > 0 for j in to_post) else None
    for j in to_post:
        lane = rp if j.x > 0 else lc
        out.edge((j.x, j.y), (lane, j.y), (lane, cont_y), (0, cont_y))

    out.right = max(out.right, right.extent)
    out.left = max(out.left, left.extent)
    out.height = ye
    out.falls = True
    return out


def make_do_while(head: Head, body: Frag | None, o: Options) -> Frag:
    kind, hw, hh, lines = head
    out = Frag()
    out.entry_junction = True
    y_merge = G / 2                          # сюда возвращается стрелка «Да»

    if body is not None:
        out.add(body, 0, G)
        out.edge((0, 0), (0, G), arrow=not body.entry_junction)
        yb = G + body.height
        top = yb + G
        yc = yb + G / 2                      # точка слияния continue
        falls = body.falls
    else:
        yb, top, yc, falls = 0.0, G, G / 2, True
        out.edge((0, 0), (0, G), arrow=True)

    _stagger(out)
    brks = [j for j in out.jumps if j.kind == "break"]
    conts = [j for j in out.jumps if j.kind == "continue"]
    out.jumps = [j for j in out.jumps if j.kind == "return"]

    cy = top + hh / 2
    out.shapes.append(Shape(kind, 0, cy, hw, hh, lines))
    out.left = max(out.left, hw / 2)
    out.right = max(out.right, hw / 2)
    if body is not None and (falls or conts):
        out.edge((0, yb if falls else yc), (0, top), arrow=True)
    head_bottom = top + hh
    ye = head_bottom + 24

    right = _Lanes(out.right + SIDE, LANE)
    left = _Lanes(-(out.left + SIDE), -LANE)
    left.start -= 12
    xb = left.alloc()                         # стрелка «Да»
    out.edge((-hw / 2, cy), (xb, cy), (xb, y_merge), (0, y_merge))
    out.labels.append(Label(-hw / 2 - 6, cy - 6, o.yes_label, "end"))
    out.edge((0, head_bottom), (0, ye))       # «Нет» - вниз
    out.labels.append(Label(6, head_bottom + 15, o.no_label))

    rb = right.alloc() if any(j.x >= 0 for j in brks) else None
    lb = left.alloc() if any(j.x < 0 for j in brks) else None
    for j in brks:
        lane = rb if j.x >= 0 else lb
        out.edge((j.x, j.y), (lane, j.y), (lane, ye), (0, ye))
    rc = right.alloc() if any(j.x > 0 for j in conts) else None
    lc = left.alloc() if any(j.x <= 0 for j in conts) else None
    for j in conts:
        lane = rc if j.x > 0 else lc
        out.edge((j.x, j.y), (lane, j.y), (lane, yc), (0, yc))

    out.right = max(out.right, right.extent)
    out.left = max(out.left, left.extent)
    out.height = ye
    out.falls = True
    return out


# ---------------------------------------------------------------------------
# switch
# ---------------------------------------------------------------------------
@dataclass
class Clause:
    label: str
    frag: Frag | None
    breaks: bool        # заканчивается break (или иным переходом) - нет проваливания


def make_switch(head: Head, clauses: list[Clause], o: Options) -> Frag:
    from .text import text_width

    kind, dw, dh, lines = head
    out = Frag()
    out.shapes.append(Shape(kind, 0, dh / 2, dw, dh, lines))
    y_bus = dh + 24
    ytop = y_bus + DROP

    # --- столбцы ---------------------------------------------------------
    lw = [text_width(c.label, o) + 8 for c in clauses]
    L = [c.frag.left if c.frag else 0.0 for c in clauses]
    R = [max(c.frag.right if c.frag else 0.0, lw[i]) for i, c in enumerate(clauses)]
    xs: list[float] = []
    for i in range(len(clauses)):
        xs.append(0.0 if i == 0 else xs[-1] + R[i - 1] + CG + L[i])
    # Put the middle case column on the switch axis. This keeps the decision's
    # central stem, the central case, and the merge trunk on one vertical line,
    # even when the first or last case has a different text width.
    middle = len(xs) // 2
    shift = xs[middle] if len(xs) % 2 else (xs[middle - 1] + xs[middle]) / 2
    xs = [x - shift for x in xs]

    bottoms = [ytop]
    for i, c in enumerate(clauses):
        if c.frag is not None:
            out.add(c.frag, xs[i], ytop)
            bottoms.append(ytop + c.frag.height)
    ye = max(bottoms) + MERGE

    # шина
    out.edge((0, dh), (0, y_bus))
    out.edge((xs[0], y_bus), (xs[-1], y_bus))
    for i, c in enumerate(clauses):
        x = xs[i]
        if c.frag is not None:
            out.edge((x, y_bus), (x, ytop), arrow=not c.frag.entry_junction)
        else:
            out.edge((x, y_bus), (x, ye), (0, ye))
        out.labels.append(Label(x + 6, y_bus + 16, c.label))

    jy = y_bus + 14
    for i, c in enumerate(clauses):
        f = c.frag
        if f is None or not f.falls:
            continue
        x, yb = xs[i], ytop + f.height
        last = i == len(clauses) - 1
        if c.breaks or last:
            out.edge((x, yb), (x, ye), (0, ye))
        else:
            xl = x + R[i] + CG / 2
            out.edge((x, yb), (x, yb + 14), (xl, yb + 14), (xl, jy), (xs[i + 1], jy))

    out.left = max(out.left, dw / 2, -(xs[0]) + L[0])
    out.right = max(out.right, dw / 2, xs[-1] + R[-1])

    # break внутри case: полоса снаружи, слияние в точку выхода
    _stagger(out)
    brks = [j for j in out.jumps if j.kind == "break"]
    out.jumps = [j for j in out.jumps if j.kind != "break"]
    rb = out.right + LANE if any(j.x >= 0 for j in brks) else None
    lb = -(out.left + LANE) if any(j.x < 0 for j in brks) else None
    for j in brks:
        lane = rb if j.x >= 0 else lb
        out.edge((j.x, j.y), (lane, j.y), (lane, ye), (0, ye))
    if rb is not None:
        out.right = rb
    if lb is not None:
        out.left = -lb

    out.height = ye
    out.falls = True
    return out


# ---------------------------------------------------------------------------
# Функция целиком
# ---------------------------------------------------------------------------
def make_function(start: Head, body: Frag | None, end: Head, o: Options,
                  warnings: list[str]) -> Frag:
    sk, sw, sh, sl = start
    ek, ew, eh, el = end
    out = Frag()
    out.add(block(sk, sw, sh, sl), 0, 0)
    y = sh
    falls = True
    if body is not None:
        top = y + G
        out.add(body, 0, top)
        out.edge((0, y), (0, top), arrow=not body.entry_junction)
        y = top + body.height
        falls = body.falls

    end_top = y + G
    yj = end_top - G / 2
    if falls:
        out.edge((0, y), (0, end_top), arrow=True)
    else:
        out.edge((0, yj), (0, end_top), arrow=True)
    out.add(block(ek, ew, eh, el), 0, end_top)

    _stagger(out)
    rets = [j for j in out.jumps if j.kind == "return"]
    for j in out.jumps:
        if j.kind != "return":
            warnings.append(f"'{j.kind}' вне цикла/switch - проигнорирован")
    out.jumps = []
    rl = out.right + LANE if any(j.x >= 0 for j in rets) else None
    ll = -(out.left + LANE) if any(j.x < 0 for j in rets) else None
    for j in rets:
        lane = rl if j.x >= 0 else ll
        out.edge((j.x, j.y), (lane, j.y), (lane, yj), (0, yj))
    if rl is not None:
        out.right = rl
    if ll is not None:
        out.left = -ll
    out.height = end_top + eh
    return out
