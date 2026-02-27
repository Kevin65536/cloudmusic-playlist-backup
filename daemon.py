"""
网易云音乐播放列表后台守护程序
- 静默运行（通过 pythonw.exe 启动时无窗口）
- 自动检测网易云音乐进程，启动时开始监控
- 播放列表大幅变化时弹窗提醒，询问是否恢复
- 单实例锁，防止重复启动
"""

import os
import sys
import time
import json
import subprocess
import ctypes
import logging
import queue
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from backup_manager import (
    create_backup,
    list_backups,
    restore_backup,
    extract_summary,
    compute_hash,
    PLAYLIST_FILE,
    BACKUP_DIR,
)

# ── 常量配置 ──────────────────────────────────────────────
CLOUDMUSIC_PROCESS = "cloudmusic.exe"
POLL_INTERVAL = 5          # 进程检测间隔（秒）
DEBOUNCE_SECONDS = 5       # 文件变化防抖时间（秒）
CHANGE_THRESHOLD_OVERLAP = 0.4   # 重叠率低于此值视为大幅变化
CHANGE_THRESHOLD_DROP = 0.5      # 歌曲数下降超过此比例视为大幅变化
MIN_TRACKS_FOR_DETECTION = 5     # 之前歌曲数少于此值则不检测

# Windows MessageBox 常量
MB_YESNO = 0x04
MB_ICONWARNING = 0x30
MB_ICONINFORMATION = 0x40
MB_TOPMOST = 0x40000
MB_SETFOREGROUND = 0x10000
IDYES = 6

# ── 单实例锁 ─────────────────────────────────────────────
MUTEX_NAME = "Global\\CloudMusicPlaylistBackupDaemon"


def acquire_singleton_lock():
    """尝试获取单实例互斥锁，失败则退出"""
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return False
    return True


# ── 日志配置 ─────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(LOG_DIR, "daemon.log"), encoding="utf-8"
        ),
    ],
)
logger = logging.getLogger("Daemon")


# ── 进程检测 ─────────────────────────────────────────────
def is_cloudmusic_running() -> bool:
    """检查网易云音乐进程是否在运行"""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {CLOUDMUSIC_PROCESS}", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return CLOUDMUSIC_PROCESS.lower() in result.stdout.lower()
    except Exception:
        return False


# ── 文件监控处理器 ────────────────────────────────────────
class DaemonPlaylistHandler(FileSystemEventHandler):
    """将文件变化事件放入队列，由主线程处理"""

    def __init__(self, playlist_filename: str, alert_queue: queue.Queue):
        super().__init__()
        self.playlist_filename = playlist_filename
        self.alert_queue = alert_queue
        self._last_event_time = 0

    def on_modified(self, event):
        if event.is_directory:
            return
        if os.path.basename(event.src_path) != self.playlist_filename:
            return

        now = time.time()
        if now - self._last_event_time < DEBOUNCE_SECONDS:
            return
        self._last_event_time = now

        # 等待文件写入完成
        time.sleep(1.5)
        self.alert_queue.put(event.src_path)


