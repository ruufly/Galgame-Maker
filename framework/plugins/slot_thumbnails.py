"""存档快照插件: 存档时保存当前画面缩略图, 在存档/读档界面显示。

- 订阅 save 事件: 截图 -> 缩小 -> 存到存档目录 (相对路径, 不存绝对路径)
  -> 写入存档元数据 "screenshot" 字段
- 注册槽位缩略图提供者: 读元数据 -> 加载图片 -> 槽位界面绘制

依赖 API (引擎已提供): display.capture() / save.set_meta / save.get_meta /
save.meta_path / display.register_slot_thumbnail_provider
"""

import os

import pygame

from framework.api import Plugin, event_listener

THUMB_W, THUMB_H = 150, 84


@event_listener("save")
def _on_save(engine, slot, path, **kw):
    """存档完成: 用最近一次纯游戏画面生成缩略图 (避开槽位面板)。"""
    try:
        surf = engine.get_last_game_frame() or engine.display.capture()
        thumb = pygame.transform.smoothscale(surf, (THUMB_W, THUMB_H))
        rel = f"thumb_slot{int(slot) + 1}.png"   # 相对存档目录
        abs_path = os.path.join(os.path.dirname(path), rel)
        pygame.image.save(thumb, abs_path)
        engine.save.set_meta(slot, "screenshot", rel)
        from framework.engine import log
        log.info(f"存档快照已保存: {rel}")
    except Exception as exc:
        from framework.engine import log
        log.warning(f"存档快照保存失败: {exc}")


class SlotThumbnailsPlugin(Plugin):
    name = "slot_thumbnails"
    version = "1.0"

    def on_load(self):
        """注册槽位缩略图提供者。"""
        engine = self.engine
        def provider(slot_index, info):
            rel = info.get("screenshot")
            if not rel:
                return None
            slot = info.get("slot", slot_index)
            p = engine.save.meta_path(slot, rel)
            if not p or not os.path.isfile(p):
                return None
            try:
                img = pygame.image.load(p)
                return pygame.transform.smoothscale(img, (THUMB_W, THUMB_H))
            except Exception:
                return None

        engine.display.register_slot_thumbnail_provider(provider)
        print("[插件] 存档快照: 存档时保存画面缩略图 (相对路径)")

    def on_unload(self):
        engine = self.engine
        engine.display.register_slot_thumbnail_provider(None)
        print("[插件] slot_thumbnails 已卸载")
