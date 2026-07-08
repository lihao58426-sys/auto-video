"""
平台参数配置
============
职责：定义抖音 / 小红书 / 视频号三个平台的画面尺寸、音色、字幕样式等参数。

为什么要单独一个文件？
  - 三个平台的配置占了 30+ 行，属于"数据"而非"逻辑"
  - 加新平台（比如快手）只需要在这里加一段 dict
  - main.py、script_gen.py、scenes.py 都需要读平台参数
"""

# 各平台参数
PLATFORM_CONFIG: dict = {
    "抖音": {
        "size": (1080, 1920),          # 竖屏 9:16
        "voice": "zh-CN-YunxiNeural",  # 云希 — 阳光男声
        "font_size": 72,
        "sub_color": "white",
        "sub_pos_ratio": 0.74,         # 字幕在画面 74% 的位置
        "clip_range": (1.5, 3.0),      # 每镜 1.5-3 秒
        "tail": "想体验的老铁，评论区扣1！",
        "style_note": "快节奏、有冲击力、接地气，突出速度与刺激感",
    },
    "小红书": {
        "size": (1080, 1440),           # 竖屏 3:4
        "voice": "zh-CN-XiaoxiaoNeural", # 晓晓 — 温柔女声
        "font_size": 56,
        "sub_color": "white",
        "sub_pos_ratio": 0.82,
        "clip_range": (2.5, 4.0),       # 每镜 2.5-4 秒（更慢）
        "tail": "地址放评论啦，姐妹快冲～",
        "style_note": "精致、种草、闺蜜分享感，突出出片好看和体验感",
    },
    "视频号": {
        "size": (1080, 1920),
        "voice": "zh-CN-YunjianNeural",  # 云健 — 专业男声
        "font_size": 62,
        "sub_color": "white",
        "sub_pos_ratio": 0.80,
        "clip_range": (3.0, 5.0),        # 每镜 3-5 秒（最慢）
        "tail": "周末带上家人朋友，一起来体验。",
        "style_note": "稳重、专业、有安全感，突出适合家庭朋友聚会",
    },
}
