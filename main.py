import sys
import os
import subprocess
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QRect, QSize
from PyQt5.QtGui import QPainter, QColor, QFont, QPen, QPixmap, QFontDatabase
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QComboBox, QFileDialog, QMessageBox, QSizePolicy,
    QCheckBox, QRadioButton, QButtonGroup
)
import serial.tools.list_ports

# ----------------------------------------------------------------------
# 路径处理函数 (为 PyInstaller 打包做准备)
# ----------------------------------------------------------------------
def get_base_path():
    """获取程序运行时的基准路径（即可执行文件所在的目录）。"""
    if getattr(sys, 'frozen', False):
        # 打包环境：返回可执行文件所在的目录
        return os.path.dirname(sys.executable)
    else:
        # 开发环境：返回脚本文件所在的目录
        return os.path.dirname(os.path.abspath(__file__))

def get_resource_path(relative_path):
    """根据给定的相对路径，返回资源的绝对路径。"""
    base_path = get_base_path()
    return os.path.join(base_path, relative_path)

# ----------------------------------------------------------------------
# 烧录线程
# ----------------------------------------------------------------------

class BurnThread(QThread):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    log_update = pyqtSignal(str)

    def __init__(self, firmware_path, port, bootloader_path=None, partition_path=None, burn_efuse=False):
        super().__init__()
        self.firmware_path = firmware_path
        self.port = port
        self.bootloader_path = bootloader_path
        self.partition_path = partition_path
        self.burn_efuse = burn_efuse

    def run(self):
        try:
            import shutil
            # 先尝试在 PATH 中查找可执行 esptool
            esptool_exec = shutil.which('esptool.py') or shutil.which('esptool')
            if not esptool_exec:
                # 如果没找到，回退到使用模块方式： python -m esptool
                esptool_exec = [sys.executable, '-m', 'esptool']
            else:
                esptool_exec = [esptool_exec]
            
            # --- 1. eFuse 烧录 (如果需要) ---
            if self.burn_efuse:
                espefuse_exec = shutil.which('espefuse.py') or shutil.which('espefuse')
                if not espefuse_exec:
                    espefuse_exec = [sys.executable, '-m', 'espefuse']
                else:
                    espefuse_exec = [espefuse_exec]

                efuse_base = [
                    '--chip', 'esp32c6',
                    '--port', self.port,
                    '--do-not-confirm'
                ]
                efuse_cmd = espefuse_exec + efuse_base + ['burn_efuse', 'DIS_PAD_JTAG']
                
                self.log_update.emit(f"Running eFuse command: {' '.join(efuse_cmd)}")
                
                # 统一日志处理
                self._run_subprocess(efuse_cmd)
                self.log_update.emit("eFuse burned successfully")
            
            # --- 2. write_flash 命令 ---
            
            base_cmd = [
                '--chip', 'esp32c6',
                '--port', self.port,
                '--baud', '460800'
            ]
            
            write_cmd = esptool_exec + base_cmd + ['write_flash']
            
            if self.bootloader_path:
                write_cmd.extend(['0x0', self.bootloader_path])
            
            if self.partition_path:
                write_cmd.extend(['0x8000', self.partition_path])
            
            write_cmd.extend(['0x10000', self.firmware_path])

            self.log_update.emit(f"Running esptool command: {' '.join(write_cmd)}")
            self._run_subprocess(write_cmd)
            
            self.log_update.emit("Firmware burned successfully")
            self.finished.emit()
            
        except subprocess.CalledProcessError as e:
            # 捕获子进程返回码非零时的错误
            msg = e.stderr.strip() if getattr(e, 'stderr', None) else str(e)
            self.error.emit(f"Command failed (Code {e.returncode}): {msg}")
        except FileNotFoundError:
            self.error.emit("esptool/espefuse not found. Ensure esptool is installed and in your PATH.")
        except Exception as e:
            self.error.emit(f"An unexpected error occurred: {str(e)}")

    def _run_subprocess(self, cmd):
        """执行子进程并实时转发日志"""
        proc = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True, 
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0 # Windows下隐藏控制台窗口
        )
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                print(line)
                self.log_update.emit(line)
        proc.wait()
        if proc.returncode != 0:
            # 捕获日志后，如果返回非零，主动抛出错误
            raise subprocess.CalledProcessError(proc.returncode, cmd)
        

