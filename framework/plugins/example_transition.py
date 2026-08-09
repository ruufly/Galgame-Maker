"""示例插件 4: 自定义背景过渡效果 (水平擦除 wipe)。

演示过渡系统的可扩展性: 继承 engine.display.Transition 并注册到
display.transitions 注册表, 脚本里即可使用 ``bg ... with wipe``。
"""

from framework.api import Plugin
from framework.engine.display import Transition


class WipeTransition(Transition):
    """水平擦除: 新背景从左往右覆盖旧背景。"""

    name = "wipe"
    duration = 0.8

    def draw_bg(self, target):
        if self.old is not None:
            target.blit(self.old, (0, 0))
        w, h = self.new.get_size()
        x1 = int(w * min(1.0, self.t))
        if x1 > 0:
            sub = self.new.subsurface((0, 0, x1, h))
            target.blit(sub, (0, 0))


class TransitionPlugin(Plugin):
    name = "custom_transitions"
    version = "1.0"

    def on_load(self):
        self.engine.display.register_transition("wipe", WipeTransition)
        print("[插件] 已注册自定义过渡: wipe")
