"""
============================================================
卡丁车门店 · 全自动短视频生成系统（ffmpeg 引擎 · 增强版）
------------------------------------------------------------
功能：扫描素材 → AI视觉识别素材 → AI生成分镜脚本 → 逐句配音
      → 加字幕/模糊背景/画质增强 → 拼接镜头 → 叠加BGM → 输出
支持平台：抖音 / 小红书 / 微信视频号
AI模型：DeepSeek（脚本）+ Qwen VL（素材识别）
============================================================
"""

import os
import re
import json
import base64
import shutil
import asyncio
import subprocess
from datetime import datetime

import requests
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from imageio_ffmpeg import get_ffmpeg_exe


# ======================== 基础配置区 ========================
FFMPEG = get_ffmpeg_exe()

FONT_PATH = r"C:\Windows\Fonts\msyh.ttc"
CUR_DIR = os.path.dirname(os.path.abspath(__file__))
MATERIALS_FOLDER = os.path.join(CUR_DIR, "materials")
OUTPUT_FOLDER    = os.path.join(CUR_DIR, "output")

# DeepSeek — 脚本生成
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# Qwen（通义千问）— 素材视觉识别 + 可选脚本生成
QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "")
QWEN_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
QWEN_TEXT_MODEL = "qwen-plus"
QWEN_VISION_MODEL = "qwen-vl-plus"

FPS = 30
CRF = 20
PRESET = "veryfast"
AUDIO_BITRATE = "128k"
BGM_VOLUME = 0.15
SCENE_TAIL_PAD = 0.5
BLUR_STRENGTH = 20
SUB_MARGIN = 60

# 画质增强滤镜（来自 video2.py）
SHARPEN = "unsharp=5:5:1.0:5:5:0.0"
COLOR   = "eq=contrast=1.06:saturation=1.12:brightness=0.01"


# 各平台参数
PLATFORM_CONFIG = {
    "抖音": {
        "size": (1080, 1920),
        "voice": "zh-CN-YunxiNeural",
        "font_size": 72,
        "sub_color": "white",
        "sub_pos_ratio": 0.74,
        "clip_range": (1.5, 3.0),
        "tail": "想体验的老铁，评论区扣1！",
        "style_note": "快节奏、有冲击力、接地气，突出速度与刺激感",
    },
    "小红书": {
        "size": (1080, 1440),
        "voice": "zh-CN-XiaoxiaoNeural",
        "font_size": 56,
        "sub_color": "white",
        "sub_pos_ratio": 0.82,
        "clip_range": (2.5, 4.0),
        "tail": "地址放评论啦，姐妹快冲～",
        "style_note": "精致、种草、闺蜜分享感，突出出片好看和体验感",
    },
    "视频号": {
        "size": (1080, 1920),
        "voice": "zh-CN-YunjianNeural",
        "font_size": 62,
        "sub_color": "white",
        "sub_pos_ratio": 0.80,
        "clip_range": (3.0, 5.0),
        "tail": "周末带上家人朋友，一起来体验。",
        "style_note": "稳重、专业、有安全感，突出适合家庭朋友聚会",
    },
}


# ======================== 工具函数 ========================
def run_ffmpeg(cmd, desc=""):
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="ignore")
    if r.returncode != 0:
        print(f"   [FAIL] ffmpeg 失败 [{desc}]")
        print("   " + (r.stderr or "")[-500:])
        return False
    return True


def get_media_duration(path):
    r = subprocess.run([FFMPEG, "-i", path], capture_output=True, text=True,
                       encoding="utf-8", errors="ignore")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", r.stderr or "")
    if m:
        h, mm, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
        return h * 3600 + mm * 60 + s
    return None


def scan_materials(folder):
    print(f"扫描素材文件夹: {folder}")
    materials = {"images": [], "videos": []}
    if not os.path.exists(folder):
        print(f"[ERROR] 文件夹不存在: {folder}")
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

    print(f"[OK] 图片 {len(materials['images'])} 张 / 视频 {len(materials['videos'])} 个")
    return materials


# ======================== 素材视觉识别（Qwen VL） ========================
def encode_image_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def extract_video_frame(video_path, out_path, at=1.0):
    return run_ffmpeg([FFMPEG, "-y", "-ss", str(at), "-i", video_path,
                       "-vframes", "1", "-q:v", "2", out_path], "抽帧")


