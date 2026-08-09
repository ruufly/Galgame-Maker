"""音频模块: BGM / 音效 (基于 pygame.mixer, 失败时自动降级为静音)。"""

import os

from framework.engine import log


class Audio:
    def __init__(self, engine) -> None:
        self.engine = engine
        self.mixer_ok = False
        self.bgm_volume = 0.8
        self.sfx_volume = 1.0
        self.current_bgm = None
        try:
            import pygame
            pygame.mixer.init()
            self.mixer_ok = True
        except Exception as exc:
            log.warning(f"音频初始化失败, 游戏将静音运行: {exc}")

    # ------------------------------------------------------------------
    def resolve(self, path: str) -> str:
        return self.engine.resolve_path(path)

    def play_music(self, path: str, loop: bool = True) -> bool:
        """播放 BGM。返回是否成功。"""
        if not self.mixer_ok:
            return False
        try:
            import pygame
            real = self.resolve(path)
            if not os.path.isfile(real):
                log.warning(f"BGM 文件不存在: {real}")
                return False
            pygame.mixer.music.load(real)
            pygame.mixer.music.set_volume(self.bgm_volume)
            pygame.mixer.music.play(-1 if loop else 0)
            self.current_bgm = path
            self.engine.emit("music_play", path=path, loop=loop)
            return True
        except Exception as exc:
            log.warning(f"BGM 播放失败 {path}: {exc}")
            return False

    def stop_music(self) -> None:
        if not self.mixer_ok:
            return
        try:
            import pygame
            pygame.mixer.music.stop()
            self.current_bgm = None
            self.engine.emit("music_stop")
        except Exception as exc:
            log.warning(f"停止 BGM 失败: {exc}")

    def play_sound(self, path: str) -> bool:
        if not self.mixer_ok:
            return False
        try:
            import pygame
            real = self.resolve(path)
            if not os.path.isfile(real):
                log.warning(f"音效文件不存在: {real}")
                return False
            snd = pygame.mixer.Sound(real)
            snd.set_volume(self.sfx_volume)
            snd.play()
            self.engine.emit("sound_play", path=path)
            return True
        except Exception as exc:
            log.warning(f"音效播放失败 {path}: {exc}")
            return False

    def set_bgm_volume(self, vol: float) -> None:
        self.bgm_volume = max(0.0, min(1.0, vol))
        if self.mixer_ok:
            try:
                import pygame
                pygame.mixer.music.set_volume(self.bgm_volume)
            except Exception:
                pass

    def set_sfx_volume(self, vol: float) -> None:
        self.sfx_volume = max(0.0, min(1.0, vol))
