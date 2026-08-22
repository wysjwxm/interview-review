# Interview Review — 面试复盘与改进

个人工具:对技术面试录音进行复盘、分析,生成可操作的改进建议。

设计原则:**纯 Python 标准库**(除一个 `pypdf`)、跨平台(Windows / macOS / Linux)、本地运行、数据不出本机。除转写会按 `.env` 配置上传语音识别服务外,其余全程只在本机 `127.0.0.1` 处理。

---

## 功能特性

- **简历文本提取** — PDF → 纯文本,轻量清理后整理为 Markdown。
- **面试音频转写** — 云端语音识别(OpenAI 兼容 API),服务可动态切换,只需改 `.env`。
- **一键上传式复盘** — 本地网页拖拽上传「简历 PDF + 面试录音」,自动落盘并生成结构化复盘文档(5 个章节)。
- **隐私友好** — 上传服务只在 `127.0.0.1` 监听;简历仅在本机分析;媒体文件默认不入 git。

---

## 环境要求

| 依赖 | 类型 | 用途 | 安装方式 |
|------|------|------|----------|
| Python 3.8+ | 运行时 | 全部脚本 | mac系统自带，若无请自行安装 |
| pypdf | pip 包 | PDF 简历文本提取 | `pip install -r requirements.txt` |
| ffmpeg | 系统二进制 | 音频预处理(统一转 16kHz mp3) | `brew install ffmpeg` / `apt install ffmpeg` |
| 语音识别服务 | 云端 API | 音频转文字 | 配 `.env`(见下文) |

> 除 `pypdf` 外,项目**不依赖任何第三方 Python 库**;ffmpeg 与语音识别服务不是 pip 依赖,故不在 `requirements.txt` 中。

---

## 安装

```bash
# 1. 克隆仓库
git clone <repo-url> && cd interview-review

# 2. 安装 Python 依赖(仅 pypdf)
pip install -r requirements.txt

# 3. 配置语音识别服务(需要转写时)
cp .env.example .env   # 然后编辑 .env,填好 ASR_BASE_URL / ASR_API_KEY / ASR_MODEL

# 4. (可选)安装 ffmpeg,用于音频预处理
brew install ffmpeg    # macOS;Linux 用 apt,Windows 到官网下载
```

---

## 目录结构

```
.
├── resume/
│   ├── media/      # 简历 PDF(不入库;不删除不改名,最新者为当前简历)
│   └── 个人简历.md  # 唯一的简历文档(提取后整理)
├── interview/
│   ├── media/      # 面试录音(不入库)
│   ├── txt/        # 转录文本
│   └── <名>.md     # 生成的复盘分析文档
├── transcribe.py   # 音频转文本(云端 API,动态配置)
├── pdf2text.py     # PDF 简历转文本(依赖 pypdf)
├── upload_server.py # 上传服务(纯标准库,本地 127.0.0.1)
├── upload_page.html # 浏览器上传页面
├── start_review.py  # 一键触发上传脚本
├── requirements.txt # pip 依赖清单(仅 pypdf)
├── .env.example    # 转写服务配置模板
└── CLAUDE.md       # Claude Code 项目指令(可选,见「Claude Code 集成」)
```

---

## 使用方式

### 方式一:一键上传式复盘(推荐)

```bash
python3 start_review.py
```

脚本会自动完成:启动本地上传服务 → 打开浏览器上传页 → 等待提交「简历 PDF + 面试录音」(最长约 10 分钟)→ 写入结果到状态文件(默认 `$TMPDIR/interview_review/upload.json`)并清理服务。

上传页行为:

- 「复盘名称」决定录音与复盘文档的文件名(`interview/<复盘名>.<扩展名>`、`interview/<复盘名>.txt/.md`);留空自动用时间戳命名。
- **简历可选**:页面会自动检测 `resume/media/` 下最新的 PDF 作为「当前简历」并默认沿用;拖入新 PDF 则作为最新简历(旧文件保留,同名自动加 ` (2)` 序号)。
- 简历文本统一整理到唯一的一份 `resume/个人简历.md`:上传新简历或尚无该 md 时重新提取覆盖,否则复用。

提交后,完整的复盘流程(简历提取 → 转写 → 区分说话人并纠错 → 生成 5 章节复盘文档)由编排方按下面的脚本与结构完成;若使用 Claude Code,可直接输入「我要面试复盘」或 `/interview-review` 一键走完整流程。

### 方式二:直接转写音频

```bash
./transcribe.py "interview/media/<名>.<扩展名>" "interview/txt/<名>.txt"
```

- 依赖已配置的 `.env`(ASR 服务)与 ffmpeg(可选,自动检测)。
- 输出为识别文本;区分说话人、纠正识别错误等二次整理由复盘流程完成。

### 方式三:提取简历文本

```bash
python3 pdf2text.py "resume/media/<名>.pdf"
```

- 文本打印到标准输出;可传第二个参数写入文件。
- 若为扫描/图片型 PDF(无文本层),脚本会提示需 OCR。

---

## 复盘文档结构

每次复盘生成的 `interview/<名>.md` 固定包含 5 个章节:

1. **问答概要** — 按时间/话题顺序梳理问了什么、怎么答的、结果如何。
2. **面试缺点** — 表达、紧张、答非所问、基础薄弱等暴露的问题。
3. **可改进点** — 针对缺点的具体、可操作改进措施。
4. **缺少的知识点** — 面试中明显暴露的未掌握/答错的知识点。
5. **下一步建议学习的知识点** — 结合目标岗位与简历的优先学习清单(可排序)。

---

## 配置说明(`.env`)

复制 `.env.example` 为 `.env` 后填写,支持任意 OpenAI 兼容的语音识别服务,换服务只需改三个变量:

| 变量 | 说明 |
|------|------|
| `ASR_BASE_URL` | API 地址(不含 `/audio/transcriptions`) |
| `ASR_API_KEY` | 密钥 |
| `ASR_MODEL` | 模型名 |
| `ASR_LANGUAGE` | (可选)显式指定语言,如 `zh` |


---

## 隐私说明

- 上传服务只在 `127.0.0.1` 监听,文件不出本机。
- 简历仅在本机分析,不上传任何服务。
- 录音会经 `transcribe.py` 上传到你 `.env` 里配置的语音识别服务转写;若介意,可改用本地转写方案。
- `.gitignore` 默认忽略 `resume/`、`interview/`、`.env` 等隐私/媒体文件,仅跟踪 `.txt`/`.md`。

---

## Claude Code 集成(可选)

本项目顺带提供了 Claude Code 的编排集成(`CLAUDE.md` + `.claude/commands/interview-review.md`),让「我要面试复盘」/ `/interview-review` 一键走完整复盘流程。这部分**不是必须的**——核心脚本(`start_review.py` 等)与任何 agent / 手工命令行都兼容;不使用 Claude Code 时,直接忽略 `.claude/` 目录即可。
