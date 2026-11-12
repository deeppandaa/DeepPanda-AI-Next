import sys
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QLabel, QLineEdit, QPushButton)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QFont

class ChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 200)
        self.setMaximumHeight(250)
        self.expenses = []
        self.setFixedWidth(300)

    def set_expenses(self, amounts):
        self.expenses = amounts
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(0, 31, 63))
        if not self.expenses:
            p.setPen(QColor(100, 100, 100))
            p.setFont(QFont("Arial", 12))
            p.drawText(self.rect(), Qt.AlignCenter, "Veri Yok")
            return
        max_val = max(self.expenses) or 1
        pad = 20
        ch = self.height() - pad * 2
        bw = (self.width() - pad * 2) / len(self.expenses)
        for i, val in enumerate(self.expenses):
            bh = (val / max_val) * ch
            x = pad + i * bw
            y = self.height() - pad - bh
            p.setPen(QColor(0, 255, 255))
            p.setBrush(QColor(0, 180, 180))
            p.drawRect(int(x), int(y), int(bw - 4), int(bh))
            p.setPen(QColor(255, 255, 255))
            p.setFont(QFont("Arial", 8))
            p.drawText(int(x), int(y - 5), int(bw), 10, Qt.AlignCenter, str(val))
        p.end()

class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('DeepPanda Harcama Paneli')
        self.setMinimumSize(760, 520)
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #001f3f; color: white; }
            QLineEdit { background-color: #003366; color: #00ffff; border: 1px solid #00ffff; }
            QPushButton { background-color: #0074D9; color: white; border: 1px solid #00ffff; padding: 5px; }
            QPushButton:hover { background-color: #00ffff; color: #001f3f; }
            QTableWidget { background-color: #002244; color: #00ffff; gridline-color: #00ffff; }
            QLabel#total { font-size: 18px; color: #00ffff; }
            QLabel#error { color: red; }
        """)
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        input_layout = QHBoxLayout()
        self.desc_edit = QLineEdit()
        self.desc_edit.setObjectName("description")
        self.desc_edit.setPlaceholderText("Açıklama")
        self.amount_edit = QLineEdit()
        self.amount_edit.setObjectName("amount")
        self.amount_edit.setPlaceholderText("Tutar (Kuruş)")
        self.add_btn = QPushButton("Ekle")
        self.add_btn.setObjectName("add")
        input_layout.addWidget(self.desc_edit)
        input_layout.addWidget(self.amount_edit)
        input_layout.addWidget(self.add_btn)
        main_layout.addLayout(input_layout)

        table_layout = QHBoxLayout()
        self.table = QTableWidget(0, 2)
        self.table.setObjectName("table")
        self.table.setHorizontalHeaderLabels(["Açıklama", "Tutar (Kuruş)"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        table_layout.addWidget(self.table)

        self.chart_widget = ChartWidget()
        self.chart_widget.setObjectName("chart")
        chart_container = QWidget()
        chart_layout = QVBoxLayout(chart_container)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        chart_layout.addWidget(self.chart_widget)
        table_layout.addWidget(chart_container)
        main_layout.addLayout(table_layout)

        bottom_layout = QHBoxLayout()
        self.total_label = QLabel("0")
        self.total_label.setObjectName("total")
        self.error_label = QLabel("")
        self.error_label.setObjectName("error")
        self.error_label.setStyleSheet("color: red;")
        self.remove_btn = QPushButton("Sil")
        self.remove_btn.setObjectName("remove")
        bottom_layout.addWidget(self.total_label)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.remove_btn)
        bottom_layout.addWidget(self.error_label)
        main_layout.addLayout(bottom_layout)

        self.add_btn.clicked.connect(self.add_expense)
        self.remove_btn.clicked.connect(self.remove_expense)
        self.update_total()
        self.chart_widget.set_expenses([])

    def add_expense(self):
        desc = self.desc_edit.text().strip()
        amount_str = self.amount_edit.text().strip()
        if not desc:
            self.error_label.setText("Açıklama boş olamaz.")
            return
        if not amount_str or not all(c in '0123456789' for c in amount_str):
            self.error_label.setText("Tutar pozitif tam sayı olmalıdır.")
            return
        amount = int(amount_str)
        if amount == 0:
            self.error_label.setText("Tutar pozitif tam sayı olmalıdır.")
            return
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(desc))
        self.table.setItem(row, 1, QTableWidgetItem(str(amount)))
        self.desc_edit.clear()
        self.amount_edit.clear()
        self.error_label.setText("")
        self.update_total()

    def remove_expense(self):
        selected = self.table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        self.table.removeRow(row)
        self.update_total()

    def update_total(self):
        total = 0
        amounts = []
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 1)
            if item:
                try:
                    val = int(item.text())
                    total += val
                    amounts.append(val)
                except ValueError:
                    pass
        self.total_label.setText(str(total))
        self.chart_widget.set_expenses(amounts)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = Window()
    window.show()
    sys.exit(app.exec())
