#!/usr/bin/env python3
"""面试复盘上传服务(本地网页)

跨平台(Windows / macOS / Linux)的本地上传服务:在浏览器里提交
「简历 PDF + 面试录音」,保存到项目 media 目录,并把保存信息写入
状态文件供复盘流程读取。

纯 Python 标准库实现(3.8+),无第三方依赖。只在 127.0.0.1 监听,
文件不离开本机。

简历逻辑:
- 上传页打开时可通过 GET /state 查询 resume/media 下已有的 PDF(取最新),
  页面会展示并默认沿用;此时简历为可选。
- 简历 PDF 不做改名/删除:每次上传直接存入 resume/media(保留上传文件名,
  与已有同名时自动追加 " (2)"/" (3)" 序号);分析时以最新 PDF 为当前简历。
- 简历文本统一整理到唯一的一份 resume/个人简历.md(替换上传时重新生成)。

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
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

SCRIPT_DIR = Path(__file__).resolve().parent

# 允许的音频扩展名(转写前会用 ffmpeg 统一预处理,格式限制放宽些)
AUDIO_EXTS = {
    "m4a", "mp3", "wav", "ogg", "opus", "flac", "aac", "amr",
    "mp4", "m4b", "m4r", "webm", "caf", "aiff", "aif", "wma",
}
RESUME_EXTS = {"pdf"}

# 简历文本统一整理到这一份 md(resume/ 下唯一的一份简历文档)
RESUME_MD = "resume/个人简历.md"

MAX_BODY = 2 * 1024 * 1024 * 1024  # 2GB 上限,防止异常大包


@dataclass
class ServerSettings:
    """HTTP 服务配置(挂到 server.settings,替代原裸 dict)。"""
    root: Path
    page_html: Optional[str] = None
    status_file: Optional[Path] = None
    url_file: Optional[str] = None
    pidfile: Optional[str] = None


def sanitize_name(name: str) -> str:
    """清洗会话/文件名,防止路径穿越、非法字符与隐藏文件点号开头。"""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", name).strip()
    name = re.sub(r"\s+", " ", name)
    name = name.lstrip(".")
    return name or "未命名会话"


def sanitize_filename(name: str) -> str:
    """清洗上传的文件名(保留扩展名),用于落盘。"""
    base, ext = os.path.splitext(name)
    base = sanitize_name(base) or "简历"
    ext = (ext or "").lower()
    return base + ext


def unique_path(directory: Union[str, Path], filename: str) -> Path:
    """返回不重名的路径:若目标已存在,自动追加 " (2)"/" (3)" 序号。"""
    directory = Path(directory)
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    base, ext = os.path.splitext(filename)
    n = 2
    while True:
        candidate = directory / f"{base} ({n}){ext}"
        if not candidate.exists():
            return candidate
        n += 1


def find_existing_resume(root: Union[str, Path]) -> Optional[dict]:
    """返回 resume/media 下最新的 .pdf(作为「当前简历」),无则返回 None。

    简历 md 统一为 resume/个人简历.md;media 下的 PDF 不做改名/删除。
    """
    resume_dir = Path(root) / "resume" / "media"
    if not resume_dir.is_dir():
        return None
    pdfs = [p for p in resume_dir.iterdir() if p.suffix.lower() == ".pdf"]
    if not pdfs:
        return None
    pdfs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    p = pdfs[0]
    return {
        "filename": p.name,
        "path": str(p.relative_to(root)),
        "md_path": RESUME_MD,
        "has_md": (Path(root) / RESUME_MD).is_file(),
        "size": p.stat().st_size,
    }


def parse_multipart(body: bytes, boundary: str) -> Tuple[Dict[str, str], Dict[str, Tuple[str, bytes]]]:
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


class Handler(BaseHTTPRequestHandler):
    server_version = "InterviewUpload/1.0"

    @property
    def settings(self) -> ServerSettings:
        return self.server.settings

    # ---- 响应 ----
    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ---- 路由 ----
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._serve_page()
        elif self.path == "/state":
            self._handle_state()
        else:
            self._send_json(404, {"ok": False, "error": "Not Found"})

    def do_POST(self):
        if self.path != "/upload":
            self._send_json(404, {"ok": False, "error": "Not Found"})
            return
        self._handle_upload()

    # ---- 页面 ----
    def _serve_page(self) -> None:
        html = self.settings.page_html
        if not html:
            self._send_json(500, {"ok": False, "error": "页面文件缺失(upload_page.html)"})
            return
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ---- 状态(现有简历)----
    def _handle_state(self) -> None:
        self._send_json(200, {"ok": True, "existing_resume": find_existing_resume(self.settings.root)})

    # ---- 上传 ----
    def _parse_upload(self) -> Optional[Tuple[Dict[str, str], Dict[str, Tuple[str, bytes]]]]:
        """校验 Content-Length / boundary 并解析 multipart;失败已发错误响应,返回 None。"""
        ctype = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            self._send_json(413, {"ok": False, "error": "请求体过大"})
            return None
        if "boundary=" not in ctype:
            self._send_json(400, {"ok": False, "error": "缺少 multipart boundary"})
            return None
        boundary = ctype.split("boundary=", 1)[1].split(";", 1)[0].strip().strip('"')
        body = self.rfile.read(length)
        try:
            return parse_multipart(body, boundary)
        except Exception as exc:
            self._send_json(400, {"ok": False, "error": f"解析表单失败:{exc}"})
            return None

    def _resolve_session(self, fields: Dict[str, str]) -> str:
        """清洗复盘名称;未填写时用时间戳。判断基于原始字段,与 sanitize 结果无关。"""
        session = sanitize_name(fields.get("session", ""))
        if not fields.get("session"):
            session = time.strftime("%Y年%m月%d日 %H点%M分")
        return session

    def _handle_resume(self, resume, existing) -> Optional[dict]:
        """校验并保存上传的简历,返回 resume_info;校验失败已发错误响应,返回 None。"""
        if resume:
            rname, rdata = resume
            rext = os.path.splitext(rname)[1].lstrip(".").lower()
            if rext not in RESUME_EXTS:
                self._send_json(400, {"ok": False, "error": "简历必须是 PDF 文件"})
                return None
            if not rdata.startswith(b"%PDF"):
                self._send_json(400, {"ok": False, "error": "简历内容不是有效的 PDF(缺少 %PDF 头)"})
                return None

            # 新简历直接保存(保留上传文件名);若与已有简历同名,自动加序号,不覆盖
            resume_dir = self.settings.root / "resume" / "media"
            resume_dir.mkdir(parents=True, exist_ok=True)
            target = unique_path(resume_dir, sanitize_filename(rname))
            target.write_bytes(rdata)
            return {
                "filename": target.name,
                "path": str(target.relative_to(self.settings.root)),
                "md_path": RESUME_MD,
                "has_md": (self.settings.root / RESUME_MD).is_file(),
                "replaced": True,
            }

        # 未上传新简历 → 沿用现有简历
        if not existing:
            self._send_json(400, {"ok": False, "error": "缺少简历 PDF(且 resume/media 下没有现有简历)"})
            return None
        return {
            "filename": existing["filename"],
            "path": existing["path"],
            "md_path": existing["md_path"],
            "has_md": existing["has_md"],
            "replaced": False,
        }

    def _handle_audio(self, audio, session) -> Optional[dict]:
        """校验并保存上传的录音,返回 audio_info;格式失败已发错误响应,返回 None。"""
        aname, adata = audio
        aext = os.path.splitext(aname)[1].lstrip(".").lower()
        if aext not in AUDIO_EXTS:
            self._send_json(400, {"ok": False, "error": f"不支持的音频格式:{aext or '无扩展名'}"})
            return None

        audio_dir = self.settings.root / "interview" / "media"
        audio_dir.mkdir(parents=True, exist_ok=True)
        audio_rel = f"interview/media/{session}.{aext}"
        apath = self.settings.root / audio_rel
        overwritten = apath.exists()
        apath.write_bytes(adata)
        return {
            "filename": aname, "ext": aext, "path": audio_rel,
            "size": len(adata), "overwritten": overwritten,
        }

    def _write_status(self, status: dict) -> bool:
        """把上传结果写入状态文件;失败已发 500 并返回 False。"""
        status_file = self.settings.status_file
        if not status_file:
            return True
        try:
            status_file.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except OSError as exc:
            self._send_json(500, {"ok": False, "error": f"写入状态文件失败:{exc}"})
            return False

    def _handle_upload(self) -> None:
        parsed = self._parse_upload()
        if parsed is None:
            return
        fields, files = parsed

        session = self._resolve_session(fields)
        resume = files.get("resume")      # 可选(已有现有简历时)
        audio = files.get("audio")
        if not audio:
            self._send_json(400, {"ok": False, "error": "缺少面试录音"})
            return

        existing = find_existing_resume(self.settings.root)
        resume_info = self._handle_resume(resume, existing)
        if resume_info is None:
            return
        audio_info = self._handle_audio(audio, session)
        if audio_info is None:
            return

        status = {
            "ok": True,
            "session_name": session,
            "resume": resume_info,
            "audio": audio_info,
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        if not self._write_status(status):
            return
        self._send_json(200, status)

        # 上传成功:稍后自动关闭服务,避免残留进程
        if self.settings.status_file:
            threading.Timer(3.0, self.server.shutdown).start()

    def log_message(self, fmt, *args):
        sys.stderr.write("[upload] %s\n" % (fmt % args))


def main() -> None:
    parser = argparse.ArgumentParser(description="面试复盘上传服务(本地网页)")
    parser.add_argument("--root", default=str(SCRIPT_DIR), help="项目根目录(默认:脚本所在目录)")
    parser.add_argument("--status", help="上传结果写入的状态文件路径")
    parser.add_argument("--url-file", help="把实际访问 URL 写入该文件")
    parser.add_argument("--pidfile", help="把进程 PID 写入该文件")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not (root / "interview").is_dir():
        print(f"错误:目录 {root} 不是有效的项目根目录(缺少 interview/)", file=sys.stderr)
        sys.exit(1)

    page_file = SCRIPT_DIR / "upload_page.html"
    try:
        page_html = page_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"错误:找不到页面文件 {page_file}", file=sys.stderr)
        sys.exit(1)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.settings = ServerSettings(
        root=root,
        page_html=page_html,
        status_file=Path(args.status) if args.status else None,
        url_file=args.url_file,
        pidfile=args.pidfile,
    )

    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/"
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
