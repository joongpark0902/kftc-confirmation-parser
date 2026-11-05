import importlib.util
import tempfile
import unittest
from pathlib import Path
from kftc_engine import PaidItem,SiteRow


class GuiV3Test(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('kftc_gui_v3'),'v3 GUI 필요')
        from kftc_gui_v3 import KftcAppV3
        self.tmp=tempfile.TemporaryDirectory()
        self.app=KftcAppV3()
        self.app.withdraw();self.app.dir_var.set(self.tmp.name);self.app.update()

    def tearDown(self):
        if hasattr(self,'app'):
            for timer in self.app.tk.call('after','info'):self.app.tk.call('after','cancel',timer)
            self.app.destroy();self.tmp.cleanup()

    def test_status_column_and_selection_counts_follow_saved_output(self):
        from print_storage import PrintStore,PdfInfo
        item=PaidItem('1','004',company='회사A',bank_name='국민은행',ref_date='2025-12-31')
        site=SiteRow('1','1',name='회사A')
        self.app.items=[item];self.app._fill([item])
        self.assertIn('storage',self.app.tree['columns'])
        self.app.tree.selection_set('0');self.app.update()
        self.assertIn('추가 저장 1',self.app.selection_var.get())
        store=PrintStore(Path(self.tmp.name));store.set_expected(item,[site])
        p=Path(self.tmp.name)/'out.pdf';p.write_bytes(b'pdf')
        store.record(item,site,p,PdfInfo('회사A','','국민은행','2025-12-31',False,1))
        self.app._apply_store(store);self.app.update()
        self.assertEqual(self.app.tree.set('0','storage'),'출력본 있음')
        self.assertIn('중복 1',self.app.selection_var.get())
        self.assertIn('추가 저장 0',self.app.selection_var.get())

    def test_changed_destination_clears_previous_duplicate_status(self):
        item=PaidItem('1','004',company='회사A',bank_name='국민은행',ref_date='2025-12-31')
        self.app.items=[item];self.app._fill([item]);self.app.tree.selection_set('0')
        self.app.dir_var.set(str(Path(self.tmp.name)/'other'));self.app.update()
        self.assertIn('확인 필요',self.app.tree.set('0','storage'))
        self.assertNotIn('중복 1',self.app.selection_var.get())

    def test_adding_storage_column_preserves_original_headers(self):
        self.assertEqual(self.app.tree.heading('company','text'),'회사명')
        self.assertEqual(self.app.tree.heading('ref','text'),'조회기준일')
        self.assertEqual(self.app.tree.heading('bank','text'),'금융기관')


if __name__=='__main__':unittest.main()
