#!/usr/bin/env python3
"""面试复盘上传服务(本地网页)

跨平台(Windows / macOS / Linux)的本地上传服务:在浏览器里提交
「简历 PDF + 面试录音」,保存到项目 media 目录,并把保存信息写入
状态文件供复盘流程读取。

纯 Python 标准库实现(3.8+),无第三方依赖。只在 127.0.0.1 监听,
文件不离开本机。

用法:
    python3 upload_server.py --root <项目根目录> \
        [--status <状态文件>] [--url-file <URL文件>] [--pidfile <PID文件>]

作者: 个人项目(面试复盘)
"""
import argparse
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# 允许的音频扩展名(转写前会用 ffmpeg 统一预处理,格式限制放宽些)
AUDIO_EXTS = {
    "m4a", "mp3", "wav", "ogg", "opus", "flac", "aac", "amr",
    "mp4", "m4b", "m4r", "webm", "caf", "aiff", "aif", "wma",
}
RESUME_EXTS = {"pdf"}

MAX_BODY = 2 * 1024 * 1024 * 1024  # 2GB 上限,防止异常大包


def sanitize_name(name):
    """清洗会话名,防止路径穿越 / 非法字符。"""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", name).strip()
    name = re.sub(r"\s+", " ", name)
    return name or "未命名会话"


def parse_multipart(body, boundary):
    """解析 multipart/form-data,返回 (fields, files)。

    files: {字段名: (原始文件名, 文件字节)}
    fields: {字段名: 文本}
    """
    delimiter = b"--" + boundary.encode("ascii")
    fields, files = {}, {}
    for seg in body.split(delimiter):
        if seg.startswith(b"\r\n"):      # 边界后的前导 CRLF
            seg = seg[2:]
        if seg.startswith(b"--"):        # 结尾的 "--boundary--"
            seg = seg[2:]
        if seg.endswith(b"\r\n"):        # 段尾与下一个边界之间的分隔
            seg = seg[:-2]
        if not seg.strip():
            continue
        if b"\r\n\r\n" not in seg:
            continue
        head, content = seg.split(b"\r\n\r\n", 1)
        disp = None
        for line in head.split(b"\r\n"):
            if line.lower().startswith(b"content-disposition:"):
                disp = line[len(b"content-disposition:"):].strip()
                break
        if disp is None:
            continue
        name = filename = None
        for param in disp.split(b";")[1:]:
            param = param.strip()
            low = param.lower()
            if low.startswith(b"name="):
                name = param[5:].strip(b'"').decode("utf-8", "replace")
            elif low.startswith(b"filename="):
                filename = param[9:].strip(b'"').decode("utf-8", "replace")
        if name is None:
            continue
        if filename:
            files[name] = (filename, content)
        else:
            fields[name] = content.decode("utf-8", "replace")
    return fields, files


