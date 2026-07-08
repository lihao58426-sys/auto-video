"""
字幕渲染 + 单镜头合成
====================
职责：
  1. 把一句字幕文字画成 PNG 图片（透明底 + 白字黑边）
  2. 把一个素材 + 字幕图片 + 配音 → ffmpeg 合成一个镜头片段

依赖：config.py（ffmpeg 参数 / 滤镜 / 工具函数）
"""

import logging
import os

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

from config import (
    FFMPEG,
    FONT_PATH,
    SUB_MARGIN,
    BLUR_STRENGTH,
    SHARPEN,
    COLOR,
    FPS,
    CRF,
    PRESET,
    AUDIO_BITRATE,
    run_ffmpeg,
)


# ======================== 字幕图片 ========================
def render_subtitle_png(text: str, cfg: dict, out_path: str) -> str | None:
    """把字幕文字渲染成 PNG 图片（透明背景 + 白色文字 + 黑色描边）

    为什么用图片而不是 ffmpeg drawtext？
      - 中文字体在 ffmpeg 里容易乱码
      - PIL 能精确控制换行、描边、位置
      - 渲染一次 PNG，ffmpeg 直接叠加上去即可

    Args:
        text: 字幕文字
        cfg: 平台参数（size / font_size / sub_color / sub_pos_ratio）
        out_path: 输出 PNG 路径

    Returns:
        生成的 PNG 路径，text 为空返回 None
    """
    if not text:
        return None

    W, H = cfg["size"]
    fs = cfg["font_size"]
    color = cfg["sub_color"]

    # 加载字体
    try:
        font = ImageFont.truetype(FONT_PATH, fs)
    except Exception as e:
        logger.warning(f"字体加载失败({e})，改用默认字体")
        font = ImageFont.load_default()

    # 自动换行：超出最大宽度就折行
    max_w = W - SUB_MARGIN * 2
    lines: list[str] = []
    cur = ""
    for ch in text:
        test = cur + ch
        if font.getbbox(test)[2] > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = test
    if cur:
        lines.append(cur)

    ascent, descent = font.getmetrics()
    line_h = ascent + descent + 10
    stroke = max(2, int(fs * 0.08))

    # 透明画布，画白字 + 黑边
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    y0 = int(H * cfg["sub_pos_ratio"])
    for i, line in enumerate(lines):
        bbox = font.getbbox(line)
        lw = bbox[2] - bbox[0]
        x = (W - lw) // 2
        y = y0 + i * line_h
        draw.text((x, y), line, font=font, fill=color,
                  stroke_width=stroke, stroke_fill="black")

    img.save(out_path)
    return out_path


# ======================== 单镜头合成 ========================
def build_scene(
    scene: dict, i: int, cfg: dict,
    materials: dict, tmp_dir: str,
) -> str | None:
    """用 ffmpeg 合成一个镜头：素材 + 字幕 + 配音 → mp4

    滤镜链：
      原始素材 → 模糊背景 + 锐化前景 → 叠加字幕 PNG → 混入配音 → 输出单镜头 mp4

    Args:
        scene: 单个分镜 {"material_index":0, "duration":3.0, "text":"...", "voice_path":"..."}
        i: 镜头序号（1-based）
        cfg: 平台参数
        materials: 素材列表
        tmp_dir: 临时目录

    Returns:
        生成的镜头 mp4 路径，失败返回 None
    """
    all_mats = materials["images"] + materials["videos"]
    W, H = cfg["size"]
    dur = float(scene.get("duration", 3.0))
    idx = scene.get("material_index", 0)

    if idx < 0 or idx >= len(all_mats):
        logger.warning(f"镜头 {i} 素材索引越界，跳过")
        return None

    path = all_mats[idx]
    text = scene.get("text", "")
    ext = os.path.splitext(path)[1].lower()
    is_image = ext in (".jpg", ".jpeg", ".png", ".bmp")
    logger.info(f"镜头 {i}: {os.path.basename(path)} | {dur}s | {text[:14]}")

    # 生成字幕图片
    sub_png = None
    if text:
        sub_png = os.path.join(tmp_dir, f"sub_{i}.png")
        render_subtitle_png(text, cfg, sub_png)

    # 构建 ffmpeg 输入
    inputs: list[str] = []
    ci = 0

    if is_image:
        inputs += ["-loop", "1", "-t", f"{dur}", "-i", path]
    else:
        inputs += ["-stream_loop", "-1", "-i", path]
    main_i = ci
    ci += 1

    sub_i = None
    if sub_png:
        inputs += ["-loop", "1", "-i", sub_png]
        sub_i = ci
        ci += 1

    voice = scene.get("voice_path")
    if voice and os.path.exists(voice):
        inputs += ["-i", voice]
    else:
        # 没有配音 → 生成静音轨道
        inputs += ["-f", "lavfi", "-i",
                   "anullsrc=channel_layout=stereo:sample_rate=44100"]
    aud_i = ci
    ci += 1

    # ffmpeg 滤镜链
    fc = (
        f"[{main_i}:v]split=2[fgs][bgs];"
        f"[bgs]scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},boxblur={BLUR_STRENGTH}:1[bg];"
        f"[fgs]scale={W}:{H}:force_original_aspect_ratio=decrease,"
        f"{SHARPEN},{COLOR}[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={FPS},setsar=1[bgd];"
    )
    if sub_i is not None:
        fc += f"[bgd][{sub_i}:v]overlay=0:0,format=yuv420p[v];"
    else:
        fc += "[bgd]format=yuv420p[v];"
    fc += (
        f"[{aud_i}:a]aformat=sample_rates=44100:channel_layouts=stereo,"
        f"apad[a]"
    )

    out = os.path.join(tmp_dir, f"scene_{i:03d}.mp4")
    cmd = [
        FFMPEG, "-y", *inputs,
        "-filter_complex", fc,
        "-map", "[v]", "-map", "[a]",
        "-t", f"{dur}", "-r", str(FPS),
        "-c:v", "libx264", "-crf", str(CRF), "-preset", PRESET,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", "44100", "-ac", "2",
        out,
    ]

    return out if (run_ffmpeg(cmd, f"镜头{i}") and os.path.exists(out)) else None