# ----------------------------------------------------------------------
# UI 控件
# ----------------------------------------------------------------------

# PixelButton 和 ImageDisplayWidget 保持不变，但为了代码简洁，
# 这里只保留 PixelButton 以确保功能完整性，其余样式代码省略。

class PixelButton(QWidget):
    clicked = pyqtSignal()
    # ... (PixelButton 类的其余代码保持不变) ...
    def __init__(self, text='', parent=None, color='#8bd3ff', text_color='#000000'):
        super().__init__(parent)
        self._text = text
        self.base_color = QColor(color)
        self.base_color.setAlpha(220)
        self.text_color = QColor(text_color)
        self.pressed = False
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(34)
        self.setContentsMargins(0, 0, 0, 0)
        f = QFont('Courier New', 10)
        try:
            if hasattr(QFont, 'NoAntialias'):
                f.setStyleStrategy(QFont.NoAntialias)
        except Exception:
            pass
        self._font = f
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def mousePressEvent(self, ev):
        self.pressed = True
        self.update()

    def mouseReleaseEvent(self, ev):
        try:
            btn = ev.button()
        except Exception:
            btn = None
        inside = self.rect().contains(ev.pos())
        if self.pressed:
            self.pressed = False
            if (btn is None or btn == Qt.LeftButton) and inside:
                try:
                    self.clicked.emit()
                except Exception:
                    pass
            self.update()

    def connect(self, slot):
        try:
            self.clicked.connect(slot)
        except Exception:
            pass

    def setText(self, text):
        self._text = text
        self.update()

    def sizeHint(self):
        return QSize(80, 34)

    def paintEvent(self, event):
        r = self.rect()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setRenderHint(QPainter.TextAntialiasing, False)

        color = QColor(self.base_color)
        if self.pressed:
            color = color.darker(130)
        elif self.underMouse():
            color = color.lighter(105)

        painter.fillRect(r, color)

        pen = QPen(QColor(0, 0, 0))
        pen.setWidth(3)
        painter.setPen(pen)
        painter.drawRect(r.adjusted(1, 1, -2, -2))

        highlight = QColor(255, 255, 255, 50)
        painter.fillRect(QRect(r.left() + 4, r.top() + 4, r.width() - 8, 6), highlight)

        painter.setPen(self.text_color)
        painter.setFont(self._font)
        painter.drawText(r, Qt.AlignCenter, self._text)


