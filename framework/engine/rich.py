"""富文本: 行内样式标记解析 + 样式化渲染 + 可选 LaTeX 公式。

标记语法 (支持嵌套, 后开先闭)::

    {c=#ff0000}红字{/c}          颜色   (#RRGGBB / #RRGGBBAA / 255,0,0 / 名称)
    {b}加粗{/b}                  bold
    {i}斜体{/i}                  italic
    {u}下划线{/u}                underline
    {s=28}大字{/s}               字号 (像素)
    {o=#000000}描边{/o}          文字描边颜色
    {m}x^2 + \\frac{1}{2}{/m}    LaTeX 公式 (需 matplotlib, 未安装时按原文显示)

    未识别的 {..} 按字面输出。公式源码内可自由使用花括号
    (如 \\frac{1}{2}), 不会被误解析。

渲染基于字符级缓存 (同一字符+样式只渲染一次), 中文长对话性能足够。
"""

import re

import pygame

from framework.engine import log

# ----------------------------------------------------------------------
# 颜色解析
# ----------------------------------------------------------------------
_NAMED_COLORS = {
    "white": (255, 255, 255), "black": (0, 0, 0),
    "red": (255, 0, 0), "green": (0, 255, 0), "blue": (0, 0, 255),
    "yellow": (255, 255, 0), "cyan": (0, 255, 255), "magenta": (255, 0, 255),
    "gray": (128, 128, 128), "grey": (128, 128, 128),
    "orange": (255, 165, 0), "purple": (160, 32, 240),
    "pink": (255, 105, 180), "brown": (139, 69, 19),
}


