"""预装界面样式 (built-in styles)。

脚本加载时预置到 runtime.styles, 无需定义即可 ``use style <name>``;
脚本中定义同名 style 块会自动重载 (覆盖) 内置样式。

属性值与脚本 style 块一致 (颜色字符串 / 数字), 由 runtime 统一解析。
"""

BUILTIN_STYLES = {
    # 深蓝圆角 + 红色点缀
    "modern": {
        "textbox_bg": "#1a1a2e",
        "textbox_alpha": 210,
        "textbox_border": "#e94560",
        "textbox_border_width": 3,
        "textbox_radius": 12,
        "text_color": "#eaeaea",
        "text_size": 28,
        "speaker_color": "#ffd282",
        "speaker_bg": "#1e3a5f",
        "arrow_color": "#e94560",
        "choice_bg": "#16213e",
        "choice_bg_hover": "#0f3460",
        "choice_border": "#533483",
        "choice_border_hover": "#e94560",
    },
    # 复古金边
    "classic": {
        "textbox_bg": "#222222",
        "textbox_alpha": 220,
        "textbox_border": "#d4af37",
        "textbox_border_width": 2,
        "textbox_radius": 0,
        "text_color": "#f0e6d2",
        "text_size": 26,
        "speaker_color": "#ffd700",
        "speaker_bg": "#3a2a12",
        "arrow_color": "#d4af37",
        "choice_bg": "#2a2a22",
        "choice_bg_hover": "#4a4028",
        "choice_border": "#8a7a40",
        "choice_border_hover": "#d4af37",
    },
    # 高对比纯黑 (适合恐怖/悬疑)
    "dark": {
        "textbox_bg": "#000000",
        "textbox_alpha": 200,
        "textbox_border": "#555555",
        "textbox_border_width": 1,
        "textbox_radius": 0,
        "text_color": "#cccccc",
        "text_size": 26,
        "speaker_color": "#888888",
        "speaker_bg": "#111111",
        "arrow_color": "#777777",
        "choice_bg": "#101010",
        "choice_bg_hover": "#303030",
        "choice_border": "#555555",
        "choice_border_hover": "#aaaaaa",
    },
    # 明亮 (适合日常/治愈系)
    "light": {
        "textbox_bg": "#f5f5f0",
        "textbox_alpha": 235,
        "textbox_border": "#c8b89a",
        "textbox_border_width": 2,
        "textbox_radius": 16,
        "text_color": "#333333",
        "text_size": 26,
        "speaker_color": "#6b4f2a",
        "speaker_bg": "#f0e4c8",
        "arrow_color": "#8a7a5a",
        "choice_bg": "#faf6ec",
        "choice_bg_hover": "#f0e4c8",
        "choice_border": "#c8b89a",
        "choice_border_hover": "#8a6a3a",
    },
    # 赛博霓虹
    "cyber": {
        "textbox_bg": "#0a0a1a",
        "textbox_alpha": 225,
        "textbox_border": "#00ffcc",
        "textbox_border_width": 3,
        "textbox_radius": 8,
        "text_color": "#d8fff4",
        "text_size": 27,
        "speaker_color": "#ff00aa",
        "speaker_bg": "#1a0033",
        "arrow_color": "#00ffcc",
        "choice_bg": "#0d1128",
        "choice_bg_hover": "#1e2a4a",
        "choice_border": "#6600ff",
        "choice_border_hover": "#00ffcc",
    },
}
