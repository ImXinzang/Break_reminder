#!/usr/bin/env python3
import sys
import time
import subprocess
import os
import json
import threading
import argparse
import math
import random
import re
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout,
                             QHBoxLayout, QPushButton, QSystemTrayIcon,
                             QMenu, QAction, QDialog, QSpinBox, QLineEdit,
                             QMessageBox)
from PyQt5.QtGui import QIcon, QFont, QPalette, QBrush, QPixmap, QColor, QLinearGradient, QRadialGradient, QPainter, QPen
from PyQt5.QtCore import Qt, QTimer, pyqtSignal

CONFIG_FILE = os.path.expanduser("~/.break_reminder_config.json")
PID_FILE = os.path.expanduser("~/.break_reminder.pid")
WORK_CYCLE_SECONDS = 8 * 3600  # 托盘指针满圈 = 今日累计工作 8 小时
LAUNCH_AGENT_ID = "com.user.breakreminder"
LAUNCH_AGENT_PLIST = os.path.expanduser(f"~/Library/LaunchAgents/{LAUNCH_AGENT_ID}.plist")

DEFAULT_CONFIG = {
    "remind_interval_minutes": 45,
    "auto_start": False,
    "off_work_time": "17:30",
    "language": "zh"
}

# ========= 国际化文本 =========
I18N = {
    "zh": {
        "app_title": "休息提醒器",
        "working": "工作中",
        "remaining": "剩余",
        "today_usage": "今日使用",
        "remind_interval": "提醒间隔",
        "minutes": "分钟",
        "off_work_time": "下班时间",
        "minimize": "最小化",
        "locked_pause": "🔒 已锁屏 - 计时暂停",
        "rest_title": "该休息了！",
        "rest_msg_prefix": "您已连续工作了",
        "rest_msg_suffix": "\n请起身活动，喝杯水放松一下！",
        "lock_rest": "锁屏休息",
        "continue_work": "继续工作",
        "offwork_title": "🐮牛马~下班时间到,请享受你的生活！",
        "offwork_title_friday": "牛马~下班时间到!🐮\n明天是周末哦!🎉\n现在赶紧滚回去享受你的周末生活!🎉",
        "offwork_msg_prefix": "今日使用电脑时长",
        "offwork_got_it": "知道了",
        "offwork_dialog_title": "下班提醒",
        "rest_dialog_title": "休息提醒",
        "tray_show": "显示窗口",
        "tray_auto_start": "开机自动启动",
        "tray_quit": "退出",
        "tray_minimized": "程序已最小化到托盘",
        "hours": "小时",
        "mins": "分钟",
        "lang_btn": "EN",
    },
    "en": {
        "app_title": "Break Reminder",
        "working": "Working",
        "remaining": "remaining",
        "today_usage": "Today",
        "remind_interval": "Interval",
        "minutes": "min",
        "off_work_time": "Off Work",
        "minimize": "Minimize",
        "locked_pause": "🔒 Locked - Timer Paused",
        "rest_title": "Time to Rest!",
        "rest_msg_prefix": "You've been working for ",
        "rest_msg_suffix": "\nTake a break, drink some water and relax!",
        "lock_rest": "Lock & Rest",
        "continue_work": "Keep Working",
        "offwork_title": "🐮Drudge,Off Work now!Enjoying your life!",
        "offwork_title_friday": "Drudge, Off work!🐮\nTomorrow is the weekend🎉\nGo home and enjoy it!🎉",
        "offwork_msg_prefix": "Screen time today",
        "offwork_got_it": "Got It",
        "offwork_dialog_title": "Off Work Reminder",
        "rest_dialog_title": "Break Reminder",
        "tray_show": "Show Window",
        "tray_auto_start": "Auto Start on Login",
        "tray_quit": "Quit",
        "tray_minimized": "App minimized to tray",
        "hours": "h",
        "mins": "m",
        "lang_btn": "中",
    }
}

def t(key):
    """获取当前语言的文本。"""
    lang = _current_lang
    return I18N.get(lang, I18N["zh"]).get(key, key)

_current_lang = "zh"

def set_current_lang(lang):
    global _current_lang
    _current_lang = lang

def get_current_lang():
    return _current_lang

# 通过 /usr/bin/log stream 实时监控 loginwindow 进程日志
# 锁屏: "going inactive, create activity semaphore"
# 解锁: "closing and releasing _screenLockWindowController"

DEBUG_LOCK = False  # 设为 True 可开启锁屏检测调试日志
DEBUG_TIMER = False  # 设为 True 可开启计时器调试日志（用于排查弹框问题）


def debug_lock(msg):
    """输出锁屏检测调试日志。"""
    if DEBUG_LOCK:
        print(f"[LOCK {time.strftime('%H:%M:%S')}] {msg}", flush=True)

def debug_timer(msg):
    """输出计时器调试日志。"""
    if DEBUG_TIMER:
        print(f"[TIMER {time.strftime('%H:%M:%S')}] {msg}", flush=True)


