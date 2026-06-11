# 休息提醒器 (Break Reminder)

一款跨平台的休息提醒工具，帮助您定时休息，保护颈椎、腰椎健康。支持 **macOS** 和 **Windows** 双平台。

<div align="center">

[![macOS](https://img.shields.io/badge/macOS-10.14%2B-blue?logo=apple)](https://github.com/ImXinzang/Break_reminder/)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-blue?logo=windows)](https://github.com/ImXinzang/Break_reminder/)
[![Python](https://img.shields.io/badge/Python-3.8%2B-yellow?logo=python)](https://www.python.org/)
[![PyQt5](https://img.shields.io/badge/PyQt5-5.15%2B-green)](https://www.riverbankcomputing.com/software/pyqt/)
[![License](https://img.shields.io/badge/License-MIT-red)](LICENSE)

[功能特点](#功能特点) • [平台版本](#平台版本) • [安装运行](#安装运行) • [配置说明](#配置说明) • [常见问题](#常见问题)

</div>

---

## ✨ 功能特点

| 功能 | 描述 |
|-----|------|
| ⏰ **定时提醒** | 可自定义提醒间隔（默认45分钟） |
| 🏠 **下班提醒** | 可设置下班时间，到点自动提醒 |
| 📊 **今日统计** | 显示今日使用电脑时长 |
| 🌐 **中英文切换** | 支持中文/英文界面 |
| 🔒 **锁屏检测** | 锁屏时暂停计时，解锁后继续 |
| 💾 **系统托盘** | 最小化到系统托盘，后台运行 |
| 🚀 **开机自启** | 通过托盘菜单一键设置/取消开机自启动 |
| 🎨 **精美界面** | 渐变绿色主题，护眼设计 |

---

## 🖥️ 平台版本

### macOS 版本

| 项目 | 说明 |
|-----|------|
| **主文件** | `break_reminder.py` |
| **锁屏检测** | 实时监控 `log stream` 系统日志 |
| **锁屏函数** | `CGSession -suspend` |
| **单实例检测** | PID 文件 + `os.kill(pid, 0)` |
| **开机自启** | launchctl + plist 文件 |
| **默认字体** | PingFang SC (苹方) |
| **后台运行** | 自动检测 `pythonw` |

### Windows 版本

| 项目 | 说明 |
|-----|------|
| **主文件** | `break_reminder_windows.py` |
| **锁屏检测** | WTS 会话通知 + 轮询备用 |
| **锁屏函数** | `LockWorkStation()` API |
| **单实例检测** | Windows 互斥体 `CreateMutexW` |
| **开机自启** | 注册表 |
| **默认字体** | Microsoft YaHei (微软雅黑) |
| **打包工具** | PyInstaller |

---

## 🚀 安装运行

### 先决条件

- **Python 3.8+** (推荐 3.14)
- **PyQt5**

---

### macOS

#### 1. 安装依赖

```bash
pip3 install PyQt5
```

#### 2. 运行程序

```bash
# 直接运行（使用默认配置）
python3 /path/to/break_reminder.py

# 设置提醒间隔（1分钟，用于测试）
python3 break_reminder.py --interval 1

# 显示当前配置
python3 break_reminder.py -s
```

#### 3. 后台运行（可选）

```bash
pythonw break_reminder.py
```

#### 4. 设置开机自启动

1. 运行程序后，右键点击托盘图标
2. 勾选 **"开机自动启动"**
3. 程序会自动创建 LaunchAgent 配置

---

### Windows

#### 1. 安装依赖

```bash
pip install PyQt5
```

#### 2. 运行程序

```bash
# 直接运行
python break_reminder_windows.py

# 设置提醒间隔（1分钟，用于测试）
python break_reminder_windows.py --interval 1

# 显示当前配置
python break_reminder_windows.py -s
```

#### 3. 打包为 .exe（可选）

```bash
pip install pyinstaller
python build_windows.py
```

生成的可执行文件位于 `dist/BreakReminder.exe`

---

## 📝 命令行参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `-s, --show` | 显示当前配置 | `python3 break_reminder.py -s` |
| `--interval` | 设置提醒间隔（分钟） | `python3 break_reminder.py --interval 45` |

**使用示例：**

```bash
# macOS
python3 break_reminder.py --interval 30

# Windows
python break_reminder_windows.py --interval 30
```

---

## ⚙️ 配置说明

配置文件保存在用户主目录：

| 平台 | 路径 |
|-----|------|
| macOS | `~/.break_reminder_config.json` |
| Windows | `~\.break_reminder_config.json` |

### 配置项

```json
{
  "remind_interval_minutes": 45,
  "auto_start": false,
  "off_work_time": "17:30",
  "language": "zh"
}
```

| 参数 | 说明 | 默认值 | 可选值 |
|------|------|--------|--------|
| `remind_interval_minutes` | 提醒间隔（分钟） | 45 | 1-180 |
| `auto_start` | 开机自启动 | false | true/false |
| `off_work_time` | 下班时间 | "17:30" | 格式：HH:MM |
| `language` | 界面语言 | "zh" | "zh" / "en" |

---

## 📊 工作流程

```
用户登录 → 自动启动 / 手动运行程序
                    ↓
         检查单实例（防止重复启动）
                    ↓
                后台运行
                    ↓
         等待提醒间隔（默认45分钟）
                    ↓
        弹出休息提醒窗口（置顶显示）
        "您已连续工作了XX小时XX分钟"
                    ↓
          ┌─────────┴─────────┐
          ↓                   ↓
    "锁屏休息"            "继续工作"
          ↓                   ↓
      锁定屏幕            重置计时器
          ↓
    暂停计时，等待解锁
          ↓
    解锁后自动重置计时器
```

---

## 🔒 锁屏检测机制

### macOS

使用 `log stream --predicate 'process == "loginwindow"'` 实时监控系统日志：

| 事件 | 关键字 |
|-----|--------|
| 锁屏 | `going inactive, create activity semaphore` |
| 解锁 | `closing and releasing _screenLockWindowController` |

**优点**：事件驱动，毫秒级响应，零CPU占用

### Windows

优先使用 `WTSRegisterSessionNotification` 注册会话通知：

| 事件 | 消息值 |
|-----|--------|
| 锁屏 | `WTS_SESSION_LOCK (7)` |
| 解锁 | `WTS_SESSION_UNLOCK (8)` |

如果注册失败，自动回退到轮询模式（每2秒检测一次）。

**优点**：系统级通知，100%可靠，毫秒级响应

---

## 🖼️ 界面说明

### 主窗口

| 元素 | 说明 |
|-----|------|
| 状态显示 | 工作中 - 剩余 XX:XX |
| 今日使用 | 显示今日累计使用电脑时长 |
| 提醒间隔 | 可调整提醒时间间隔（1-180分钟） |
| 下班时间 | 设置下班时间（格式：HH : MM） |
| 语言切换 | 点击右上角"EN/中"切换语言 |
| 最小化按钮 | 隐藏窗口到托盘 |

### 休息提醒弹窗

- 屏幕中央置顶显示
- 显示连续工作时长
- **锁屏休息**：锁定屏幕并暂停计时
- **继续工作**：重置计时器继续工作

### 下班提醒弹窗

- 到达下班时间后自动弹出
- 显示今日使用电脑总时长
- 点击"知道了"关闭

### 系统托盘

- 绿色时钟图标
- 右键菜单：
  - 显示窗口
  - 开机自动启动（可勾选）
  - 退出
- 双击：显示主窗口

---

## 📁 文件结构

```
Break_reminder/
├── break_reminder.py              # macOS 主脚本
├── break_reminder_windows.py      # Windows 主脚本
└── README.md                      # 本文档

macOS 自动生成的文件：
~/Library/LaunchAgents/
└── com.user.breakreminder.plist   # 开机自启配置
~/.break_reminder_config.json      # 用户配置
~/.break_reminder.pid              # 进程ID文件

Windows 自动生成的文件：
~\.break_reminder_config.json      # 用户配置
dist/
└── BreakReminder.exe              # 打包后的可执行文件
```

---

## ❓ 常见问题

### Q: 程序启动后没有显示窗口？

A: 这是正常的。程序启动后会在后台运行，只在系统托盘显示图标。双击托盘图标可以显示主窗口。

### Q: 如何测试提醒功能？

A: 使用命令行参数设置短间隔：

```bash
# macOS
python3 break_reminder.py --interval 1

# Windows
python break_reminder_windows.py --interval 1
```

### Q: 锁屏后计时还在继续吗？

A: 锁屏时计时会暂停，状态显示"🔒 已锁屏 - 计时暂停"，解锁后自动继续。

### Q: 如何完全退出程序？

A: 右键点击托盘图标 → 选择"退出"。

### Q: 托盘图标不显示？

A: 请确保系统托盘区域有足够空间，或检查系统设置中的通知设置。

### Q: 下班时间格式是什么？

A: 格式为 `HH : MM`，例如 `17 : 30` 表示下午5:30。

### Q: 如何切换语言？

A: 点击主窗口右上角的"EN"或"中"按钮切换中英文界面。

### Q: macOS 开机自启不生效？

A: 请检查：
1. LaunchAgent 配置文件是否存在：`~/Library/LaunchAgents/com.user.breakreminder.plist`
2. 使用 `launchctl list | grep break` 检查是否已加载
3. 查看系统日志获取更多信息

### Q: Windows 锁屏检测不工作？

A: 程序会自动检测：
1. 优先使用 WTS 会话通知（推荐，毫秒级响应）
2. 如果注册失败，自动回退到轮询模式
3. 轮询模式每2秒检测一次锁屏状态

---

## 🛠️ 技术实现

### 技术栈

- **Python 3.14**
- **PyQt5** - GUI 框架
- **macOS**: log stream / LaunchAgent
- **Windows**: WTS API / 注册表

### 核心类结构

```
MainWindow (主窗口)
├── ScreenLockMonitor (锁屏监控)
│   ├── WTS 会话通知 (Windows)
│   └── 轮询检测 (备用)
├── ReminderDialog (休息提醒弹窗)
├── OffWorkDialog (下班提醒弹窗)
└── SystemTray (系统托盘)
```

### 平台差异对比

| 功能 | macOS | Windows |
|-----|-------|---------|
| 锁屏检测 | `log stream` 实时监控 | `WTSRegisterSessionNotification` + 轮询备用 |
| 锁屏函数 | `CGSession -suspend` | `LockWorkStation()` API |
| 单实例检测 | PID 文件 + `os.kill` | Windows 互斥体 |
| 开机自启 | launchctl + plist | 注册表 |
| 默认字体 | PingFang SC | Microsoft YaHei |
| 后台运行 | `pythonw` | PyInstaller `--windowed` |

---

## 📜 许可证

MIT License

---

## 👤 作者

休息提醒器 - 保护您的健康，从定时休息开始！

**GitHub**: [ImXinzang/Break_reminder](https://github.com/ImXinzang/Break_reminder/)

---

<div align="center">

⭐ 如果这个项目对您有帮助，请给个 Star！

</div>
