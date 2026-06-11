#!/usr/bin/env python3
import sys
import time
import subprocess
import os
import json
import threading
import argparse
import math
import re
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout,
                             QHBoxLayout, QPushButton, QSystemTrayIcon,
                             QMenu, QAction, QDialog, QSpinBox, QLineEdit,
                             QMessageBox, QAbstractSpinBox)
from PyQt5.QtGui import QIcon, QFont, QPalette, QBrush, QPixmap, QColor, QLinearGradient, QPainter, QPen, QRegExpValidator
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QTime, QRegExp

CONFIG_FILE = os.path.expanduser("~/.break_reminder_config.json")
PID_FILE = os.path.expanduser("~/.break_reminder.pid")

DEFAULT_CONFIG = {
    "remind_interval_minutes": 45,
    "auto_start": False,
    "off_work_time": "17:30",
    "language": "zh"
}

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
        "offwork_title": "🐮牛马~你已经下班啦！",
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
        "offwork_title": "🐮Drudge,Off Work now!",
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
    lang = _current_lang
    return I18N.get(lang, I18N["zh"]).get(key, key)


_current_lang = "zh"


def set_current_lang(lang):
    global _current_lang
    _current_lang = lang


def get_current_lang():
    return _current_lang


DEBUG_LOCK = False
DEBUG_TIMER = True


