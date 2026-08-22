# Interview Review — 面试复盘与改进

个人项目,用于对技术面试录音进行复盘、分析并生成改进建议。

## 触发方式(重要)

本项目**不做任何自动分析**。只有当你输入以下命令时,才执行对应分析:

| 命令 | 作用 | 输入文件 | 输出文件 |
|------|------|----------|----------|
| `分析简历 <名>` | 提取简历文本 | `resume/media/<名>.pdf` | `resume/个人简历.md` |
| `分析面试音频 <名>` | 转写并复盘录音 | `interview/media/<名>.<扩展名>` | `interview/txt/<名>.txt` + `interview/<名>.md` |
| `我要面试复盘`(或 `/interview-review`) | 运行 `start_review.py`,弹出上传页面、提交简历 PDF + 面试录音 | 用户在浏览器上传(经 `upload_server.py`) | 自动执行下方「我要面试复盘」流程 |

`<名>` 为多媒体文件的**不含扩展名的文件名**。若你只给了部分名字或文件名不确定,先列出 `media/` 目录下文件让你确认,再执行。

## 目录结构

```
.
├── resume/
│   ├── media/      # 简历 PDF(多媒体放这里,不入库;不删除不改名,最新者为当前简历)
│   └── 个人简历.md  # 唯一的简历文档(「分析简历」与上传式复盘共用)
├── interview/
│   ├── media/      # 面试录音(音频放这里,不入库)
│   ├── txt/        # 转录文本(interview/txt/<名>.txt,「分析面试音频 <名>」与上传式复盘共用)
│   └── <名>.md     # 「分析面试音频 <名>」生成的复盘分析文档
├── transcribe.py   # 音频转文本脚本(云端 API,动态配置)
├── pdf2text.py     # PDF 简历转文本脚本(纯 Python,依赖 pypdf)
├── upload_server.py # 「我要面试复盘」上传服务(纯 Python 标准库,跨平台,本地 127.0.0.1)
├── upload_page.html # 「我要面试复盘」浏览器上传页面
├── start_review.py  # 「我要面试复盘」一键触发脚本(用户可直接运行,或由 Claude 运行)
├── .claude/commands/interview-review.md # 「我要面试复盘」/`/interview-review` 的编排流程说明
├── requirements.txt # Python 依赖清单(仅 pypdf)
├── .env.example    # 转写服务配置模板(复制为 .env 后填写)
├── CLAUDE.md
└── .gitignore      # 只跟踪 .txt/.md,忽略 PDF/音频/密钥等
```

## 工作流程

### `分析简历 <名>`

1. 提取文本:运行 `python3 pdf2text.py "resume/media/<名>.pdf"`,读取脚本输出的文字。
   > 首次使用前:`pip install -r requirements.txt`(仅一个依赖 `pypdf`,纯 Python、零传递依赖);若为扫描/图片型 PDF 无文本层,脚本会提示需 OCR。
2. 把提取出的文本整理成 Markdown(保留原始结构,修正换行与明显识别误差),**覆盖写入** `resume/个人简历.md`。**不做分析**。

### `分析面试音频 <名>`

1. **转写(云端 API)**:运行 `transcribe.py`,音频经 ffmpeg 预处理后上传到 `.env` 里配置的语音识别服务,返回文字:
   ```bash
   ./transcribe.py "interview/media/<名>.<扩展名>" "interview/txt/<名>.txt"
   ```
   > 首次使用前:复制 `.env.example` 为 `.env`,填好 `ASR_BASE_URL` / `ASR_API_KEY` / `ASR_MODEL`(见 `.env.example` 内注释,换服务只需改 `.env`)。
   > 依赖 Python3、`ffmpeg`,均在本地,无需安装任何模型或第三方库。
2. **整理转录文本**(写回 `interview/txt/<名>.txt`):对原始转录做二次处理——
   - 分析问答双方话语,把「面试官」与「候选人」**分开排版**;
   - 结合候选人的**技术背景、行业背景**(参考简历),纠正识别错误的字词(技术名词、专业术语等,如 "ncks"→Nacos、"县程"→线程),并把纠正后的内容写回转录文本。
