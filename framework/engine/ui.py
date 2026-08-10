"""UI 绘制原语: 面板 / 文字 / 换行 / 遮罩。

把"画一个框、往里面填内容"这类高频操作抽成可复用函数,
引擎内部 (文本框/选项/通知) 与插件 (draw_overlay 钩子) 共用,
避免重复造轮子。用法::

    import pygame
    from framework.engine import ui

    # 半透明面板 + 边框
    ui.panel(surface, pygame.Rect(10, 10, 200, 60),
             bg_color=(0, 0, 0, 180), border_color=(255, 255, 255, 80))

    # 居中文字
    ui.text(surface, font, "你好", center=(100, 40))

    # 自动换行多行文字
    ui.multiline_text(surface, font, "长文本...", 20, 20, max_width=180)
"""

import pygame

from framework.engine.rich import render_with_outline


def panel(surface, rect, bg_color=(0, 0, 0, 185),
          border_color=None, border_width=0, radius=0,
          shadow=None, shadow_offset=(3, 3)):
    """绘制半透明面板, 支持可选边框、圆角与投影。

    参数:
        surface      目标 Surface
        rect         面板位置尺寸 (pygame.Rect 或 (x, y, w, h))
        bg_color     (r, g, b, a) 背景色
        border_color 边框颜色 (None 则不画边框)
        border_width 边框宽度
        radius       圆角半径 (pygame 2.0+ 支持)
        shadow       投影颜色 (None 则不画投影)
        shadow_offset 投影偏移 (dx, dy)

    返回 rect (pygame.Rect), 便于继续在其上摆内容。
    """
    rect = pygame.Rect(rect)
    w, h = rect.size
    if w <= 0 or h <= 0:
        return rect
    if shadow is not None:
        panel(surface, (rect.x + shadow_offset[0], rect.y + shadow_offset[1],
                        w, h), bg_color=shadow, radius=radius)
    panel_surf = pygame.Surface((w, h), pygame.SRCALPHA)
    if radius > 0:
        pygame.draw.rect(panel_surf, bg_color, panel_surf.get_rect(),
                         border_radius=radius)
        if border_color is not None:
            pygame.draw.rect(panel_surf, border_color, panel_surf.get_rect(),
                             border_width, border_radius=radius)
    else:
        panel_surf.fill(bg_color)
        if border_color is not None:
            pygame.draw.rect(panel_surf, border_color, panel_surf.get_rect(),
                             border_width)
    surface.blit(panel_surf, rect.topleft)
    return rect


def text(surface, font, content, color=(255, 255, 255),
         pos=None, center=None, alpha=None,
         bold=False, italic=False, underline=False,
         outline=None, outline_width=1):
    """渲染一行文字。

    参数:
        pos          文字左上角坐标
        center       文字中心点坐标 (与 pos 二选一)
        alpha        整体透明度 0-255
        bold/italic/underline  文字样式 (pygame 渲染支持时生效)
        outline      描边颜色 (None 则无描边)
        outline_width 描边宽度 (像素)

    返回文字 rect, 便于继续布局。
    """
    if bold or italic:
        font.set_bold(bold)
        font.set_italic(italic)
    surf = render_with_outline(font, content, color, outline, outline_width,
                               underline)
    if bold or italic:
        font.set_bold(False)
        font.set_italic(False)
    if alpha is not None:
        surf.set_alpha(max(0, min(255, int(alpha))))
    if center is not None:
        rect = surf.get_rect(center=center)
    elif pos is not None:
        rect = surf.get_rect(topleft=pos)
    else:
        rect = surf.get_rect()
    surface.blit(surf, rect)
    return rect


def wrap_text(font, text, max_width):
    """按像素宽度对文本逐字符换行, 返回行列表。"""
    if not text:
        return [""]
    lines = []
    cur = ""
    for ch in text:
        test = cur + ch
        if font.size(test)[0] > max_width and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


def multiline_text(surface, font, text, x, y, max_width,
                   color=(245, 245, 245), line_height=None, max_lines=None,
                   align="left"):
    """绘制自动换行的多行文字 (左上角定位)。

    参数:
        align: "left" / "center" / "right"

    返回 (绘制到的底部 y, 实际行数)。
    """
    line_h = line_height or font.get_linesize()
    lines = wrap_text(font, text, max_width)
    if max_lines is not None:
        lines = lines[: max_lines]
    yy = y
    for line in lines:
        surf = font.render(line, True, color)
        if align == "center":
            xx = x + (max_width - surf.get_width()) // 2
        elif align == "right":
            xx = x + max_width - surf.get_width()
        else:
            xx = x
        surface.blit(surf, (xx, yy))
        yy += line_h
    return yy, len(lines)


def dim_overlay(surface, alpha=150, color=(0, 0, 0)):
    """全屏半透明遮罩 (常用于选项菜单/暂停背景)。"""
    overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    overlay.fill((color[0], color[1], color[2], alpha))
    surface.blit(overlay, (0, 0))


def nine_slice(source, rect, edge=12):
    """把图片按九宫格拉伸到 rect, 四角不变、边与中心拉伸。

    适用于小尺寸圆角边框图 (按钮/面板/文本框背景)。edge 为四边宽度。
    """
    rect = pygame.Rect(rect)
    w, h = source.get_size()
    if w <= edge * 2 or h <= edge * 2:
        # 图太小, 直接拉伸
        return pygame.transform.smoothscale(source, rect.size)
    if rect.w < edge * 2 or rect.h < edge * 2:
        return pygame.transform.smoothscale(source, rect.size)
    target = pygame.Surface(rect.size, pygame.SRCALPHA)
    cw, ch = edge, edge
    mw, mh = w - 2 * cw, h - 2 * ch
    tw, th = rect.w - 2 * cw, rect.h - 2 * ch
    pieces = [
        (0, 0, cw, ch, 0, 0, cw, ch),                       # 左上
        (cw, 0, mw, ch, cw, 0, tw, ch),                     # 上
        (w - cw, 0, cw, ch, rect.w - cw, 0, cw, ch),        # 右上
        (0, ch, cw, mh, 0, ch, cw, th),                     # 左
        (cw, ch, mw, mh, cw, ch, tw, th),                   # 中
        (w - cw, ch, cw, mh, rect.w - cw, ch, cw, th),      # 右
        (0, h - ch, cw, ch, 0, rect.h - ch, cw, ch),        # 左下
        (cw, h - ch, mw, ch, cw, rect.h - ch, tw, ch),      # 下
        (w - cw, h - ch, cw, ch, rect.w - cw, rect.h - ch, cw, ch),  # 右下
    ]
    for sx, sy, sw, sh, dx, dy, dw, dh in pieces:
        if sw <= 0 or sh <= 0 or dw <= 0 or dh <= 0:
            continue
        piece = source.subsurface((sx, sy, sw, sh))
        if (dw, dh) != piece.get_size():
            piece = pygame.transform.smoothscale(piece, (dw, dh))
        target.blit(piece, (dx, dy))
    return target