def describe_image(img_path):
    """调用 Qwen VL 视觉模型识别画面内容"""
    if not QWEN_API_KEY:
        return "(未设置 QWEN_API_KEY)"
    try:
        b64 = encode_image_base64(img_path)
        headers = {"Content-Type": "application/json",
                   "Authorization": f"Bearer {QWEN_API_KEY}"}
        data = {
            "model": QWEN_VISION_MODEL,
            "messages": [{"role": "user", "content": [
                {"type": "text",
                 "text": "用一句话(25字内)描述这张卡丁车相关画面：主体是什么、"
                         "动作/场景、画面氛围。只描述看到的内容。"},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            ]}],
            "max_tokens": 80,
        }
        resp = requests.post(QWEN_API_URL, headers=headers, json=data, timeout=40)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
        print(f"   视觉模型返回 {resp.status_code}: {resp.text[:150]}")
    except Exception as e:
        print(f"   识别失败: {e}")
    return "(未识别)"


def caption_materials(materials, tmp_dir):
    """用 AI 识别每个素材的画面内容，返回描述列表"""
    if not QWEN_API_KEY:
        print("未设置 QWEN_API_KEY，跳过素材识别（AI 将盲排画面）")
        return None
    print("正在识别素材内容（Qwen VL）...")
    all_mats = materials["images"] + materials["videos"]
    captions = []
    image_ext = (".jpg", ".jpeg", ".png", ".bmp")
    for i, path in enumerate(all_mats):
        ext = os.path.splitext(path)[1].lower()
        if ext in image_ext:
            img_for_ai = path
        else:
            img_for_ai = os.path.join(tmp_dir, f"frame_{i}.jpg")
            if not extract_video_frame(path, img_for_ai):
                captions.append("(视频，无法预览)")
                continue
        desc = describe_image(img_for_ai)
        captions.append(desc)
        print(f"   素材 {i}: {desc}")
    return captions


# ======================== 配音 ========================
async def generate_voice(text, out_path, voice_name):
    if not text:
        return None
    try:
        communicate = edge_tts.Communicate(text, voice_name)
        await communicate.save(out_path)
        return out_path
    except Exception as e:
        print(f"   配音失败: {e}")
        return None


def convert_to_wav(mp3_path):
    wav_path = os.path.splitext(mp3_path)[0] + ".wav"
    ok = run_ffmpeg([FFMPEG, "-y", "-i", mp3_path,
                     "-ar", "44100", "-ac", "2", wav_path], desc="mp3->wav")
    return wav_path if (ok and os.path.exists(wav_path)) else mp3_path


async def prepare_scene_audios(script, cfg, tmp_dir):
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
            print(f"   镜头 {i+1} 无配音，用静音时长 {scene.get('duration')}s")
    return script


# ======================== 字幕图片 ========================
def render_subtitle_png(text, cfg, out_path):
    if not text:
        return None
    W, H = cfg["size"]
    fs = cfg["font_size"]
    color = cfg["sub_color"]

    try:
        font = ImageFont.truetype(FONT_PATH, fs)
    except Exception as e:
        print(f"   字体加载失败({e})，改用默认字体")
        font = ImageFont.load_default()

    max_w = W - SUB_MARGIN * 2
    lines, cur = [], ""
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


# ======================== 单镜头生成 ========================
def build_scene(scene, i, cfg, materials, tmp_dir):
    all_mats = materials["images"] + materials["videos"]
    W, H = cfg["size"]
    dur = float(scene.get("duration", 3.0))
    idx = scene.get("material_index", 0)

    if idx < 0 or idx >= len(all_mats):
        print(f"   镜头 {i} 素材索引越界，跳过")
        return None

    path = all_mats[idx]
    text = scene.get("text", "")
    ext = os.path.splitext(path)[1].lower()
    is_image = ext in (".jpg", ".jpeg", ".png", ".bmp")
    print(f"   镜头 {i}: {os.path.basename(path)} | {dur}s | {text[:14]}")

    sub_png = None
    if text:
        sub_png = os.path.join(tmp_dir, f"sub_{i}.png")
        render_subtitle_png(text, cfg, sub_png)

    inputs, ci = [], 0
    if is_image:
        inputs += ["-loop", "1", "-t", f"{dur}", "-i", path]
    else:
        inputs += ["-stream_loop", "-1", "-i", path]
    main_i = ci; ci += 1

    sub_i = None
    if sub_png:
        inputs += ["-loop", "1", "-i", sub_png]
        sub_i = ci; ci += 1

    voice = scene.get("voice_path")
    if voice and os.path.exists(voice):
        inputs += ["-i", voice]
    else:
        inputs += ["-f", "lavfi", "-i",
                   "anullsrc=channel_layout=stereo:sample_rate=44100"]
    aud_i = ci; ci += 1

    # 滤镜链：模糊背景 + 锐化调色 + 字幕叠加
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
    fc += (f"[{aud_i}:a]aformat=sample_rates=44100:channel_layouts=stereo,"
           f"apad[a]")

    out = os.path.join(tmp_dir, f"scene_{i:03d}.mp4")
    cmd = [FFMPEG, "-y", *inputs,
           "-filter_complex", fc,
           "-map", "[v]", "-map", "[a]",
           "-t", f"{dur}", "-r", str(FPS),
           "-c:v", "libx264", "-crf", str(CRF), "-preset", PRESET,
           "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", "44100", "-ac", "2",
           out]

    return out if (run_ffmpeg(cmd, f"镜头{i}") and os.path.exists(out)) else None


