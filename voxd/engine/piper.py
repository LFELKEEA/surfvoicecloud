"""Piper 引擎：CPU 兜底，永远是最后一道防线。

它不能克隆、不能控情绪，但**一定能出声**——主引擎挂了、权重没下完、
显存被游戏占了，它都能顶上。这就是「泛用」的最后保险。
"""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import tempfile
import wave
from pathlib import Path

import numpy as np

from .base import Caps, EngineError


def _ascii_mirrors(src: Path) -> list[Path]:
    """给 espeak 数据目录准备几个「纯 ASCII」的落点，按优先级排。"""
    tag = hashlib.md5(str(src).encode("utf-8", "replace")).hexdigest()[:8]
    roots = []
    override = os.environ.get("SURFCORE_ESPEAK_DATA")
    if override:
        roots.append(Path(override))
    for env in ("ProgramData", "PUBLIC"):
        base = os.environ.get(env)
        if base:
            roots.append(Path(base) / "surfcore")
    roots.append(Path(os.environ.get("SystemDrive", "C:") + "\\surfcore-cache"))
    try:
        roots.append(Path(tempfile.gettempdir()) / "surfcore")
    except Exception:  # noqa: BLE001 - 临时目录不可用时只是少一个落点
        pass
    return [r / f"espeak-ng-data-{tag}" for r in roots]


def espeak_data_dir(src: Path) -> Path:
    """返回能让 espeak-ng 正常初始化的 data 目录。

    2026-10-30 实测：espeak-ng 处理不了非 ASCII 的 data 路径。装在
    `D:\\...\\工作区\\...` 这类目录时，`initialize()` 会失败、回落到编译期路径
    `D:/a/piper1-gpl/...`，打印一行 No such file or directory 后 **直接 exit()**，
    整个 voxd 进程跟着消失（一次 huayan 请求就能把 8765 打挂）。

    这里把 espeak-ng-data 镜像到纯 ASCII 目录再用；镜像也失败就抛错，让这个引擎
    停在 `error` 状态，而不是等到合成时才把进程带走。
    """
    if str(src).isascii() or not src.exists():
        return src
    last_error: Exception | None = None
    for dst in _ascii_mirrors(src):
        if not str(dst).isascii():  # 临时目录也可能带中文用户名
            continue
        try:
            marker = dst / ".mirrored-from"
            if marker.exists() and marker.read_text(encoding="utf-8", errors="ignore") == str(src):
                return dst
            shutil.copytree(src, dst, dirs_exist_ok=True)
            marker.write_text(str(src), encoding="utf-8")
            return dst
        except Exception as e:  # noqa: BLE001 - 换下一个落点
            last_error = e
    raise EngineError(
        f"espeak 数据在含非 ASCII 的路径（{src}），镜像到 ASCII 目录失败"
        f"（{last_error}）。请把语音包装到纯英文路径，或设置环境变量 "
        f"SURFCORE_ESPEAK_DATA 指向一个 ASCII 目录。"
    )


class PiperEngine:
    name = "piper"
    caps = Caps(clone=False, instruct=False, langs=("zh", "en"), sr=22050, rate_control=True)

    def __init__(self, model_path: str, config_path: str | None = None):
        self.model_path = model_path
        self.config_path = config_path or (model_path + ".json")
        self.voice = None
        self.sr = 22050

    def load(self) -> None:
        try:
            from piper import PiperVoice
        except Exception as e:  # noqa: BLE001
            raise EngineError(f"piper 未安装：{e}") from e
        data_dir = None
        try:
            from piper.phonemize_espeak import ESPEAK_DATA_DIR
        except ImportError:
            data_dir = None  # 老版本 piper 没有这个模块
        else:
            data_dir = espeak_data_dir(Path(ESPEAK_DATA_DIR))
        try:
            if data_dir is not None:
                self.voice = PiperVoice.load(
                    self.model_path, config_path=self.config_path, espeak_data_dir=str(data_dir)
                )
            else:
                self.voice = PiperVoice.load(self.model_path, config_path=self.config_path)
        except TypeError:
            # 老版本 piper 没有 espeak_data_dir 参数
            self.voice = PiperVoice.load(self.model_path, config_path=self.config_path)
        except Exception as e:  # noqa: BLE001
            raise EngineError(f"加载 piper 模型失败（{self.model_path}）：{e}") from e
        cfg = getattr(self.voice, "config", None)
        self.sr = int(getattr(cfg, "sample_rate", 0) or getattr(self.voice, "sample_rate", 22050))

    def close(self) -> None:
        self.voice = None

    def _chunks(self, text: str, rate: float = 1.0):
        v = self.voice
        if hasattr(v, "synthesize"):  # piper 1.8+
            # length_scale 越大越慢；用它控速不会像重采样那样连带改音高。
            cfg = None
            try:
                from piper import SynthesisConfig

                cfg = SynthesisConfig(length_scale=1.0 / max(0.5, min(2.0, rate)))
            except Exception:  # noqa: BLE001 - 老版本没有这个类，退回原速
                cfg = None
            for ch in v.synthesize(text, syn_config=cfg):
                fa = getattr(ch, "audio_float_array", None)
                if fa is not None:
                    yield np.asarray(fa, dtype=np.float32).reshape(-1)
                    continue
                ib = getattr(ch, "audio_int16_bytes", None) or getattr(ch, "audio_int16_array", None)
                if isinstance(ib, (bytes, bytearray)):
                    yield np.frombuffer(ib, dtype="<i2").astype(np.float32) / 32767.0
                elif ib is not None:
                    yield np.asarray(ib, dtype=np.float32) / 32767.0
            return
        # 老接口：写进 wav 再读回来
        buf = io.BytesIO()
        v.synthesize_wav(text, buf)
        buf.seek(0)
        with wave.open(buf, "rb") as w:
            self.sr = w.getframerate()
            data = w.readframes(w.getnframes())
        yield np.frombuffer(data, dtype="<i2").astype(np.float32) / 32767.0

    def render(self, text, *, voice, instruct=None, lang="zh", rate=1.0, pitch=0.0):
        if self.voice is None:
            raise EngineError("piper 未加载")
        yield from self._chunks(text, rate)
