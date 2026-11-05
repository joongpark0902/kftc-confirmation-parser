import importlib.util
import time
import unittest
import customtkinter as ctk


class ThemeTransitionTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('theme_transition'),'부드러운 테마 전환 모듈 필요')
        from kftc_gui_v3 import KftcAppV3
        self.app=KftcAppV3();self.app.withdraw();self.app.update()

    def tearDown(self):
        if hasattr(self,'app'):
            self.app._closed=True
            if hasattr(self.app,'_theme_animator'):self.app._theme_animator.cancel()
            for timer in self.app.tk.call('after','info'):self.app.tk.call('after','cancel',timer)
            self.app.destroy()

    def settle(self):
        end=time.monotonic()+2
        def poll():
            if time.monotonic()>=end or (not self.app._theme_animator.running and not self.app._scanning):
                self.app.quit()
            else:self.app.after(20,poll)
        self.app.after(20,poll)
        self.app.mainloop()
        self.assertFalse(self.app._theme_animator.running)

    def test_rapid_toggle_finishes_at_latest_requested_mode_and_preserves_values(self):
        from kftc_engine import PaidItem
        import ui_theme_v2 as theme
        self.app.items=[PaidItem('1','004',company='테마 시험')]
        self.app._fill(self.app.items);self.app.tree.selection_set('0')
        self.app.filter_var.set('입력 유지');self.app.prev_var.set('선택한 조서.xlsx')
        self.app.dark_mode_var.set(True);self.app._toggle_dark_mode()
        self.assertTrue(self.app._theme_animator.running)
        self.app.dark_mode_var.set(False);self.app._toggle_dark_mode()
        self.settle()
        self.assertEqual(ctk.get_appearance_mode(),'Light')
        self.assertEqual(self.app.filter_var.get(),'입력 유지')
        self.assertEqual(self.app.prev_var.get(),'선택한 조서.xlsx')
        self.assertEqual(self.app.tree.selection(),('0',))
        self.assertEqual(self.app.style.lookup('KftcV2.Treeview','background'),theme.SURFACE[0])

    def test_native_style_is_not_reset_when_already_using_clam(self):
        import ui_theme_v2 as theme
        from unittest.mock import patch
        original=self.app.style.theme_use
        writes=[]
        def track(name=None):
            if name is not None:writes.append(name)
            return original() if name is None else original(name)
        with patch.object(self.app.style,'theme_use',side_effect=track):
            self.app.dark_mode_var.set(True);self.app._toggle_dark_mode();self.settle()
        self.assertEqual(writes,[])
        self.assertEqual(self.app.style.lookup('KftcV2.Treeview','background'),theme.SURFACE[1])


if __name__=='__main__':unittest.main()
