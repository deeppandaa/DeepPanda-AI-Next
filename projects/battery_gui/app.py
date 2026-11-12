import sys
from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget, QLabel, QProgressBar, QPushButton
from PySide6.QtCore import QTimer
from battery import read_status

class BatteryWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('DeepPanda Pil Paneli')
        self.resize(800, 640)
        self.setMinimumSize(650, 550)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.setStyleSheet("""
            QMainWindow { background-color: #0a192f; }
            QWidget { background-color: #0a192f; }
            QLabel { color: #e6f1ff; font-size: 18px; }
            QProgressBar {
                height: 30px;
                background-color: #172a45;
                color: #98FF98;
                text-align: center;
                border: 1px solid #1e3a8a;
            }
            QProgressBar::chunk { background-color: #98FF98; }
            QPushButton {
                background-color: #1e3a8a;
                color: white;
                padding: 10px;
                font-size: 16px;
                border-radius: 5px;
            }
            QPushButton:hover { background-color: #2c5aa0; }
        """)

        self.lbl_title = QLabel('DeepPanda Pil Paneli')
        self.lbl_title.setStyleSheet('font-size: 24px; font-weight: bold; color: #e6f1ff; margin-bottom: 20px;')

        self.lbl_status = QLabel('Durum: Yükleniyor...')
        self.lbl_pct = QLabel('%0')
        self.lbl_pct.setStyleSheet('font-size: 48px; color: #98FF98; font-weight: bold;')
        self.bar = QProgressBar()
        self.bar.setFixedHeight(30)
        self.btn_refresh = QPushButton('Yenile')
        self.lbl_info = QLabel('Bu uygulama sadece izleme yapar, güç ayarı değiştirmez.')
        self.lbl_info.setStyleSheet('color: #888; font-size: 12px;')

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_status)
        layout.addWidget(self.lbl_pct)
        layout.addWidget(self.bar)
        layout.addWidget(self.btn_refresh)
        layout.addWidget(self.lbl_info)

        self.btn_refresh.clicked.connect(self.update_status)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_status)
        self.timer.start(5000)
        self.update_status()

    def update_status(self):
        try:
            data = read_status()
            pct = data['percent']
            status = data['status']
            remaining = data['remaining']

            if pct is None:
                self.lbl_pct.setText('--')
                self.bar.setValue(0)
            else:
                self.lbl_pct.setText(f'%{pct}')
                self.bar.setValue(pct)

            self.lbl_status.setText(f'Durum: {status}')

            if remaining is not None:
                mins = remaining // 60
                secs = remaining % 60
                self.lbl_info.setText(f'Kalan Süre: {mins} dk {secs} sn')
            else:
                self.lbl_info.setText('Bu uygulama sadece izleme yapar, güç ayarı değiştirmez.')

        except OSError as e:
            self.lbl_status.setText(f'Durum: Hata - {e}')
            self.lbl_pct.setText('--')
            self.bar.setValue(0)

if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    w = BatteryWindow()
    w.show()
    sys.exit(app.exec())