class ScreenLockMonitor:
    """通过 log stream 监控 macOS 锁屏/解锁事件。"""

    # 锁屏关键字
    LOCK_KEYWORDS = ["going inactive, create activity semaphore"]
    # 解锁关键字（最可靠）
    UNLOCK_KEYWORDS = ["closing and releasing _screenLockWindowController"]

    def __init__(self, on_lock=None, on_unlock=None):
        self.on_lock = on_lock
        self.on_unlock = on_unlock
        self._process = None
        self._thread = None
        self._running = False
        self._screen_locked = False

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        debug_lock("ScreenLockMonitor 已启动")

    def stop(self):
        self._running = False
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=3)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
        debug_lock("ScreenLockMonitor 已停止")

    def is_locked(self):
        return self._screen_locked

    def _monitor_loop(self):
        while self._running:
            try:
                debug_lock("启动 log stream 进程...")
                self._process = subprocess.Popen(
                    [
                        '/usr/bin/log', 'stream',
                        '--predicate', 'process == "loginwindow"',
                        '--info'
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    bufsize=1
                )

                for line in self._process.stdout:
                    if not self._running:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    self._parse_line(line)

            except Exception as e:
                debug_lock(f"log stream 异常: {e}")
            
            if self._running:
                debug_lock("log stream 退出，5秒后重启...")
                time.sleep(5)

    def _parse_line(self, line):
        for kw in self.UNLOCK_KEYWORDS:
            if kw in line:
                debug_lock(f"检测到解锁: {kw}")
                self._screen_locked = False
                if self.on_unlock:
                    try:
                        self.on_unlock()
                    except Exception as e:
                        debug_lock(f"解锁回调异常: {e}")
                return

        for kw in self.LOCK_KEYWORDS:
            if kw in line:
                debug_lock(f"检测到锁屏: {kw}")
                self._screen_locked = True
                if self.on_lock:
                    try:
                        self.on_lock()
                    except Exception as e:
                        debug_lock(f"锁屏回调异常: {e}")
                return


# ========= 配置管理 =========

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                return {**DEFAULT_CONFIG, **config}
        except:
            return DEFAULT_CONFIG
    return DEFAULT_CONFIG

def _is_break_reminder_process(pid):
    """检查给定 PID 是否确实是 break_reminder 进程（防止 PID 被系统进程复用）。"""
    try:
        result = subprocess.run(
            ['ps', '-p', str(pid), '-o', 'args=', '-c'],
            capture_output=True, text=True, timeout=3
        )
        args = result.stdout.strip()
        return 'break_reminder' in args
    except Exception:
        return False

def ensure_single_instance():
    """确保只有一个实例在运行。"""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                old_pid = int(f.read().strip())
            # 仅当该 PID 确实是 break_reminder 进程时才视为已运行
            if _is_break_reminder_process(old_pid):
                sys.exit(0)
        except (OSError, ValueError, ProcessLookupError):
            pass
        # PID 无效或已被其他进程占用 → 清除残留文件
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))

def cleanup_pid_file():
    try:
        os.remove(PID_FILE)
    except OSError:
        pass

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


# ========= 锁屏操作 =========

