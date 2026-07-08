"""
AI 分镜脚本生成
===============
职责：根据素材数量 + 平台风格，调 AI 生成分镜脚本（哪段素材配什么字幕）

支持双模型自动切换：优先 DeepSeek，没有就降级到 Qwen，再没有就用默认模板。

依赖：config.py（API 密钥）
"""

import json
import logging

import requests

from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_API_URL,
    QWEN_API_KEY,
    QWEN_API_URL,
    QWEN_TEXT_MODEL,
)
from exceptions import AIGenerationError

logger = logging.getLogger(__name__)


# ======================== AI 调用底层 ========================
def _call_ai_api(api_url: str, api_key: str, model: str, prompt: str) -> dict | None:
    """通用 AI API 调用（OpenAI 兼容协议）

    不管调的是 DeepSeek 还是 Qwen，都用同一个函数。
    返回解析后的 JSON dict，失败返回 None。
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是专业短视频导演，只输出JSON。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.8,
        "max_tokens": 1200,
    }
    resp = requests.post(api_url, headers=headers, json=data, timeout=60)

    if resp.status_code == 200:
        content = resp.json()["choices"][0]["message"]["content"].strip()
        # AI 返回的 JSON 可能被 ```json ... ``` 包裹，去掉
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        return json.loads(content)

    logger.warning(f"AI 返回 {resp.status_code}: {resp.text[:150]}")
    return None


def _pick_ai_provider() -> tuple[str | None, str | None, str | None, str | None]:
    """自动选择可用的 AI 提供商

    优先级：DeepSeek > Qwen
    返回：(provider_name, api_key, api_url, model)
    都不可用返回：(None, None, None, None)
    """
    if DEEPSEEK_API_KEY:
        return "deepseek", DEEPSEEK_API_KEY, DEEPSEEK_API_URL, "deepseek-chat"
    if QWEN_API_KEY:
        return "qwen", QWEN_API_KEY, QWEN_API_URL, QWEN_TEXT_MODEL
    return None, None, None, None


# ======================== 脚本生成 ========================
def generate_script_with_ai(
    materials: dict,
    platform: str,
    cfg: dict,
    captions: list[str] | None = None,
) -> dict | None:
    """用 AI 生成分镜脚本（主力模式）

    Args:
        materials: scan_materials 的返回值
        platform: 平台名（"抖音"/"小红书"/"视频号"）
        cfg: 平台参数（来自 platforms.py）
        captions: AI 识别的素材描述（来自 materials.py），没有就盲排

    Returns:
        分镜脚本 dict: {"title": "...", "bgm_style": "...", "scenes": [...]}
    """
    logger.info(f"AI 生成【{platform}】卡丁车分镜脚本...")
    all_mats = materials["images"] + materials["videos"]
    if not all_mats:
        return None

    lo, hi = cfg["clip_range"]

    # 有 AI 识别结果 → 精准编排；没有 → 盲排
    if captions:
        mat_desc = "\n".join(f"  [{i}] {c}" for i, c in enumerate(captions))
        mat_block = f"""每个素材的真实画面内容如下（务必根据内容编排）：
{mat_desc}

编排原则：
- 选画面最有冲击力/最抓眼的素材放第一镜做钩子；
- 字幕文案要和该镜头画面内容匹配；
- 相似画面不要连着放，注意节奏与镜头衔接。"""
    else:
        mat_block = (
            f"素材：共 {len(all_mats)} 个"
            f"（图片 {len(materials['images'])}，视频 {len(materials['videos'])}）。"
        )

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
        logger.warning("未设置任何 AI API Key，改用默认脚本")
        return generate_default_script(materials, platform, cfg)

    logger.info(f"使用 AI: {provider} ({model})")
    try:
        script = _call_ai_api(url, key, model, prompt)
        if script:
            logger.info(f"AI 脚本：{script.get('title')} / {len(script.get('scenes', []))} 镜头")
            return script
    except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
        logger.warning(f"AI 调用出错：{e}，改用默认脚本")

    return generate_default_script(materials, platform, cfg)


def generate_default_script(materials: dict, platform: str, cfg: dict) -> dict | None:
    """生成默认分镜脚本（无 AI 时的降级方案）

    不需要任何 API，纯本地拼接。每个素材配一句预设文案。
    """
    all_mats = materials["images"] + materials["videos"]
    if not all_mats:
        return None

    hook = "这速度谁顶得住？"
    body = [
        "真实赛车座舱，一脚油门到底",
        "过弯漂移，肾上腺素拉满",
        "新手也能轻松上手",
        "和朋友来一场真正的竞速",
        "弯道超车的瞬间太爽了",
        "全程真实赛道体验",
    ]

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

    logger.info(f"默认脚本完成，共 {n} 镜头")
    return {"title": f"{platform}·极速卡丁车", "bgm_style": "动感", "scenes": scenes}
