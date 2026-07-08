"""
视频拼接 + BGM 叠加
===================
职责：把所有单镜头 mp4 按顺序拼成完整视频，可选叠加背景音乐。

依赖：config.py（ffmpeg 路径/参数）+ scenes.py（build_scene）
"""

import logging
import os
import shutil

from config import (
    FFMPEG,
    CUR_DIR,
    BGM_VOLUME,
    AUDIO_BITRATE,
    run_ffmpeg,
)
from scenes import build_scene

logger = logging.getLogger(__name__)


def compose_video(
    script: dict, cfg: dict, materials: dict,
    tmp_dir: str, output_path: str,
) -> str | None:
    """拼接所有镜头 → 叠加 BGM → 输出最终视频

    这是视频生成的最后一步。前面所有模块产出的东西在这里汇总。

    Args:
        script: 分镜脚本（已含 voice_path 和 duration）
        cfg: 平台参数
        materials: 素材列表
        tmp_dir: 临时目录
        output_path: 最终输出路径（如 output/0708_抖音.mp4）

    Returns:
        最终视频路径，失败返回 None
    """
    scenes = script.get("scenes", [])
    if not scenes:
        logger.error(" 没有分镜信息")
        return None

    # 逐镜头生成
    logger.info("逐镜头生成...")
    scene_files = [
        f for f in (
            build_scene(s, i, cfg, materials, tmp_dir)
            for i, s in enumerate(scenes, 1)
        ) if f
    ]
    if not scene_files:
        logger.error(" 没有生成任何镜头")
        return None

    # 拼接所有镜头
    logger.info("拼接镜头...")
    list_file = os.path.join(tmp_dir, "concat_list.txt")
    with open(list_file, "w", encoding="utf-8") as fp:
        for f in scene_files:
            fp.write(f"file '{f}'\n")

    merged = os.path.join(tmp_dir, "_merged.mp4")
    if not run_ffmpeg(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0",
         "-i", list_file, "-c", "copy", merged],
        desc="拼接",
    ):
        return None

    # 叠加背景音乐（可选）
    bgm_path = os.path.join(CUR_DIR, "bgm.mp3")
    if os.path.exists(bgm_path):
        logger.info("叠加背景音乐: bgm.mp3")
        ok = run_ffmpeg(
            [FFMPEG, "-y", "-i", merged, "-i", bgm_path,
             "-filter_complex",
             f"[1:a]volume={BGM_VOLUME}[b];"
             "[0:a][b]amix=inputs=2:duration=first:dropout_transition=0[a]",
             "-map", "0:v", "-map", "[a]",
             "-c:v", "copy", "-c:a", "aac", "-b:a", AUDIO_BITRATE,
             output_path],
            desc="叠加BGM",
        )
        if ok:
            return output_path
        logger.warning("BGM 叠加失败，输出无 BGM 版本")

    # 没有 BGM → 直接复制合并后的文件
    shutil.copy(merged, output_path)
    return output_path
