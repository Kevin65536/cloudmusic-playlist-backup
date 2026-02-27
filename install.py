"""
安装/卸载开机自启动
在 Windows 启动目录中创建 VBS 脚本，实现静默启动守护进程
"""

import os
import sys
import subprocess
import argparse


STARTUP_DIR = os.path.join(
    os.environ["APPDATA"],
    "Microsoft", "Windows", "Start Menu", "Programs", "Startup",
)
VBS_FILENAME = "CloudMusicPlaylistBackup.vbs"
VBS_PATH = os.path.join(STARTUP_DIR, VBS_FILENAME)

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DAEMON_SCRIPT = os.path.join(PROJECT_DIR, "daemon.py")


def get_pythonw_path() -> str:
    """获取 pythonw.exe 路径"""
    python_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(python_dir, "pythonw.exe")
    if os.path.exists(pythonw):
        return pythonw
    # 如果找不到 pythonw，退回到 python
    return sys.executable


def install():
    """安装开机自启动"""
    pythonw = get_pythonw_path()

    # 创建 VBS 启动脚本（静默启动，无窗口）
    vbs_content = (
        f'Set WshShell = CreateObject("WScript.Shell")\n'
        f'WshShell.CurrentDirectory = "{PROJECT_DIR}"\n'
        f'WshShell.Run """{pythonw}"" ""{DAEMON_SCRIPT}""", 0, False\n'
    )

    with open(VBS_PATH, "w", encoding="utf-8") as f:
        f.write(vbs_content)

    print("✅ 开机自启动已安装!")
    print()
    print(f"   启动脚本: {VBS_PATH}")
    print(f"   Python:   {pythonw}")
    print(f"   守护程序: {DAEMON_SCRIPT}")
    print()
    print("   守护进程将在下次登录时自动启动。")
    print("   现在启动守护进程? ", end="")

    answer = input("(Y/n): ").strip().lower()
    if answer in ("", "y", "yes"):
        start_daemon(pythonw)


def uninstall():
    """卸载开机自启动"""
    if os.path.exists(VBS_PATH):
        os.remove(VBS_PATH)
        print("✅ 开机自启动已卸载!")
        print(f"   已删除: {VBS_PATH}")
    else:
        print("ℹ️  开机自启动未安装，无需卸载")

    # 尝试终止正在运行的守护进程
    print()
    print("   是否同时终止正在运行的守护进程? ", end="")
    answer = input("(y/N): ").strip().lower()
    if answer in ("y", "yes"):
        stop_daemon()


def status():
    """查看安装状态"""
    installed = os.path.exists(VBS_PATH)
    print(f"   开机自启动: {'✅ 已安装' if installed else '❌ 未安装'}")
    if installed:
        print(f"   启动脚本:   {VBS_PATH}")

    # 检查守护进程是否在运行
    running = is_daemon_running()
    print(f"   守护进程:   {'✅ 运行中' if running else '⚪ 未运行'}")


def start_daemon(pythonw: str = None):
    """立即启动守护进程"""
    if is_daemon_running():
        print("   守护进程已在运行中")
        return

    if pythonw is None:
        pythonw = get_pythonw_path()

    subprocess.Popen(
        [pythonw, DAEMON_SCRIPT],
        cwd=PROJECT_DIR,
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
    )
    print("   ✅ 守护进程已启动!")
    print("   当网易云音乐启动时将自动开始监控播放列表。")


def stop_daemon():
    """终止守护进程"""
    try:
        # 查找并终止 pythonw.exe 运行的 daemon.py
        result = subprocess.run(
            [
                "wmic", "process", "where",
                f"commandline like '%daemon.py%' and name='pythonw.exe'",
                "get", "processid",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        pids = [
            line.strip()
            for line in result.stdout.strip().split("\n")
            if line.strip().isdigit()
        ]

        if pids:
            for pid in pids:
                subprocess.run(
                    ["taskkill", "/PID", pid, "/F"],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            print(f"   ✅ 已终止守护进程 (PID: {', '.join(pids)})")
        else:
            print("   ⚪ 未找到运行中的守护进程")
    except Exception as e:
        print(f"   ❌ 终止失败: {e}")


def is_daemon_running() -> bool:
    """检查守护进程是否在运行"""
    try:
        result = subprocess.run(
            [
                "wmic", "process", "where",
                f"commandline like '%daemon.py%' and name='pythonw.exe'",
                "get", "processid",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        pids = [
            line.strip()
            for line in result.stdout.strip().split("\n")
            if line.strip().isdigit()
        ]
        return len(pids) > 0
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(
        description="管理播放列表备份守护进程的开机自启动",
    )
    subparsers = parser.add_subparsers(dest="action")

    subparsers.add_parser("install", help="安装开机自启动")
    subparsers.add_parser("uninstall", help="卸载开机自启动")
    subparsers.add_parser("status", help="查看安装状态")
    subparsers.add_parser("start", help="立即启动守护进程")
    subparsers.add_parser("stop", help="终止守护进程")

    args = parser.parse_args()

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║       网易云音乐 播放列表备份 - 自启动管理              ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    if args.action == "install":
        install()
    elif args.action == "uninstall":
        uninstall()
    elif args.action == "status":
        status()
    elif args.action == "start":
        start_daemon()
    elif args.action == "stop":
        stop_daemon()
    else:
        status()
        print()
        print("  用法:")
        print("    python install.py install    安装开机自启动")
        print("    python install.py uninstall  卸载开机自启动")
        print("    python install.py status     查看状态")
        print("    python install.py start      立即启动守护进程")
        print("    python install.py stop       终止守护进程")


if __name__ == "__main__":
    main()
