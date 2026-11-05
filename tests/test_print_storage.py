"""출력 이력은 실제 파일 및 문서 식별값과 일치해야 중복으로 인정한다."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

from kftc_engine import PaidItem, SiteRow


class PrintStorageTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('print_storage'), '출력 저장 모듈 필요')
        from print_storage import PrintStore, PdfInfo
        self.PrintStore, self.PdfInfo = PrintStore, PdfInfo
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.item = PaidItem('M1', '004', company='회사A', bank_name='국민은행', ref_date='2025-12-31')
        self.site = SiteRow('M1', '1', name='회사A', biz_no='123-45-67890')
        self.info = self.PdfInfo('회사A','1234567890','국민은행','2025-12-31',False,2)

    def tearDown(self):
        if hasattr(self,'temp'): self.temp.cleanup()

    def test_valid_output_is_duplicate_but_missing_or_changed_file_is_not(self):
        store = self.PrintStore(self.root)
        store.set_expected(self.item,[self.site])
        source = self.root/'source.pdf'
        source.write_bytes(b'pdf original')
        store.record(self.item,self.site,source,self.info)
        self.assertEqual(store.status(self.item).label,'출력본 있음')
        source.write_bytes(b'pdf changed')
        self.assertEqual(store.status(self.item).label,'확인 필요')
        source.unlink()
        self.assertNotEqual(store.status(self.item).label,'출력본 있음')

    def test_view_only_record_never_blocks_print_output(self):
        store=self.PrintStore(self.root)
        store.set_expected(self.item,[self.site])
        source=self.root/'view.pdf'; source.write_bytes(b'view')
        info=self.PdfInfo('회사A','1234567890','국민은행','2025-12-31',True,2)
        store.record(self.item,self.site,source,info,kind='view')
        self.assertEqual(store.status(self.item).label,'열람용만 있음')
        self.assertFalse(store.has_output(self.item,self.site))

    def test_partial_sites_and_unknown_completeness(self):
        store=self.PrintStore(self.root)
        second=SiteRow('M1','2',name='회사A 지점')
        store.set_expected(self.item,[self.site,second])
        source=self.root/'out.pdf'; source.write_bytes(b'print')
        store.record(self.item,self.site,source,self.info)
        self.assertEqual(store.status(self.item).label,'일부 저장')
        other=self.PrintStore(self.root/'other')
        self.assertEqual(other.status(self.item).label,'미저장')

    def test_record_outside_destination_is_rejected(self):
        store=self.PrintStore(self.root/'destination')
        source=self.root/'elsewhere.pdf'; source.write_bytes(b'elsewhere')
        with self.assertRaises(ValueError): store.record(self.item,self.site,source,self.info)

    def test_identity_mismatch_and_view_cannot_be_registered_as_output(self):
        store=self.PrintStore(self.root)
        source=self.root/'source.pdf'; source.write_bytes(b'pdf')
        wrong=self.PdfInfo('회사B','9999999999','국민은행','2025-12-31',False,2)
        with self.assertRaises(ValueError): store.record(self.item,self.site,source,wrong)
        view=self.PdfInfo('회사A','1234567890','국민은행','2025-12-31',True,2)
        with self.assertRaises(ValueError): store.record(self.item,self.site,source,view)

    def test_changed_site_identity_does_not_skip_existing_output(self):
        store=self.PrintStore(self.root)
        source=self.root/'source.pdf';source.write_bytes(b'pdf')
        store.record(self.item,self.site,source,self.info)
        changed=SiteRow('M1','1',name='회사B',biz_no='9999999999')
        self.assertFalse(store.has_output(self.item,changed))


if __name__=='__main__': unittest.main()