# ======================== AI 脚本生成（DeepSeek / Qwen 双模型） ========================
def _call_ai_api(api_url, api_key, model, prompt):
    """通用 AI API 调用（OpenAI 兼容协议）"""
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {api_key}"}
    data = {"model": model,
            "messages": [
                {"role": "system", "content": "你是专业短视频导演，只输出JSON。"},
                {"role": "user", "content": prompt}],
            "temperature": 0.8, "max_tokens": 1200}
    resp = requests.post(api_url, headers=headers, json=data, timeout=60)
    if resp.status_code == 200:
        content = resp.json()["choices"][0]["message"]["content"].strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        return json.loads(content)
    print(f"AI 返回 {resp.status_code}: {resp.text[:150]}")
    return None


def _pick_ai_provider():
    """自动选择可用的 AI 提供商：优先 DeepSeek，其次 Qwen"""
    if DEEPSEEK_API_KEY:
        return "deepseek", DEEPSEEK_API_KEY, DEEPSEEK_API_URL, "deepseek-chat"
    if QWEN_API_KEY:
        return "qwen", QWEN_API_KEY, QWEN_API_URL, QWEN_TEXT_MODEL
    return None, None, None, None


def generate_script_with_ai(materials, platform, cfg, captions=None):
    print(f"AI 生成【{platform}】卡丁车分镜脚本...")
    all_mats = materials["images"] + materials["videos"]
    if not all_mats:
        return None

    lo, hi = cfg["clip_range"]

    # 如果有素材识别结果，构建精准的素材描述
    if captions:
        mat_desc = "\n".join(f"  [{i}] {c}" for i, c in enumerate(captions))
        mat_block = f"""每个素材的真实画面内容如下（务必根据内容编排）：
{mat_desc}

编排原则：
- 选画面最有冲击力/最抓眼的素材放第一镜做钩子；
- 字幕文案要和该镜头画面内容匹配；
- 相似画面不要连着放，注意节奏与镜头衔接。"""
    else:
        mat_block = (f"素材：共 {len(all_mats)} 个"
                     f"（图片 {len(materials['images'])}，视频 {len(materials['videos'])}）。")

    prompt = f"""你是专业短视频导演，为【卡丁车体验门店】制作{platform}平台爆款视频。
{mat_block}
目标总时长 15-25 秒。
卖点：极速漂移、肾上腺素飙升、赛道竞速、新手也能玩、朋友家人聚会、真实赛车座舱、拍照出片酷炫。
平台风格：{cfg['style_note']}

只输出如下 JSON：
{{
  "title": "标题(12字内)",
  "bgm_style": "动感/轻快/热血",
  "scenes": [
    {{"material_index":0,"duration":{lo},"text":"字幕文字"}}
  ]
}}
要求：第一镜为最抓眼球的钩子；material_index 取 0~{len(all_mats)-1} 且每个只用一次；
每镜 duration 在 {lo}-{hi} 秒；最后一镜字幕用 "{cfg['tail']}"；字幕简短有力、热血刺激。"""

    provider, key, url, model = _pick_ai_provider()
    if not provider:
        print("未设置任何 AI API Key（DEEPSEEK_API_KEY / QWEN_API_KEY），改用默认脚本")
        return generate_default_script(materials, platform, cfg)

    print(f"使用 AI: {provider} ({model})")
    try:
        script = _call_ai_api(url, key, model, prompt)
        if script:
            print(f"[OK] AI 脚本：{script.get('title')} / {len(script.get('scenes', []))} 镜头")
            return script
    except Exception as e:
        print(f"AI 调用出错：{e}，改用默认脚本")
    return generate_default_script(materials, platform, cfg)


