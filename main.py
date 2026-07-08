"""
卡丁车门店 · 全自动短视频生成系统 — 主入口
===========================================
职责：只做编排调度，不干具体活。

调用链（8 个模块的分工）：
  1. config.py     → 常量和 ffmpeg 工具
  2. platforms.py  → 三平台参数（尺寸/音色/字幕样式）
  3. materials.py  → 扫描素材文件夹 + AI 识别画面内容
  4. script_gen.py → AI 生成分镜脚本（或默认模板）
  5. voice.py      → edge-tts 逐句配音
  6. scenes.py     → 渲染字幕 PNG + 合成单镜头
  7. compose.py    → 拼接所有镜头 + 叠加 BGM
  8. main.py       → 你就是它 ← 按顺序调用上面 7 个

用法：
  python main.py          交互模式：选择平台 → 生成视频
  python main.py 抖音      直接指定平台生成
"""

import asyncio
import logging
import os
import shutil
import sys
from datetime import datetime

from config import (
    FONT_PATH,
    MATERIALS_FOLDER,
    OUTPUT_FOLDER,
    DEEPSEEK_API_KEY,
    QWEN_API_KEY,
)
from platforms import PLATFORM_CONFIG
from materials import scan_materials, caption_materials
from script_gen import generate_script_with_ai, generate_default_script
from voice import prepare_scene_audios
from compose import compose_video

# ── 日志配置（入口文件负责，所有模块自动继承）──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("auto_video.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ======================== 主流程 ========================
async def generate_video(platform: str = "抖音") -> str | None:
    """生成一条完整的短视频

    这是整个系统的唯一入口函数。按顺序调 5 个步骤：
      扫描素材 → AI 生成脚本 → TTS 配音 → 合成 → 输出

    Args:
        platform: 平台名，必须是 PLATFORM_CONFIG 里的 key

    Returns:
        最终视频文件路径，失败返回 None
    """
    logger.info(f"开始生成【{platform}】卡丁车视频")
    logger.info("=" * 50)

    cfg = PLATFORM_CONFIG[platform]

    # 检查字体（缺字体字幕会崩）
    if not os.path.exists(FONT_PATH):
        logger.warning(f"字体不存在: {FONT_PATH}（请在 config.py 改成有效路径）")

    # ── 步骤 1：扫描素材 ── materials.py ──
    materials = scan_materials(MATERIALS_FOLDER)
    if not materials["images"] and not materials["videos"]:
        logger.error("没有素材，无法生成")
        return None

    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    tmp_dir = os.path.join(OUTPUT_FOLDER, "_tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    # ── 步骤 2：AI 识别素材内容 ── materials.py ──
    captions = caption_materials(materials, tmp_dir)

    # ── 步骤 3：生成分镜脚本 ── script_gen.py ──
    has_any_key = DEEPSEEK_API_KEY or QWEN_API_KEY
    if has_any_key:
        script = generate_script_with_ai(materials, platform, cfg, captions)
    else:
        logger.warning("未设置任何 AI API Key，使用默认脚本")
        script = generate_default_script(materials, platform, cfg)

    if not script:
        return None

    # ── 步骤 4：TTS 配音 ── voice.py ──
    logger.info("逐句生成配音...")
    script = await prepare_scene_audios(script, cfg, tmp_dir)

    # ── 步骤 5：合成输出 ── compose.py ──
    today = datetime.now()
    output_path = os.path.join(
        OUTPUT_FOLDER,
        f"{today.month:02d}{today.day:02d}_{platform}.mp4",
    )

    result = compose_video(script, cfg, materials, tmp_dir, output_path)

    # 清理临时文件
    try:
        shutil.rmtree(tmp_dir)
    except Exception:
        pass

    if result:
        logger.info(f"完成！输出: {output_path}")
        logger.info(f"标题: {script.get('title')} | BGM: {script.get('bgm_style')}")

    return result


# ======================== 入口 ========================
if __name__ == "__main__":
    # 支持命令行直接指定平台：python main.py 抖音
    if len(sys.argv) > 1:
        platform = sys.argv[1]
        if platform in PLATFORM_CONFIG:
            asyncio.run(generate_video(platform))
        else:
            logger.error(f"未知平台: {platform}")
            logger.info(f"可选: {', '.join(PLATFORM_CONFIG.keys())}")
    else:
        # 交互模式
        print("=" * 50)
        print("卡丁车门店 · 自动视频生成系统")
        print("=" * 50)
        print("\n请选择平台：")
        print("1. 抖音")
        print("2. 小红书")
        print("3. 微信视频号")
        print("0. 退出")
        choice = input("\n请输入选项 (0-3): ").strip()

        mapping = {"1": "抖音", "2": "小红书", "3": "视频号"}
        if choice in mapping:
            asyncio.run(generate_video(mapping[choice]))
        elif choice == "0":
            print("再见！")
        else:
            logger.error("无效选项")