class ImageDisplayWidget(QWidget):
    """显示背景图片的上半部分"""
    def __init__(self, bg_path=None, parent=None):
        super().__init__(parent)
        self.bg_path = bg_path
        self.setMinimumHeight(200)

    def paintEvent(self, event):
        painter = QPainter(self)
        
        # 优化：在 paintEvent 中加载并缩放图片，使用 get_resource_path
        bg = QPixmap(get_resource_path(self.bg_path)) if self.bg_path else None
        
        if bg and not bg.isNull():
            scaled = bg.scaled(self.width(), self.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            # fallback plain background
            painter.fillRect(self.rect(), QColor(30, 30, 30))


class ControlPanelWidget(QWidget):
    """下半部分控制面板"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: rgba(20, 20, 20, 240);")


# ----------------------------------------------------------------------
# 主窗口
# ----------------------------------------------------------------------

class N1Burner(QMainWindow):
    def __init__(self):
        super().__init__()
        # 定义默认资源相对于基准路径的相对路径
        self.default_bootloader_rel_path = os.path.join('bootloader_default', 'bldr.bin')
        self.default_partition_rel_path = os.path.join('partition_table_default', 'table.bin')
        
        self.init_ui()
        self.burn_thread = None
        
    # ... (init_ui 等方法保持不变，只修改资源路径获取部分) ...

    def init_ui(self):
        # ... (UI 初始化代码保持不变) ...
        self.setWindowTitle('N1 Burner')
        self.setGeometry(100, 100, 800, 700)

        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 上半部分：背景图片 - 使用相对路径
        image_widget = ImageDisplayWidget(os.path.join('res', 'bg.png'))
        main_layout.addWidget(image_widget, 1)

        control_panel = ControlPanelWidget()
        control_layout = QVBoxLayout(control_panel)
        control_layout.setContentsMargins(20, 20, 20, 20)
        control_layout.setSpacing(12)
        
        # 统一字体样式
        style_base = "color: white; font-weight: bold;"
        style_box = f"background-color: rgba(0, 0, 0, 180); padding: 6px; border-radius: 8px; {style_base}"
        
        # 首次烧录选项
        first_burn_layout = QHBoxLayout()
        self.first_burn_checkbox = QCheckBox('首次烧录 (First Burn)')
        self.first_burn_checkbox.setStyleSheet("""
            QCheckBox { color: white; font-weight: bold; spacing: 8px; }
            QCheckBox::indicator { width: 18px; height: 18px; background-color: rgba(255, 255, 255, 200); border: 2px solid rgba(0, 0, 0, 140); border-radius: 3px; }
            QCheckBox::indicator:checked { background-color: rgba(139, 211, 255, 255); border: 2px solid rgba(0, 0, 0, 180); }
            QCheckBox::indicator:unchecked:hover { background-color: rgba(255, 255, 255, 240); }
        """)
        self.first_burn_checkbox.stateChanged.connect(self.on_first_burn_changed)
        first_burn_layout.addWidget(self.first_burn_checkbox)
        first_burn_layout.addStretch(1)
        control_layout.addLayout(first_burn_layout)

        # Bootloader 选项
        self.bootloader_widget = QWidget()
        bootloader_main_layout = QVBoxLayout(self.bootloader_widget)
        bootloader_main_layout.setContentsMargins(0, 0, 0, 0)
        bootloader_main_layout.setSpacing(8)
        
        bootloader_radio_layout = QHBoxLayout()
        lbl_bootloader = QLabel('Bootloader:')
        lbl_bootloader.setStyleSheet(f"{style_box} min-width: 100px;")
        lbl_bootloader.setAlignment(Qt.AlignCenter)
        bootloader_radio_layout.addWidget(lbl_bootloader)
        
        self.bootloader_group = QButtonGroup(self)
        self.bootloader_default_radio = QRadioButton('Use default 使用默认')
        self.bootloader_default_radio.setStyleSheet("color: white;")
        self.bootloader_default_radio.setChecked(True)
        self.bootloader_default_radio.toggled.connect(self.on_bootloader_option_changed)
        self.bootloader_group.addButton(self.bootloader_default_radio)
        bootloader_radio_layout.addWidget(self.bootloader_default_radio)
        
        self.bootloader_custom_radio = QRadioButton('Customize 自定义')
        self.bootloader_custom_radio.setStyleSheet("color: white;")
        self.bootloader_group.addButton(self.bootloader_custom_radio)
        bootloader_radio_layout.addWidget(self.bootloader_custom_radio)
        bootloader_radio_layout.addStretch(1)
        bootloader_main_layout.addLayout(bootloader_radio_layout)
        
        bootloader_file_layout = QHBoxLayout()
        bootloader_file_layout.addSpacing(100)
        self.bootloader_input = QLineEdit()
        self.bootloader_input.setReadOnly(True)
        self.bootloader_input.setStyleSheet("background-color: rgba(255,255,255,200); border: 2px solid rgba(0,0,0,140); padding: 6px; border-radius: 3px;")
        self.bootloader_input.setMaximumHeight(32)
        self.bootloader_input.setEnabled(False)
        bootloader_file_layout.addWidget(self.bootloader_input)
        
        self.bootloader_browse_btn = PixelButton('Browse', color='#ffd38b')
        self.bootloader_browse_btn.setMinimumWidth(70)
        self.bootloader_browse_btn.setEnabled(False)
        self.bootloader_browse_btn.connect(self.select_bootloader)
        bootloader_file_layout.addWidget(self.bootloader_browse_btn)
        bootloader_main_layout.addLayout(bootloader_file_layout)
        
        control_layout.addWidget(self.bootloader_widget)
        self.bootloader_widget.setVisible(False)

        # Partition Table 选项
        self.partition_widget = QWidget()
        partition_main_layout = QVBoxLayout(self.partition_widget)
        partition_main_layout.setContentsMargins(0, 0, 0, 0)
        partition_main_layout.setSpacing(8)
        
        partition_radio_layout = QHBoxLayout()
        lbl_partition = QLabel('Partition Table:')
        lbl_partition.setStyleSheet(f"{style_box} min-width: 100px;")
        lbl_partition.setAlignment(Qt.AlignCenter)
        partition_radio_layout.addWidget(lbl_partition)
        
        self.partition_group = QButtonGroup(self)
        self.partition_default_radio = QRadioButton('Use default 使用默认')
        self.partition_default_radio.setStyleSheet("color: white;")
        self.partition_default_radio.setChecked(True)
        self.partition_default_radio.toggled.connect(self.on_partition_option_changed)
        self.partition_group.addButton(self.partition_default_radio)
        partition_radio_layout.addWidget(self.partition_default_radio)
        
        self.partition_custom_radio = QRadioButton('Customize 自定义')
        self.partition_custom_radio.setStyleSheet("color: white;")
        self.partition_group.addButton(self.partition_custom_radio)
        partition_radio_layout.addWidget(self.partition_custom_radio)
        partition_radio_layout.addStretch(1)
        partition_main_layout.addLayout(partition_radio_layout)
        
        partition_file_layout = QHBoxLayout()
        partition_file_layout.addSpacing(100)
        self.partition_input = QLineEdit()
        self.partition_input.setReadOnly(True)
        self.partition_input.setStyleSheet("background-color: rgba(255,255,255,200); border: 2px solid rgba(0,0,0,140); padding: 6px; border-radius: 3px;")
        self.partition_input.setMaximumHeight(32)
        self.partition_input.setEnabled(False)
        partition_file_layout.addWidget(self.partition_input)
        
        self.partition_browse_btn = PixelButton('Browse', color='#ffd38b')
        self.partition_browse_btn.setMinimumWidth(70)
        self.partition_browse_btn.setEnabled(False)
        self.partition_browse_btn.connect(self.select_partition)
        partition_file_layout.addWidget(self.partition_browse_btn)
        partition_main_layout.addLayout(partition_file_layout)
        
        control_layout.addWidget(self.partition_widget)
        self.partition_widget.setVisible(False)

        # 熔丝位选项
        self.efuse_widget = QWidget()
        efuse_main_layout = QVBoxLayout(self.efuse_widget)
        efuse_main_layout.setContentsMargins(0, 0, 0, 0)
        efuse_main_layout.setSpacing(0)
        
        efuse_layout = QHBoxLayout()
        self.efuse_checkbox = QCheckBox('Burn eFuse - DIS_PAD_JTAG (烧录熔丝位 - 禁用 JTAG)')
        # 优化颜色，使用更醒目的警告色
        self.efuse_checkbox.setStyleSheet("""
            QCheckBox { color: #ff6666; font-weight: bold; spacing: 8px; }
            QCheckBox::indicator { width: 18px; height: 18px; background-color: rgba(255, 255, 255, 200); border: 2px solid rgba(255, 60, 60, 180); border-radius: 3px; }
            QCheckBox::indicator:checked { background-color: rgba(255, 60, 60, 255); border: 2px solid rgba(200, 0, 0, 200); }
            QCheckBox::indicator:unchecked:hover { background-color: rgba(255, 255, 255, 240); }
        """)
        efuse_layout.addWidget(self.efuse_checkbox)
        efuse_layout.addStretch(1)
        efuse_main_layout.addLayout(efuse_layout)
        
        control_layout.addWidget(self.efuse_widget)
        self.efuse_widget.setVisible(False)

        # Firmware selection
        firmware_layout = QHBoxLayout()
        lbl_fw = QLabel('Firmware:')
        lbl_fw.setStyleSheet(f"{style_box} min-width: 80px;")
        lbl_fw.setAlignment(Qt.AlignCenter)
        firmware_layout.addWidget(lbl_fw)

        self.firmware_input = QLineEdit()
        self.firmware_input.setReadOnly(True)
        self.firmware_input.setStyleSheet("background-color: rgba(255,255,255,200); border: 2px solid rgba(0,0,0,140); padding: 6px; border-radius: 3px;")
        self.firmware_input.setMaximumHeight(32)
        firmware_layout.addWidget(self.firmware_input)

        self.browse_btn = PixelButton('Browse', color='#ffd38b')
        self.browse_btn.setMinimumWidth(70)
        self.browse_btn.connect(self.select_firmware)
        firmware_layout.addWidget(self.browse_btn)

        control_layout.addLayout(firmware_layout)

        # Serial port selection
        port_layout = QHBoxLayout()
        lbl_port = QLabel('Serial Port:')
        lbl_port.setStyleSheet(f"{style_box} min-width: 80px;")
        lbl_port.setAlignment(Qt.AlignCenter)
        port_layout.addWidget(lbl_port)

        self.port_combo = QComboBox()
        self.port_combo.setStyleSheet("background-color: rgba(255,255,255,200); border: 2px solid rgba(0,0,0,140); padding: 4px; border-radius: 3px;")
        self.port_combo.setMaximumHeight(32)
        self.refresh_ports()
        port_layout.addWidget(self.port_combo)

        self.refresh_btn = PixelButton('Refresh', color='#9be28b')
        self.refresh_btn.setMinimumWidth(70)
        self.refresh_btn.connect(self.refresh_ports)
        port_layout.addWidget(self.refresh_btn)

        control_layout.addLayout(port_layout)

        # Log display
        log_layout = QHBoxLayout()
        lbl_log_title = QLabel('Log:')
        lbl_log_title.setStyleSheet(f"color: #ffffff; {style_box} min-width: 40px;")
        lbl_log_title.setAlignment(Qt.AlignCenter)
        lbl_log_title.setFixedWidth(40)
        log_layout.addWidget(lbl_log_title)
        
        self.log_label = QLabel('Ready')
        self.log_label.setStyleSheet(
            "color: #88ff88; "
            "background-color: rgba(0, 0, 0, 180); "
            "border: 1px solid rgba(100, 100, 100, 140); "
            "padding: 6px; "
            "border-radius: 8px; "
            "font-family: monospace;"
        )
        self.log_label.setAlignment(Qt.AlignCenter)
        self.log_label.setWordWrap(True)
        self.log_label.setMaximumHeight(60)
        log_layout.addWidget(self.log_label)
        control_layout.addLayout(log_layout)

        # Burn button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        self.burn_btn = PixelButton('Burn Firmware', color='#ff8b8b')
        self.burn_btn.setMinimumWidth(150)
        self.burn_btn.connect(self.burn_firmware)
        btn_layout.addWidget(self.burn_btn)
        btn_layout.addStretch(1)
        control_layout.addLayout(btn_layout)

        control_layout.addStretch(0)

        main_layout.addWidget(control_panel, 0)

        self.setCentralWidget(main_widget)

    # ... (select_firmware, select_bootloader, select_partition,
    # on_first_burn_changed, on_bootloader_option_changed, on_partition_option_changed,
    # refresh_ports 保持不变) ...

    def select_firmware(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, 'Select Firmware', '', 'Bin Files (*.bin);;All Files (*)'
        )
        if file_path:
            self.firmware_input.setText(file_path)

    def select_bootloader(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, 'Select Bootloader', '', 'Bin Files (*.bin);;All Files (*)'
        )
        if file_path:
            self.bootloader_input.setText(file_path)

    def select_partition(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, 'Select Partition Table', '', 'Bin Files (*.bin);;All Files (*)'
        )
        if file_path:
            self.partition_input.setText(file_path)

    def on_first_burn_changed(self, state):
        is_first_burn = state == Qt.Checked
        self.bootloader_widget.setVisible(is_first_burn)
        self.partition_widget.setVisible(is_first_burn)
        self.efuse_widget.setVisible(is_first_burn)
        if not is_first_burn:
            self.efuse_checkbox.setChecked(False)

    def on_bootloader_option_changed(self, checked):
        if checked:
            self.bootloader_input.setEnabled(False)
            self.bootloader_browse_btn.setEnabled(False)
            self.bootloader_input.clear()
        else:
            self.bootloader_input.setEnabled(True)
            self.bootloader_browse_btn.setEnabled(True)

    def on_partition_option_changed(self, checked):
        if checked:
            self.partition_input.setEnabled(False)
            self.partition_browse_btn.setEnabled(False)
            self.partition_input.clear()
        else:
            self.partition_input.setEnabled(True)
            self.partition_browse_btn.setEnabled(True)

    def refresh_ports(self):
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        if not ports:
            self.port_combo.addItem('No ports available')
            self.port_combo.setEnabled(False)
        else:
            self.port_combo.setEnabled(True)
            for p in ports:
                self.port_combo.addItem(p.device)

    def burn_firmware(self):
        firmware = self.firmware_input.text()
        port = self.port_combo.currentText()

        if not firmware or not os.path.exists(firmware):
            QMessageBox.warning(self, 'Error', 'Please select a valid firmware file')
            return

        if not port or port == 'No ports available':
            QMessageBox.warning(self, 'Error', 'Please select a serial port')
            return

        # 处理首次烧录选项，并使用 get_resource_path() 获取默认资源路径
        bootloader_path = None
        partition_path = None
        
        if self.first_burn_checkbox.isChecked():
            # 处理 bootloader
            if self.bootloader_default_radio.isChecked():
                # 使用 get_resource_path
                bootloader_path = get_resource_path(self.default_bootloader_rel_path)
                if not os.path.exists(bootloader_path):
                    QMessageBox.warning(self, 'Error', f'Default bootloader not found at:\n{bootloader_path}')
                    return
            else:
                bootloader_path = self.bootloader_input.text()
                if not bootloader_path or not os.path.exists(bootloader_path):
                    QMessageBox.warning(self, 'Error', 'Please select a valid bootloader file')
                    return
            
            # 处理分区表
            if self.partition_default_radio.isChecked():
                # 使用 get_resource_path
                partition_path = get_resource_path(self.default_partition_rel_path)
                if not os.path.exists(partition_path):
                    QMessageBox.warning(self, 'Error', f'Default partition table not found at:\n{partition_path}')
                    return
            else:
                partition_path = self.partition_input.text()
                if not partition_path or not os.path.exists(partition_path):
                    QMessageBox.warning(self, 'Error', 'Please select a valid partition table file')
                    return

        # 获取熔丝位烧录选项
        burn_efuse = self.efuse_checkbox.isChecked()
        
        if burn_efuse:
            reply = QMessageBox.warning(
                self, 
                'Warning - eFuse Burn', 
                'You are about to burn eFuse (DIS_PAD_JTAG).\n\n'
                'This operation is IRREVERSIBLE!\n'
                'JTAG debugging will be permanently disabled.\n\n'
                'Are you sure you want to continue?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                return

        self.burn_btn.setEnabled(False)
        self.burn_thread = BurnThread(firmware, port, bootloader_path, partition_path, burn_efuse)
        self.burn_thread.finished.connect(self.on_burn_finished)
        self.burn_thread.error.connect(self.on_burn_error)
        self.burn_thread.log_update.connect(self.on_log_update)
        self.burn_thread.start()

    def on_burn_finished(self):
        QMessageBox.information(self, 'Success', 'Firmware burned successfully!')
        self.burn_btn.setEnabled(True)

    def on_burn_error(self, error):
        QMessageBox.critical(self, 'Error', f'Burn failed: {error}')
        self.burn_btn.setEnabled(True)

    def on_log_update(self, message):
        self.log_label.setText(message)


def try_load_pixel_font(path):
    # 路径改为使用 get_resource_path
    abs_path = get_resource_path(path)
    if os.path.exists(abs_path):
        QFontDatabase.addApplicationFont(abs_path)


if __name__ == '__main__':
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    # 示例：假设字体文件放在 project/fonts/
    # try_load_pixel_font(os.path.join('fonts', 'PressStart2P-Regular.ttf'))

    app = QApplication(sys.argv)
    burner = N1Burner()
    burner.show()
    sys.exit(app.exec_())