def generate_default_script(materials, platform, cfg):
    all_mats = materials["images"] + materials["videos"]
    if not all_mats:
        return None

    hook = "这速度谁顶得住？"
    body = ["真实赛车座舱，一脚油门到底", "过弯漂移，肾上腺素拉满",
            "新手也能轻松上手", "和朋友来一场真正的竞速",
            "弯道超车的瞬间太爽了", "全程真实赛道体验"]

    lo, hi = cfg["clip_range"]
    mid = (lo + hi) / 2
    n = len(all_mats)
    scenes = []
    for i in range(n):
        if i == 0:
            text = hook
        elif i == n - 1:
            text = cfg["tail"]
        else:
            text = body[(i - 1) % len(body)]
        scenes.append({"material_index": i, "duration": mid, "text": text})

    print(f"[OK] 默认脚本完成，共 {n} 镜头")
    return {"title": f"{platform}·极速卡丁车", "bgm_style": "动感", "scenes": scenes}


# ======================== 拼接合成 ========================
def compose_video(script, cfg, materials, tmp_dir, output_path):
    print("逐镜头生成...")
    scenes = script.get("scenes", [])
    if not scenes:
        print("[ERROR] 没有分镜信息")
        return None

    scene_files = [f for f in
                   (build_scene(s, i, cfg, materials, tmp_dir)
                    for i, s in enumerate(scenes, 1)) if f]
    if not scene_files:
        print("[ERROR] 没有生成任何镜头")
        return None

    print("拼接镜头...")
    list_file = os.path.join(tmp_dir, "concat_list.txt")
    with open(list_file, "w", encoding="utf-8") as fp:
        for f in scene_files:
            fp.write(f"file '{f}'\n")

    merged = os.path.join(tmp_dir, "_merged.mp4")
    if not run_ffmpeg([FFMPEG, "-y", "-f", "concat", "-safe", "0",
                       "-i", list_file, "-c", "copy", merged], "拼接"):
        return None

    # BGM 叠加（可选）
    bgm_path = os.path.join(CUR_DIR, "bgm.mp3")
    if os.path.exists(bgm_path):
        print(f"叠加背景音乐: bgm.mp3")
        ok = run_ffmpeg(
            [FFMPEG, "-y", "-i", merged, "-i", bgm_path,
             "-filter_complex",
             f"[1:a]volume={BGM_VOLUME}[b];"
             "[0:a][b]amix=inputs=2:duration=first:dropout_transition=0[a]",
             "-map", "0:v", "-map", "[a]",
             "-c:v", "copy", "-c:a", "aac", "-b:a", AUDIO_BITRATE,
             output_path], "叠加BGM")
        if ok:
            return output_path
        print("BGM 叠加失败，输出无 BGM 版本")

    shutil.copy(merged, output_path)
    return output_path


# ======================== 主流程 ========================
async def generate_video(platform="抖音"):
    print(f"\n{'='*50}\n开始生成【{platform}】卡丁车视频\n{'='*50}\n")
    cfg = PLATFORM_CONFIG[platform]

    if not os.path.exists(FONT_PATH):
        print(f"字体不存在: {FONT_PATH}（请在配置区改成有效路径）")

    materials = scan_materials(MATERIALS_FOLDER)
    if not materials["images"] and not materials["videos"]:
        print("[ERROR] 没有素材，无法生成")
        return None

    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    tmp_dir = os.path.join(OUTPUT_FOLDER, "_tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    # 1. AI 视觉识别素材内容（Qwen VL）
    captions = caption_materials(materials, tmp_dir)

    # 2. AI 生成脚本（DeepSeek / Qwen）
    has_any_key = DEEPSEEK_API_KEY or QWEN_API_KEY
    if has_any_key:
        script = generate_script_with_ai(materials, platform, cfg, captions)
    else:
        print("未设置任何 AI API Key，使用默认脚本")
        script = generate_default_script(materials, platform, cfg)
    if not script:
        return None

    # 3. TTS 配音
    print("逐句生成配音...")
    script = await prepare_scene_audios(script, cfg, tmp_dir)

    # 4. 合成输出
    today = datetime.now()
    output_path = os.path.join(
        OUTPUT_FOLDER, f"{today.month:02d}{today.day:02d}_{platform}.mp4")

    result = compose_video(script, cfg, materials, tmp_dir, output_path)

    # 5. 清理临时文件
    try:
        shutil.rmtree(tmp_dir)
    except Exception:
        pass

    if result:
        print(f"\n{'='*50}\n[OK] 完成！\n输出: {output_path}\n"
              f"标题: {script.get('title')} | BGM: {script.get('bgm_style')}\n{'='*50}\n")
    return result


# ======================== 入口 ========================
if __name__ == "__main__":
    print("=" * 50)
    print("卡丁车门店 · 自动视频生成系统 (增强版)")
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
        print("[ERROR] 无效选项")
