# 网易云音乐播放列表备份工具

解决网易云音乐 Windows 客户端没有播放列表历史记录功能的痛点。  
当你不小心点了一首歌导致播放列表被替换时，可以轻松恢复之前的列表。

## 功能

- **自动监控**: 后台监控播放列表文件变化，自动创建备份
- **手动备份**: 随时手动创建备份快照
- **智能去重**: 内容未变化时自动跳过，不浪费空间
- **查看详情**: 查看任意备份中的完整歌曲列表
- **差异对比**: 对比两个备份或备份与当前列表的差异
- **一键恢复**: 恢复任意历史备份，恢复前自动保护当前列表
- **最多保留 100 个备份**，自动清理最旧的

## 快速开始

### 方式一：双击 bat 文件

| 文件 | 用途 |
|------|------|
| `启动监控.bat` | 启动后台监控，播放列表变化时自动备份 |
| `手动备份.bat` | 立即创建一个备份 |
| `查看备份.bat` | 列出所有备份 |

### 方式二：命令行

```bash
# 启动自动监控（推荐长期运行）
python main.py watch

# 手动备份
python main.py backup
python main.py backup --force    # 强制备份（即使内容未变化）

# 列出所有备份
python main.py list

# 查看备份详情
python main.py detail 3           # 查看第 3 个备份（前 20 首）
python main.py detail 3 --full    # 查看完整歌曲列表

# 对比差异
python main.py compare 2 5        # 对比第 2 和第 5 个备份
python main.py compare 3 --current  # 将第 3 个备份与当前播放列表对比

# 恢复备份
python main.py restore 3          # 恢复第 3 个备份（会先自动备份当前列表）
python main.py restore 3 -y       # 跳过确认提示

# 删除备份
python main.py delete 5
```

## 典型使用场景

1. **日常防护**: 双击 `启动监控.bat`，最小化窗口让它在后台运行
2. **播放列表被覆盖了**: 
   - 运行 `python main.py list` 找到你想恢复的备份
   - 运行 `python main.py compare 5 --current` 确认差异
   - 运行 `python main.py restore 5` 恢复
   - 关闭并重新打开网易云音乐客户端

## 依赖

- Python 3.6+
- watchdog (`pip install watchdog`)

## 文件说明

```
CloudMusic Playlist/
├── main.py              # CLI 主程序入口
├── backup_manager.py    # 备份管理核心逻辑
├── watcher.py           # 文件变化监控模块
├── 启动监控.bat          # 快捷启动监控
├── 手动备份.bat          # 快捷手动备份
├── 查看备份.bat          # 快捷查看备份列表
├── backups/             # 备份文件存放目录（自动创建）
│   ├── backup_meta.json # 备份元数据索引
│   └── playlist_*.json  # 各个备份文件
└── logs/                # 日志目录（自动创建）
    └── watcher.log      # 监控日志
```

## 注意事项

- 恢复备份后需要**重启网易云音乐客户端**才能生效
- 监控程序运行时不影响网易云音乐的正常使用
- 备份文件保存在工具目录下的 `backups/` 文件夹中
