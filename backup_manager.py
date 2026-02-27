"""
网易云音乐播放列表备份管理核心模块
负责备份的创建、存储、查询、对比和恢复
"""

import json
import os
import shutil
import hashlib
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


# 默认路径配置
PLAYLIST_FILE = r"C:\Users\qdsxh\AppData\Local\NetEase\CloudMusic\webdata\file\playingList"
BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")
META_FILE = os.path.join(BACKUP_DIR, "backup_meta.json")
MAX_BACKUPS = 100  # 最大保留备份数


def ensure_backup_dir():
    """确保备份目录存在"""
    os.makedirs(BACKUP_DIR, exist_ok=True)


def compute_hash(content: str) -> str:
    """计算文件内容的 MD5 哈希"""
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def load_meta() -> dict:
    """加载备份元数据"""
    ensure_backup_dir()
    if os.path.exists(META_FILE):
        with open(META_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"backups": []}


def save_meta(meta: dict):
    """保存备份元数据"""
    ensure_backup_dir()
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def extract_summary(playlist_data: dict) -> dict:
    """从播放列表数据中提取摘要信息"""
    tracks = playlist_data.get("list", [])
    song_list = []
    for t in tracks:
        track = t.get("track", {})
        artists = track.get("artists", [])
        artist_name = artists[0].get("name", "未知") if artists else "未知"
        song_list.append({
            "id": track.get("id", ""),
            "name": track.get("name", "未知"),
            "artist": artist_name,
        })

    # 来源信息（如果有的话）
    source = ""
    if tracks:
        from_info = tracks[0].get("fromInfo", {})
        source_data = from_info.get("sourceData", {})
        source = source_data.get("name", "")

    return {
        "total_tracks": len(tracks),
        "source": source,
        "songs": song_list,
        "first_5": [f"{s['name']} - {s['artist']}" for s in song_list[:5]],
    }


def create_backup(
    playlist_path: str = PLAYLIST_FILE,
    reason: str = "auto",
    force: bool = False,
) -> Optional[dict]:
    """
    创建一个备份。
    reason: "auto" | "manual" | "restore_before"
    force: 如果为 True，即使内容未变化也进行备份
    返回备份信息 dict，如果跳过则返回 None
    """
    ensure_backup_dir()

    if not os.path.exists(playlist_path):
        print(f"[错误] 播放列表文件不存在: {playlist_path}")
        return None

    with open(playlist_path, "r", encoding="utf-8") as f:
        content = f.read()

    content_hash = compute_hash(content)

    # 检查是否和上一次备份相同（避免重复备份）
    if not force:
        meta = load_meta()
        if meta["backups"]:
            last = meta["backups"][-1]
            if last.get("hash") == content_hash:
                return None  # 内容未变化，跳过

    # 解析内容
    try:
        playlist_data = json.loads(content)
    except json.JSONDecodeError:
        print("[错误] 播放列表文件不是有效的 JSON")
        return None

    summary = extract_summary(playlist_data)

    # 生成备份文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"playlist_{timestamp}.json"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)

    # 如果同一秒内有多个备份，加序号
    counter = 1
    while os.path.exists(backup_path):
        backup_filename = f"playlist_{timestamp}_{counter}.json"
        backup_path = os.path.join(BACKUP_DIR, backup_filename)
        counter += 1

    # 保存备份文件
    shutil.copy2(playlist_path, backup_path)

    # 更新元数据
    backup_info = {
        "filename": backup_filename,
        "timestamp": datetime.now().isoformat(),
        "timestamp_display": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "hash": content_hash,
        "reason": reason,
        "total_tracks": summary["total_tracks"],
        "source": summary["source"],
        "first_5": summary["first_5"],
    }

    meta = load_meta()
    meta["backups"].append(backup_info)

    # 清理过旧的备份（保留 MAX_BACKUPS 个）
    if len(meta["backups"]) > MAX_BACKUPS:
        to_remove = meta["backups"][:-MAX_BACKUPS]
        meta["backups"] = meta["backups"][-MAX_BACKUPS:]
        for old in to_remove:
            old_path = os.path.join(BACKUP_DIR, old["filename"])
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except OSError:
                    pass

    save_meta(meta)
    return backup_info


def list_backups() -> list:
    """列出所有备份"""
    meta = load_meta()
    return meta["backups"]


