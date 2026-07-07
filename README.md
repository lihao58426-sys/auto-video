# AI 短视频自动生成系统

全自动卡丁车门店短视频生成：扫描素材 → AI 视觉识别 → 生成分镜脚本 → Edge TTS 配音 → FFmpeg 合成（模糊背景 + 锐化调色 + 字幕叠加）→ 输出成品。

## 功能

- **AI 视觉识别**：Qwen VL 自动识别素材画面内容，精准编排
- **AI 脚本生成**：DeepSeek / Qwen 双模型，根据素材 + 平台风格生成分镜脚本
- **TTS 配音**：Edge TTS 多音色语音合成
- **画质增强**：模糊背景 + 锐化调色 + PIL 字幕渲染
- **多平台适配**：抖音（9:16）、小红书（3:4）、视频号（9:16）

## 技术栈

Python · DeepSeek API · Qwen VL · Edge TTS · FFmpeg · PIL

### 环境要求

- Python >= 3.10
- FFmpeg（通过 `imageio-ffmpeg` 自动获取）
- 中文字体（默认 `C:\Windows\Fonts\msyh.ttc`）
- 环境变量：

| 变量名 | 说明 |
|--------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key（脚本生成） |
| `QWEN_API_KEY` | 通义千问 API Key（素材识别，可选） |

## 安装

```bash
git clone https://github.com/lihao58426-sys/auto-video.git
cd auto-video
pip install -r requirements.txt
```

## 使用

1. 将素材（图片/视频）放入 `materials/` 目录
2. 可选：放入 `bgm.mp3` 作为背景音乐

```bash
python auto-video.py
```

选择平台（抖音/小红书/视频号），自动完成全流程。

## 输出

生成的视频在 `output/` 目录下，格式为 `MMDD_平台.mp4`。
