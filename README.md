# Daily AI News

这个项目现在的主流程是：

1. 手动整理当天新闻。
2. 按结构化 JSON 模板写入 `input/news_script.txt`。
3. 运行 `./scripts/run_all.sh`。
4. 系统自动完成预检查、配音、补静音、渲染场景、合成横屏主视频。
5. 系统按 `sections` 自动生成竖屏短视频（每个 section 一条）。

## 输入格式

`input/news_script.txt` 现在推荐使用 JSON。结构分成 `meta` 和 `sections` 两部分：

```json
{
  "meta": {
    "title": "今日 AI 新闻简报",
    "subtitle": "AI 辅助生成 · 公开信息整理",
    "date": "2026-04-27",
    "opening": "大家好，欢迎收看今天的 AI 新闻简报。今天是 2026 年 4 月 27 日。",
    "closing": "以上就是今天的主要新闻。以上内容由 AI 辅助生成，基于公开信息整理，仅供参考。"
  },
  "sections": [
    {
      "name": "国内新闻",
      "intro": "我们先来看国内新闻。",
      "items": [
        {
          "headline": "平台治理与新就业群体服务",
          "source": "新华社",
          "visual": "policy",
          "keywords": ["平台经济", "算法透明", "劳动权益"],
          "facts": ["文件聚焦快递员、网约车司机、外卖配送员等群体。", "强调平台企业规范用工和改善从业环境。"],
          "takeaway": "平台治理会继续向算法透明、休息权和极端天气保护等方向推进。",
          "script": "首先关注平台经济和新就业群体。新华社今天发布消息，中共中央办公厅、国务院办公厅印发关于加强新就业群体服务管理的意见。文件重点提到，要依法维护快递员、网约车司机、外卖配送员、网络主播等新就业群体的合法权益，并推动平台企业规范用工、改善从业环境、提高算法透明度。"
        }
      ]
    }
  ]
}
```

字段建议：

- `meta.date` 使用 `YYYY-MM-DD`。
- `script` 写真正要播报的口播内容。
- `facts` 写 2 到 3 条屏幕重点。
- `takeaway` 写这一条新闻的判断或意义。
- `watch` 仍然是可选字段，当前不作为默认卡片内容展示。
- `visual` 可用值包括 `focus`、`policy`、`data`、`alert`、`world`、`science`、`market`、`recap`。

旧版纯文本稿件仍然能跑，但画面模板和内容拆分会明显弱一些。

## 安装依赖

推荐在项目根目录执行：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

系统依赖：

- `ffmpeg`
- `ffprobe`
- macOS 中文字体

如果你是 Apple Silicon Mac，`ffmpeg` 通常会在 `/opt/homebrew/bin/ffmpeg`。

## 运行方式

完整流程：

```bash
./scripts/run_all.sh
```

只跑横屏主视频（跳过短视频）：

```bash
ENABLE_SHORTS_OUTPUT=0 ./scripts/run_all.sh
```

短视频授权音轨（可选）：

1. 把可商用授权音乐放到 `input/authorized_audio/shorts/`。
2. 对每个音频创建同名授权标记文件，文件名为：
`<音频文件名>.license.txt` 或 `<音频文件名>.rights.txt`
3. 短视频只会自动使用这批“带授权标记”的音轨；找不到时会自动输出纯人声短视频。
4. 长视频逻辑不变，仍按原有方式处理 `input/bgm.mp3`。

短视频自动压缩到 1 分钟内：

1. 默认目标上限为 59 秒（可通过 `SHORTS_MAX_SECONDS` 调整）。
2. 脚本会优先尝试更精简的口播版本；若仍超时，会自动轻度加速口播音频。
3. 仅影响短视频流程，长视频流程不受影响。

默认使用 `edge-tts`，并带有重试、缓存和音频有效性校验。
如果当前运行环境不允许联网，`edge-tts` 会明确报错，而不是继续生成坏音频。
实验性的本地 Apple 导出仍然保留，但不再是默认主路径。只有显式设置 `ENABLE_EXPERIMENTAL_LOCAL_TTS=1` 时才会尝试。

单独检查环境：

```bash
.venv/bin/python scripts/preflight.py
```

单独生成字幕：

```bash
.venv/bin/python scripts/02_make_srt.py
```

## 这次升级后的变化

- `news_script.txt` 支持结构化输入。
- 配音和字幕都从同一份结构化稿件生成。
- 画面改成按板块和新闻条目切换多个模板，不再只有一张静态风景图。
- 每条新闻会自动生成两张统一格式的卡片，第一张只显示 `source`、`visual`、`headline`、`keywords`。
- 第二张只显示 `source`、`visual`、`takeaway`、`facts`。
- 增加运行前检查，提前发现依赖、字体、输入文件和日期问题。
- 新增竖屏短视频输出：按 `sections` 逐条生成，输出目录为 `output/shorts/`，文件名包含日期（如 `short_2026-05-01_01_国内新闻.mp4`）。
- 短视频背景音乐改为“仅授权音轨池自动选用”；未提供授权音轨时自动降级为纯人声，避免误用版权音乐。
