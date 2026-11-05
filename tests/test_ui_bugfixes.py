import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs,urlsplit


class SearchEncodingTest(unittest.TestCase):
    def test_company_name_and_reserved_characters_roundtrip_in_euckr(self):
        from kftc_engine import KftcEngine
        class Session:
            def get(self,path):self.path=path;return '<html></html>'
        session=Session()
        with tempfile.TemporaryDirectory() as td:
            engine=KftcEngine(session,Path(td),log_fn=lambda _:None)
            engine.list_paid(filter_val='테스트 & 회사+지점')
            self.assertTrue(session.path.isascii(),'검색어는 ASCII 퍼센트 인코딩 URL이어야 합니다')
            query=parse_qs(urlsplit(session.path).query,encoding='euc-kr',errors='strict')
            self.assertEqual(query['filter_val'],['테스트 & 회사+지점'])
            self.assertEqual(query['filter_sel'],['E'])


class LaunchTest(unittest.TestCase):
    def test_launch_uses_shell_elevation_instead_of_createprocess(self):
        import mop_bridge
        with tempfile.TemporaryDirectory() as td:
            exe=Path(td)/'모두의 프린터.exe';exe.write_bytes(b'test executable')
            with patch.object(mop_bridge.os,'startfile') as start, patch.object(mop_bridge.subprocess,'Popen',side_effect=AssertionError('일반 실행 금지')):
                mop_bridge.launch(exe)
            self.assertEqual(start.call_args.args,(str(exe),'runas'))
            self.assertEqual(start.call_args.kwargs['cwd'],str(exe.parent))

    def test_cancelled_elevation_has_readable_message(self):
        import mop_bridge
        with tempfile.TemporaryDirectory() as td:
            exe=Path(td)/'mop.exe';exe.write_bytes(b'test')
            error=OSError('cancelled');error.winerror=1223
            with patch.object(mop_bridge.os,'startfile',side_effect=error):
                with self.assertRaisesRegex(RuntimeError,'취소'):
                    mop_bridge.launch(exe)


class WindowTest(unittest.TestCase):
    def setUp(self):
        from kftc_gui_v3 import KftcAppV3
        self.app=KftcAppV3();self.app.withdraw();self.app.update()

    def tearDown(self):
        for timer in self.app.tk.call('after','info'):self.app.tk.call('after','cancel',timer)
        self.app.destroy()

    def test_settings_reuses_owned_window_and_preserves_unsaved_text(self):
        self.app._open_print_settings();self.app.update()
        windows=[w for w in self.app.winfo_children() if w.winfo_toplevel() is w]
        self.assertEqual(len(windows),1)
        win=windows[0]
        self.assertEqual(str(win.transient()),str(self.app))
        entry=win.grid_slaves(row=0,column=1)[0]
        entry.delete(0,'end');entry.insert(0,'입력 중인 설정')
        self.app._open_print_settings();self.app.update()
        windows2=[w for w in self.app.winfo_children() if w.winfo_toplevel() is w]
        self.assertEqual(windows2,[win])
        self.assertEqual(entry.get(),'입력 중인 설정')

    def test_company_filter_is_in_listing_not_storage_panel(self):
        panels=self.app.grid_slaves(row=3,column=0)
        listing=panels[0]
        fields=[]
        def walk(widget):
            for child in widget.winfo_children():
                if hasattr(child,'cget'):
                    try:
                        if child.cget('textvariable')==self.app.filter_var:fields.append(child)
                    except Exception:pass
                walk(child)
        walk(listing)
        self.assertTrue(fields,'회사명 입력은 목록 패널 안에 있어야 합니다')


if __name__=='__main__':unittest.main()
