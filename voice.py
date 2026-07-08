"""
TTS 配音模块
============
职责：把分镜脚本里每句字幕文字，用 edge-tts 转成语音文件。

流程：
  字幕文字 → edge-tts 生成 mp3 → ffmpeg 转 wav → 计算音频时长 → 更新镜头 duration

依赖：config.py（FFMPEG / SCENE_TAIL_PAD / run_ffmpeg / get_media_duration）
"""

import logging
import os

import edge_tts

from config import (
    FFMPEG,
    SCENE_TAIL_PAD,
    run_ffmpeg,
    get_media_duration,
)
from exceptions import TTSError

logger = logging.getLogger(__name__)


# ======================== 单句配音 ========================
async def generate_voice(text: str, out_path: str, voice_name: str) -> str | None:
    """用 edge-tts 把文字转成 mp3 语音

    Args:
        text: 要朗读的文字
        out_path: 输出 mp3 路径
        voice_name: edge-tts 音色名（如 zh-CN-YunxiNeural）

    Returns:
        生成的 mp3 文件路径，失败返回 None
    """
    if not text:
        return None
    try:
        communicate = edge_tts.Communicate(text, voice_name)
        await communicate.save(out_path)
        return out_path
    except (OSError, RuntimeError) as e:
        # edge-tts 网络异常 或 音频编码错误
        logger.warning(f"配音失败: {e}")
        return None


# ======================== 格式转换 ========================
def convert_to_wav(mp3_path: str) -> str:
    """mp3 → wav（ffmpeg 合成时 wav 兼容性更好）"""
    wav_path = os.path.splitext(mp3_path)[0] + ".wav"
    ok = run_ffmpeg(
        [FFMPEG, "-y", "-i", mp3_path,
         "-ar", "44100", "-ac", "2", wav_path],
        desc="mp3->wav",
    )
    return wav_path if (ok and os.path.exists(wav_path)) else mp3_path


# ======================== 批量配音 ========================
async def prepare_scene_audios(script: dict, cfg: dict, tmp_dir: str) -> dict:
    """给脚本里每个镜头生成配音，并自动计算镜头时长

    这是配音模块的核心函数——遍历所有镜头，逐句配音，
    根据音频长度自动设置镜头 duration（画面和声音对齐）。

    Args:
        script: 分镜脚本（来自 script_gen.py）
        cfg: 平台参数（来自 platforms.py）
        tmp_dir: 临时目录

    Returns:
        更新后的 script（每个 scene 多了 voice_path 和 duration）
    """
    for i, scene in enumerate(script.get("scenes", [])):
        text = scene.get("text", "")
        mp3_path = os.path.join(tmp_dir, f"scene_{i}.mp3")
        result = await generate_voice(text, mp3_path, cfg["voice"])

        if result:
            wav_path = convert_to_wav(mp3_path)
            dur = get_media_duration(wav_path)
            if dur:
                scene["duration"] = round(dur + SCENE_TAIL_PAD, 2)
            scene["voice_path"] = wav_path
        else:
            scene["voice_path"] = None
            logger.info(f"镜头 {i+1} 无配音，用静音时长 {scene.get('duration')}s")

    return script