def parse_color(s, default=(255, 255, 255)):
    """把颜色描述解析成 (r,g,b[,a]) 元组。失败时返回 default。"""
    s = str(s).strip()
    if not s:
        return default
    if s.startswith("#"):
        h = s[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        try:
            if len(h) == 6:
                return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
            if len(h) == 8:
                return (int(h[0:2], 16), int(h[2:4], 16),
                        int(h[4:6], 16), int(h[6:8], 16))
        except ValueError:
            return default
    if "," in s:
        try:
            parts = [int(x.strip()) for x in s.split(",")]
            if len(parts) in (3, 4) and all(0 <= p <= 255 for p in parts):
                return tuple(parts)
        except ValueError:
            pass
    return _NAMED_COLORS.get(s.lower(), default)


# ----------------------------------------------------------------------
# 标记解析
# ----------------------------------------------------------------------
_OPEN_TAGS = {
    "c": "color", "color": "color",
    "s": "size", "size": "size",
    "o": "outline", "outline": "outline",
    "b": "bold", "bold": "bold",
    "i": "italic", "italic": "italic",
    "u": "underline", "underline": "underline",
    "m": "math", "math": "math",
}


class Run:
    """一段同样式文本。math=True 时 text 为公式源码。"""

    __slots__ = ("text", "color", "size", "bold", "italic", "underline",
                 "outline", "outline_width", "math")

    def __init__(self, text, color=(245, 245, 245), size=26,
                 bold=False, italic=False, underline=False,
                 outline=None, outline_width=1, math=False):
        self.text = text
        self.color = color
        self.size = size
        self.bold = bold
        self.italic = italic
        self.underline = underline
        self.outline = outline
        self.outline_width = outline_width
        self.math = math

    def style_key(self):
        return (self.color, self.size, self.bold, self.italic,
                self.underline, self.outline, self.outline_width, self.math)

    def same_style(self, other):
        return self.style_key() == other.style_key()


def parse_rich(text, base_size=26, base_color=(245, 245, 245)):
    """把带标记的文本解析成 Run 列表 (相邻同样式自动合并)。"""
    st = {"color": base_color, "size": base_size, "outline": None,
          "bold": False, "italic": False, "underline": False}
    stack = []
    runs = []
    buf = []
    i, n = 0, len(text)

    def flush():
        if buf:
            runs.append(Run("".join(buf), **st))
            buf.clear()

    while i < n:
        ch = text[i]
        if ch != "{":
            buf.append(ch)
            i += 1
            continue
        # 配对扫描大括号 (支持公式里的嵌套 { }: {m=\frac{1}{2}})
        depth = 1
        j = i + 1
        while j < n:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if depth != 0:
            buf.append(ch)
            i += 1
            continue
        tag = text[i + 1:j].strip()
        if not tag:
            buf.append("{")
            i += 1
            continue

        # 闭合标记
        if tag.startswith("/"):
            key = _OPEN_TAGS.get(tag[1:].strip().lower())
            if key is None:
                buf.append(text[i:j + 1])
                i = j + 1
                continue
            # 先以当前样式输出本段文本, 再恢复样式
            flush()
            restored = False
            while stack:
                k, old = stack.pop()
                if old is None:
                    st.pop(k, None)
                else:
                    st[k] = old
                if k == key:
                    restored = True
                    break
            if not restored:
                buf.append(text[i:j + 1])
            i = j + 1
            continue

        # 开启标记
        name, _, val = tag.partition("=")
        key = _OPEN_TAGS.get(name.strip().lower())
        if key is None:
            buf.append(text[i:j + 1])
            i = j + 1
            continue

        if key == "math":
            # 公式模式: 直接扫描到 {/m} 或 {/math}, 内容不做标记解析
            flush()
            k, end_len = len(text), 0
            for end in ("{/m}", "{/math}"):
                pos = text.find(end, j + 1)
                if pos != -1 and pos < k:
                    k, end_len = pos, len(end)
            if end_len == 0:
                expr = text[j + 1:]
                i = n
            else:
                expr = text[j + 1:k]
                i = k + end_len
            runs.append(Run(expr, color=st["color"], size=st["size"],
                            math=True))
            continue

        # 先以当前样式输出此前文本, 再应用新样式
        flush()
        stack.append((key, st.get(key)))
        val = val.strip()
        if key == "color":
            st["color"] = parse_color(val, st["color"])
        elif key == "size":
            try:
                st["size"] = max(6, int(float(val)))
            except ValueError:
                pass
        elif key == "outline":
            st["outline"] = parse_color(val, None) if val else None
        elif key in ("bold", "italic", "underline"):
            st[key] = True
        i = j + 1
        continue

    flush()
    return runs


# ----------------------------------------------------------------------
# 描边渲染
# ----------------------------------------------------------------------
def render_with_outline(font, text, color, outline_color=None,
                        outline_width=1, underline=False):
    """渲染文字, 可选描边。返回 Surface。"""
    if underline:
        font.set_underline(True)
    try:
        base = font.render(text, True, color)
    finally:
        if underline:
            font.set_underline(False)
    if not outline_color:
        return base
    w = outline_width
    surf = pygame.Surface((base.get_width() + 2 * w, base.get_height() + 2 * w),
                          pygame.SRCALPHA)
    for dx in range(-w, w + 1):
        for dy in range(-w, w + 1):
            if dx == 0 and dy == 0:
                continue
            if underline:
                font.set_underline(True)
            try:
                o = font.render(text, True, outline_color)
            finally:
                if underline:
                    font.set_underline(False)
            surf.blit(o, (w + dx, w + dy))
    surf.blit(base, (w, w))
    return surf


# ----------------------------------------------------------------------
# LaTeX 渲染 (基于 matplotlib mathtext, 无需系统 TeX)
# ----------------------------------------------------------------------
class MathRenderer:
    """把 LaTeX 公式渲染成透明 pygame Surface, 附带基线信息。

    使用 matplotlib figure + baseline 定位, 提取精确的
    基线上高度 (asc) 与基线以下深度 (desc), 与普通文字对齐。
    未安装 matplotlib 时 available=False, 公式按原文显示。
    """

    def __init__(self, engine=None):
        self.engine = engine
        self.available = False
        self._meta_parser = None
        self._cache = {}          # (expr, size, color) -> (surface, asc, desc)
        try:
            import matplotlib
            matplotlib.use("Agg")
            from matplotlib import mathtext
            self._meta_parser = mathtext.MathTextParser("agg")
            self.available = True
        except Exception as exc:
            log.info(f"matplotlib 不可用, LaTeX 公式将按原文显示: {exc}")

    def render(self, expr, size=26, color=(245, 245, 245), color_override=True):
        """渲染公式, 返回 (pygame.Surface, asc, desc)。失败返回 None。"""
        key = (expr, size, tuple(color))
        if key in self._cache:
            return self._cache[key]
        if not self.available:
            return None
        try:
            import numpy as np
            import matplotlib.pyplot as plt
            from matplotlib.font_manager import FontProperties

            prop = FontProperties(size=size)
            # 估算画布大小 (用 parse 元数据), 防止文字被裁
            ox, oy, w, h, depth, _ = self._meta_parser.parse(expr, dpi=72, prop=prop)
            pad = int(h) + 24
            fig = plt.figure(figsize=(max(2.0, (w + 2 * pad) / 72.0),
                                      max(2.0, (h + 2 * pad) / 72.0)), dpi=72)
            fig.patch.set_alpha(0)
            fig.text(0.5, 0.5, f"${expr}$", fontsize=size, color="black",
                     ha="center", va="baseline")
            fig.canvas.draw()
            buf = np.asarray(fig.canvas.buffer_rgba())
            plt.close(fig)

            alpha = buf[:, :, 3]
            ys, xs = np.nonzero(alpha > 8)
            if len(xs) == 0:
                return None
            y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
            baseline = buf.shape[0] / 2.0
            asc = baseline - y0
            desc = y1 - baseline

            rgba = buf[y0:y1, x0:x1].copy()
            # 公式渲染为黑色文字, 着目标色
            rgba[:, :, 0] = color[0]
            rgba[:, :, 1] = color[1]
            rgba[:, :, 2] = color[2]
            surf = pygame.image.frombuffer(rgba.tobytes(),
                                           (rgba.shape[1], rgba.shape[0]), "RGBA")
            result = (surf, asc, desc)
            self._cache[key] = result
            return result
        except Exception as exc:
            log.warning(f"LaTeX 渲染失败 {expr!r}: {exc}")
            return None


# ----------------------------------------------------------------------
# 富文本渲染器
# ----------------------------------------------------------------------
class RichTextRenderer:
    """把 Run 列表布局成行并绘制到目标 Surface。

    用法::

        r = RichTextRenderer(engine)
        runs = r.parse("你好{c=red}世界{/c}!")
        r.draw(surface, runs, x=20, y=30, max_width=500)
    """

    def __init__(self, engine):
        self.engine = engine
        self.math = MathRenderer(engine)
        self._char_cache = {}
        self._underline_cache = {}

    # ---- 解析 --------------------------------------------------------
    def parse(self, text, base_size=26, base_color=(245, 245, 245)):
        return parse_rich(text, base_size, base_color)

    def truncate(self, runs, n_chars):
        """按可见字符数截断 (打字机效果用)。

        公式整体计 1 个字符 (公式一次性整体出现)。
        """
        out = []
        remaining = n_chars
        for run in runs:
            if remaining <= 0:
                break
            if run.math:
                out.append(run)
                remaining -= 1
                continue
            if len(run.text) <= remaining:
                out.append(run)
                remaining -= len(run.text)
            else:
                out.append(Run(run.text[:remaining], run.color, run.size,
                               run.bold, run.italic, run.underline,
                               run.outline, run.outline_width))
                remaining = 0
        return out

    def logic_len(self, runs) -> int:
        """逻辑字符数: 普通字符逐字计, 公式整体计 1 (打字机/逐字模式用)。"""
        total = 0
        for run in runs:
            if run.math:
                total += 1
            else:
                total += len(run.text)
        return total

    # ---- 单字符/公式 surface ----------------------------------------
    def _char_surface(self, ch, run):
        key = (run.size, run.bold, run.italic, ch, tuple(run.color),
               tuple(run.outline) if run.outline else None, run.outline_width)
        if key in self._char_cache:
            return self._char_cache[key]
        font = self.engine.get_font(run.size, bold=run.bold, italic=run.italic)
        surf = render_with_outline(font, ch, run.color, run.outline,
                                   run.outline_width, run.underline)
        self._char_cache[key] = surf
        return surf

    def _math_surface(self, run):
        return self.math.render(run.text, run.size, run.color)

    def _item_width(self, item):
        """item: (text, run)。text 单字符或公式源码。"""
        text, run = item
        if run.math:
            res = self._math_surface(run)
            return res[0].get_width() if res else 0
        return self._char_surface(text, run).get_width()

    # ---- 布局 --------------------------------------------------------
    def layout(self, runs, max_width):
        """把 runs 布局成多行, 返回 lines: list of [(text, run)]。"""
        lines = [[]]
        cur_w = 0
        for run in runs:
            if run.math:
                w = self._item_width((run.text, run))
                if cur_w + w > max_width and cur_w > 0:
                    lines.append([])
                    cur_w = 0
                lines[-1].append((run.text, run))
                cur_w += w
                continue
            for ch in run.text:
                w = self._char_surface(ch, run).get_width()
                if cur_w + w > max_width and cur_w > 0:
                    lines.append([])
                    cur_w = 0
                lines[-1].append((ch, run))
                cur_w += w
        return lines

    def measure_line(self, line):
        return sum(self._item_width(item) for item in line)

    def _line_metrics(self, line):
        asc = desc = 0
        for text, run in line:
            if run.math:
                res = self._math_surface(run)
                if res:
                    asc = max(asc, res[1])
                    desc = max(desc, res[2])
            else:
                font = self.engine.get_font(run.size, bold=run.bold,
                                            italic=run.italic)
                asc = max(asc, font.get_ascent())
                desc = max(desc, font.get_descent())
        return asc, desc

    # ---- 绘制 --------------------------------------------------------
    def draw(self, target, runs, x, y, max_width, align="left",
             line_height=None, alpha=None, max_lines=None):
        """多行绘制富文本 (左上角定位)。返回 (底部 y, 行数)。"""
        lines = self.layout(runs, max_width)
        if max_lines is not None:
            lines = lines[:max_lines]
        yy = y
        for line in lines:
            asc, desc = self._line_metrics(line)
            line_h = line_height or (asc + desc + 2)
            w = self.measure_line(line)
            if align == "center":
                xx = x + (max_width - w) // 2
            elif align == "right":
                xx = x + max_width - w
            else:
                xx = x
            baseline = yy + asc
            for text, run in line:
                if run.math:
                    res = self._math_surface(run)
                    if res:
                        surf, s_asc, _ = res
                        target.blit(surf, (xx, int(baseline - s_asc)))
                        xx += surf.get_width()
                    continue
                surf = self._char_surface(text, run)
                if alpha is not None:
                    surf = surf.copy()  # 不污染字符缓存
                    surf.set_alpha(max(0, min(255, int(alpha))))
                target.blit(surf, (xx, int(baseline - surf.get_height())))
                xx += surf.get_width()
            yy += line_h
        return yy, len(lines)

    def draw_centered(self, target, runs, cx, cy, max_width=10 ** 6,
                      alpha=None):
        """单行水平居中绘制, cy 为垂直中心。返回绘制的宽度。

        垂直对齐: 使文本的视觉中心 (asc 与 desc 的中点) 落在 cy 上。
        """
        line = list(self.layout(runs, max_width)[0]) if runs else []
        if not line:
            return 0
        w = self.measure_line(line)
        asc, desc = self._line_metrics(line)
        x = cx - w // 2
        baseline = cy + (asc - desc) // 2
        for text, run in line:
            if run.math:
                res = self._math_surface(run)
                if res:
                    surf, s_asc, _ = res
                    target.blit(surf, (x, int(baseline - s_asc)))
                    x += surf.get_width()
                continue
            surf = self._char_surface(text, run)
            if alpha is not None:
                surf = surf.copy()  # 不污染字符缓存
                surf.set_alpha(max(0, min(255, int(alpha))))
            target.blit(surf, (x, int(baseline - surf.get_height())))
            x += surf.get_width()
        return w