3. **生成复盘文档**:结合简历背景与整理后的转录文本,生成 `interview/<名>.md`,见「面试复盘文档」章节。

### `我要面试复盘`(上传式复盘)

用户说「我要面试复盘」(或调用 `/interview-review`)时,运行一键触发脚本 `start_review.py`(用户在终端直接运行它也可以),随后自动执行完整复盘。详细步骤见 `.claude/commands/interview-review.md`,此处为概要:

1. **触发上传**:运行 `python3 start_review.py`,脚本自动完成——启动上传服务、打开浏览器上传页、等待提交(最多约 10 分钟)、写入结果并清理服务。用户提交简历 PDF + 面试录音。
2. **读取状态**:`start_review.py` 把上传结果写入状态 JSON(默认 `$TMPDIR/interview_review/upload.json`),读取 `session_name`、`resume.path`、`resume.md_path`、`resume.replaced`、`resume.has_md`、`audio.path`、`audio.ext`。
3. **分析简历**:若 `resume.replaced == false` 且 `resume.has_md == true`(简历未变、md 已存在)则**直接复用** `resume/个人简历.md`,跳过提取;否则运行 `python3 pdf2text.py "<resume.path>"`,整理后**覆盖写入** `resume/个人简历.md`(仅整理,不做分析)。
4. **转写并整理录音**:确认 `.env` 已配置,运行 `./transcribe.py "<audio.path>" "interview/txt/<session>.txt"`,再区分说话人、纠正识别错误后写回该 `.txt`。
5. **生成复盘文档**:生成 `interview/<session>.md`(5 个章节)。
6. **汇报**:列出生成文件与关键结论。

> 命名与简历逻辑:
> - 上传页面有「复盘名称」输入框,用于**面试录音与复盘文档**(`interview/<复盘名>.<扩展名>`、`interview/<复盘名>.txt/.md`);留空自动生成时间戳名称。
> - 简历 PDF **保留上传文件自己的名字**,`resume/media/` 下的简历文件**不删除、不改名**(同名时自动追加 ` (2)`/` (3)` 序号)。页面打开时会检查其中最新的 PDF 作为「当前简历」展示在拖拽框中:
>   - 有现有简历时,简历为**可选**,默认沿用;不拖入新 PDF 就直接用现有简历;
>   - 拖入新 PDF 会直接存入 `resume/media/` 作为最新简历(旧文件保留),分析时以最新的为准;
>   - 简历文本统一整理到唯一的一份 `resume/个人简历.md`:上传新简历或尚无 md 时重新提取覆盖,否则复用。
> 隐私:服务只在 `127.0.0.1` 监听,文件不出本机;录音后续按 `.env` 配置上传语音识别服务转写。

## 分析文档章节

### 简历文本(`resume/个人简历.md`)

直接保存 PDF 提取出的文本、整理成 Markdown 即可,**不做分析**。

### 面试复盘文档(`interview/<名>.md`)

1. **问答概要** —— 按时间/话题顺序梳理问了什么、怎么答的、结果如何。
2. **面试缺点** —— 暴露的问题(表达、紧张、答非所问、基础薄弱等)。
3. **可改进点** —— 针对缺点的具体、可操作改进措施。
4. **缺少的知识点** —— 面试中明显暴露的未掌握/答错的知识点。
5. **下一步建议学习的知识点** —— 结合目标岗位与简历,列出优先学习清单(可排序)。

## 约定与注意事项

- 所有输出文档用**中文**,技术术语保留英文。
- 转录文本是复盘的事实依据;总结要具体到「哪个问题、哪句话、哪里答偏」,避免空泛。
- 转录文本须区分说话人(面试官 / 候选人)并纠正识别错误(见「分析面试音频」步骤 2)。
- 多媒体文件(PDF/音频)**只放 `media/` 子目录**;转录文本放 `interview/txt/`;`resume/`、`interview/` 根目录只放生成的 `.md`。
- 隐私提示:简历仅在本机分析;录音会通过 `transcribe.py` 上传到你在 `.env` 配置的语音识别服务,若介意可改用本地转写方案。