def debug_lock(msg):
    if DEBUG_LOCK:
        print(f"[LOCK {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def debug_timer(msg):
    if DEBUG_TIMER:
        print(f"[TIMER {time.strftime('%H:%M:%S')}] {msg}", flush=True)


class ScreenLockMonitor:
    """Windows 锁屏/解锁事件监控器 - 使用 WTS 会话通知。"""

    def __init__(self, on_lock=None, on_unlock=None, hwnd=None):
        self.on_lock = on_lock
        self.on_unlock = on_unlock
        self._hwnd = hwnd
        self._screen_locked = False
        self._registered = False
        self._wtsapi32 = None

    def start(self):
        if self._registered:
            return
        try:
            import ctypes
            from ctypes import wintypes

            self._wtsapi32 = ctypes.windll.wtsapi32

            if self._hwnd is None and QApplication.instance():
                top_windows = QApplication.topLevelWidgets()
                for w in top_windows:
                    if w.isVisible() and w.windowTitle():
                        self._hwnd = int(w.winId())
                        break

            if self._hwnd:
                NOTIFY_FOR_THIS_SESSION = 0
                result = self._wtsapi32.WTSRegisterSessionNotification(self._hwnd, NOTIFY_FOR_THIS_SESSION)
                if result:
                    self._registered = True
                    debug_lock("ScreenLockMonitor 已启动 (WTS 会话通知)")
                    return
                else:
                    debug_lock(f"WTSRegisterSessionNotification 失败: {ctypes.GetLastError()}")

            debug_lock("WTS 注册失败，切换到轮询模式")
            self._start_polling()
        except Exception as e:
            debug_lock(f"WTS 初始化异常: {e}，切换到轮询模式")
            self._start_polling()

    def _start_polling(self):
        self._running = True
        self._last_check = False
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        debug_lock("ScreenLockMonitor 已启动 (轮询模式)")

    def stop(self):
        self._running = False
        if self._registered and self._wtsapi32 and self._hwnd:
            try:
                self._wtsapi32.WTSUnRegisterSessionNotification(self._hwnd)
                debug_lock("WTS 会话通知已注销")
            except Exception as e:
                debug_lock(f"WTS 注销异常: {e}")
        self._registered = False
        debug_lock("ScreenLockMonitor 已停止")

    def is_locked(self):
        return self._screen_locked

    def on_session_change(self, event_type):
        WTS_SESSION_LOCK = 7
        WTS_SESSION_UNLOCK = 8

        if event_type == WTS_SESSION_LOCK:
            debug_lock("WTS 事件: 检测到锁屏")
            self._screen_locked = True
            if self.on_lock:
                try:
                    self.on_lock()
                except Exception as e:
                    debug_lock(f"锁屏回调异常: {e}")
        elif event_type == WTS_SESSION_UNLOCK:
            debug_lock("WTS 事件: 检测到解锁")
            self._screen_locked = False
            if self.on_unlock:
                try:
                    self.on_unlock()
                except Exception as e:
                    debug_lock(f"解锁回调异常: {e}")

    def _monitor_loop(self):
        while self._running:
            try:
                current_locked = self._check_workstation_locked()
                if current_locked != self._last_check:
                    if current_locked:
                        debug_lock("轮询检测到锁屏")
                        self._screen_locked = True
                        if self.on_lock:
                            try:
                                self.on_lock()
                            except Exception as e:
                                debug_lock(f"锁屏回调异常: {e}")
                    else:
                        debug_lock("轮询检测到解锁")
                        self._screen_locked = False
                        if self.on_unlock:
                            try:
                                self.on_unlock()
                            except Exception as e:
                                debug_lock(f"解锁回调异常: {e}")
                    self._last_check = current_locked
            except Exception as e:
                debug_lock(f"监控异常: {e}")
            time.sleep(2)

    def _check_workstation_locked(self):
        """检查 Windows 工作站是否被锁定（备用轮询方法）。"""
        try:
            import ctypes
            from ctypes import wintypes

            wtsapi32 = ctypes.windll.wtsapi32

            WTS_CURRENT_SERVER_HANDLE = 0
            WTS_CURRENT_SESSION = -1
            WTSSessionInfoEx = 24

            wtsapi32.WTSQuerySessionInformationW.restype = wintypes.BOOL
            wtsapi32.WTSQuerySessionInformationW.argtypes = [
                wintypes.HANDLE,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.POINTER(wintypes.LPWSTR),
                ctypes.POINTER(wintypes.DWORD),
            ]

            ppBuffer = wintypes.LPWSTR()
            pBytesReturned = wintypes.DWORD()

            if wtsapi32.WTSQuerySessionInformationW(
                    WTS_CURRENT_SERVER_HANDLE,
                    WTS_CURRENT_SESSION,
                    WTSSessionInfoEx,
                    ctypes.byref(ppBuffer),
                    ctypes.byref(pBytesReturned),
            ):
                pInfo = ctypes.cast(ppBuffer, ctypes.POINTER(ctypes.c_ulong))
                if pInfo:
                    session_flags = pInfo.contents.value
                    LOCKED_FLAG = 0x80
                    is_locked = (session_flags & LOCKED_FLAG) != 0
                    wtsapi32.WTSFreeMemory(ppBuffer)
                    return is_locked
                wtsapi32.WTSFreeMemory(ppBuffer)
            return False
        except Exception as e:
            debug_lock(f"WTS API 轮询异常: {e}")
            return False


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return {**DEFAULT_CONFIG, **config}
        except:
            return DEFAULT_CONFIG
    return DEFAULT_CONFIG


def ensure_single_instance():
    """Windows 单实例检测 - 使用互斥体。"""
    try:
        import ctypes
        from ctypes import wintypes

        mutex_name = "BreakReminder_Mutex_2026"
        kernel32 = ctypes.windll.kernel32
        mutex = kernel32.CreateMutexW(None, False, mutex_name)
        last_error = kernel32.GetLastError()

        if last_error == 183:
            sys.exit(0)

        global _mutex_handle
        _mutex_handle = mutex
    except Exception:
        if os.path.exists(PID_FILE):
            try:
                with open(PID_FILE, 'r') as f:
                    old_pid = int(f.read().strip())
                try:
                    import psutil
                    if psutil.pid_exists(old_pid):
                        sys.exit(0)
                except ImportError:
                    pass
                try:
                    os.remove(PID_FILE)
                except OSError:
                    pass
            except (OSError, ValueError, ProcessLookupError):
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
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)


