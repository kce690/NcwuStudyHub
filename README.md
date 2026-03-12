# NCWUStudyHub

NCWUStudyHub 是一个本地可运行的 Gradio Web 应用：上传 `.pptx` 后，自动提取文本和图片，并生成适合大学生复习的 Markdown 学习笔记。

## 项目简介

第一版目标是先跑通本地学习资料整理流程，不做数据库、登录系统、多用户系统。

核心流程：

1. 上传一个或多个 `.pptx`
2. 提取每页文字与图片
3. 调用 AI（可选）生成学习笔记
4. 网页展示结果并支持下载 `note.md`
5. 保留中间产物，便于复查

## 功能说明

- Web 界面（Gradio Blocks）：
  - 多文件上传
  - API Key / Base URL / Model 配置
  - 输出目录配置
  - 处理日志
  - 原始文本预览
  - 图片 Gallery 预览
  - Markdown 笔记预览
  - 下载 `note.md`
- 本地产物输出（每个 PPT 一个文件夹）：
  - `raw_text.md`
  - `cleaned_slides.json`
  - `images/`
  - `note.md`
  - `meta.json`
  - `process.log`
- AI 未配置或失败时不会中断流程，仍会保存原始提取结果与回退笔记。
- 保留 CLI 入口 `main.py`（同样只处理 `.pptx`）。

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

## 安装方式

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

### 3) 配置 `.env`

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

`.env` 示例：

```env
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

## 运行方式

### 启动 Web 应用（推荐）

```bash
python app.py
```

默认地址：`http://127.0.0.1:7860`

### CLI 用法（保留）

```bash
python main.py --input ./input_ppt --output ./output_notes --overwrite
```

## Web 页面功能说明

页面包含：

1. 顶部标题与简介
2. 左侧输入区
   - `.pptx` 多文件上传
   - API Key（密码输入）
   - Base URL
   - Model
   - 输出目录
   - 开始处理按钮
3. 右侧输出区
   - 处理摘要
   - 处理日志
   - 文件结果总览表
   - 按文件查看详情
   - 原始文本预览
   - 图片预览
   - Markdown 笔记预览
   - `note.md` 下载

## 输出目录示例

```text
output_notes_web/
  demo/
    raw_text.md
    cleaned_slides.json
    images/
      slide_001_img_01.png
    note.md
    meta.json
    process.log
```

## 简单测试样例

1. 准备 `demo.pptx`（至少 2 页，含 1 页图片）
2. 启动 `python app.py`
3. 上传文件并处理
4. 检查：
   - 页面是否显示提取文本和图片
   - 是否生成并可下载 `note.md`
   - `output_notes_web/demo/` 是否包含中间产物

## 当前限制

1. 第一版只支持 `.pptx`
2. 第一版不做 OCR
3. 第一版不做登录和数据库
4. AI 未配置时只做原始提取并生成回退笔记
5. 复杂排版不保证完美还原

## 后续规划

1. OCR 支持（图片文字识别）
2. 更细粒度结构提取（表格、公式、图文映射）
3. 多种学习笔记模板
4. 批量质量评估报告
