import tempfile
import unittest
from pathlib import Path

from kftc_engine import PaidItem, SiteRow


def _store_with_two_companies(folder):
    from print_storage import PrintStore, PdfInfo
    store = PrintStore(folder)
    for no, company in (('1', '회사A'), ('2', '(주)회사B')):
        item = PaidItem(no, '004', company=company, bank_name='국민은행', ref_date='2025-12-31')
        site = SiteRow(no, no, name=company)
        store.set_expected(item, [site])
        p = Path(folder) / f'{no}.pdf'
        p.write_bytes(b'pdf' + no.encode())
        store.record(item, site, p, PdfInfo(company, '', '국민은행', '2025-12-31', False, 1))
    return store


class CompanyFilterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_prepare_inputs_uses_only_selected_company(self):
        from print_parse import prepare_inputs, companies
        store = _store_with_two_companies(self.folder)
        self.assertEqual(companies(store), ['(주)회사B', '회사A'])
        only_a = prepare_inputs(store, '회사A')
        self.assertEqual([p.name for p in only_a.iterdir()], ['0001_1.pdf'])
        only_b = prepare_inputs(store, '회사B')  # (주) 표기 차이는 같은 회사로 본다
        self.assertEqual([p.name for p in only_b.iterdir()], ['0001_2.pdf'])
        self.assertEqual(len(list(prepare_inputs(store).iterdir())), 2)

    def test_sites_with_other_names_stay_with_listed_company(self):
        """사업장 PDF 머리 회사명이 달라도 조회 목록의 회사로 묶는다."""
        from print_storage import PrintStore, PdfInfo
        from print_parse import prepare_inputs, companies
        store = PrintStore(self.folder)
        item = PaidItem('9', '004', company='회사A', bank_name='국민은행', ref_date='2025-12-31')
        sites = [SiteRow('9', '1', name='회사A'), SiteRow('9', '2', name='회사A 망원점')]
        store.set_expected(item, sites)
        for site in sites:
            p = self.folder / f'{site.mngt_num}.pdf'
            p.write_bytes(b'pdf' + site.mngt_num.encode())
            store.record(item, site, p, PdfInfo(site.name, '', '국민은행', '2025-12-31', False, 1))
        self.assertEqual(companies(store), ['회사A'])
        self.assertEqual(len(list(prepare_inputs(store, '회사A').iterdir())), 2)

    def test_unknown_company_has_no_outputs(self):
        from print_parse import prepare_inputs
        store = _store_with_two_companies(self.folder)
        with self.assertRaisesRegex(ValueError, '회사C'):
            prepare_inputs(store, '회사C')

    def test_latest_workbook_is_matched_by_company_name(self):
        import os, time
        from print_parse import latest_for_company, workbook_company
        a1 = self.folder / 'BC조서_회사A_v1_20261101-1000.xlsx'
        b2 = self.folder / 'BC조서_회사B_v2_20261102-1000.xlsx'
        a3 = self.folder / 'BC조서_회사A_v3_20261103-1000.xlsx'
        for i, f in enumerate((a1, b2, a3)):
            f.write_bytes(b'x')
            os.utime(f, (time.time() + i, time.time() + i))
        self.assertEqual(workbook_company(a3), '회사A')
        self.assertEqual(workbook_company(self.folder / '다른이름.xlsx'), '')
        self.assertEqual(latest_for_company(self.folder, '(주)회사A'), a3)
        self.assertEqual(latest_for_company(self.folder, '회사B'), b2)
        self.assertIsNone(latest_for_company(self.folder, '회사C'))


class RegenDialogTest(unittest.TestCase):
    def setUp(self):
        from kftc_gui_v3 import KftcAppV3
        self.tmp = tempfile.TemporaryDirectory()
        self.app = KftcAppV3()
        self.app.withdraw()
        self.app.dir_var.set(self.tmp.name)
        self.app.update()

    def tearDown(self):
        for timer in self.app.tk.call('after', 'info'):
            self.app.tk.call('after', 'cancel', timer)
        self.app.destroy()
        self.tmp.cleanup()

    def _section_title(self, widget):
        """버튼이 들어 있는 구역(패널)의 제목 글자."""
        import customtkinter as ctk
        while widget is not None and widget.master is not self.app:
            widget = widget.master
        texts = []
        def walk(w):
            for c in w.winfo_children():
                if isinstance(c, ctk.CTkLabel):
                    texts.append(c.cget('text'))
                walk(c)
        walk(widget)
        return ' '.join(t for t in texts if isinstance(t, str))

    def test_regenerate_button_moved_to_section_03(self):
        self.assertIn('03  발급된 조회서', self._section_title(self.app.btn_parse))
        self.assertNotIn('이전 BC조서', self._section_title(self.app.btn_parse))
        self.assertFalse(hasattr(self.app, 'prev_entry'))

    def test_help_window_lists_steps(self):
        self.app._open_help()
        self.app.update()
        self.assertTrue(self.app.help_window.winfo_exists())
        self.assertIn('BC조서만 다시 생성', self._all_text(self.app.help_window))

    def _all_text(self, root):
        import customtkinter as ctk
        out = []
        def walk(w):
            for c in w.winfo_children():
                if isinstance(c, ctk.CTkLabel):
                    out.append(str(c.cget('text')))
                walk(c)
        walk(root)
        return '\n'.join(out)

    def test_dialog_defaults_to_typed_company_and_cleans_pasted_path(self):
        _store_with_two_companies(Path(self.tmp.name))
        self.app.filter_var.set('회사B')
        self.app._do_parse_only()
        self.app.update()
        self.assertEqual(self.app._regen_company.get(), '(주)회사B')
        self.assertIn('입력값 이식 없이', self.app._regen_status.cget('text'))
        self.app.prev_var.set('  "C:\\없는 폴더\\BC조서_회사B_v1_20261101-1000.xlsx"  ')
        self.app.update()
        self.assertEqual(self.app.prev_var.get(), 'C:\\없는 폴더\\BC조서_회사B_v1_20261101-1000.xlsx')
        self.assertIn('파일을 찾지 못했', self.app._regen_status.cget('text'))
        # 잘못된 파일이면 생성하지 않고 창을 유지한다
        self.app._regen_start()
        self.app.update()
        self.assertTrue(self.app.regen_window.winfo_exists())


if __name__ == '__main__':
    unittest.main()