def lock_screen():
    """Windows 锁屏。"""
    try:
        import ctypes
        ctypes.windll.user32.LockWorkStation()
    except Exception:
        try:
            subprocess.Popen(
                ['rundll32.exe', 'user32.dll,LockWorkStation'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except Exception:
            pass


def format_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"


def format_duration_chinese(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    if hours > 0 and minutes > 0:
        return f"{hours}{t('hours')}{minutes}{t('mins')}"
    elif hours > 0:
        return f"{hours}{t('hours')}"
    else:
        return f"{minutes}{t('mins')}"


def center_widget(widget):
    geo = QApplication.desktop().screenGeometry()
    widget.move(
        (geo.width() - widget.width()) // 2,
        (geo.height() - widget.height()) // 2
    )


def is_auto_start_enabled():
    """Windows 开机自启检测 - 检查注册表。"""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ
        )
        try:
            winreg.QueryValueEx(key, "BreakReminder")
            winreg.CloseKey(key)
            return True
        except WindowsError:
            winreg.CloseKey(key)
            return False
    except Exception:
        return False


def set_auto_start(enabled, script_path=None):
    """Windows 设置开机自启 - 使用注册表。"""
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE
        )

        if enabled:
            if script_path is None:
                script_path = os.path.abspath(__file__)

            python_path = sys.executable
            if python_path.endswith('python.exe'):
                pythonw_path = os.path.join(os.path.dirname(python_path), 'pythonw.exe')
                if os.path.exists(pythonw_path):
                    python_path = pythonw_path

            command = f'"{python_path}" "{script_path}"'

            winreg.SetValueEx(key, "BreakReminder", 0, winreg.REG_SZ, command)
            debug_timer(f"已设置开机自启: {command}")
        else:
            try:
                winreg.DeleteValue(key, "BreakReminder")
                debug_timer("已移除开机自启")
            except WindowsError:
                pass

        winreg.CloseKey(key)
    except Exception as e:
        debug_timer(f"设置开机自启失败: {e}")
        raise


class ReminderDialog(QDialog):
    def __init__(self, title, message):
        super().__init__()
        self.user_skipped = False
        self.setWindowTitle(title)
        self.setModal(True)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Dialog)
        self.setFixedSize(750, 400)
        center_widget(self)

        palette = self.palette()
        gradient = QLinearGradient(0, 0, 750, 400)
        gradient.setColorAt(0, QColor(232, 245, 233))
        gradient.setColorAt(0.5, QColor(220, 237, 200))
        gradient.setColorAt(1, QColor(200, 230, 201))
        palette.setBrush(QPalette.Background, QBrush(gradient))
        self.setPalette(palette)

        layout = QVBoxLayout()
        layout.setContentsMargins(60, 40, 60, 40)

        title_label = QLabel(title)
        title_label.setFont(QFont('Microsoft YaHei', 22, QFont.Bold))
        title_label.setStyleSheet('color: #1B5E20;')
        title_label.setAlignment(Qt.AlignCenter)

        message_label = QLabel(message)
        message_label.setFont(QFont('Microsoft YaHei', 15))
        message_label.setStyleSheet('color: rgba(27, 94, 32, 0.85);')
        message_label.setAlignment(Qt.AlignCenter)
        message_label.setWordWrap(True)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        rest_btn = QPushButton(t("lock_rest"))
        rest_btn.setFont(QFont('Microsoft YaHei', 14, QFont.Bold))
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
        skip_btn.setFont(QFont('Microsoft YaHei', 14, QFont.Bold))
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