def get_backup_detail(index: int) -> Optional[dict]:
    """
    获取指定备份的详细信息（包括完整歌曲列表）
    index: 从 1 开始的序号
    """
    meta = load_meta()
    if index < 1 or index > len(meta["backups"]):
        return None

    backup_info = meta["backups"][index - 1]
    backup_path = os.path.join(BACKUP_DIR, backup_info["filename"])

    if not os.path.exists(backup_path):
        return None

    with open(backup_path, "r", encoding="utf-8") as f:
        playlist_data = json.load(f)

    summary = extract_summary(playlist_data)
    return {**backup_info, "songs": summary["songs"]}


def compare_backups(index1: int, index2: int) -> Optional[dict]:
    """
    比较两个备份的差异
    返回: 新增的歌曲、删除的歌曲、相同的歌曲数量
    """
    detail1 = get_backup_detail(index1)
    detail2 = get_backup_detail(index2)

    if not detail1 or not detail2:
        return None

    set1 = {s["id"] for s in detail1["songs"]}
    set2 = {s["id"] for s in detail2["songs"]}

    added_ids = set2 - set1
    removed_ids = set1 - set2
    common_count = len(set1 & set2)

    songs1_map = {s["id"]: s for s in detail1["songs"]}
    songs2_map = {s["id"]: s for s in detail2["songs"]}

    added = [songs2_map[sid] for sid in added_ids if sid in songs2_map]
    removed = [songs1_map[sid] for sid in removed_ids if sid in songs1_map]

    return {
        "backup1": {"index": index1, "time": detail1["timestamp_display"], "total": detail1["total_tracks"]},
        "backup2": {"index": index2, "time": detail2["timestamp_display"], "total": detail2["total_tracks"]},
        "added": added,
        "removed": removed,
        "common_count": common_count,
    }


def compare_with_current(index: int, playlist_path: str = PLAYLIST_FILE) -> Optional[dict]:
    """
    将指定备份与当前播放列表对比
    """
    detail = get_backup_detail(index)
    if not detail:
        return None

    with open(playlist_path, "r", encoding="utf-8") as f:
        current_data = json.load(f)

    current_summary = extract_summary(current_data)

    set_backup = {s["id"] for s in detail["songs"]}
    set_current = {s["id"] for s in current_summary["songs"]}

    added_ids = set_current - set_backup
    removed_ids = set_backup - set_current
    common_count = len(set_backup & set_current)

    backup_map = {s["id"]: s for s in detail["songs"]}
    current_map = {s["id"]: s for s in current_summary["songs"]}

    added = [current_map[sid] for sid in added_ids if sid in current_map]
    removed = [backup_map[sid] for sid in removed_ids if sid in backup_map]

    return {
        "backup": {"index": index, "time": detail["timestamp_display"], "total": detail["total_tracks"]},
        "current": {"total": current_summary["total_tracks"]},
        "added_in_current": added,
        "removed_from_backup": removed,
        "common_count": common_count,
    }


def restore_backup(
    index: int,
    playlist_path: str = PLAYLIST_FILE,
    backup_current_first: bool = True,
) -> bool:
    """
    恢复指定备份到播放列表文件
    index: 从 1 开始的序号
    backup_current_first: 恢复前先备份当前列表
    """
    meta = load_meta()
    if index < 1 or index > len(meta["backups"]):
        print(f"[错误] 无效的备份序号: {index}")
        return False

    backup_info = meta["backups"][index - 1]
    backup_path = os.path.join(BACKUP_DIR, backup_info["filename"])

    if not os.path.exists(backup_path):
        print(f"[错误] 备份文件不存在: {backup_path}")
        return False

    # 恢复前先备份当前列表
    if backup_current_first and os.path.exists(playlist_path):
        create_backup(playlist_path, reason="restore_before")

    # 执行恢复
    shutil.copy2(backup_path, playlist_path)
    print(f"[成功] 已恢复备份 #{index} ({backup_info['timestamp_display']})")
    print(f"       共 {backup_info['total_tracks']} 首歌曲")
    print(f"       请重启网易云音乐客户端以生效")
    return True


def delete_backup(index: int) -> bool:
    """删除指定的备份"""
    meta = load_meta()
    if index < 1 or index > len(meta["backups"]):
        print(f"[错误] 无效的备份序号: {index}")
        return False

    backup_info = meta["backups"].pop(index - 1)
    backup_path = os.path.join(BACKUP_DIR, backup_info["filename"])

    if os.path.exists(backup_path):
        os.remove(backup_path)

    save_meta(meta)
    print(f"[成功] 已删除备份 #{index} ({backup_info['timestamp_display']})")
    return True
