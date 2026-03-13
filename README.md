# NCWUStudyHub

NCWUStudyHub 是一个本地运行的 PPT 学习资料整理 Web 工具。上传 `.pptx` 后，系统会提取文字和图片，生成便于大学生复习的 Markdown 笔记。

## 核心特性

1. 两种生成模式
- 普通模式（无需 API）
- AI 增强模式（需要 API，失败会自动降级为普通模式）

2. 三栏 Web 布局（Gradio Blocks）
- 左侧：上传与控制区
- 中间：内容展示区
- 右侧：AI 问答区

3. 本地文件输出（每个 PPT 一个目录）
- `raw_text.md`
- `cleaned_slides.json`
- `images/`
- `note.md`
- `meta.json`
- `process.log`

4. 更稳健的生成流程（新）
- 单个文件处理失败不会中断整个批次
- 生成异常会在页面日志中直接显示，不再出现“点击无反应”
- 启动阶段自动规避 Windows 代理对 `localhost` 自检的干扰

## 模式说明

### 1) 普通模式（`basic`）
- 不依赖 AI API
- 规则驱动整理：
  - 去空白、去重
  - 合并碎片文本
  - 保留标题/正文/项目符号层级
  - 对图示页标注“本页核心为图示内容”
- 生成基础版 `note.md`

### 2) AI 增强模式（`ai`）
- 需要 API Key
- 在普通模式结果基础上进行提炼和重组
- 输出中文 Markdown，包含复习提纲与自测题
- 若 API 缺失或调用失败，自动降级为普通模式，不影响流程

## 右侧 AI 问答如何工作

- 右侧问答会读取“中间区域当前选中文件”的内容作为上下文：
  - `note.md`（主上下文）
  - `raw_text.md`（辅助上下文）
- AI 被要求严格基于上下文回答，不编造。
- 如果问题超出资料范围，会返回“当前资料中没有足够信息”。
- 若未配置 API，对话会提示“当前未配置 AI 对话能力”。

## 图片处理策略

- 不会无脑插入所有图片。
- 仅筛选关键图示（规则驱动）：
  - 图示主导页面优先保留
  - 含明显图示关键词页面优先保留
  - 重复/低信息量图片会被过滤
- 插图附简短说明，并尽量放在相关小节附近。

## 项目结构

```text
NCWUStudyHub/
  app.py
  main.py
  processor.py
  ppt_loader.py
  extractor.py
  image_exporter.py
  ai_writer.py
  formatter.py
  utils.py
  requirements.txt
  .env.example
  README.md
```

## 安装与运行

### 1) 创建虚拟环境

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2) 安装依赖

```bash
pip install -r requirements.txt
```

### 3) 配置环境变量

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

`.env` 示例：

```env
DEEPSEEK_API_KEY=your_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```

### 4) 启动 Web

```bash
python app.py
```

浏览器访问：`http://127.0.0.1:7860`

说明：
- 应用固定监听 `127.0.0.1:7860`，请不要使用 `http://0.0.0.0:7860` 访问。
- 若系统开启代理，程序会自动对本地自检请求禁用代理，避免 `startup-events 502`。

## CLI（可选保留）

```bash
python main.py --input ./input_ppt --output ./output_notes --mode basic --overwrite
python main.py --input ./input_ppt --output ./output_notes --mode ai --overwrite
```

## Web 使用流程

1. 左侧上传一个或多个 `.pptx`
2. 选择处理模式（普通模式 / AI 增强模式）
3. 点击“开始处理”
4. 中间查看日志、原始文本、最终笔记、关键图示并下载 `note.md`
5. 右侧基于当前选中文件继续提问

## 新增功能（2026-03）

1. 批处理容错
- 某个 PPT 失败时，其他文件仍会继续生成，结果表中可看到失败项及原因。

2. 生成失败可见
- 生成阶段出现异常时，前端会展示失败摘要和异常信息，便于快速定位问题。

3. 本地启动兼容性优化
- 针对 Windows 代理环境增加本地启动自检兼容处理，降低 `502` 启动失败概率。

## 当前限制

1. 第一版只支持 `.pptx`
2. 第一版不做 OCR
3. 普通模式不依赖大模型
4. 右侧 AI 问答依赖 API 配置
5. 复杂排版不保证完全还原

## 故障排查：点击“生成笔记”没有反应

1. 确认已上传至少一个 `.pptx` 文件（只支持 `.pptx`，不支持 `.ppt`）。
2. 检查依赖版本，`gradio` 建议使用 `<6`：
   - `pip install -U "gradio>=4.44.0,<6"`
3. 重新启动：
   - `python app.py`
4. 若仍失败，查看页面错误弹窗与 `output_notes_web/*/process.log`。

## 渐进式生成体验（2026-03 更新）

### 页面布局

- 三栏布局保持不变：
  - 左侧：上传与参数控制
  - 中间：实时笔记展示区（渐进更新）
  - 右侧：AI 问答 + 处理日志/结果表

### 交互改动

1. 点击“开始处理”后，页面会自动平滑滚动到中间笔记展示区。
2. 中间区域会先显示“正在生成中”的状态。
3. 生成过程按页（或内容块）渐进展示，不再等待全部完成后一次性显示。
4. 每处理完一个单元，页面立即追加该单元笔记与相关图片。
5. 不再默认展示“原始提取文本预览”区域。

### 模式说明（渐进化）

- 普通模式：
  - 按页提取 -> 按页生成基础笔记块 -> 实时追加显示 -> 最终合并为完整 `note.md`
- AI 增强模式：
  - 按页提取 -> 按页调用 AI 生成笔记块 -> 实时追加显示 -> 最终合并为完整 `note.md`
  - 若某页 AI 失败，自动回退该页为普通模式块，不阻塞后续页面

### 右侧 AI 对话

- 对话上下文始终来自“当前已生成的笔记内容”。
- 随着中间区域增量生成，右侧问答可基于最新内容回答。
- 若尚未生成任何内容，会提示先开始处理。

### 输出目录

- 仍保留原有输出结构：
  - `cleaned_slides.json`
  - `images/`
  - `note.md`
  - `meta.json`
  - `process.log`
  - `raw_text.md`（仅输出保留，前端默认不展示）

## 新界面流程（以此为准）

### 阶段 1：全屏上传页

- 首屏仅展示核心上传与配置：
  - 标题与简介
  - `.pptx` 上传
  - 普通模式 / AI 增强模式
  - AI 配置（折叠显示）
  - 输出目录
  - 开始处理按钮
- 不显示笔记区、日志区、问答区。

### 阶段 2：笔记阅读页

- 点击“开始处理”后切换到阅读页。
- 处理中仅显示简短提示“正在整理笔记...”，不展示详细日志。
- 完成后页面聚焦最终笔记正文。
- 右侧保留窄侧栏 AI 问答，仅作为辅助。
- 不展示原始提取文本、处理日志、调试状态等中间信息。

### 图片展示规则

- 图片不再作为底部小缩略图堆叠展示。
- 在笔记前部新增“核心图示”区块，优先呈现关键图。
- 每页相关图片跟随对应笔记段落展示。
- 图片按正文配图尺寸渲染，默认大图展示，不做过度裁剪。