class OffWorkDialog(QDialog):
    def __init__(self, work_time_str):
        super().__init__()
        self.setWindowTitle(t("offwork_dialog_title"))
        self.setModal(True)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Dialog)
        self.setFixedSize(750, 400)
        center_widget(self)

        palette = self.palette()
        gradient = QLinearGradient(0, 0, 750, 400)
        gradient.setColorAt(0, QColor(232, 245, 233))
        gradient.setColorAt(0.5, QColor(220, 237, 200))
        gradient.setColorAt(1, QColor(200, 230, 201))
        palette.setBrush(QPalette.Background, QBrush(gradient))
        self.setPalette(palette)

        layout = QVBoxLayout()
        layout.setContentsMargins(60, 40, 60, 40)

        title_label = QLabel(t("offwork_title"))
        title_label.setFont(QFont('Microsoft YaHei', 24, QFont.Bold))
        title_label.setStyleSheet('color: #1B5E20;')
        title_label.setAlignment(Qt.AlignCenter)

        prefix_label = QLabel(t("offwork_msg_prefix").rstrip('\n'))
        prefix_label.setFont(QFont('Microsoft YaHei', 18))
        prefix_label.setStyleSheet('color: rgba(27, 94, 32, 0.9);')
        prefix_label.setAlignment(Qt.AlignCenter)

        time_label = QLabel(work_time_str)
        time_label.setFont(QFont('Microsoft YaHei', 22, QFont.Bold))
        time_label.setStyleSheet('color: #1B5E20;')
        time_label.setAlignment(Qt.AlignCenter)

        ok_btn = QPushButton(t("offwork_got_it"))
        ok_btn.setFont(QFont('Microsoft YaHei', 14, QFont.Bold))
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
        self.current_state = "working"
        self.state_start_time = time.time()
        self.total_start_time = time.time()
        self._screen_locked = False
        self._paused_elapsed = 0

        self._daily_work_seconds = 0.0
        self._last_tick_time = time.time()
        self._current_date = datetime.now().date()
        self._off_work_notified = False

        self._rest_decision_event = threading.Event()
        self._skip_rest = False
        self._interval_changing = False

        lang = self.config.get('language', 'zh')
        set_current_lang(lang)

        self.setWindowTitle(t("app_title"))
        self.setFixedSize(750, 400)
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

        self._lock_monitor = ScreenLockMonitor(
            on_lock=self._handle_lock,
            on_unlock=self._handle_unlock
        )
        self._lock_monitor.start()

        self.hide()

    def set_background(self):
        palette = QPalette()
        gradient = QLinearGradient(0, 0, 750, 400)
        gradient.setColorAt(0, QColor(232, 245, 233))
        gradient.setColorAt(0.5, QColor(220, 237, 200))
        gradient.setColorAt(1, QColor(200, 230, 201))
        palette.setBrush(QPalette.Background, QBrush(gradient))
        self.setPalette(palette)
        self.setStyleSheet('''
            QLabel {
                color: #333333;
                font-family: 'Microsoft YaHei';
            }
            QPushButton {
                border-radius: 12px;
                padding: 12px 20px;
                font-family: 'Microsoft YaHei';
                font-weight: bold;
                font-size: 14px;
                border: none;
            }
            QPushButton#minBtn {
                background-color: #81C784;
                color: #1B5E20;
                font-size: 32px;
            }
            QPushButton#minBtn:hover {
                background-color: #66BB6A;
            }
            QSpinBox {
                font-family: 'Microsoft YaHei';
                font-size: 20px;
                font-weight: bold;
                padding: 4px 8px;
                border: 1px solid #c8e6c9;
                border-radius: 8px;
                background-color: rgba(255, 255, 255, 0.7);
                color: #333333;
            }
            QLineEdit {
                font-family: 'Microsoft YaHei';
                font-size: 20px;
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

        top_layout = QHBoxLayout()
        top_layout.setSpacing(0)
        left_spacer = QLabel("")
        left_spacer.setFixedSize(50, 1)

        self.status_label = QLabel(t("working"))
        self.status_label.setFont(QFont('Microsoft YaHei', 20, QFont.Bold))
        self.status_label.setAlignment(Qt.AlignCenter)

        self.lang_btn = QPushButton(t("lang_btn"))
        self.lang_btn.setFixedSize(50, 30)
        self.lang_btn.setFont(QFont('Microsoft YaHei', 16, QFont.Bold))
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

        self.elapsed_label = QLabel(f"{t('today_usage')}: 00:00:00")
        self.elapsed_label.setFont(QFont('Microsoft YaHei', 13))
        self.elapsed_label.setAlignment(Qt.AlignCenter)

        separator = QLabel("")
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: rgba(0,0,0,0.08); margin: 4px 0;")

        interval_layout = QHBoxLayout()
        interval_layout.setSpacing(0)
        self.interval_label = QLabel(t("remind_interval"))
        self.interval_label.setFont(QFont('Microsoft YaHei', 14))
        self.interval_label.setFixedWidth(160)
        self.interval_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 180)
        self.interval_spin.setValue(self.config['remind_interval_minutes'])
        self.interval_spin.setSuffix(f" {t('minutes')}")
        self.interval_spin.setFixedWidth(180)
        self.interval_spin.setButtonSymbols(QSpinBox.NoButtons)
        self.interval_spin.setAlignment(Qt.AlignCenter)
        self.interval_spin.setFont(QFont('Microsoft YaHei', 20, QFont.Bold))
        self.interval_spin.setStyleSheet('QSpinBox { padding: 4px 8px; border-radius: 8px; background-color: rgba(255, 255, 255, 0.7); }')
        self.interval_spin.valueChanged.connect(self._on_interval_changed)

        interval_layout.addStretch()
        interval_layout.addWidget(self.interval_label)
        interval_layout.addSpacing(20)
        interval_layout.addWidget(self.interval_spin)
        interval_layout.addStretch()

        offwork_layout = QHBoxLayout()
        offwork_layout.setSpacing(0)
        self.offwork_label = QLabel(t("off_work_time"))
        self.offwork_label.setFont(QFont('Microsoft YaHei', 14))
        self.offwork_label.setFixedWidth(160)
        self.offwork_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.offwork_time_edit = QLineEdit()
        self.offwork_time_edit.setFixedWidth(180)
        self.offwork_time_edit.setAlignment(Qt.AlignCenter)
        self.offwork_time_edit.setInputMask("99 : 99")
        self.offwork_time_edit.setFont(QFont('Microsoft YaHei', 20, QFont.Bold))
        self.offwork_time_edit.setStyleSheet('QLineEdit { padding: 4px 8px; border-radius: 8px; background-color: rgba(255, 255, 255, 0.7); }')
        off_work_str = self.config.get('off_work_time', '17:30')
        display_str = off_work_str.replace(":", " : ")
        self.offwork_time_edit.setText(display_str)
        self.offwork_time_edit.editingFinished.connect(self._on_offwork_time_finished)

        offwork_layout.addStretch()
        offwork_layout.addWidget(self.offwork_label)
        offwork_layout.addSpacing(20)
        offwork_layout.addWidget(self.offwork_time_edit)
        offwork_layout.addStretch()

        self.min_btn = QPushButton(t("minimize"))
        self.min_btn.setObjectName("minBtn")
        self.min_btn.setFixedHeight(60)
        self.min_btn.clicked.connect(self.hide)
        self.min_btn.setFixedWidth(300)

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
        layout.addWidget(self.min_btn, alignment=Qt.AlignCenter)
        layout.addSpacing(10)

        self.setLayout(layout)

    def _toggle_language(self):
        new_lang = "en" if get_current_lang() == "zh" else "zh"
        set_current_lang(new_lang)
        self.config['language'] = new_lang
        save_config(self.config)
        self._refresh_ui()

    def _refresh_ui(self):
        self.setWindowTitle(t("app_title"))
        self.lang_btn.setText(t("lang_btn"))
        self.interval_label.setText(t("remind_interval"))
        self.offwork_label.setText(t("off_work_time"))
        self.interval_spin.setSuffix(f" {t('minutes')}")
        self.min_btn.setText(t("minimize"))
        self._refresh_tray_menu()

    def _on_interval_changed(self, value):
        if self._interval_changing:
            return
        self._interval_changing = True

        self.config['remind_interval_minutes'] = value
        save_config(self.config)

        self.state_start_time = time.time()

        self._interval_changing = False

    def _on_offwork_time_finished(self):
        text = self.offwork_time_edit.text().strip().replace(" ", "")
        if re.match(r'^([01]\d|2[0-3]):[0-5]\d$', text):
            self.config['off_work_time'] = text
            save_config(self.config)
            self._off_work_notified = False
            debug_timer(f"下班时间已保存: {text}")
        else:
            old_val = self.config.get('off_work_time', '17:30')
            self.offwork_time_edit.setText(old_val.replace(":", " : "))
            debug_timer(f"下班时间格式错误，恢复为: {old_val}")

    def create_clock_icon(self):
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.setPen(QPen(Qt.darkGreen, 2))
        painter.setBrush(Qt.green)
        painter.drawEllipse(2, 2, 28, 28)

        painter.setPen(QPen(Qt.darkGreen, 1))
        for i in range(12):
            angle = i * 30 * 3.14159 / 180
            x1 = 16 + 10 * math.cos(angle)
            y1 = 16 + 10 * math.sin(angle)
            x2 = 16 + 12 * math.cos(angle)
            y2 = 16 + 12 * math.sin(angle)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        painter.setPen(QPen(Qt.darkGreen, 2))
        painter.drawLine(16, 16, 16, 8)

        painter.setPen(QPen(Qt.darkGreen, 1.5))
        painter.drawLine(16, 16, 22, 16)

        painter.end()

        return QIcon(pixmap)

    def init_tray(self):
        if hasattr(self, 'tray_icon') and self.tray_icon is not None:
            self._refresh_tray_menu()
            return

        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.create_clock_icon())
        self._build_tray_menu()
        self.tray_icon.show()
        self.tray_icon.activated.connect(self.tray_activated)

    def _build_tray_menu(self):
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
        debug_timer(f"reminder_loop 启动，间隔={self.config['remind_interval_minutes']}分钟")

        while self.running:
            interval = self.config['remind_interval_minutes'] * 60

            if self._screen_locked:
                time.sleep(1)
                continue

            elapsed = time.time() - self.state_start_time

            if elapsed >= interval:
                debug_timer(f"倒计时到！elapsed={elapsed:.1f}s, interval={interval}s，弹窗")
                self._skip_rest = False
                self._rest_decision_event.clear()
                self.show_rest_signal.emit()
                self._rest_decision_event.wait()

                if not self.running:
                    return

                if self._skip_rest:
                    self.state_start_time = time.time()
                    debug_timer("用户选择继续工作，计时器重置")
                else:
                    debug_timer("用户选择锁屏休息，执行锁屏")
                    lock_screen()
            else:
                time.sleep(1)

    def _handle_lock(self):
        self._screen_locked = True
        self._paused_elapsed = time.time() - self.state_start_time
        debug_lock(f"锁屏！已工作 {self._paused_elapsed:.1f}s，暂停计时")
        self.pause_timer_signal.emit()

    def _handle_unlock(self):
        self._screen_locked = False
        debug_lock("解锁！重置计时器")
        self.reset_timer_signal.emit()

    def _on_lock_pause(self):
        self.status_label.setText(t("locked_pause"))
        if hasattr(self, '_rest_dialog') and self._rest_dialog is not None:
            debug_lock("锁屏，关闭休息弹窗")
            self._rest_dialog.close()
            self._rest_dialog = None
            self._rest_decision_event.set()
            self._skip_rest = True
        if hasattr(self, '_offwork_dialog') and self._offwork_dialog is not None:
            debug_lock("锁屏，关闭下班弹窗")
            self._offwork_dialog.close()
            self._offwork_dialog = None

    def _on_unlock_reset(self):
        self.state_start_time = time.time()
        self.current_state = "working"
        debug_timer("解锁后计时器重置")
        self.ensure_background_signal.emit()

    def _ensure_background(self):
        self.hide()
        if not self.tray_icon.isVisible():
            self.tray_icon.show()

    def _show_rest_dialog_main(self):
        work_time_str = format_duration_chinese(self._daily_work_seconds)

        self._rest_dialog = ReminderDialog(
            t("rest_title"),
            f"{t('rest_msg_prefix')}{work_time_str}{t('rest_msg_suffix')}"
        )
        debug_timer("休息弹窗显示中...")
        self._rest_dialog.exec_()
        debug_timer(f"休息弹窗关闭，user_skipped={self._rest_dialog.user_skipped}")

        self.state_start_time = time.time()

        self._skip_rest = self._rest_dialog.user_skipped
        self._rest_dialog = None
        self._rest_decision_event.set()

    def _show_off_work_dialog(self):
        work_time_str = format_duration_chinese(self._daily_work_seconds)
        self._offwork_dialog = OffWorkDialog(work_time_str)
        self._offwork_dialog.exec_()
        self._offwork_dialog = None

    def update_display(self):
        now = time.time()
        now_dt = datetime.now()

        today = now_dt.date()
        if today != self._current_date:
            self._current_date = today
            self._daily_work_seconds = 0.0
            self._off_work_notified = False

        if not self._screen_locked:
            delta = now - self._last_tick_time
            if delta > 0 and delta < 10:
                self._daily_work_seconds += delta
        self._last_tick_time = now

        self.elapsed_label.setText(f"{t('today_usage')}: {format_time(self._daily_work_seconds)}")

        if self._screen_locked:
            return

        elapsed = now - self.state_start_time
        remaining = max(0, self.config['remind_interval_minutes'] * 60 - elapsed)
        self.status_label.setText(f"{t('working')} - {t('remaining')} {format_time(remaining)}")

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
                    debug_timer("到达下班时间，弹窗")
                    self.show_off_work_signal.emit()
            except Exception:
                pass

    def close_app(self):
        self.running = False
        self._rest_decision_event.set()
        self._lock_monitor.stop()
        self.tray_icon.hide()
        cleanup_pid_file()
        QApplication.quit()

    def nativeEvent(self, eventType, message):
        WM_WTSSESSION_CHANGE = 0x02B1

        if eventType == "windows_generic_MSG":
            try:
                import ctypes
                from ctypes import wintypes
                msg = ctypes.wintypes.MSG.from_address(message.__int__())
                if msg.message == WM_WTSSESSION_CHANGE:
                    event_type = msg.wParam
                    debug_lock(f"收到 WM_WTSSESSION_CHANGE, wParam={event_type}")
                    if hasattr(self, '_lock_monitor') and self._lock_monitor:
                        self._lock_monitor.on_session_change(event_type)
                    return (True, 0)
            except Exception as e:
                debug_lock(f"nativeEvent 异常: {e}")
        return (False, 0)

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
