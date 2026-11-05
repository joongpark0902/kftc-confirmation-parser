"""실제 Tk 위젯으로 v2 테마·선택·작업 잠금을 확인. 외부 요청 없음."""
import importlib
import unittest

from kftc_engine import PaidItem


class GuiV2Test(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('kftc_gui_v2'), 'v2 GUI가 있어야 합니다')
        from kftc_gui_v2 import KftcAppV2
        self.app = KftcAppV2()
        self.app.withdraw()
        self.app.update()

    def tearDown(self):
        if hasattr(self, 'app'):
            for timer in self.app.tk.call('after', 'info'):
                self.app.tk.call('after', 'cancel', timer)
            self.app.destroy()

    def test_theme_switch_updates_native_table_and_preserves_selection(self):
        import ui_theme_v2 as theme
        self.app._fill([PaidItem('1', '004', company='테스트회사', bank_name='국민은행')])
        self.app.tree.selection_set('0')
        self.app.dark_mode_var.set(True)
        self.app._toggle_dark_mode()
        self.app.update()
        self.assertEqual(self.app.tree.selection(), ('0',))
        self.assertEqual(self.app.style.lookup('KftcV2.Treeview', 'background'), theme.color(theme.SURFACE))
        self.assertEqual(self.app.tree.item('0', 'values')[1], '테스트회사')

    def test_busy_disables_mutating_inputs_and_restores_buttons(self):
        self.app._set_busy(True)
        self.app.update()
        for widget in self.app.job_controls:
            self.assertEqual(widget.cget('state'), 'disabled')
        self.app._set_busy(False)
        self.app.update()
        for widget in self.app.job_controls:
            self.assertEqual(widget.cget('state'), 'normal')
        self.assertEqual(self.app.btn_stop.cget('state'), 'disabled')

    def test_empty_and_filled_list_selection_counts(self):
        self.assertTrue(self.app.empty_label.winfo_manager())
        self.app._fill([PaidItem('1', '004', company='테스트회사', bank_name='국민은행')])
        self.app.tree.selection_set('0')
        self.app.update()
        self.assertFalse(self.app.empty_label.winfo_manager())
        self.assertIn('1', self.app.selection_var.get())
        self.app._fill([])
        self.app.update()
        self.assertTrue(self.app.empty_label.winfo_manager())
        self.assertIn('0', self.app.selection_var.get())


if __name__ == '__main__':
    unittest.main()
