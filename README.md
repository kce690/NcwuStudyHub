# NCWUStudyHub

一个本地 Python 工具：把 PPT（第一版优先 `.pptx`）提取为结构化内容，并生成适合大学生复习的 Markdown 学习笔记。

## 项目简介

NCWUStudyHub v1 聚焦“PPT -> 学习笔记”核心流程：

1. 扫描输入目录中的 `.pptx` / `.ppt`
2. 提取每一页原生文本（不使用 OCR）
3. 导出每一页图片
4. 调用 OpenAI 风格接口整理为 Markdown 笔记
5. 输出本地文件（含原始文本、结构化 JSON、图片、日志和最终笔记）

## 功能说明

- 支持递归扫描输入目录
- 优先处理 `.pptx`
- 在 Windows 上尝试将 `.ppt` 自动转换为 `.pptx`（依赖本机 PowerPoint + `pywin32`）
- 提取每页：
  - `slide_number`
  - `title`
  - `text_blocks`
  - `bullet_points`
  - `image_paths`
- 单文件失败不影响其他文件
- AI 调用失败自动回退：仍产出原始提取文件和 `note.md`
- 处理结束后终端打印摘要（成功数、失败数、输出目录）

## 安装方式

1. 安装 Python 3.10+
2. 安装依赖：

```bash
pip install -r requirements.txt
```

3. 配置环境变量：

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

## `.env` 配置说明

```env
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

- `OPENAI_API_KEY`：必填（不配置则跳过 AI，走回退模板）
- `OPENAI_BASE_URL`：OpenAI 风格接口地址
- `OPENAI_MODEL`：默认模型名

## 使用示例

基础命令：

```bash
python main.py --input ./input_ppt --output ./output_notes
```

可选参数：

- `--model`：覆盖模型名
- `--api-base`：覆盖 API Base URL
- `--max-files`：最多处理文件数
- `--overwrite`：覆盖已存在输出目录
- `--verbose`：打印详细日志

示例：

```bash
python main.py --input ./input_ppt --output ./output_notes --model gpt-4o-mini --overwrite --verbose
```

## 输出文件说明

每个 PPT 会在 `output_notes/<文件名>/` 下生成：

```text
output_notes/
  文件名A/
    raw_text.md
    cleaned_slides.json
    images/
      slide_001_img_01.png
      slide_003_img_01.png
    note.md
    meta.json
    process.log
```

- `raw_text.md`：按页保存原始提取文本
- `cleaned_slides.json`：结构化后的每页文本与图片路径
- `images/`：导出的图片资源
- `note.md`：最终学习笔记（含相对路径图片引用 `images/...`）
- `meta.json`：处理元信息（页数、图片数、状态、错误等）
- `process.log`：单文件处理日志

## 简单测试样例说明

1. 在 `input_ppt/` 放入一个简单课件 `demo.pptx`（至少 2 页，其中 1 页带图片）
2. 运行：

```bash
python main.py --input ./input_ppt --output ./output_notes --overwrite
```

3. 检查：
   - `output_notes/demo/raw_text.md` 是否按页有文本
   - `output_notes/demo/images/` 是否导出图片
   - `output_notes/demo/note.md` 是否包含 `images/...` 图片引用

## 当前限制

1. 第一版优先支持 `.pptx`
2. `.ppt` 依赖 Windows + 本机安装 PowerPoint 才能稳定转换
3. 第一版不做 OCR
4. 第一版不保证完美还原复杂排版
5. 第一版不做网页界面

## 后续规划

1. 增加 OCR 支持（处理图片型文字页）
2. 更细粒度版式解析（表格、公式、图文对应）
3. 增加多笔记模板（速记版/考试版/讲义版）
4. 增加批量评估与质量报告

## 项目结构

```text
NCWUStudyHub/
  main.py
  ppt_loader.py
  ppt_converter.py
  extractor.py
  image_exporter.py
  ai_writer.py
  formatter.py
  utils.py
  requirements.txt
  .env.example
  README.md
```
