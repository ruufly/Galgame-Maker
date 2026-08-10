"""自定义动作插件。

注册 explode (屏幕震动) 动作, 并提供 do_action <类型> [k=v ...]
指令让脚本触发任意已注册动作。
"""

from framework.api import Plugin, command


class CustomActionsPlugin(Plugin):
    name = "custom_actions"
    version = "1.0"

    def on_load(self):
        engine = self.engine

        # 自定义动作: "explode" 屏幕震动
        def act_explode(engine, params, source):
            try:
                duration = float(params.get("duration", 0.5))
            except (TypeError, ValueError):
                duration = 0.5
            engine.display.shake(duration, 10)
            engine.show_notice("explode 动作触发!")
            return False    # 不关闭选择列表

        engine.register_action("explode", act_explode)

        # DSL 指令: do_action <type> [k=v ...]
        @self.add_command("do_action")
        def do_action(engine, stmt, **kw):
            """do_action <动作类型> [参数=值 ...] —— 触发任意已注册动作。"""
            if not stmt.args:
                return None
            atype = stmt.args[0]
            params = {}
            for a in stmt.args[1:]:
                if "=" in a:
                    k, v = a.split("=", 1)
                    params[k] = v
            engine.run_action({"type": atype, **params}, source="script")
            return None

        # 自定义立绘登场/退场效果: "wobble" (左右摇摆 + 淡入/淡出)
        def _eff_wobble(spr, t, direction, display):
            import math
            base = spr.effect[4]
            if direction == "enter":
                spr.alpha = int(255 * t)
                offset = math.sin(t * math.pi * 4) * 30 * (1 - t)
            else:
                spr.alpha = int(255 * (1 - t))
                offset = math.sin(t * math.pi * 4) * 30 * t
            spr.center = [base[0] + offset, base[1]]
            spr.rect.center = (int(round(spr.center[0])),
                               int(round(spr.center[1])))
            spr.surface.set_alpha(spr.alpha)

        engine.display.register_sprite_effect("wobble", _eff_wobble, 0.8)

        # 自定义文字显示模式: "wave" (波浪节奏打字)
        def _tm_wave(d, dt):
            import math
            d.reveal += d.TYPE_SPEED * dt * (1.2 + 0.4 * math.sin(d.reveal * 0.3))

        engine.display.register_text_mode("wave", {"update": _tm_wave})

        print("[插件] 已注册动作: explode (do_action explode) | "
              "立绘效果: wobble | 文字模式: wave (typing wave)")
