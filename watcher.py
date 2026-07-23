#!/usr/bin/env python3
"""
watcher.py — 文件监听 + 自动刷新仪表盘

监听 OpenClaw trajectory 目录变化，新文件或修改时自动重跑 ETL 管线，
并通过内建 HTTP 服务让浏览器自动获取最新数据。

使用方式:
    python watcher.py                    # 启动监听 + HTTP (端口 8889)
    python watcher.py --port 8890        # 自定义端口
    python watcher.py --no-browser       # 不自动打开浏览器
"""

import argparse
import json
import logging
import os
import shutil
import sys
import threading
import time
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from main import run_pipeline

logger = logging.getLogger("watcher")

# ---- 全局状态 ----
DEBOUNCE_SEC = 10
_timer = None
_lock = threading.Lock()
LAST_UPDATE = {"ts": "", "count": 0, "html": ""}

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(ROOT_DIR, "reports")
SESSIONS_DIR = os.path.expanduser("~/.openclaw/agents/main/sessions")


def rebuild():
    global LAST_UPDATE
    try:
        logger.info("重建仪表盘...")
        html_path = run_pipeline(use_real_data=True, sessions_dir=SESSIONS_DIR)
        # 复制到固定文件名，方便浏览器访问
        fixed_path = os.path.join(REPORTS_DIR, "dashboard.html")
        shutil.copy2(html_path, fixed_path)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with _lock:
            LAST_UPDATE = {"ts": now, "count": LAST_UPDATE["count"] + 1, "html": fixed_path}
        logger.info("仪表盘已更新: %s", fixed_path)
    except Exception:
        logger.exception("重建失败")


def debounced_rebuild():
    global _timer
    with _lock:
        if _timer is not None:
            _timer.cancel()
        _timer = threading.Timer(DEBOUNCE_SEC, rebuild)
        _timer.start()
        logger.debug("变化已记录，%d 秒后触发重建", DEBOUNCE_SEC)


class TrajectoryHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.src_path.endswith(".trajectory.jsonl"):
            debounced_rebuild()

    def on_modified(self, event):
        if event.src_path.endswith(".trajectory.jsonl"):
            debounced_rebuild()


class DashboardHTTPHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=REPORTS_DIR, **kwargs)

    def do_GET(self):
        if self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with _lock:
                status = dict(LAST_UPDATE)
            self.wfile.write(json.dumps(status).encode())
            return
        # 默认路由: / → dashboard.html
        if self.path == "/" or self.path == "/index.html":
            self.path = "/dashboard.html"
        super().do_GET()

    def log_message(self, fmt, *args):
        pass  # 抑制访问日志


def _start_http(port):
    server = HTTPServer(("0.0.0.0", port), DashboardHTTPHandler)
    logger.info("HTTP 服务: http://localhost:%d", port)
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="OpenClaw 仪表盘文件监听 + 自动刷新")
    parser.add_argument("--port", type=int, default=8889)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # 首次构建
    rebuild()

    # HTTP 服务（守护线程）
    threading.Thread(target=_start_http, args=(args.port,), daemon=True).start()

    # 文件监听
    observer = Observer()
    observer.schedule(TrajectoryHandler(), SESSIONS_DIR, recursive=False)
    observer.start()
    logger.info("监听目录: %s", SESSIONS_DIR)

    if not args.no_browser:
        import webbrowser
        time.sleep(0.5)
        webbrowser.open(f"http://localhost:{args.port}")

    logger.info("按 Ctrl+C 退出")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        observer.join()
        logger.info("已退出")


if __name__ == "__main__":
    main()
