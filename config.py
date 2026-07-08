"""
基础配置 + 共享工具函数
======================
职责：提供全局常量、API 密钥、ffmpeg 路径，以及所有模块共用的 ffmpeg 工具函数。

为什么 run_ffmpeg / get_media_duration 放在这里而不是 compose.py？
  - scenes.py、voice.py、materials.py 都需要它们
  - 放在 compose.py 会导致循环导入（compose 需要 scenes，scenes 需要 compose）
  - config.py 不依赖项目内任何模块 → 放在这里谁都安全引用
"""

import logging
import os
import re
import subprocess

from imageio_ffmpeg import get_ffmpeg_exe

logger = logging.getLogger(__name__)

# ======================== ffmpeg 路径 ========================
FFMPEG = get_ffmpeg_exe()

# ======================== 目录与字体 ========================
FONT_PATH = r"C:\Windows\Fonts\msyh.ttc"
CUR_DIR = os.path.dirname(os.path.abspath(__file__))
MATERIALS_FOLDER = os.path.join(CUR_DIR, "materials")
OUTPUT_FOLDER = os.path.join(CUR_DIR, "output")

# ======================== AI API 密钥 ========================
# DeepSeek — 脚本生成
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# Qwen（通义千问）— 素材视觉识别 + 可选脚本生成
QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "")
QWEN_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
QWEN_TEXT_MODEL = "qwen-plus"
QWEN_VISION_MODEL = "qwen-vl-plus"

# ======================== 视频参数 ========================
FPS = 30
CRF = 20
PRESET = "veryfast"
AUDIO_BITRATE = "128k"
BGM_VOLUME = 0.15
SCENE_TAIL_PAD = 0.5
BLUR_STRENGTH = 20
SUB_MARGIN = 60

# ======================== 画质增强滤镜 ========================
SHARPEN = "unsharp=5:5:1.0:5:5:0.0"
COLOR = "eq=contrast=1.06:saturation=1.12:brightness=0.01"


# ======================== 共享工具函数 ========================
def run_ffmpeg(cmd: list, desc: str = "") -> bool:
    """执行 ffmpeg 命令，失败时打印错误信息

    所有需要调 ffmpeg 的模块都用这个函数，不用各自写 subprocess。
    """
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="ignore")
    if r.returncode != 0:
        logger.error(f"ffmpeg 失败 [{desc}]")
        logger.error("   " + (r.stderr or "")[-500:])
        return False
    return True


def get_media_duration(path: str) -> float | None:
    """获取音视频文件的时长（秒）

    用于配音后自动计算镜头时长，让画面和声音对齐。
    """
    r = subprocess.run([FFMPEG, "-i", path], capture_output=True, text=True,
                       encoding="utf-8", errors="ignore")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", r.stderr or "")
    if m:
        h, mm, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
        return h * 3600 + mm * 60 + s
    return None
