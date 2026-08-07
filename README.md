# 休息提醒器 / Break Reminder

一个跨平台的桌面休息提醒工具，帮助久坐人群定时休息、保护健康。支持 macOS 和 Windows 双平台。

A cross-platform desktop break reminder app that helps you take regular breaks. Supports both macOS and Windows.

## 功能特性 / Features

- **定时休息提醒** — 每隔设定间隔（默认 45 分钟）弹窗提醒起身活动
- **锁屏休息** — 一键锁屏进入休息状态，解锁后自动重置计时器
- **锁屏智能暂停** — 检测到系统锁屏时自动暂停计时，避免锁屏期间白白消耗工作倒计时
- **下班提醒** — 到达设定下班时间后弹出提醒，并展示今日电脑使用时长（周五还有特殊彩蛋）
- **今日使用统计** — 实时追踪当日累计电脑使用时间
- **开机自启** — 支持托盘菜单一键切换开机自动启动
- **系统托盘常驻** — 最小化到托盘后台运行，双击托盘图标恢复窗口
- **中英文切换** — 界面内置中英文双语，随时一键切换
- **单实例保护** — 防止重复启动多个实例
- **配置持久化** — 所有设置自动保存到 `~/.break_reminder_config.json`

## 截图 / Screenshots

主界面采用浅绿色渐变设计，弹窗风格统一：

| 主窗口 | 休息提醒弹窗 | 下班提醒弹窗 |
|--------|-------------|-------------|
| 显示工作倒计时、今日使用时长，可调整提醒间隔和下班时间 | 提供"锁屏休息"和"继续工作"两个选项 | 展示今日使用时长，周五显示周末专属文案 |

## 文件结构 / Project Structure

```
Break_reminder/
├── break_reminder_macos.py      # macOS 版本
├── break_reminder_windows.py    # Windows 版本
├── LICENSE                      # MIT 许可证
└── README.md
```

## 平台差异 / Platform Differences

两个版本功能一致，主要差异在于底层系统 API 的实现方式：

| 特性 | macOS 版本 | Windows 版本 |
|------|-----------|-------------|
| GUI 框架 | PyQt5 | PyQt5 |
| 锁屏检测 | `log stream` 监控 loginwindow 日志 | WTS 会话通知 + 轮询备用 |
| 锁屏操作 | `CGSession -suspend` | `user32.LockWorkStation()` |
| 开机自启 | LaunchAgent (plist) | 注册表 (HKCU\...\Run) |
| 单实例检测 | PID 文件 + 进程名校验 | Windows 互斥体 (Mutex) |
| 系统字体 | PingFang SC | Microsoft YaHei |
| 窗口尺寸 | 460x320 | 750x400 |

## 安装与运行 / Installation & Usage

### 依赖 / Dependencies

```bash
pip install PyQt5
```

> Windows 版可选安装 `psutil` 以增强单实例检测的可靠性。

### 直接运行 / Run Directly

```bash
# macOS
python3 break_reminder_macos.py

# Windows
python break_reminder_windows.py
```

### 命令行参数 / CLI Arguments

```bash
# 查看当前配置
python break_reminder_macos.py -s

# 设置提醒间隔（分钟）
python break_reminder_macos.py --interval 30
```

### 打包为可执行文件 / Build Executable

使用 PyInstaller 打包（仓库未附带 `.spec` 配置，直接用命令行参数打包即可）：

```bash
pip install pyinstaller

# macOS
pyinstaller --onefile --windowed --name BreakReminder break_reminder_macos.py

# Windows
pyinstaller --onefile --windowed --name BreakReminder break_reminder_windows.py
```

打包产物在 `dist/` 目录下。如需自定义图标或隐藏控制台，可自行添加 `--icon` 等参数。

## 配置说明 / Configuration

配置文件位于 `~/.break_reminder_config.json`，首次运行自动创建。

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `remind_interval_minutes` | 45 | 提醒间隔（分钟） |
| `auto_start` | false | 开机自启（实际状态由系统机制决定） |
| `off_work_time` | "17:30" | 下班时间（HH:mm） |
| `language` | "zh" | 界面语言（"zh" / "en"） |

## 使用方式 / Usage

1. 启动后程序自动最小化到系统托盘
2. 双击托盘图标（时钟形状）打开主窗口
3. 在主窗口中可调整提醒间隔和下班时间
4. 右键托盘图标可：显示窗口 / 切换开机自启 / 退出
5. 到达提醒间隔后弹出休息提醒，可选择"锁屏休息"或"继续工作"
6. 到达下班时间后弹出下班提醒

## 许可证 / License

[MIT License](LICENSE)

## 技术栈 / Tech Stack

- Python 3
- PyQt5
- macOS: LaunchAgent / log stream / CGSession
- Windows: WTS API / Win32 Registry / Mutex
