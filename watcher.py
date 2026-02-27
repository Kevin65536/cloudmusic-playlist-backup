"""
网易云音乐播放列表文件监控模块
通过 watchdog 监控 playingList 文件变化，自动创建备份
"""

import os
import sys
import time
import logging
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from backup_manager import create_backup, PLAYLIST_FILE

# 日志配置
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(LOG_DIR, "watcher.log"), encoding="utf-8"
        ),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("PlaylistWatcher")


class PlaylistChangeHandler(FileSystemEventHandler):
    """监控播放列表文件变化的事件处理器"""

    def __init__(self, playlist_filename: str, debounce_seconds: float = 3.0):
        super().__init__()
        self.playlist_filename = playlist_filename
        self.debounce_seconds = debounce_seconds
        self._last_event_time = 0

    def on_modified(self, event):
        if event.is_directory:
            return

        # 只关注目标文件
        basename = os.path.basename(event.src_path)
        if basename != self.playlist_filename:
            return

        # 防抖：短时间内多次写入只备份一次
        now = time.time()
        if now - self._last_event_time < self.debounce_seconds:
            return
        self._last_event_time = now

        logger.info(f"检测到播放列表变化: {event.src_path}")

        # 短暂等待，确保文件写入完成
        time.sleep(1)

        try:
            result = create_backup(event.src_path, reason="auto")
            if result:
                logger.info(
                    f"自动备份成功: {result['filename']} "
                    f"({result['total_tracks']} 首歌)"
                )
            else:
                logger.debug("播放列表内容未变化，跳过备份")
        except Exception as e:
            logger.error(f"自动备份失败: {e}")


def start_watcher(playlist_path: str = PLAYLIST_FILE):
    """
    启动文件监控
    playlist_path: 播放列表文件完整路径
    """
    watch_dir = os.path.dirname(playlist_path)
    playlist_filename = os.path.basename(playlist_path)

    if not os.path.exists(watch_dir):
        logger.error(f"监控目录不存在: {watch_dir}")
        sys.exit(1)

    # 启动时先做一次备份
    logger.info("启动时执行初始备份...")
    try:
        result = create_backup(playlist_path, reason="auto")
        if result:
            logger.info(
                f"初始备份完成: {result['filename']} "
                f"({result['total_tracks']} 首歌)"
            )
        else:
            logger.info("播放列表与上次备份相同，跳过初始备份")
    except Exception as e:
        logger.error(f"初始备份失败: {e}")

    # 设置文件监控
    handler = PlaylistChangeHandler(playlist_filename)
    observer = Observer()
    observer.schedule(handler, watch_dir, recursive=False)
    observer.start()

    logger.info(f"开始监控播放列表: {playlist_path}")
    logger.info("按 Ctrl+C 停止监控")
    print()
    print("=" * 60)
    print("  网易云音乐播放列表守护程序已启动")
    print(f"  监控文件: {playlist_path}")
    print(f"  备份目录: {os.path.join(os.path.dirname(__file__), 'backups')}")
    print("  当播放列表发生变化时将自动备份")
    print("  按 Ctrl+C 停止")
    print("=" * 60)
    print()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭监控...")
        observer.stop()

    observer.join()
    logger.info("监控已停止")


if __name__ == "__main__":
    start_watcher()
