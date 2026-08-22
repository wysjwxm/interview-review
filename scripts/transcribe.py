#!/usr/bin/env python3
# ============================================================
# transcribe.py — 音频转文本(云端语音识别,OpenAI 兼容 API)
#
# 可动态配置、不绑死某个服务:换服务只需改 .env 里的三个变量。
# 纯标准库实现,无需 pip install;依赖 ffmpeg(预处理,可选)。
# 要求 Python 3.8+。
#
# 用法:
#   python3 scripts/transcribe.py <音频文件> [输出文件]
#   不传输出文件时,结果打印到标准输出。
# ============================================================
import argparse
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Optional, Tuple
from urllib import error, request

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # scripts/ 的上级 = 项目根


def load_dotenv(path: Path) -> None:
    """加载 .env 文件(KEY=VALUE)。已存在的环境变量优先,不被覆盖。"""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def require(name: str) -> str:
    """读取并校验必填配置,缺失则报错退出。"""
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"错误:缺少 {name}。请复制 .env.example 为 .env 并填写。")
    return value


def preprocess(audio: Path) -> Path:
    """用 ffmpeg 统一转成 16kHz 单声道 mp3(缩小体积、保证格式兼容)。

    若录音很长导致超限(如 Groq 单次 25MB),可把 bitrate 调低(如 32k)。
    """
    fd, tmp_path = tempfile.mkstemp(suffix=".mp3", prefix="transcribe-")
    os.close(fd)
    tmp = Path(tmp_path)
    cmd = [
        "ffmpeg", "-loglevel", "error", "-y", "-i", str(audio),
        "-ar", "16000", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "64k", str(tmp),
    ]
    subprocess.run(cmd, check=True)
    return tmp


def multipart_body(fields: list, files: list) -> Tuple[bytes, str]:
    """构造 multipart/form-data 请求体,返回 (body_bytes, content_type)。"""
    boundary = "----transcribe-" + uuid.uuid4().hex
    body = bytearray()
    for name, value in fields:
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        body += str(value).encode("utf-8")
        body += b"\r\n"
    for name, (filename, data, ctype) in files:
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
        body += f"Content-Type: {ctype}\r\n\r\n".encode()
        body += data
        body += b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def build_payload(audio: Path) -> Tuple[bytes, str, str]:
    """预处理音频并返回 (data, filename, content_type);ffmpeg 可用时转成 16kHz mp3。"""
    tmp = None
    upload = audio
    try:
        if shutil.which("ffmpeg") is not None:
            tmp = preprocess(audio)
            upload = tmp
        data = upload.read_bytes()
        filename = upload.name
        ctype = mimetypes.guess_type(str(upload))[0] or "application/octet-stream"
        return data, filename, ctype
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def transcribe(base_url: str, api_key: str, model: str, language: str,
               data: bytes, filename: str, ctype: str) -> str:
    """调用云端语音识别 API,返回识别文本(失败退出,文案与旧版逐字一致)。"""
    fields = [("model", model)]
    if language:
        fields.append(("language", language))
    body, content_type = multipart_body(fields, [("file", (filename, data, ctype))])

    endpoint = f"{base_url}/audio/transcriptions"
    req = request.Request(endpoint, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", content_type)

    try:
        with request.urlopen(req, timeout=600) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except error.HTTPError as e:
        err_body = e.read().decode("utf-8", "replace")
        sys.exit(f"请求失败 HTTP {e.code}:\n{err_body}")
    except error.URLError as e:
        sys.exit(f"网络错误:{e.reason}")

    # 解析响应中的 text 字段;解析失败则原样输出便于排查
    try:
        text = json.loads(raw).get("text", "")
    except json.JSONDecodeError:
        text = raw
    return text or raw


def write_result(text: str, output: Optional[str]) -> None:
    """把识别文本写入文件(带换行)或打印到标准输出。"""
    if output:
        Path(output).write_text(text + "\n", encoding="utf-8")
        print(f"已保存:{output}", file=sys.stderr)
    else:
        print(text)


def main() -> None:
    parser = argparse.ArgumentParser(description="音频转文本(云端语音识别,OpenAI 兼容 API)")
    parser.add_argument("audio", help="音频文件路径")
    parser.add_argument("output", nargs="?", help="输出文件路径(省略则打印到标准输出)")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")

    base_url = require("ASR_BASE_URL").rstrip("/")
    api_key = require("ASR_API_KEY")
    model = require("ASR_MODEL")
    language = os.environ.get("ASR_LANGUAGE", "").strip()

    audio = Path(args.audio)
    if not audio.exists():
        sys.exit(f"错误:找不到音频文件 {audio}")

    data, filename, ctype = build_payload(audio)
    text = transcribe(base_url, api_key, model, language, data, filename, ctype)
    write_result(text, args.output)


if __name__ == "__main__":
    main()