# ── 变化分析 ─────────────────────────────────────────────
def analyze_change(playlist_path: str, prev_backup_info: dict) -> dict | None:
    """
    分析播放列表变化是否为大幅变化（疑似被覆盖）。
    返回变化详情 dict（大幅变化时），或 None（正常变化时）。
    """
    try:
        with open(playlist_path, "r", encoding="utf-8") as f:
            current_data = json.load(f)
    except Exception as e:
        logger.error(f"无法读取当前播放列表: {e}")
        return None

    current_summary = extract_summary(current_data)
    current_ids = {s["id"] for s in current_summary["songs"]}
    current_count = current_summary["total_tracks"]

    if not prev_backup_info:
        return None

    # 读取上一个备份
    backup_path = os.path.join(BACKUP_DIR, prev_backup_info["filename"])
    try:
        with open(backup_path, "r", encoding="utf-8") as f:
            backup_data = json.load(f)
    except Exception as e:
        logger.error(f"无法读取备份文件: {e}")
        return None

    backup_summary = extract_summary(backup_data)
    backup_ids = {s["id"] for s in backup_summary["songs"]}
    backup_count = backup_summary["total_tracks"]

    # 之前歌曲太少，不检测
    if backup_count < MIN_TRACKS_FOR_DETECTION:
        return None

    # 计算重叠
    common = current_ids & backup_ids
    overlap_ratio = len(common) / max(backup_count, 1)
    count_drop_ratio = (backup_count - current_count) / max(backup_count, 1)

    is_drastic = (
        (overlap_ratio < CHANGE_THRESHOLD_OVERLAP)
        or (count_drop_ratio > CHANGE_THRESHOLD_DROP and current_count < backup_count)
    )

    if not is_drastic:
        return None

    # 收集丢失的歌曲样本
    lost_ids = backup_ids - current_ids
    backup_songs_map = {s["id"]: s for s in backup_summary["songs"]}
    lost_songs = [
        backup_songs_map[sid]
        for sid in list(lost_ids)[:10]
        if sid in backup_songs_map
    ]

    return {
        "old_count": backup_count,
        "new_count": current_count,
        "lost_count": len(lost_ids),
        "gained_count": len(current_ids - backup_ids),
        "common_count": len(common),
        "overlap_ratio": overlap_ratio,
        "lost_sample": lost_songs,
    }


# ── 弹窗 ─────────────────────────────────────────────────
def show_restore_dialog(change_info: dict) -> bool:
    """弹出 Windows 消息框，询问是否恢复。返回 True 表示用户选择恢复。"""
    lost_songs_text = "\n".join(
        f"  · {s['name']} - {s['artist']}" for s in change_info["lost_sample"][:8]
    )
    if change_info["lost_count"] > 8:
        lost_songs_text += f"\n  ... 等共 {change_info['lost_count']} 首"

    message = (
        f"检测到播放列表发生大幅变化！\n\n"
        f"变化前: {change_info['old_count']} 首歌曲\n"
        f"变化后: {change_info['new_count']} 首歌曲\n"
        f"丢失歌曲: {change_info['lost_count']} 首\n\n"
        f"部分丢失的歌曲:\n{lost_songs_text}\n\n"
        f"是否恢复到变化前的播放列表？\n"
        f"（恢复后请重启网易云音乐客户端）"
    )

    result = ctypes.windll.user32.MessageBoxW(
        0,
        message,
        "网易云音乐 - 播放列表变化警告",
        MB_YESNO | MB_ICONWARNING | MB_TOPMOST | MB_SETFOREGROUND,
    )
    return result == IDYES


def show_info_dialog(message: str, title: str = "提示"):
    """显示一个信息提示框"""
    ctypes.windll.user32.MessageBoxW(
        0,
        message,
        title,
        MB_ICONINFORMATION | MB_TOPMOST,
    )


