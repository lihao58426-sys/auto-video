"""
自定义异常类
===========
职责：视频生成流程中各环节的失败类型。

为什么需要？
  - AI 调用失败 → 可以降级到默认脚本（不用中断）
  - ffmpeg 渲染失败 → 可能是素材损坏，跳过这个镜头即可
  - TTS 配音失败 → 可以用静音替代这个镜头
  不同失败类型有不同的恢复策略。
"""


class AIGenerationError(Exception):
    """AI 生成失败（DeepSeek / Qwen API 不可用）

    场景：API Key 无效、额度用完、网络不通、返回格式异常
    处理：降级到默认脚本（generate_default_script）
    """
    pass


class TTSError(Exception):
    """语音合成失败

    场景：edge-tts 网络异常、音色不支持、文字过长
    处理：该镜头用静音替代，不影响其他镜头
    """
    pass


class RenderError(Exception):
    """视频渲染失败

    场景：ffmpeg 执行错误、素材文件损坏、磁盘空间不足
    处理：跳过该镜头，记录日志，不中断整个流程
    """
    pass


class MaterialError(Exception):
    """素材问题

    场景：素材文件夹不存在、无可用素材、格式不支持
    处理：终止生成，提示用户检查素材
    """
    pass
