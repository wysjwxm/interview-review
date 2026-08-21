#!/usr/bin/env python3
"""面试复盘 · 一键触发上传

运行本脚本 = 弹出上传页并等待提交材料:
    1. 启动本地上传服务(upload_server.py,127.0.0.1 随机端口)
    2. 打开浏览器上传页(简历 PDF + 面试录音)
    3. 等待提交完成(最长约 10 分钟)
    4. 把上传结果写入状态文件并打印其路径,退出码 0

两种使用方式:
- 用户直接在终端运行:`python3 start_review.py`
  → 上传完成后,回到 Claude 说一声,由 Claude 读取状态文件继续复盘。
- Claude 收到「我要面试复盘」/ `/review` 时:直接运行本脚本
  → 退出码 0 后读取状态文件,继续做简历提取、转写与复盘文档生成。

用法:
    python3 start_review.py [--status <结果JSON路径>] [--root <项目根>]

退出码:
    0  上传成功(状态文件已就绪)
    1  超时 / 服务启动失败 / 用户中断
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_STATUS = Path(tempfile.gettempdir()) / "interview_review" / "upload.json"


def open_browser(url):
    """按平台打开浏览器;返回是否成功。"""
    if sys.platform == "darwin":
        cmd = ["open", url]
    elif os.name == "nt":
        cmd = ["cmd", "/c", "start", "", url]
    else:
        cmd = ["xdg-open", url]
    try:
        subprocess.Popen(cmd, start_new_session=(os.name != "nt"))
        return True
    except OSError:
        return False


def stop_process(pidfile):
    """按 pidfile 结束上传服务进程(跨平台,尽力而为)。"""
    if not pidfile.is_file():
        return
    try:
        pid = int(pidfile.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(["kill", str(pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def main():
    ap = argparse.ArgumentParser(description="面试复盘 · 一键触发上传")
    ap.add_argument("--status", default=str(DEFAULT_STATUS),
                    help="上传结果 JSON 路径(默认:%s)" % DEFAULT_STATUS)
    ap.add_argument("--root", default=str(SCRIPT_DIR),
                    help="项目根目录(默认:脚本所在目录;一般无需改动)")
    ap.add_argument("--max-wait", type=int, default=600,
                    help="最长等待秒数(默认 600 = 10 分钟)")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    status_file = Path(args.status)
    status_file.parent.mkdir(parents=True, exist_ok=True)

    # 前置检查(脚本与上传服务在项目根,上传文件落盘到 --root)
    for name in ("upload_server.py", "upload_page.html"):
        if not (SCRIPT_DIR / name).is_file():
            print("错误:项目根缺少 %s" % name, file=sys.stderr)
            return 1
    if not (root / "interview").is_dir():
        print("错误:%s 不是有效的项目根目录(缺少 interview/)" % root, file=sys.stderr)
        return 1

    # 临时文件
    tmp = Path(tempfile.gettempdir()) / "interview_review"
    tmp.mkdir(parents=True, exist_ok=True)
    url_file = tmp / "url.txt"
    pid_file = tmp / "pid.txt"
    for f in (status_file, url_file, pid_file):
        try:
            f.unlink()
        except OSError:
            pass

    # 启动上传服务
    try:
        proc = subprocess.Popen(
            [sys.executable, str(SCRIPT_DIR / "upload_server.py"),
             "--root", str(root),
             "--status", str(status_file),
             "--url-file", str(url_file),
             "--pidfile", str(pid_file)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        print("错误:启动上传服务失败:%s" % exc, file=sys.stderr)
        return 1

    try:
        # 等待服务就绪,读取 URL
        url = None
        for _ in range(15):
            if proc.poll() is not None:
                print("错误:上传服务启动失败", file=sys.stderr)
                return 1
            if url_file.is_file():
                url = url_file.read_text(encoding="utf-8").strip()
                if url:
                    break
            time.sleep(1)
        if not url:
            print("错误:等待上传服务 URL 超时(15s)", file=sys.stderr)
            return 1

        print("上传页地址:", url)
        if open_browser(url):
            print("浏览器已打开:请在页面提交 简历 PDF + 面试录音(有现有简历时可选不换,直接沿用)")
        else:
            print("无法自动打开浏览器,请手动访问:%s" % url)

        # 等待上传完成
        deadline = time.time() + max(args.max_wait, 30)
        while time.time() < deadline:
            if status_file.is_file():
                try:
                    data = json.loads(status_file.read_text(encoding="utf-8"))
                except (ValueError, OSError):
                    data = None  # 文件可能正在写入,继续等
                if data and data.get("ok"):
                    print("\n✓ 上传完成,结果已写入:", status_file)
                    resume = data.get("resume") or {}
                    audio = data.get("audio") or {}
                    print("  复盘名称:", data.get("session_name"))
                    print("  简历:", resume.get("path") or "(未指定)")
                    print("  录音:", audio.get("path") or "(无)")
                    print("\n回到 Claude 输入「继续复盘」即可生成复盘文档。")
                    return 0
            if proc.poll() is not None and not status_file.is_file():
                print("错误:上传服务意外退出", file=sys.stderr)
                return 1
            time.sleep(2)

        print("✗ 等待上传超时(%d 秒),未收到提交。如需重试请再次运行本脚本。" % max(args.max_wait, 30),
              file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已取消,未收到上传。", file=sys.stderr)
        return 1
    finally:
        # 清理服务进程(上传成功时服务会自停,这里兜底)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        stop_process(pid_file)
        try:
            url_file.unlink(missing_ok=True)
            pid_file.unlink(missing_ok=True)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