def respond(handler, code, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    server_version = "InterviewUpload/1.0"

    # ---- 路由 ----
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._serve_page()
        else:
            respond(self, 404, {"ok": False, "error": "Not Found"})

    def do_POST(self):
        if self.path != "/upload":
            respond(self, 404, {"ok": False, "error": "Not Found"})
            return
        self._handle_upload()

    # ---- 页面 ----
    def _serve_page(self):
        html = self.server.settings.get("page_html")
        if not html:
            respond(self, 500, {"ok": False, "error": "页面文件缺失(upload_page.html)"})
            return
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ---- 上传 ----
    def _handle_upload(self):
        s = self.server.settings
        ctype = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            respond(self, 413, {"ok": False, "error": "请求体过大"})
            return
        if "boundary=" not in ctype:
            respond(self, 400, {"ok": False, "error": "缺少 multipart boundary"})
            return
        boundary = ctype.split("boundary=", 1)[1].split(";", 1)[0].strip().strip('"')
        body = self.rfile.read(length)
        try:
            fields, files = parse_multipart(body, boundary)
        except Exception as exc:
            respond(self, 400, {"ok": False, "error": "解析表单失败:%s" % exc})
            return

        session = sanitize_name(fields.get("session", ""))
        if not fields.get("session"):
            session = time.strftime("%Y年%m月%d日 %H点%M分")

        resume = files.get("resume")
        audio = files.get("audio")
        errors = []
        if not resume:
            errors.append("缺少简历 PDF")
        if not audio:
            errors.append("缺少面试录音")
        if errors:
            respond(self, 400, {"ok": False, "error": "；".join(errors)})
            return

        rname, rdata = resume
        aname, adata = audio
        rext = os.path.splitext(rname)[1].lstrip(".").lower()
        aext = os.path.splitext(aname)[1].lstrip(".").lower()

        if rext not in RESUME_EXTS:
            respond(self, 400, {"ok": False, "error": "简历必须是 PDF 文件"})
            return
        if not rdata.startswith(b"%PDF"):
            respond(self, 400, {"ok": False, "error": "简历内容不是有效的 PDF(缺少 %PDF 头)"})
            return
        if aext not in AUDIO_EXTS:
            respond(self, 400, {"ok": False, "error": "不支持的音频格式:%s" % (aext or "无扩展名")})
            return

        root = Path(s["root"])
        resume_dir = root / "resume" / "media"
        audio_dir = root / "interview" / "media"
        resume_dir.mkdir(parents=True, exist_ok=True)
        audio_dir.mkdir(parents=True, exist_ok=True)

        resume_rel = "resume/media/%s.pdf" % session
        audio_rel = "interview/media/%s.%s" % (session, aext)
        rpath = root / resume_rel
        apath = root / audio_rel

        overwritten = {"resume": rpath.exists(), "audio": apath.exists()}
        rpath.write_bytes(rdata)
        apath.write_bytes(adata)

        status = {
            "ok": True,
            "session_name": session,
            "resume": {
                "filename": rname, "path": resume_rel, "size": len(rdata),
                "overwritten": overwritten["resume"],
            },
            "audio": {
                "filename": aname, "ext": aext, "path": audio_rel, "size": len(adata),
                "overwritten": overwritten["audio"],
            },
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        status_file = s.get("status_file")
        if status_file:
            try:
                with open(status_file, "w", encoding="utf-8") as fh:
                    json.dump(status, fh, ensure_ascii=False, indent=2)
            except Exception as exc:
                respond(self, 500, {"ok": False, "error": "写入状态文件失败:%s" % exc})
                return

        respond(self, 200, status)

        # 上传成功:稍后自动关闭服务,避免残留进程
        if status_file:
            threading.Timer(3.0, self.server.shutdown).start()

    def log_message(self, fmt, *args):
        sys.stderr.write("[upload] %s\n" % (fmt % args))


def main():
    parser = argparse.ArgumentParser(description="面试复盘上传服务(本地网页)")
    parser.add_argument("--root", default=str(SCRIPT_DIR), help="项目根目录(默认:脚本所在目录)")
    parser.add_argument("--status", help="上传结果写入的状态文件路径")
    parser.add_argument("--url-file", help="把实际访问 URL 写入该文件")
    parser.add_argument("--pidfile", help="把进程 PID 写入该文件")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not (root / "interview").is_dir():
        print("错误:目录 %s 不是有效的项目根目录(缺少 interview/)" % root, file=sys.stderr)
        sys.exit(1)

    page_file = SCRIPT_DIR / "upload_page.html"
    try:
        page_html = page_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        print("错误:找不到页面文件 %s" % page_file, file=sys.stderr)
        sys.exit(1)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.settings = {
        "root": str(root),
        "status_file": args.status,
        "url_file": args.url_file,
        "pidfile": args.pidfile,
        "page_html": page_html,
    }

    port = server.server_address[1]
    url = "http://127.0.0.1:%d/" % port
    print(url, flush=True)

    if args.url_file:
        Path(args.url_file).write_text(url, encoding="utf-8")
    if args.pidfile:
        Path(args.pidfile).write_text(str(os.getpid()), encoding="utf-8")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        for f in (args.url_file, args.pidfile):
            if f:
                try:
                    Path(f).unlink(missing_ok=True)
                except OSError:
                    pass


if __name__ == "__main__":
    main()
