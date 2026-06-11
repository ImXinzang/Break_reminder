# 休息提醒器 (Break Reminder)

一款专为 macOS 设计的休息提醒工具，帮助您定时休息，保护颈椎、腰椎健康。

## 功能特点

- ⏰ **定时提醒** - 可自定义提醒间隔（默认45分钟）
- 🏠 **下班提醒** - 可设置下班时间，到点自动提醒
- 📊 **今日统计** - 显示今日使用电脑时长
- 🌐 **中英文切换** - 支持中文/英文界面
- 🔒 **锁屏检测** - 锁屏时暂停计时，解锁后继续
- 💾 **系统托盘** - 最小化到系统托盘，后台运行
- 🚀 **开机自启** - 通过托盘菜单一键设置/取消开机自启动

## 系统要求

- macOS 10.14 或更高版本
- Python 3.8+ (推荐使用 Python 3.14)
- PyQt5

## 安装

### 1. 安装依赖

```bash
pip3 install PyQt5
```

### 2. 下载脚本

将 `break_reminder.py` 保存到本地目录，例如：
```
/Users/你的用户名/Health/
```

## 使用方法

### 手动运行

```bash
# 直接运行（使用默认配置）
python3 "/Users/你的用户名/Health/break_reminder.py"

# 设置提醒间隔（1分钟，用于测试）
python3 break_reminder.py --interval 1

# 显示当前配置
python3 break_reminder.py -s
```

### 设置开机自启动

1. 运行程序后，右键点击托盘图标
2. 勾选 **"开机自动启动"**
3. 程序会自动创建 LaunchAgent 配置

## 命令行参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `-s, --show` | 显示当前配置 | `-s` |
| `--interval` | 设置提醒间隔（分钟） | `--interval 45` |

## 工作流程

```
用户登录 → LaunchAgent 自动启动 → 启动Python脚本
                                        ↓
                              检查是否已有进程（防止重复启动）
                                        ↓
                                      后台运行
                                        ↓
                                等待提醒间隔（默认45分钟）
                                        ↓
                          弹出休息提醒窗口（置顶显示）
                          "您已连续工作了XX小时XX分钟"
                                        ↓
                          ┌─────────────┴─────────────┐
                          ↓                           ↓
                    "锁屏休息"                    "继续工作"
                          ↓                           ↓
                      锁定屏幕                   重置计时器
                          ↓
                  暂停计时，等解锁
                          ↓
                  解锁后自动重置计时器
```

## 锁屏处理

- **锁屏时**：暂停计时，状态显示"🔒 已锁屏 - 计时暂停"
- **解锁后**：自动继续计时，重置工作周期

## 界面说明

### 主窗口

- **状态显示**：工作中 - 剩余 XX:XX
- **今日使用**：显示今日累计使用电脑时长
- **提醒间隔**：可调整提醒时间间隔
- **下班时间**：设置下班时间（格式：HH : MM）
- **语言切换**：点击右上角"EN/中"切换语言
- **最小化按钮**：隐藏窗口到托盘

### 休息提醒弹窗

- 屏幕中央置顶显示
- 显示连续工作时长
- **锁屏休息**：锁定屏幕并暂停计时
- **继续工作**：重置计时器继续工作

### 下班提醒弹窗

- 到达下班时间后自动弹出
- 显示今日使用电脑总时长

### 系统托盘

- 绿色时钟图标
- 右键菜单：
  - 显示窗口
  - 开机自动启动（可勾选）
  - 退出
- 双击：显示主窗口

## 配置文件

配置文件保存在：`~/.break_reminder_config.json`

```json
{
  "remind_interval_minutes": 45,
  "auto_start": false,
  "off_work_time": "17:30",
  "language": "zh"
}
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `remind_interval_minutes` | 提醒间隔（分钟） | 45 |
| `auto_start` | 开机自启动 | false |
| `off_work_time` | 下班时间 | "17:30" |
| `language` | 界面语言（zh/en） | "zh" |

## 文件结构

```
Health/
├── break_reminder.py                    # 主脚本
└── README.md                            # 本文档

自动生成的文件：
~/Library/LaunchAgents/
└── com.user.breakreminder.plist         # 开机自启配置

~/.break_reminder_config.json            # 用户配置
~/.break_reminder.pid                    # 进程ID文件
/tmp/break_reminder.log                  # 运行日志
/tmp/break_reminder.err                  # 错误日志
```

## 常见问题

### Q: 程序启动后没有显示窗口？

A: 这是正常的。程序启动后会在后台运行，只在系统托盘显示图标。双击托盘图标可以显示主窗口。

### Q: 如何测试提醒功能？

A: 使用命令行参数设置短间隔：
```bash
python3 break_reminder.py --interval 1
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

## 技术实现

### 锁屏检测

通过 macOS 的 `log stream` 命令实时监控 `loginwindow` 进程日志：
- 锁屏关键字：`going inactive, create activity semaphore`
- 解锁关键字：`closing and releasing _screenLockWindowController`

### 开机自启动

通过 macOS LaunchAgent 实现：
- 配置文件：`~/Library/LaunchAgents/com.user.breakreminder.plist`
- 支持通过托盘菜单一键启用/禁用

### 单实例运行

通过 PID 文件确保只有一个实例运行：
- PID 文件：`~/.break_reminder.pid`

## 技术栈

- Python 3.14
- PyQt5
- macOS log stream / LaunchAgent

## 许可证

MIT License

## 作者

休息提醒器 - 保护您的健康，从定时休息开始！
