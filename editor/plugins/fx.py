"""fx 插件 — 编辑器接口 (屏幕特效指令参数表单)。"""

from editor.plugins_api import registry


def setup(reg):
    p = reg.register_plugin("fx", meta={
        "name": "fx",
        "description": "屏幕特效: 震动/闪白/闪黑/染色/频闪/脉冲",
    })
    for cmd, params in {
        "shake": [("时长 (秒)", "number", "0.3"),
                  ("幅度 (像素)", "int", "8")],
        "flash": [("时长 (秒)", "number", "0.15")],
        "blackflash": [("时长 (秒)", "number", "0.3")],
        "strobe": [("时长 (秒)", "number", "0.8")],
        "tint": [("颜色 r,g,b", "color", "255,0,0"),
                 ("时长 (秒)", "number", "0.5")],
        "pulse": [("颜色 r,g,b", "color", "0,255,128"),
                  ("时长 (秒)", "number", "1.0")],
    }.items():
        p.add_command(cmd, params=params)
