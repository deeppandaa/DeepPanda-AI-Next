import os, sys, unittest
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette
from app import Window, ChartWidget

class TestExpensePanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        self.window = Window()

    def tearDown(self):
        self.window.close()
        del self.window

    def test_initial_state_total_zero(self):
        self.assertEqual(self.window.total_label.text(), "0")

    def test_initial_table_empty(self):
        self.assertEqual(self.window.table.rowCount(), 0)

    def test_add_valid_expense(self):
        self.window.desc_edit.setText("Yemek")
        self.window.amount_edit.setText("1500")
        self.window.add_btn.click()
        self.assertEqual(self.window.table.rowCount(), 1)
        self.assertEqual(self.window.total_label.text(), "1500")
        self.assertEqual(self.window.error_label.text(), "")

    def test_add_multiple_expenses(self):
        self.window.desc_edit.setText("A")
        self.window.amount_edit.setText("100")
        self.window.add_btn.click()
        self.window.desc_edit.setText("B")
        self.window.amount_edit.setText("200")
        self.window.add_btn.click()
        self.assertEqual(self.window.table.rowCount(), 2)
        self.assertEqual(self.window.total_label.text(), "300")

    def test_remove_selected_expense(self):
        self.window.desc_edit.setText("A")
        self.window.amount_edit.setText("100")
        self.window.add_btn.click()
        self.window.desc_edit.setText("B")
        self.window.amount_edit.setText("200")
        self.window.add_btn.click()
        self.window.table.selectRow(0)
        self.window.remove_expense()
        self.assertEqual(self.window.table.rowCount(), 1)
        self.assertEqual(self.window.total_label.text(), "200")

    def test_remove_no_selection(self):
        initial_rows = self.window.table.rowCount()
        self.window.remove_expense()
        self.assertEqual(self.window.table.rowCount(), initial_rows)

    def test_add_blank_description(self):
        self.window.desc_edit.setText("   ")
        self.window.amount_edit.setText("100")
        self.window.add_btn.click()
        self.assertEqual(self.window.table.rowCount(), 0)
        self.assertNotEqual(self.window.error_label.text(), "")

    def test_add_zero_amount(self):
        self.window.desc_edit.setText("A")
        self.window.amount_edit.setText("0")
        self.window.add_btn.click()
        self.assertEqual(self.window.table.rowCount(), 0)
        self.assertNotEqual(self.window.error_label.text(), "")

    def test_add_negative_amount(self):
        self.window.desc_edit.setText("A")
        self.window.amount_edit.setText("-100")
        self.window.add_btn.click()
        self.assertEqual(self.window.table.rowCount(), 0)
        self.assertNotEqual(self.window.error_label.text(), "")

    def test_add_float_amount(self):
        self.window.desc_edit.setText("A")
        self.window.amount_edit.setText("10.5")
        self.window.add_btn.click()
        self.assertEqual(self.window.table.rowCount(), 0)
        self.assertNotEqual(self.window.error_label.text(), "")

    def test_add_unicode_amount(self):
        self.window.desc_edit.setText("A")
        self.window.amount_edit.setText("١٠٠")
        self.window.add_btn.click()
        self.assertEqual(self.window.table.rowCount(), 0)
        self.assertNotEqual(self.window.error_label.text(), "")

    def test_chart_widget_empty(self):
        cw = ChartWidget()
        cw.set_expenses([])
        self.assertIsNotNone(cw)

    def test_remove_button_click(self):
        remove_btn = self.window.findChild(object, "remove")
        self.assertIsNotNone(remove_btn)
        self.window.desc_edit.setText("A")
        self.window.amount_edit.setText("100")
        self.window.add_btn.click()
        self.window.desc_edit.setText("B")
        self.window.amount_edit.setText("200")
        self.window.add_btn.click()
        self.window.table.selectRow(0)
        remove_btn.click()
        self.assertEqual(self.window.table.rowCount(), 1)
        self.assertEqual(self.window.total_label.text(), "200")

    def test_no_selection_button(self):
        self.window.desc_edit.setText("A")
        self.window.amount_edit.setText("100")
        self.window.add_btn.click()
        initial_rows = self.window.table.rowCount()
        initial_total = self.window.total_label.text()
        remove_btn = self.window.findChild(object, "remove")
        self.window.table.clearSelection()
        remove_btn.click()
        self.assertEqual(self.window.table.rowCount(), initial_rows)
        self.assertEqual(self.window.total_label.text(), initial_total)

    def test_dark_theme(self):
        pal = self.window.palette()
        bg = pal.color(QPalette.Window)
        self.assertEqual((bg.red(), bg.green(), bg.blue()), (0, 31, 63))

    def test_duplicates(self):
        self.window.desc_edit.setText("A")
        self.window.amount_edit.setText("100")
        self.window.add_btn.click()
        self.window.desc_edit.setText("A")
        self.window.amount_edit.setText("100")
        self.window.add_btn.click()
        self.assertEqual(self.window.table.rowCount(), 2)
        self.assertEqual(self.window.total_label.text(), "200")

    def test_source_caps(self):
        with open('app.py', 'r', encoding='utf-8') as f:
            app_src = f.read()
        with open('test_app.py', 'r', encoding='utf-8') as f:
            test_src = f.read()
        self.assertLess(len(app_src), 4300)
        self.assertLess(len(test_src), 3100)

    def test_fullwidth_rejected(self):
        initial_rows = self.window.table.rowCount()
        initial_total = self.window.total_label.text()
        self.window.desc_edit.setText("A")
        self.window.amount_edit.setText("１００")
        self.window.add_btn.click()
        self.assertEqual(self.window.table.rowCount(), initial_rows)
        self.assertEqual(self.window.total_label.text(), initial_total)
        self.assertNotEqual(self.window.error_label.text(), "")

if __name__ == '__main__':
    unittest.main()
