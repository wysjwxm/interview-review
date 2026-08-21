---
description: 弹出上传页面(简历 PDF + 面试录音),自动执行面试复盘流程
---

# 面试复盘 · 上传式

用户输入「我要面试复盘」或调用 `/review` 时,按下面流程执行。
上传服务为纯 Python 标准库(跨平台),全程只在本机 `127.0.0.1` 监听。

## 1. 准备

- 确认当前工作目录是项目根目录(含 `interview/`);若不确定,先 `cd` 到项目根再继续。
- 确认项目根目录下有 `upload_server.py` 与 `upload_page.html`。
- 用系统临时目录生成本次会话的临时文件路径(避免污染仓库):
  ```bash
  ROOT="$(pwd)"
  TMP="$(python3 -c "import tempfile,os;print(os.path.join(tempfile.gettempdir(),'interview_review'))")"
  mkdir -p "$TMP"
  STATUS="$TMP/status.json"; URLFILE="$TMP/url.txt"; PIDFILE="$TMP/server.pid"
  rm -f "$STATUS" "$URLFILE" "$PIDFILE"
  ```

## 2. 启动上传服务(后台)

```bash
python3 "$ROOT/upload_server.py" --root "$ROOT" --status "$STATUS" --url-file "$URLFILE" --pidfile "$PIDFILE"
```

在后台运行。轮询等待 `$URLFILE` 出现(最多约 15 秒),然后读取其中的实际 URL:
```bash
for i in $(seq 1 15); do [ -f "$URLFILE" ] && break; sleep 1; done
cat "$URLFILE"
```
> 若 15 秒内未出现,说明服务启动失败,读取后台任务输出排查并终止流程。

## 3. 打开浏览器

按系统用对应命令打开 URL:
- macOS:`open "$URL"`
- Linux:`xdg-open "$URL"`
- Windows(cmd):`start "$URL"`

同时向用户提示:「请在弹出的页面上提交 简历 PDF + 面试录音,提交后我会自动开始复盘。」

## 4. 等待上传(阻塞轮询)

```bash
for i in $(seq 1 300); do [ -f "$STATUS" ] && break; sleep 2; done
[ -f "$STATUS" ] && echo UPLOADED || echo TIMEOUT
```
> 该循环最长约 10 分钟,执行这条 Bash 命令时**把工具 timeout 设为 600000ms**,否则会提前中断。
- 若 `TIMEOUT`(约 10 分钟未上传):提示用户已超时,按第 5 步结尾清理服务进程,流程结束。
- 若 `UPLOADED`:用 Read 工具读取 `$STATUS`,得到:
  - `session_name` — 复盘名称(可能含中文/空格)
  - `resume.path` — 简历相对路径,如 `resume/media/xxx.pdf`
  - `audio.path` / `audio.ext` — 录音相对路径与扩展名
  然后把所有后续命令里的 `<session>` 一律替换为该名称(注意引用带空格/中文的路径)。

清理服务进程(已自我退出则忽略错误):
```bash
[ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE")" 2>/dev/null; rm -f "$PIDFILE"
```

## 5. 分析简历

- 运行 `python3 pdf2text.py "<resume.path>"`(不传输出文件,读取 stdout 文本)。
- 若提示缺少 pypdf:请用户先执行 `pip install -r requirements.txt` 后重试本步。
- 若提示 PDF 无文本层(扫描/图片型):告知需 OCR,并说明转录流程不依赖简历、继续执行第 6 步。
- 把提取出的文本整理成 Markdown(保留结构、修正换行与明显识别误差),保存为 `resume/<session>.md`。**仅整理,不做分析。**

## 6. 转写并整理录音

- 确认项目根目录 `.env` 已配置 `ASR_BASE_URL` / `ASR_API_KEY` / `ASR_MODEL`;
  若缺失,提示用户复制 `.env.example` 填写后重试本步,并在用户配置前暂停。
- 运行转写:
  ```bash
  ./transcribe.py "interview/media/<session>.<ext>" "interview/<session>.txt"
  ```
- 读取转录文本,结合简历背景(`resume/<session>.md` 与 `resume/` 下已有的简历)整理并**写回** `interview/<session>.txt`:
  - 把「面试官」与「候选人」双方话语分开排版;
  - 纠正识别错误的技术名词/专业术语(如 "ncks"→Nacos、"县程"→线程)。

## 7. 生成复盘文档

生成 `interview/<session>.md`,包含 5 个章节:
1. 问答概要 —— 按时间/话题顺序梳理问了什么、怎么答的、结果如何
2. 面试缺点 —— 表达、紧张、答非所问、基础薄弱等问题
3. 可改进点 —— 针对缺点的具体可操作措施
4. 缺少的知识点 —— 明显暴露的未掌握/答错的知识点
5. 下一步建议学习的知识点 —— 结合目标岗位与简历的优先学习清单

## 8. 汇报

- 列出生成的文件:`resume/<session>.md`、`interview/<session>.txt`、`interview/<session>.md`。
- 给出复盘关键结论,并提示可继续追问细节。
- 隐私提示:录音仅在本机处理后按 `.env` 配置上传语音识别服务;若介意可改用本地转写。