# ── 守护进程主类 ──────────────────────────────────────────
class PlaylistDaemon:
    def __init__(self, playlist_path: str = PLAYLIST_FILE):
        self.playlist_path = playlist_path
        self.watch_dir = os.path.dirname(playlist_path)
        self.playlist_filename = os.path.basename(playlist_path)
        self.observer = None
        self.alert_queue = queue.Queue()
        self.is_watching = False
        self.was_running = False
        self.suppress_next = False  # 恢复后抑制下一次弹窗

    def start_watching(self):
        """开始监控播放列表文件"""
        if self.is_watching:
            return

        handler = DaemonPlaylistHandler(self.playlist_filename, self.alert_queue)
        self.observer = Observer()
        self.observer.schedule(handler, self.watch_dir, recursive=False)
        self.observer.start()
        self.is_watching = True

        # 启动监控时做一次初始备份
        try:
            result = create_backup(self.playlist_path, reason="auto")
            if result:
                logger.info(
                    f"初始备份: {result['filename']} ({result['total_tracks']} 首)"
                )
        except Exception as e:
            logger.error(f"初始备份失败: {e}")

        logger.info("开始监控播放列表")

    def stop_watching(self):
        """停止监控"""
        if not self.is_watching:
            return

        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)
            self.observer = None

        self.is_watching = False
        logger.info("停止监控播放列表")

    def handle_change(self, filepath: str):
        """处理文件变化事件"""
        logger.info("检测到播放列表变化")

        # ① 获取变化前的最后一个备份（用于后续对比）
        backups = list_backups()
        prev_backup = backups[-1] if backups else None

        # ② 备份当前（变化后的）内容
        try:
            result = create_backup(filepath, reason="auto")
            if result:
                logger.info(
                    f"自动备份: {result['filename']} ({result['total_tracks']} 首)"
                )
            else:
                logger.debug("内容未变化，跳过备份")
                return
        except Exception as e:
            logger.error(f"备份失败: {e}")
            return

        # ③ 如果刚执行过恢复，抑制本次检测（避免恢复本身触发弹窗）
        if self.suppress_next:
            self.suppress_next = False
            logger.info("恢复后的文件写入，跳过大幅变化检测")
            return

        # ④ 分析是否为大幅变化
        if prev_backup:
            change_info = analyze_change(filepath, prev_backup)
            if change_info:
                logger.warning(
                    f"大幅变化! {change_info['old_count']} → "
                    f"{change_info['new_count']} 首, "
                    f"丢失 {change_info['lost_count']} 首"
                )

                if show_restore_dialog(change_info):
                    logger.info("用户选择恢复")
                    # 要恢复的是 prev_backup（变化前的备份）
                    # 它现在是倒数第二个备份
                    backups = list_backups()
                    restore_index = len(backups) - 1  # 1-indexed, 倒数第二个

                    self.suppress_next = True
                    success = restore_backup(
                        restore_index, filepath, backup_current_first=False
                    )

                    if success:
                        logger.info("恢复成功")
                        show_info_dialog(
                            "播放列表已恢复！\n\n请重启网易云音乐客户端以加载恢复的播放列表。",
                            "恢复成功",
                        )
                    else:
                        logger.error("恢复失败")
                        show_info_dialog(
                            "恢复失败，请尝试手动恢复。\n\n"
                            "运行: python main.py list 查看备份\n"
                            "运行: python main.py restore <序号> 恢复",
                            "恢复失败",
                        )
                else:
                    logger.info("用户选择保留当前播放列表")

    def run(self):
        """守护进程主循环"""
        logger.info("=" * 50)
        logger.info("守护进程启动")
        logger.info(f"监控文件: {self.playlist_path}")
        logger.info(f"目标进程: {CLOUDMUSIC_PROCESS}")
        logger.info(f"备份目录: {BACKUP_DIR}")

        try:
            while True:
                # 检测网易云音乐进程
                running = is_cloudmusic_running()

                if running and not self.was_running:
                    logger.info("网易云音乐已启动")
                    time.sleep(3)  # 等待应用初始化
                    self.start_watching()
                elif not running and self.was_running:
                    logger.info("网易云音乐已关闭")
                    # 关闭前做一次最终备份
                    try:
                        result = create_backup(self.playlist_path, reason="auto")
                        if result:
                            logger.info(f"关闭前备份: {result['filename']}")
                    except Exception:
                        pass
                    self.stop_watching()

                self.was_running = running

                # 处理文件变化事件队列
                try:
                    while True:
                        filepath = self.alert_queue.get_nowait()
                        self.handle_change(filepath)
                except queue.Empty:
                    pass

                time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            logger.info("收到中断信号")
        except Exception as e:
            logger.error(f"守护进程异常: {e}", exc_info=True)
        finally:
            self.stop_watching()
            logger.info("守护进程已停止")


# ── 入口 ─────────────────────────────────────────────────
def main():
    if not acquire_singleton_lock():
        logger.info("已有一个守护进程实例在运行，退出")
        sys.exit(0)

    daemon = PlaylistDaemon()
    daemon.run()


if __name__ == "__main__":
    main()
