"""
网易云音乐播放列表备份工具 - CLI 主程序
支持: 监控、手动备份、列表、详情、对比、恢复、删除
"""

import sys
import os
import argparse
from datetime import datetime

from backup_manager import (
    create_backup,
    list_backups,
    get_backup_detail,
    compare_backups,
    compare_with_current,
    restore_backup,
    delete_backup,
    PLAYLIST_FILE,
)


def print_header():
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║       网易云音乐 播放列表备份工具 v1.0                  ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()


def cmd_watch(args):
    """启动文件监控守护程序"""
    from watcher import start_watcher
    start_watcher(args.playlist)


def cmd_backup(args):
    """手动创建备份"""
    result = create_backup(args.playlist, reason="manual", force=args.force)
    if result:
        print(f"✅ 备份成功!")
        print(f"   文件: {result['filename']}")
        print(f"   时间: {result['timestamp_display']}")
        print(f"   歌曲数: {result['total_tracks']}")
        if result['first_5']:
            print(f"   前几首: {' | '.join(result['first_5'][:3])}")
    else:
        print("ℹ️  播放列表内容未发生变化，跳过备份 (使用 --force 强制备份)")


def cmd_list(args):
    """列出所有备份"""
    backups = list_backups()
    if not backups:
        print("📭 暂无备份记录")
        print("   使用 'python main.py watch' 启动自动监控")
        print("   或使用 'python main.py backup' 手动备份")
        return

    print(f"📋 共有 {len(backups)} 个备份:\n")
    print(f"{'序号':>4}  {'时间':<20} {'歌曲数':>6}  {'来源':<6}  {'前几首歌曲'}")
    print("─" * 80)

    for i, b in enumerate(backups, 1):
        reason_map = {"auto": "自动", "manual": "手动", "restore_before": "恢复前"}
        reason = reason_map.get(b.get("reason", ""), b.get("reason", ""))
        first_songs = " | ".join(b.get("first_5", [])[:2])
        if len(b.get("first_5", [])) > 2:
            first_songs += " ..."

        print(f"  {i:>2}.  {b['timestamp_display']:<20} {b['total_tracks']:>4}首  [{reason:<4}]  {first_songs}")

    print()
    print("💡 提示: 使用 'python main.py detail <序号>' 查看详情")
    print("         使用 'python main.py restore <序号>' 恢复备份")


def cmd_detail(args):
    """查看某个备份的详细内容"""
    detail = get_backup_detail(args.index)
    if not detail:
        print(f"❌ 备份 #{args.index} 不存在")
        return

    reason_map = {"auto": "自动备份", "manual": "手动备份", "restore_before": "恢复前备份"}
    reason = reason_map.get(detail.get("reason", ""), detail.get("reason", ""))

    print(f"📄 备份 #{args.index} 详情")
    print(f"   时间:   {detail['timestamp_display']}")
    print(f"   类型:   {reason}")
    print(f"   歌曲数: {detail['total_tracks']}")
    if detail.get("source"):
        print(f"   来源:   {detail['source']}")
    print(f"   文件:   {detail['filename']}")
    print(f"   哈希:   {detail.get('hash', 'N/A')}")
    print()

    songs = detail.get("songs", [])
    if args.full:
        print(f"🎵 完整歌曲列表 ({len(songs)} 首):\n")
        for j, s in enumerate(songs, 1):
            print(f"  {j:>4}. {s['name']} - {s['artist']}")
    else:
        print(f"🎵 歌曲列表 (前 20 首，共 {len(songs)} 首):\n")
        for j, s in enumerate(songs[:20], 1):
            print(f"  {j:>4}. {s['name']} - {s['artist']}")
        if len(songs) > 20:
            print(f"\n  ... 还有 {len(songs) - 20} 首歌曲")
            print(f"  使用 'python main.py detail {args.index} --full' 查看全部")


def cmd_compare(args):
    """对比两个备份"""
    if args.current:
        # 与当前播放列表对比
        result = compare_with_current(args.index1, args.playlist)
        if not result:
            print("❌ 对比失败，请检查备份序号是否正确")
            return

        print(f"🔍 备份 #{args.index1} vs 当前播放列表\n")
        print(f"   备份:   {result['backup']['time']} ({result['backup']['total']} 首)")
        print(f"   当前:   {result['current']['total']} 首")
        print(f"   共同:   {result['common_count']} 首")
        print()

        added = result["added_in_current"]
        removed = result["removed_from_backup"]

        if added:
            print(f"   ➕ 当前新增 {len(added)} 首:")
            for s in added[:15]:
                print(f"      + {s['name']} - {s['artist']}")
            if len(added) > 15:
                print(f"      ... 还有 {len(added) - 15} 首")
            print()

        if removed:
            print(f"   ➖ 当前缺少 {len(removed)} 首 (备份中有):")
            for s in removed[:15]:
                print(f"      - {s['name']} - {s['artist']}")
            if len(removed) > 15:
                print(f"      ... 还有 {len(removed) - 15} 首")
            print()

        if not added and not removed:
            print("   ✅ 两者完全一致")
    else:
        # 对比两个备份
        if not args.index2:
            print("❌ 请指定第二个备份序号，或使用 --current 与当前列表对比")
            return

        result = compare_backups(args.index1, args.index2)
        if not result:
            print("❌ 对比失败，请检查备份序号是否正确")
            return

        b1 = result["backup1"]
        b2 = result["backup2"]
        print(f"🔍 备份 #{b1['index']} vs 备份 #{b2['index']}\n")
        print(f"   备份1: {b1['time']} ({b1['total']} 首)")
        print(f"   备份2: {b2['time']} ({b2['total']} 首)")
        print(f"   共同:  {result['common_count']} 首")
        print()

        if result["added"]:
            print(f"   ➕ 备份2 新增 {len(result['added'])} 首:")
            for s in result["added"][:15]:
                print(f"      + {s['name']} - {s['artist']}")
            if len(result["added"]) > 15:
                print(f"      ... 还有 {len(result['added']) - 15} 首")
            print()

        if result["removed"]:
            print(f"   ➖ 备份2 缺少 {len(result['removed'])} 首:")
            for s in result["removed"][:15]:
                print(f"      - {s['name']} - {s['artist']}")
            if len(result["removed"]) > 15:
                print(f"      ... 还有 {len(result['removed']) - 15} 首")
            print()

        if not result["added"] and not result["removed"]:
            print("   ✅ 两者完全一致")


