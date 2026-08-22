---
description: 弹出上传页面(简历 PDF + 面试录音),自动执行面试复盘流程
---

# 面试复盘 · 上传式

用户输入「我要面试复盘」或调用 `/interview-review` 时,按下面流程执行。
触发统一走一键脚本 `start_review.py`(纯 Python 标准库,跨平台,全程只在本机 `127.0.0.1` 监听);
用户也可以自己在终端直接运行该脚本完成上传,再回到对话让我继续。

## 1. 触发上传(运行脚本)

运行 `start_review.py`,它会自动:启动上传服务 → 打开浏览器 → 等待提交
简历 PDF + 面试录音(最长约 10 分钟)→ 写入结果并清理服务。

```bash
STATUS="$(python3 -c "import tempfile,os;print(os.path.join(tempfile.gettempdir(),'interview_review','upload.json'))")"
rm -f "$STATUS"
python3 start_review.py --status "$STATUS"
```
> 脚本最长约 10 分钟,执行这条 Bash 命令时**把工具 timeout 设为 620000ms**,否则会提前中断。
> 同时向用户提示:「请在弹出的页面上提交 简历 PDF + 面试录音,提交后我会自动开始复盘。」

- **退出码 0**:上传成功。用 Read 工具读取 `$STATUS`,得到:
  - `session_name` — 复盘名称(可能含中文/空格)
  - `resume.path` — 本次使用的简历相对路径。media 下的简历 PDF **不删除、不改名**,
    每次上传直接存入(同名自动加 ` (2)` 序号),`resume.path` 即其中的最新一份
  - `resume.md_path` — 简历 markdown 路径,**恒为** `resume/个人简历.md`(唯一一份)
  - `resume.replaced` — 本次是否拖入了新简历(`true`/`false`)
  - `resume.has_md` — `resume/个人简历.md` 是否已存在
  - `audio.path` / `audio.ext` — 录音相对路径与扩展名
  然后把所有后续命令里的 `<session>` 一律替换为该名称(注意引用带空格/中文的路径)。
- **退出码 1**(超时/失败/中断):提示用户已超时,可重跑脚本,流程结束。

## 2. 分析简历

先判断是否需要提取(依据状态 JSON 的 `resume` 字段):

- **跳过提取**(直接复用):`resume.replaced == false` 且 `resume.has_md == true`
  → 简历未变、md 已存在,直接用 `resume.md_path`,不重新运行 `pdf2text.py`。
- **需要提取**:本次上传了新简历(`replaced == true`,无论 md 是否存在),或尚无 md(`has_md == false`)
  → 运行 `python3 pdf2text.py "<resume.path>"`(不传输出文件,读取 stdout 文本),
  把提取出的文本整理成 Markdown(保留结构、修正换行与明显识别误差),**覆盖写入** `resume/个人简历.md`。**仅整理,不做分析。**

> resume/ 下只保留一份简历 md(`resume/个人简历.md`):沿用现有简历且 md 已存在时复用,上传新简历时重新提取覆盖。

- 若提示缺少 pypdf:请用户先执行 `pip install -r requirements.txt` 后重试本步。
- 若提示 PDF 无文本层(扫描/图片型):告知需 OCR,并说明转录流程不依赖简历、继续执行第 3 步。

## 3. 转写并整理录音

- 确认项目根目录 `.env` 已配置 `ASR_BASE_URL` / `ASR_API_KEY` / `ASR_MODEL`;
  若缺失,提示用户复制 `.env.example` 填写后重试本步,并在用户配置前暂停。
- 运行转写:
  ```bash
  ./transcribe.py "interview/media/<session>.<ext>" "interview/txt/<session>.txt"
  ```
- 读取转录文本,结合简历背景(`resume/个人简历.md`)整理并**写回** `interview/txt/<session>.txt`:
  - 把「面试官」与「候选人」双方话语分开排版;
  - 纠正识别错误的技术名词/专业术语(如 "ncks"→Nacos、"县程"→线程)。

## 4. 生成复盘文档

生成 `interview/<session>.md`,包含 5 个章节:
1. 问答概要 —— 按时间/话题顺序梳理问了什么、怎么答的、结果如何
2. 面试缺点 —— 表达、紧张、答非所问、基础薄弱等问题
3. 可改进点 —— 针对缺点的具体可操作措施
4. 缺少的知识点 —— 明显暴露的未掌握/答错的知识点
5. 下一步建议学习的知识点 —— 结合目标岗位与简历的优先学习清单

## 5. 汇报

- 列出生成的文件:`resume/个人简历.md`、`interview/txt/<session>.txt`、`interview/<session>.md`。
- 给出复盘关键结论,并提示可继续追问细节。
- 隐私提示:录音仅在本机处理后按 `.env` 配置上传语音识别服务;若介意可改用本地转写。
