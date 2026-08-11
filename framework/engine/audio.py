"""音频模块: BGM / 音效 (基于 pygame.mixer, 失败时自动降级为静音)。"""

import os

from framework.engine import log


class Audio:
    def __init__(self, engine) -> None:
        self.engine = engine
        self.mixer_ok = False
        self.bgm_volume = 0.8
        self.sfx_volume = 1.0
        self.voice_volume = 1.0        # 全局语音音量 (volume voice <0-1> 调整)
        self.current_bgm = None        # 当前 BGM 路径 (恢复播放用)
        self.current_bgm_name = None  # 当前 BGM 注册名 (存档/显示用, 可为 None)
        self.voice_sound = None
        self.voice_channel = None
        self.fade_duration = 1.0     # BGM 淡入淡出默认秒数 (window music_fade)
        self._fade = None            # {"kind":"in"/"out","duration","t","pending"}
        try:
            import pygame
            pygame.mixer.init()
            self.mixer_ok = True
            self.voice_channel = pygame.mixer.Channel(0)   # 语音专用通道
            # 防御: 重复 init (如 pygame.quit 后重建引擎) 时清除 music 残留
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
        except Exception as exc:
            log.w("log.audio.init_failed", exc=exc)

    # ------------------------------------------------------------------
    def resolve(self, path: str) -> str:
        return self.engine.resolve_path(path)

    def _music_playing(self) -> bool:
        try:
            import pygame
            return bool(pygame.mixer.music.get_busy())
        except Exception:
            return False

    def _do_play(self, path: str, loop: bool, fade: float,
                 name: str = None) -> bool:
        """实际开始播放 (淡入: 从 0 音量渐升)。

        loop=True 循环 (播完若无新曲自动重播); False 单次播放。
        name: BGM 注册名 (存档/显示用, 直接路径播放时为 None)。
        """
        import pygame
        real = self.resolve(path)
        pygame.mixer.music.load(real)
        pygame.mixer.music.set_volume(0.0 if fade > 0 else self.bgm_volume)
        pygame.mixer.music.play(-1 if loop else 0)
        self.current_bgm = path
        self.current_bgm_name = name
        self.engine.emit("music_play", name=name, path=path, loop=loop,
                         fade=fade)
        if fade > 0:
            self._fade = {"kind": "in", "duration": fade, "t": 0.0,
                          "pending": None}
        return True

    def play_music(self, path: str, loop: bool = True,
                   fade: float = None, name: str = None) -> bool:
        """播放/切换 BGM。fade None=用默认时长, 0=无淡入淡出。

        loop=True 循环播放, False 单次播放; 切换时旧曲淡出新曲淡入。
        name: 注册名 (存档/事件载荷, 可为 None)。
        """
        if not self.mixer_ok:
            return False
        fade = self.fade_duration if fade is None else max(0.0, fade)
        try:
            real = self.resolve(path)
            if not os.path.isfile(real):
                log.w("log.audio.bgm_missing", path=real)
                return False
            if self._music_playing() and self.current_bgm != path and fade > 0:
                # 切换: 先淡出旧曲, 完成后淡入新曲
                self._fade = {"kind": "out", "duration": fade, "t": 0.0,
                              "pending": ("play", path, loop, fade, name)}
                return True
            return self._do_play(path, loop, fade, name)
        except Exception as exc:
            log.w("log.audio.bgm_play_failed", path=path, exc=exc)
            return False

    def stop_music(self, fade: float = None) -> None:
        """停止 BGM (默认淡出)。"""
        if not self.mixer_ok:
            return
        fade = self.fade_duration if fade is None else max(0.0, fade)
        try:
            import pygame
            if fade > 0 and self._music_playing():
                self._fade = {"kind": "out", "duration": fade, "t": 0.0,
                              "pending": ("stop",)}
            else:
                pygame.mixer.music.stop()
                self.current_bgm = None
                self.current_bgm_name = None
                self.engine.emit("music_stop")
        except Exception as exc:
            log.w("log.audio.bgm_stop_failed", exc=exc)

    def pause_music(self, fade: float = None) -> None:
        """暂停 BGM (默认淡出后暂停)。"""
        if not self.mixer_ok:
            return
        fade = self.fade_duration if fade is None else max(0.0, fade)
        try:
            import pygame
            if fade > 0 and self._music_playing():
                self._fade = {"kind": "out", "duration": fade, "t": 0.0,
                              "pending": ("pause",)}
            else:
                pygame.mixer.music.pause()
            self.engine.emit("music_pause")
        except Exception as exc:
            log.w("log.audio.bgm_pause_failed", exc=exc)

    def resume_music(self, fade: float = None) -> None:
        """恢复 BGM (默认淡入)。"""
        if not self.mixer_ok:
            return
        fade = self.fade_duration if fade is None else max(0.0, fade)
        try:
            import pygame
            pygame.mixer.music.unpause()
            if fade > 0 and self.current_bgm:
                self._fade = {"kind": "in", "duration": fade, "t": 0.0,
                              "pending": None}
            self.engine.emit("music_resume")
        except Exception as exc:
            log.w("log.audio.bgm_resume_failed", exc=exc)

    def stop_all_sfx(self) -> None:
        """立即停止所有音效 (剧情 + UI, 非 BGM)。"""
        if not self.mixer_ok:
            return
        try:
            import pygame
            pygame.mixer.stop()
        except Exception:
            pass

    def pause_all(self, fade: float = None) -> None:
        """全局暂停: BGM 淡出暂停 + 停止音效与语音。"""
        self.pause_music(fade)
        self.stop_voice()
        self.stop_all_sfx()
        self.engine.emit("sound_all_pause")

    def stop_all(self, fade: float = None) -> None:
        """全局停止: BGM 淡出停止 + 停止音效与语音。"""
        self.stop_music(fade)
        self.stop_voice()
        self.stop_all_sfx()
        self.engine.emit("sound_all_stop")

    def set_bgm_volume(self, vol: float) -> None:
        self.bgm_volume = max(0.0, min(1.0, vol))
        if self.mixer_ok:
            try:
                import pygame
                pygame.mixer.music.set_volume(self.bgm_volume)
            except Exception:
                pass

    def update(self, dt: float) -> None:
        """每帧推进 BGM 淡入淡出 (音量渐变)。"""
        if not self.mixer_ok or self._fade is None:
            return
        f = self._fade
        f["t"] += dt
        k = min(1.0, f["t"] / max(0.001, f["duration"]))
        try:
            import pygame
            if f["kind"] == "in":
                pygame.mixer.music.set_volume(self.bgm_volume * k)
            else:
                pygame.mixer.music.set_volume(self.bgm_volume * (1 - k))
        except Exception:
            pass
        if k >= 1.0:
            pending = f.get("pending")
            self._fade = None
            if pending:
                act = pending[0]
                if act == "stop":
                    pygame.mixer.music.stop()
                    self.current_bgm = None
                    self.current_bgm_name = None
                    self.engine.emit("music_stop")
                elif act == "pause":
                    pygame.mixer.music.pause()
                elif act == "play":
                    self._do_play(pending[1], pending[2], pending[3],
                                  pending[4] if len(pending) > 4 else None)

    def play_sound(self, path: str) -> bool:
        if not self.mixer_ok:
            return False
        try:
            import pygame
            real = self.resolve(path)
            if not os.path.isfile(real):
                log.w("log.audio.sfx_missing", path=real)
                return False
            snd = pygame.mixer.Sound(real)
            snd.set_volume(self.sfx_volume)
            snd.play()
            self.engine.emit("sound_play", path=path)
            return True
        except Exception as exc:
            log.w("log.audio.sfx_play_failed", path=path, exc=exc)
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

    def set_voice_volume(self, vol: float) -> None:
        """设置全局语音音量 (作为 master, 与角色/声音音量相乘)。"""
        self.voice_volume = max(0.0, min(1.0, vol))

    # ------------------------------------------------------------------
    # 语音 (独立通道, 随 say/nar 播放与停止)
    # ------------------------------------------------------------------
    def play_voice(self, path: str, volume: float = None) -> bool:
        """播放语音 (独立通道)。

        volume: 本次播放的额外音量系数 (角色 voice_volume × 声音块 volume),
        None 表示不额外衰减。最终音量 = sfx_volume × voice_volume × volume。
        """
        if not self.mixer_ok:
            return False
        self.stop_voice()
        try:
            import pygame
            real = self.resolve(path)
            if not os.path.isfile(real):
                log.w("log.audio.voice_missing", path=real)
                return False
            snd = pygame.mixer.Sound(real)
            extra = 1.0 if volume is None else max(0.0, min(1.0, float(volume)))
            snd.set_volume(self.sfx_volume * self.voice_volume * extra)
            ch = self.voice_channel or pygame.mixer.find_channel()
            if ch is None:
                return False
            ch.play(snd)
            self.voice_sound = snd
            self.engine.emit("voice_play", path=path)
            return True
        except Exception as exc:
            log.w("log.audio.voice_play_failed", path=path, exc=exc)
            return False

    def stop_voice(self) -> None:
        if not self.mixer_ok:
            return
        try:
            import pygame
            ch = self.voice_channel
            if ch is not None:
                ch.stop()
            self.voice_sound = None
            self.engine.emit("voice_stop")
        except Exception:
            pass

    def voice_playing(self) -> bool:
        return (self.voice_channel is not None
                and self.voice_channel.get_busy())