def lock_screen():
    """锁定 macOS 屏幕。"""
    try:
        subprocess.Popen(
            ['/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession', '-suspend'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception:
        try:
            subprocess.run(
                ['osascript', '-e',
                 'tell application "System Events" to keystroke "q" using {control down, command down}'],
                capture_output=True, timeout=3
            )
        except Exception:
            pass


# ========= 工具函数 =========

def format_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"

def format_duration_chinese(seconds):
    """将秒数格式化为时长描述（根据当前语言）。"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    if hours > 0 and minutes > 0:
        return f"{hours}{t('hours')}{minutes}{t('mins')}"
    elif hours > 0:
        return f"{hours}{t('hours')}"
    else:
        return f"{minutes}{t('mins')}"

def center_widget(widget):
    screen = QApplication.primaryScreen()
    if screen is None:
        return
    geo = screen.availableGeometry()
    widget.move(
        (geo.width() - widget.width()) // 2,
        (geo.height() - widget.height()) // 2
    )

def apply_green_gradient(widget, width, height):
    """为窗口/弹窗应用统一的浅绿色渐变背景（主窗与两个弹窗共用）。"""
    palette = widget.palette()
    gradient = QLinearGradient(0, 0, width, height)
    gradient.setColorAt(0, QColor(232, 245, 233))
    gradient.setColorAt(0.5, QColor(220, 237, 200))
    gradient.setColorAt(1, QColor(200, 230, 201))
    palette.setBrush(QPalette.Background, QBrush(gradient))
    widget.setPalette(palette)

# ========= 开机自启 LaunchAgent 管理 =========

def is_auto_start_enabled():
    return os.path.exists(LAUNCH_AGENT_PLIST)

def set_auto_start(enabled, script_path=None):
    if enabled:
        if script_path is None:
            script_path = os.path.abspath(__file__)
        python_path = sys.executable
        plist_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LAUNCH_AGENT_ID}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{script_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/break_reminder.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/break_reminder.err</string>
</dict>
</plist>'''
        launch_dir = os.path.dirname(LAUNCH_AGENT_PLIST)
        os.makedirs(launch_dir, exist_ok=True)
        with open(LAUNCH_AGENT_PLIST, 'w') as f:
            f.write(plist_content)
        subprocess.run(['launchctl', 'load', LAUNCH_AGENT_PLIST], capture_output=True)
    else:
        if os.path.exists(LAUNCH_AGENT_PLIST):
            subprocess.run(['launchctl', 'unload', LAUNCH_AGENT_PLIST], capture_output=True)
            os.remove(LAUNCH_AGENT_PLIST)

# ========= ReminderDialog =========

class ReminderDialog(QDialog):
    """休息提醒弹窗，包含"锁屏休息"和"继续工作"两个按钮。"""
    def __init__(self, title, message):
        super().__init__()
        self.user_skipped = False
        self.setWindowTitle(title)
        self.setModal(True)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Dialog)
        self.setFixedSize(420, 240)
        center_widget(self)

        # 与主窗口一致的浅绿色渐变背景
        apply_green_gradient(self, 420, 240)

        layout = QVBoxLayout()
        layout.setContentsMargins(40, 30, 40, 30)

        title_label = QLabel(title)
        title_label.setFont(QFont('PingFang SC', 24, QFont.Bold))
        title_label.setStyleSheet('color: #1B5E20;')
        title_label.setAlignment(Qt.AlignCenter)

        message_label = QLabel(message)
        message_label.setFont(QFont('PingFang SC', 14))
        message_label.setStyleSheet('color: rgba(27, 94, 32, 0.85);')
        message_label.setAlignment(Qt.AlignCenter)
        message_label.setWordWrap(True)

        # 按钮行
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        rest_btn = QPushButton(t("lock_rest"))
        rest_btn.setFont(QFont('PingFang SC', 14, QFont.Bold))
        rest_btn.setStyleSheet('''
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border-radius: 25px;
                padding: 12px 30px;
                border: none;
            }
            QPushButton:hover {
                background-color: #43A047;
            }
            QPushButton:pressed {
                background-color: #388E3C;
            }
        ''')
        rest_btn.clicked.connect(self._on_rest)

        skip_btn = QPushButton(t("continue_work"))
        skip_btn.setFont(QFont('PingFang SC', 14, QFont.Bold))
        skip_btn.setStyleSheet('''
            QPushButton {
                background-color: rgba(76, 175, 80, 0.15);
                color: #2E7D32;
                border-radius: 25px;
                padding: 12px 30px;
                border: 1px solid rgba(76, 175, 80, 0.4);
            }
            QPushButton:hover {
                background-color: rgba(76, 175, 80, 0.25);
            }
            QPushButton:pressed {
                background-color: rgba(76, 175, 80, 0.1);
            }
        ''')
        skip_btn.clicked.connect(self._on_skip)

        btn_layout.addWidget(rest_btn)
        btn_layout.addWidget(skip_btn)

        layout.addWidget(title_label)
        layout.addWidget(message_label)
        layout.addStretch()
        layout.addLayout(btn_layout)
        layout.setSpacing(15)

        self.setLayout(layout)

    def _on_rest(self):
        self.close()

    def _on_skip(self):
        self.user_skipped = True
        self.close()

# ========= OffWorkDialog =========

class FireworksOverlay(QWidget):
    """下班弹框的烟花动画层：覆盖弹框、鼠标穿透不挡按钮，弹出时播放多轮爆发后自动停止。"""

    # 烟花配色（橙 / 蓝 / 黄 / 紫 / 绿 / 红）
    PALETTE = [
        QColor(255, 87, 34), QColor(33, 150, 243), QColor(255, 193, 7),
        QColor(156, 39, 176), QColor(76, 175, 80), QColor(244, 67, 54),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        if parent is not None:
            self.setGeometry(0, 0, parent.width(), parent.height())
        self.particles = []
        self.bursts = []   # (触发帧, x, y, 颜色)
        self.frame = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self._schedule_bursts()
        self.timer.start(33)  # ≈30fps

    def _schedule_bursts(self):
        """在上半区随机位置安排 5 轮爆发，错峰触发。"""
        w = self.width() or 560
        h = self.height() or 280
        for i in range(5):
            x = random.randint(int(w * 0.2), int(w * 0.8))
            y = random.randint(int(h * 0.15), int(h * 0.5))
            self.bursts.append((i * 14 + random.randint(0, 6), x, y, random.choice(self.PALETTE)))

    def _burst(self, x, y, color):
        """在 (x,y) 生成一个粒子球。"""
        for _ in range(28):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(1.5, 4.5)
            self.particles.append({
                'x': x, 'y': y,
                'vx': math.cos(angle) * speed,
                'vy': math.sin(angle) * speed,
                'life': 1.0,
                'decay': random.uniform(0.012, 0.025),
                'color': color,
                'size': random.uniform(2.0, 3.5),
            })

    def _tick(self):
        self.frame += 1
        # 到点触发爆发的那一轮
        for b in list(self.bursts):
            if self.frame >= b[0]:
                self._burst(b[1], b[2], b[3])
                self.bursts.remove(b)
        # 物理推进：重力下落 + 生命衰减
        gravity = 0.08
        for p in self.particles:
            p['x'] += p['vx']
            p['y'] += p['vy']
            p['vy'] += gravity
            p['life'] -= p['decay']
        self.particles = [p for p in self.particles if p['life'] > 0]
        self.update()
        # 粒子与待爆发都清空后停止定时器，避免常驻空转
        if not self.particles and not self.bursts:
            self.timer.stop()

    def paintEvent(self, event):
        if not self.particles:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        for p in self.particles:
            alpha = int(255 * max(0.0, p['life']))
            c = QColor(p['color'])
            c.setAlpha(alpha)
            painter.setBrush(QBrush(c))
            r = p['size']
            painter.drawEllipse(int(p['x'] - r), int(p['y'] - r), int(r * 2), int(r * 2))
        painter.end()


class OffWorkDialog(QDialog):
    """下班提醒弹窗，显示今日使用电脑时长。和休息弹窗相同配色。"""

    def __init__(self, work_time_str, title=None, wrap=False):
        super().__init__()
        if title is None:
            title = t("offwork_title")
        self.setWindowTitle(t("offwork_dialog_title"))
        self.setModal(True)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Dialog)
        # 换行时加高窗口以容纳两行标题
        dialog_h = 320 if wrap else 280
        self.setFixedSize(560, dialog_h)
        center_widget(self)

        # 与主窗口一致的浅绿色渐变背景
        apply_green_gradient(self, 560, dialog_h)

        layout = QVBoxLayout()
        layout.setContentsMargins(40, 30, 40, 30)

        title_label = QLabel(title)
        title_label.setFont(QFont('PingFang SC', 24, QFont.Bold))
        title_label.setStyleSheet('color: #1B5E20;')
        title_label.setAlignment(Qt.AlignCenter)
        if wrap:
            title_label.setWordWrap(True)

        # 前缀标签
        prefix_label = QLabel(t("offwork_msg_prefix").rstrip('\n'))
        prefix_label.setFont(QFont('PingFang SC', 16))
        prefix_label.setStyleSheet('color: rgba(27, 94, 32, 0.9);')
        prefix_label.setAlignment(Qt.AlignCenter)

        # 时长标签（加粗）
        time_label = QLabel(work_time_str)
        time_label.setFont(QFont('PingFang SC', 20, QFont.Bold))
        time_label.setStyleSheet('color: #1B5E20;')
        time_label.setAlignment(Qt.AlignCenter)

        ok_btn = QPushButton(t("offwork_got_it"))
        ok_btn.setFont(QFont('PingFang SC', 14, QFont.Bold))
        ok_btn.setStyleSheet('''
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border-radius: 25px;
                padding: 12px 60px;
                border: none;
            }
            QPushButton:hover {
                background-color: #43A047;
            }
            QPushButton:pressed {
                background-color: #388E3C;
            }
        ''')
        ok_btn.clicked.connect(self.close)

        layout.addStretch()
        layout.addWidget(title_label)
        layout.addSpacing(10)
        layout.addWidget(prefix_label)
        layout.addSpacing(6)
        layout.addWidget(time_label)
        layout.addStretch()
        layout.addWidget(ok_btn, alignment=Qt.AlignCenter)
        layout.addStretch()
        layout.setSpacing(0)

        self.setLayout(layout)

        # 烟花动画层：覆盖整个弹框、鼠标穿透不挡 OK 按钮，弹出时自动播放
        self.fireworks = FireworksOverlay(self)

# ========= MainWindow =========

class MainWindow(QWidget):
    show_rest_signal = pyqtSignal()
    show_off_work_signal = pyqtSignal()
    ensure_background_signal = pyqtSignal()
    reset_timer_signal = pyqtSignal()
    pause_timer_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.running = True
        self.state_start_time = time.time()
        self.total_start_time = time.time()
        self._screen_locked = False
        self._paused_elapsed = 0
        
        # 今日使用时长追踪
        self._daily_work_seconds = 0.0
        self._last_tick_time = time.time()
        self._current_date = datetime.now().date()
        self._off_work_notified = False
        self._off_work_pending = False  # 锁屏跨过下班时间时，解锁后补弹
        self._last_tray_state = None    # 托盘图标颜色缓存（pct 或 'paused'）
        
        # 用户决策同步
        self._rest_decision_event = threading.Event()
        self._skip_rest = False
        self._interval_changing = False
        
        # 语言设置
        lang = self.config.get('language', 'zh')
        set_current_lang(lang)
        
        self.setWindowTitle(t("app_title"))
        self.setFixedSize(460, 320)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        center_widget(self)
        
        self.set_background()
        
        self.init_ui()
        self.init_tray()

        self.show_rest_signal.connect(self._show_rest_dialog_main)
        self.show_off_work_signal.connect(self._show_off_work_dialog)
        self.ensure_background_signal.connect(self._ensure_background)
        self.reset_timer_signal.connect(self._on_unlock_reset)
        self.pause_timer_signal.connect(self._on_lock_pause)
        self.start_reminder_thread()
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_display)
        self.timer.start(1000)
        
        # 启动锁屏/解锁监控
        self._lock_monitor = ScreenLockMonitor(
            on_lock=self._handle_lock,
            on_unlock=self._handle_unlock
        )
        self._lock_monitor.start()
        
        self.hide()
    
    def set_background(self):
        apply_green_gradient(self, 460, 320)
        self.setStyleSheet('''
            QLabel {
                color: #333333;
                font-family: 'PingFang SC';
            }
            QPushButton {
                border-radius: 12px;
                padding: 12px 20px;
                font-family: 'PingFang SC';
                font-weight: bold;
                font-size: 14px;
                border: none;
            }
            QPushButton#minBtn {
                background-color: rgba(76, 175, 80, 0.25);
                color: #2E7D32;
            }
            QPushButton#minBtn:hover {
                background-color: rgba(76, 175, 80, 0.45);
            }
            QSpinBox {
                font-family: 'PingFang SC';
                font-size: 16px;
                font-weight: bold;
                padding: 4px 8px;
                border: 1px solid #c8e6c9;
                border-radius: 8px;
                background-color: rgba(255, 255, 255, 0.7);
                color: #333333;
            }
            QLineEdit {
                font-family: 'PingFang SC';
                font-size: 16px;
                font-weight: bold;
                padding: 4px 8px;
                border: 1px solid #c8e6c9;
                border-radius: 8px;
                background-color: rgba(255, 255, 255, 0.7);
                color: #333333;
            }
        ''')
    
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(30, 25, 30, 25)
        
        # 顶部行：工作中状态（居中）+ 语言切换按钮（靠右）
        top_layout = QHBoxLayout()
        top_layout.setSpacing(0)
        # 左侧占位，保证 status_label 真正居中
        left_spacer = QLabel("")
        left_spacer.setFixedSize(50, 1)
        
        self.status_label = QLabel(t("working"))
        self.status_label.setFont(QFont('PingFang SC', 20, QFont.Bold))
        self.status_label.setAlignment(Qt.AlignCenter)
        
        self.lang_btn = QPushButton(t("lang_btn"))
        self.lang_btn.setFixedSize(40, 22)
        self.lang_btn.setFont(QFont('PingFang SC', 11, QFont.Bold))
        self.lang_btn.setStyleSheet('''
            QPushButton {
                background-color: transparent;
                color: #555;
                border: none;
                padding: 0;
            }
            QPushButton:hover {
                color: #333;
            }
        ''')
        self.lang_btn.clicked.connect(self._toggle_language)
        
        top_layout.addWidget(left_spacer)
        top_layout.addStretch()
        top_layout.addWidget(self.status_label)
        top_layout.addStretch()
        top_layout.addWidget(self.lang_btn)
        top_layout.addSpacing(8)
        
        # 今日使用
        self.elapsed_label = QLabel(f"{t('today_usage')}: 00:00:00")
        self.elapsed_label.setFont(QFont('PingFang SC', 13))
        self.elapsed_label.setAlignment(Qt.AlignCenter)
        
        # 分隔线
        separator = QLabel("")
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: rgba(0,0,0,0.08); margin: 4px 0;")
        
        # 提醒间隔设置行（居中，标签和框宽度固定保证对齐）
        interval_layout = QHBoxLayout()
        interval_layout.setSpacing(0)
        self.interval_label = QLabel(t("remind_interval"))
        self.interval_label.setFont(QFont('PingFang SC', 13))
        self.interval_label.setFixedWidth(80)
        self.interval_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 180)
        self.interval_spin.setValue(self.config['remind_interval_minutes'])
        self.interval_spin.setSuffix(f" {t('minutes')}")
        self.interval_spin.setFixedWidth(120)
        self.interval_spin.setButtonSymbols(QSpinBox.NoButtons)
        self.interval_spin.setAlignment(Qt.AlignCenter)
        self.interval_spin.valueChanged.connect(self._on_interval_changed)
        
        interval_layout.addStretch()
        interval_layout.addWidget(self.interval_label)
        interval_layout.addSpacing(20)
        interval_layout.addWidget(self.interval_spin)
        interval_layout.addStretch()
        
        # 下班时间设置行（用 QLineEdit 替代 QTimeEdit，手动输入 HH:mm）
        offwork_layout = QHBoxLayout()
        offwork_layout.setSpacing(0)
        self.offwork_label = QLabel(t("off_work_time"))
        self.offwork_label.setFont(QFont('PingFang SC', 13))
        self.offwork_label.setFixedWidth(80)
        self.offwork_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        self.offwork_time_edit = QLineEdit()
        self.offwork_time_edit.setFixedWidth(120)
        self.offwork_time_edit.setAlignment(Qt.AlignCenter)
        # 设置 XX : XX 格式输入掩码
        self.offwork_time_edit.setInputMask("99 : 99")
        # 从配置读取下班时间并转换为显示格式
        off_work_str = self.config.get('off_work_time', '17:30')
        display_str = off_work_str.replace(":", " : ")
        self.offwork_time_edit.setText(display_str)
        # 仅在编辑完成（回车或失焦）时保存
        self.offwork_time_edit.editingFinished.connect(self._on_offwork_time_finished)
        
        offwork_layout.addStretch()
        offwork_layout.addWidget(self.offwork_label)
        offwork_layout.addSpacing(20)
        offwork_layout.addWidget(self.offwork_time_edit)
        offwork_layout.addStretch()
        
        # 最小化按钮
        self.min_btn = QPushButton(t("minimize"))
        self.min_btn.setObjectName("minBtn")
        self.min_btn.setFixedHeight(36)
        self.min_btn.setFont(QFont('PingFang SC', 14, QFont.Bold))
        self.min_btn.clicked.connect(self.hide)
        self.min_btn.setMinimumWidth(360)
        
        layout.addSpacing(10)
        layout.addLayout(top_layout)
        layout.addSpacing(8)
        layout.addWidget(self.elapsed_label)
        layout.addSpacing(12)
        layout.addWidget(separator)
        layout.addSpacing(16)
        layout.addLayout(interval_layout)
        layout.addSpacing(16)
        layout.addLayout(offwork_layout)
        layout.addSpacing(20)
        layout.addWidget(self.min_btn)
        layout.addSpacing(10)
        
        self.setLayout(layout)
    
    def _toggle_language(self):
        """切换中英文。"""
        new_lang = "en" if get_current_lang() == "zh" else "zh"
        set_current_lang(new_lang)
        self.config['language'] = new_lang
        save_config(self.config)
        self._refresh_ui()
    
    def _refresh_ui(self):
        """刷新所有 UI 文本（切换语言后调用）。"""
        self.setWindowTitle(t("app_title"))
        self.lang_btn.setText(t("lang_btn"))
        self.interval_label.setText(t("remind_interval"))
        self.offwork_label.setText(t("off_work_time"))
        self.interval_spin.setSuffix(f" {t('minutes')}")
        self.min_btn.setText(t("minimize"))
        # 刷新托盘菜单文本（不重建图标）
        self._refresh_tray_menu()
    
    def _on_interval_changed(self, value):
        """提醒间隔改变 → 保存配置，重置当前工作计时"""
        if self._interval_changing:
            return
        self._interval_changing = True
        
        self.config['remind_interval_minutes'] = value
        save_config(self.config)
        
        # 重置当前工作周期
        self.state_start_time = time.time()
        
        self._interval_changing = False
    
    def _on_offwork_time_finished(self):
        """下班时间编辑完成 → 保存配置（仅在回车或失焦时触发）。"""
        text = self.offwork_time_edit.text().strip().replace(" ", "")
        # 验证格式 HH:mm
        if re.match(r'^([01]\d|2[0-3]):[0-5]\d$', text):
            self.config['off_work_time'] = text
            save_config(self.config)
            # 重新允许下班提醒
            self._off_work_notified = False
            debug_timer(f"下班时间已保存: {text}")
        else:
            # 格式不对，恢复为配置中的值（带空格显示格式）
            old_val = self.config.get('off_work_time', '17:30')
            self.offwork_time_edit.setText(old_val.replace(":", " : "))
            debug_timer(f"下班时间格式错误，恢复为: {old_val}")
    
    def create_clock_icon(self, ratio=None, paused=False, work_ratio=None):
        """生成托盘图标。

        - ratio=None       → 默认绿色（启动态）
        - ratio=0..1       → 外圈进度弧 + 内圆填充色相由绿(120°)渐变到红(0°)，反映当前提醒周期的剩余进度
        - paused=True      → 蓝灰色，表示锁屏暂停（不画进度弧）
        - work_ratio=0..1  → 单根指针角度，表示今日累计工作时长占满圈(WORK_CYCLE_SECONDS)的比例
        """
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        if paused:
            main_color = QColor(120, 144, 156)      # 蓝灰：暂停
            hand_color = QColor(84, 110, 122)
        elif ratio is None:
            main_color = QColor(76, 175, 80)         # 默认绿
            hand_color = QColor(27, 94, 32)
        else:
            t = max(0.0, min(1.0, ratio))
            hue = int(120 * (1 - t))                 # 120°(绿) → 0°(红)
            main_color = QColor.fromHsv(hue, 200, 255)
            hand_color = main_color.darker(140)

        # 外圈底轨道（浅黑），进度弧会覆盖其"已用"部分，未用部分保留浅黑
        painter.setPen(QPen(QColor(0, 0, 0, 100), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(2, 2, 28, 28)

        # 内圆：径向渐变填充（中心提亮、边缘主色），柔和不僵硬
        grad = QRadialGradient(12, 12, 14)
        grad.setColorAt(0, main_color.lighter(165))
        grad.setColorAt(1, main_color)
        painter.setPen(QPen(main_color.darker(120), 1))
        painter.setBrush(QBrush(grad))
        painter.drawEllipse(3, 3, 26, 26)

        # 外圈进度弧：当前提醒周期已用进度（从12点顺时针），与内圆颜色呼应
        if ratio is not None and not paused:
            t = max(0.0, min(1.0, ratio))
            span = int(t * 360 * 16)
            painter.setPen(QPen(main_color, 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawArc(2, 2, 28, 28, 90 * 16, span)

        # 12 刻度（钟面参考）
        painter.setPen(QPen(hand_color, 1))
        for i in range(12):
            angle = i * 30 * 3.14159 / 180
            x1 = 16 + 10 * math.cos(angle)
            y1 = 16 + 10 * math.sin(angle)
            x2 = 16 + 12 * math.cos(angle)
            y2 = 16 + 12 * math.sin(angle)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        # 指针：今日累计工作时长（从12点顺时针旋转，满圈 = WORK_CYCLE_SECONDS）
        if work_ratio is not None:
            ang = max(0.0, min(1.0, work_ratio)) * 2 * math.pi
            sx = 16 + 12 * math.sin(ang)
            sy = 16 - 12 * math.cos(ang)
            bx = 16 - 4 * math.sin(ang)
            by = 16 + 4 * math.cos(ang)
            painter.setPen(QPen(hand_color, 2))
            painter.drawLine(int(bx), int(by), int(sx), int(sy))
            # 中心轴点
            painter.setPen(Qt.NoPen)
            painter.setBrush(hand_color)
            painter.drawEllipse(14, 14, 4, 4)

        painter.end()

        return QIcon(pixmap)

    def _update_tray_color(self):
        """根据倒计时进度与今日累计工作时长更新托盘图标（带缓存，仅在状态变化时才重绘）。"""
        work_ratio = min(1.0, self._daily_work_seconds / WORK_CYCLE_SECONDS)

        if self._screen_locked:
            if self._last_tray_state != 'paused':
                self.tray_icon.setIcon(self.create_clock_icon(paused=True, work_ratio=work_ratio))
                self._last_tray_state = 'paused'
            return

        interval = self.config['remind_interval_minutes'] * 60
        if interval <= 0:
            ratio = 0.0
        else:
            elapsed = time.time() - self.state_start_time
            ratio = max(0.0, min(1.0, elapsed / interval))

        # 按整百分比缓存，避免每秒重复重绘近似相同的图标
        # 状态键同时含倒计时档位与累计工作时长档位
        pct = int(ratio * 100)
        wpct = int(work_ratio * 100)
        key = f"{pct}:{wpct}"
        if self._last_tray_state != key:
            self.tray_icon.setIcon(self.create_clock_icon(ratio=ratio, work_ratio=work_ratio))
            self._last_tray_state = key
    
    def init_tray(self):
        # 如果已有托盘图标，只更新菜单文本，不重建
        if hasattr(self, 'tray_icon') and self.tray_icon is not None:
            self._refresh_tray_menu()
            return
        
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.create_clock_icon())
        self._build_tray_menu()
        self.tray_icon.show()
        self.tray_icon.activated.connect(self.tray_activated)
    
    def _build_tray_menu(self):
        """创建托盘菜单。"""
        tray_menu = QMenu()
        
        self._tray_show_action = QAction(t("tray_show"), self)
        self._tray_show_action.triggered.connect(self.show)
        tray_menu.addAction(self._tray_show_action)
        
        tray_menu.addSeparator()
        
        self.auto_start_action = QAction(t("tray_auto_start"), self)
        self.auto_start_action.setCheckable(True)
        self.auto_start_action.setChecked(is_auto_start_enabled())
        self.auto_start_action.triggered.connect(self.toggle_auto_start)
        tray_menu.addAction(self.auto_start_action)
        
        tray_menu.addSeparator()
        
        self._tray_quit_action = QAction(t("tray_quit"), self)
        self._tray_quit_action.triggered.connect(self.close_app)
        tray_menu.addAction(self._tray_quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
    
    def _refresh_tray_menu(self):
        """仅刷新托盘菜单文本（切换语言时调用，不重建图标）。"""
        self._tray_show_action.setText(t("tray_show"))
        self.auto_start_action.setText(t("tray_auto_start"))
        self._tray_quit_action.setText(t("tray_quit"))
    
    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show()
    
    def toggle_auto_start(self, checked):
        try:
            set_auto_start(checked)
            self.config['auto_start'] = checked
            save_config(self.config)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"设置开机自启失败：{e}")
            self.auto_start_action.setChecked(not checked)
    
    def start_reminder_thread(self):
        self.reminder_thread = threading.Thread(target=self.reminder_loop, daemon=True)
        self.reminder_thread.start()
    
    def reminder_loop(self):
        """核心计时循环。
        
        简化逻辑：
        1. 持续循环，每次检查 elapsed >= interval
        2. 到点 → 弹窗 → 等用户决策
        3. "继续工作" → 重置计时器
        4. "锁屏休息" → 锁屏 → 外层循环等解锁后自动重置
        5. 锁屏时跳过检查，解锁后 _on_unlock_reset 重置 state_start_time
        """
        debug_timer(f"reminder_loop 启动，间隔={self.config['remind_interval_minutes']}分钟")
        
        while self.running:
            # 读取当前间隔（每次循环都读，支持用户动态修改）
            interval = self.config['remind_interval_minutes'] * 60
            
            # 锁屏时暂停，等解锁
            if self._screen_locked:
                time.sleep(1)
                continue
            
            elapsed = time.time() - self.state_start_time
            
            if elapsed >= interval:
                # 工作时间到，弹窗提醒
                debug_timer(f"倒计时到！elapsed={elapsed:.1f}s, interval={interval}s，弹窗")
                self._skip_rest = False
                self._rest_decision_event.clear()
                self.show_rest_signal.emit()
                # 等待用户在主线程做出决策
                self._rest_decision_event.wait()

                if not self.running:
                    return

                if self._skip_rest:
                    # 用户选择"继续工作" → 重置计时器
                    self.state_start_time = time.time()
                    debug_timer("用户选择继续工作，计时器重置")
                else:
                    # 用户选择"锁屏休息" → 锁屏
                    debug_timer("用户选择锁屏休息，执行锁屏")
                    lock_screen()
                    # 外层循环会检测到 _screen_locked，暂停计时
                    # 解锁后 _on_unlock_reset 会重置 state_start_time
            else:
                time.sleep(1)

    # ========= 锁屏/解锁回调 =========
    
    def _handle_lock(self):
        """锁屏回调（在后台线程中执行，通过信号转发到主线程）。"""
        self._screen_locked = True
        self._paused_elapsed = time.time() - self.state_start_time
        debug_lock(f"锁屏！已工作 {self._paused_elapsed:.1f}s，暂停计时")
        self.pause_timer_signal.emit()
    
    def _handle_unlock(self):
        """解锁回调（在后台线程中执行，通过信号转发到主线程）。"""
        self._screen_locked = False
        debug_lock("解锁！重置计时器")
        self.reset_timer_signal.emit()
    
    def _on_lock_pause(self):
        """主线程：锁屏暂停 UI 更新。"""
        self.status_label.setText(t("locked_pause"))
    
    def _on_unlock_reset(self):
        """主线程：解锁后重置计时器。"""
        self.state_start_time = time.time()
        debug_timer("解锁后计时器重置")
        self.ensure_background_signal.emit()
        # 若锁屏期间跨过下班时间，解锁后立即补弹下班提醒
        if self._off_work_pending:
            self._off_work_pending = False
            debug_timer("解锁后补弹下班提醒")
            self.show_off_work_signal.emit()
    
    def _ensure_background(self):
        """确保程序后台常驻。"""
        self.hide()
        if not self.tray_icon.isVisible():
            self.tray_icon.show()

    def _show_rest_dialog_main(self):
        """在主线程执行弹窗，由 show_rest_signal 触发"""
        work_time_str = format_duration_chinese(self._daily_work_seconds)

        dialog = ReminderDialog(
            t("rest_title"),
            f"{t('rest_msg_prefix')}{work_time_str}{t('rest_msg_suffix')}"
        )
        debug_timer("休息弹窗显示中...")
        dialog.exec_()
        debug_timer(f"休息弹窗关闭，user_skipped={dialog.user_skipped}")

        # 弹窗关闭后，重置工作计时器（无论用户选了什么）
        self.state_start_time = time.time()

        # 记录用户决策，通知后台线程继续
        self._skip_rest = dialog.user_skipped
        self._rest_decision_event.set()
    
    def _show_off_work_dialog(self):
        """在主线程执行下班弹窗"""
        work_time_str = format_duration_chinese(self._daily_work_seconds)
        # 周五使用特殊标题（可换行显示）
        now_dt = datetime.now()
        if now_dt.weekday() == 4:  # 4 = 周五
            dialog = OffWorkDialog(work_time_str, title=t("offwork_title_friday"), wrap=True)
        else:
            dialog = OffWorkDialog(work_time_str)
        dialog.exec_()
    
    def update_display(self):
        now = time.time()
        now_dt = datetime.now()
        
        # 跨日重置
        today = now_dt.date()
        if today != self._current_date:
            self._current_date = today
            self._daily_work_seconds = 0.0
            self._off_work_notified = False
            self._off_work_pending = False
        
        # 累积今日工作时间（仅未锁屏时）
        if not self._screen_locked:
            delta = now - self._last_tick_time
            if delta > 0 and delta < 10:
                self._daily_work_seconds += delta
        self._last_tick_time = now
        
        # 检查是否到达下班时间（与锁屏状态解耦，确保锁屏跨点时也能正确触发）
        if not self._off_work_notified:
            off_work_str = self.config.get('off_work_time', '17:30')
            try:
                h, m = off_work_str.split(':')
                off_work_h = int(h)
                off_work_m = int(m)
                current_h = now_dt.hour
                current_m = now_dt.minute

                if current_h > off_work_h or (current_h == off_work_h and current_m >= off_work_m):
                    self._off_work_notified = True
                    debug_timer("到达下班时间")
                    if self._screen_locked:
                        # 锁屏时屏幕不可见，标记待解锁后补弹
                        self._off_work_pending = True
                        debug_timer("当前锁屏，解锁后补弹下班提醒")
                    else:
                        self.show_off_work_signal.emit()
            except Exception:
                pass

        # 更新托盘图标颜色（随倒计时由绿渐变红；锁屏显示暂停色）
        self._update_tray_color()

        # 锁屏时显示暂停状态，不更新倒计时/时长
        if self._screen_locked:
            return

        # 更新工作倒计时显示
        elapsed = now - self.state_start_time
        remaining = max(0, self.config['remind_interval_minutes'] * 60 - elapsed)
        self.status_label.setText(f"{t('working')} - {t('remaining')} {format_time(remaining)}")

        # 更新今日使用时长
        self.elapsed_label.setText(f"{t('today_usage')}: {format_time(self._daily_work_seconds)}")
    
    def close_app(self):
        self.running = False
        self._rest_decision_event.set()
        self._lock_monitor.stop()
        self.tray_icon.hide()
        cleanup_pid_file()
        QApplication.quit()
    
    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(t("app_title"), t("tray_minimized"))

def main():
    parser = argparse.ArgumentParser(description='休息提醒器 - 定时提醒您起身活动')
    parser.add_argument('-s', '--show', action='store_true', help='显示当前配置')
    parser.add_argument('--interval', type=int, help='设置提醒间隔（分钟）')
    
    args = parser.parse_args()
    
    if args.show:
        config = load_config()
        print("当前配置:")
        print(f"  提醒间隔: {config['remind_interval_minutes']} 分钟")
        print(f"  下班时间: {config.get('off_work_time', '17:30')}")
        print(f"  开机自启: {'开启' if is_auto_start_enabled() else '关闭'}")
        print(f"  配置文件: {CONFIG_FILE}")
        return
    
    if args.interval:
        config = load_config()
        config['remind_interval_minutes'] = max(1, args.interval)
        save_config(config)
        print("配置已更新！")
        return
    
    ensure_single_instance()
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    window = MainWindow()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