def cmd_restore(args):
    """恢复备份"""
    detail = get_backup_detail(args.index)
    if not detail:
        print(f"❌ 备份 #{args.index} 不存在")
        return

    reason_map = {"auto": "自动备份", "manual": "手动备份", "restore_before": "恢复前备份"}
    reason = reason_map.get(detail.get("reason", ""), detail.get("reason", ""))

    print(f"⚠️  即将恢复备份 #{args.index}:")
    print(f"   时间:   {detail['timestamp_display']}")
    print(f"   歌曲数: {detail['total_tracks']}")
    print(f"   类型:   {reason}")
    if detail.get("first_5"):
        print(f"   前几首: {' | '.join(detail['first_5'][:3])}")
    print()
    print(f"   恢复前会自动备份当前播放列表")
    print(f"   恢复后请重启网易云音乐客户端")
    print()

    if not args.yes:
        confirm = input("确认恢复? (y/N): ").strip().lower()
        if confirm not in ("y", "yes"):
            print("已取消")
            return

    success = restore_backup(args.index, args.playlist)
    if success:
        print()
        print("💡 请关闭并重新打开网易云音乐客户端以加载恢复的播放列表")


def cmd_delete(args):
    """删除备份"""
    detail = get_backup_detail(args.index)
    if not detail:
        print(f"❌ 备份 #{args.index} 不存在")
        return

    print(f"⚠️  即将删除备份 #{args.index}:")
    print(f"   时间:   {detail['timestamp_display']}")
    print(f"   歌曲数: {detail['total_tracks']}")

    if not args.yes:
        confirm = input("确认删除? (y/N): ").strip().lower()
        if confirm not in ("y", "yes"):
            print("已取消")
            return

    delete_backup(args.index)


def main():
    parser = argparse.ArgumentParser(
        prog="CloudMusic Playlist Backup",
        description="网易云音乐播放列表备份工具 - 自动监控、备份、恢复你的播放列表",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python main.py watch                 启动自动监控守护程序
  python main.py backup                手动创建一次备份
  python main.py list                  列出所有备份
  python main.py detail 3              查看第 3 个备份的详情
  python main.py detail 3 --full       查看完整歌曲列表
  python main.py compare 2 5           对比第 2 和第 5 个备份
  python main.py compare 3 --current   将第 3 个备份与当前列表对比
  python main.py restore 3             恢复第 3 个备份
  python main.py delete 5              删除第 5 个备份
        """,
    )

    parser.add_argument(
        "--playlist",
        default=PLAYLIST_FILE,
        help="播放列表文件路径 (默认: 网易云音乐默认位置)",
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # watch
    p_watch = subparsers.add_parser("watch", help="启动自动监控守护程序")

    # backup
    p_backup = subparsers.add_parser("backup", help="手动创建一次备份")
    p_backup.add_argument("--force", action="store_true", help="强制备份（即使内容未变化）")

    # list
    p_list = subparsers.add_parser("list", help="列出所有备份")

    # detail
    p_detail = subparsers.add_parser("detail", help="查看备份详情")
    p_detail.add_argument("index", type=int, help="备份序号")
    p_detail.add_argument("--full", action="store_true", help="显示完整歌曲列表")

    # compare
    p_compare = subparsers.add_parser("compare", help="对比备份差异")
    p_compare.add_argument("index1", type=int, help="备份序号 1")
    p_compare.add_argument("index2", type=int, nargs="?", help="备份序号 2 (不填则使用 --current)")
    p_compare.add_argument("--current", action="store_true", help="与当前播放列表对比")

    # restore
    p_restore = subparsers.add_parser("restore", help="恢复备份")
    p_restore.add_argument("index", type=int, help="要恢复的备份序号")
    p_restore.add_argument("-y", "--yes", action="store_true", help="跳过确认提示")

    # delete
    p_delete = subparsers.add_parser("delete", help="删除备份")
    p_delete.add_argument("index", type=int, help="要删除的备份序号")
    p_delete.add_argument("-y", "--yes", action="store_true", help="跳过确认提示")

    args = parser.parse_args()

    if not args.command:
        print_header()
        parser.print_help()
        return

    cmd_map = {
        "watch": cmd_watch,
        "backup": cmd_backup,
        "list": cmd_list,
        "detail": cmd_detail,
        "compare": cmd_compare,
        "restore": cmd_restore,
        "delete": cmd_delete,
    }

    print_header()
    cmd_map[args.command](args)


if __name__ == "__main__":
    main()
