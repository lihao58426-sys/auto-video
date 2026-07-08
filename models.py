"""
数据模型 — dataclass 定义
=========================
职责：替代裸 dict，让视频生成流程中每个环节的数据都有明确结构。

原来传数据的方式：
  cfg = {"size": (1080, 1920), "voice": "zh-CN-YunxiNeural", ...}
  scene = {"material_index": 0, "duration": 3.0, "text": "..."}

现在：
  cfg = VideoConfig(size=(1080, 1920), voice="zh-CN-YunxiNeural", ...)
  scene = ScriptSegment(material_index=0, duration=3.0, text="...")
"""

from dataclasses import dataclass, field


@dataclass
class VideoConfig:
    """单个平台的视频参数配置

    原来：PLATFORM_CONFIG["抖音"] 返回一个 dict
    现在：VideoConfig 对象，字段有自动补全
    """
    platform: str = ""             # 平台名（抖音/小红书/视频号）
    size: tuple[int, int] = (1080, 1920)
    voice: str = ""                # edge-tts 音色
    font_size: int = 72
    sub_color: str = "white"
    sub_pos_ratio: float = 0.74   # 字幕垂直位置（0=顶部, 1=底部）
    clip_range: tuple[float, float] = (1.5, 3.0)  # 每镜头时长范围
    tail: str = ""                 # 片尾口播
    style_note: str = ""           # 平台风格提示词（给 AI 用）

    @classmethod
    def from_platform_dict(cls, platform: str, cfg: dict) -> "VideoConfig":
        """从 PLATFORM_CONFIG dict 构造 VideoConfig"""
        return cls(
            platform=platform,
            size=cfg.get("size", (1080, 1920)),
            voice=cfg.get("voice", ""),
            font_size=cfg.get("font_size", 72),
            sub_color=cfg.get("sub_color", "white"),
            sub_pos_ratio=cfg.get("sub_pos_ratio", 0.74),
            clip_range=cfg.get("clip_range", (1.5, 3.0)),
            tail=cfg.get("tail", ""),
            style_note=cfg.get("style_note", ""),
        )

    def to_dict(self) -> dict:
        """转换回 dict（兼容现有 scences.py / voice.py 的参数格式）"""
        return {
            "size": self.size,
            "voice": self.voice,
            "font_size": self.font_size,
            "sub_color": self.sub_color,
            "sub_pos_ratio": self.sub_pos_ratio,
            "clip_range": self.clip_range,
            "tail": self.tail,
            "style_note": self.style_note,
        }


@dataclass
class Material:
    """单个素材文件"""
    path: str                      # 文件路径
    media_type: str = ""           # "image" 或 "video"
    description: str = ""          # AI 识别的画面描述（可选）


@dataclass
class ScriptSegment:
    """一个分镜镜头

    原来：scene = {"material_index": 0, "duration": 3.0, "text": "..."}
    现在：seg = ScriptSegment(material_index=0, duration=3.0, text="...")
    """
    material_index: int = 0
    duration: float = 3.0
    text: str = ""
    voice_path: str | None = None  # 配音文件路径（voice.py 填充）


@dataclass
class VideoScript:
    """完整的分镜脚本"""
    title: str = ""
    bgm_style: str = "动感"
    scenes: list[ScriptSegment] = field(default_factory=list)

    @classmethod
    def from_ai_response(cls, data: dict) -> "VideoScript":
        """从 AI 返回的 JSON dict 构造 VideoScript"""
        scenes = [
            ScriptSegment(
                material_index=s.get("material_index", 0),
                duration=s.get("duration", 3.0),
                text=s.get("text", ""),
            )
            for s in data.get("scenes", [])
        ]
        return cls(
            title=data.get("title", ""),
            bgm_style=data.get("bgm_style", "动感"),
            scenes=scenes,
        )

    def to_dict(self) -> dict:
        """转换回 dict（兼容现有代码）"""
        return {
            "title": self.title,
            "bgm_style": self.bgm_style,
            "scenes": [
                {
                    "material_index": s.material_index,
                    "duration": s.duration,
                    "text": s.text,
                    "voice_path": s.voice_path,
                }
                for s in self.scenes
            ],
        }
