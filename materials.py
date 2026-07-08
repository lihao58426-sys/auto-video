"""
素材扫描 + AI 视觉识别
======================
职责：
  1. 扫描 materials 文件夹 → 分类图片/视频
  2. 调 Qwen VL 视觉模型 → 识别每个素材的画面内容
  3. 返回素材描述列表，供 script_gen 编排分镜用

依赖：config.py（FFMPEG / API 密钥 / run_ffmpeg）
"""

import logging
import os
import base64

import requests

from config import (
    FFMPEG,
    QWEN_API_KEY,
    QWEN_VISION_MODEL,
    QWEN_API_URL,
    run_ffmpeg,
)
from exceptions import AIGenerationError

logger = logging.getLogger(__name__)


# ======================== 素材扫描 ========================
def scan_materials(folder: str) -> dict[str, list[str]]:
    """扫描文件夹，把图片和视频分开

    Args:
        folder: 素材文件夹路径

    Returns:
        {"images": ["path1.jpg", ...], "videos": ["path1.mp4", ...]}
    """
    logger.info(f"扫描素材文件夹: {folder}")
    materials: dict = {"images": [], "videos": []}

    if not os.path.exists(folder):
        logger.error(f"文件夹不存在: {folder}")
        return materials

    image_ext = (".jpg", ".jpeg", ".png", ".bmp")
    video_ext = (".mp4", ".mov", ".avi", ".mkv")

    for f in sorted(os.listdir(folder)):
        fp = os.path.join(folder, f)
        if os.path.isdir(fp):
            continue
        ext = os.path.splitext(f)[1].lower()
        if ext in image_ext:
            materials["images"].append(fp)
        elif ext in video_ext:
            materials["videos"].append(fp)

    logger.info(f"图片 {len(materials['images'])} 张 / 视频 {len(materials['videos'])} 个")
    return materials


# ======================== AI 视觉识别 ========================
def _encode_image_base64(path: str) -> str:
    """把图片文件编码为 base64 字符串（API 传输用）"""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _extract_video_frame(video_path: str, out_path: str, at: float = 1.0) -> bool:
    """从视频第 N 秒抽一帧作为缩略图，给 AI 识别用"""
    return run_ffmpeg(
        [FFMPEG, "-y", "-ss", str(at), "-i", video_path,
         "-vframes", "1", "-q:v", "2", out_path],
        desc="抽帧",
    )


def _describe_image(img_path: str) -> str:
    """调用 Qwen VL 视觉模型识别单张画面内容"""
    if not QWEN_API_KEY:
        return "(未设置 QWEN_API_KEY)"

    try:
        b64 = _encode_image_base64(img_path)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {QWEN_API_KEY}",
        }
        data = {
            "model": QWEN_VISION_MODEL,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text",
                     "text": "用一句话(25字内)描述这张卡丁车相关画面：主体是什么、"
                             "动作/场景、画面氛围。只描述看到的内容。"},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            }],
            "max_tokens": 80,
        }
        resp = requests.post(QWEN_API_URL, headers=headers, json=data, timeout=40)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
        logger.warning(f"视觉模型返回 {resp.status_code}: {resp.text[:150]}")
    except (requests.RequestException, KeyError, OSError) as e:
        # 网络异常、API 返回格式不对、图片文件损坏
        logger.warning(f"识别失败: {e}")

    return "(未识别)"


def caption_materials(materials: dict, tmp_dir: str) -> list[str] | None:
    """给每个素材生成一句话画面描述

    这是 AI 视频的核心步骤——知道素材内容后，
    script_gen 才能编排"哪个镜头配哪句文案"。

    Args:
        materials: scan_materials() 的返回值
        tmp_dir: 临时目录（视频抽帧放这里）

    Returns:
        素材描述列表，顺序和 materials 一致；未设置 API Key 返回 None
    """
    if not QWEN_API_KEY:
        logger.warning("未设置 QWEN_API_KEY，跳过素材识别（AI 将盲排画面）")
        return None

    logger.info("正在识别素材内容（Qwen VL）...")
    all_mats = materials["images"] + materials["videos"]
    captions: list[str] = []
    image_ext = (".jpg", ".jpeg", ".png", ".bmp")

    for i, path in enumerate(all_mats):
        ext = os.path.splitext(path)[1].lower()
        if ext in image_ext:
            img_for_ai = path
        else:
            img_for_ai = os.path.join(tmp_dir, f"frame_{i}.jpg")
            if not _extract_video_frame(path, img_for_ai):
                captions.append("(视频，无法预览)")
                continue
        desc = _describe_image(img_for_ai)
        captions.append(desc)
        logger.info(f"素材 {i}: {desc}")

    return captions
