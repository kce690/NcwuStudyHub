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

## 当前限制

1. 第一版只支持 `.pptx`
2. 第一版不做 OCR
3. 普通模式不依赖大模型
4. 右侧 AI 问答依赖 API 配置
5. 复杂排版不保证完全还原
