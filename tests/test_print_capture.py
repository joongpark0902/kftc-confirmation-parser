import importlib.util
import tempfile
import unittest
from pathlib import Path

from kftc_engine import PaidItem,SiteRow


class CaptureTest(unittest.TestCase):
    def setUp(self):
        from print_storage import PrintCapture,PrintStore,PdfInfo
        self.Capture,self.Store=PrintCapture,PrintStore
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.inbox=self.root/'inbox'; self.inbox.mkdir()
        self.item=PaidItem('M1','004',company='회사A',bank_name='국민은행',ref_date='2025-12-31')
        self.site=SiteRow('M1','1',name='회사A',biz_no='1234567890')
        self.info=PdfInfo('회사A','1234567890','국민은행','2025-12-31',False,2)

    def tearDown(self): self.tmp.cleanup()

    def test_ignores_existing_files_and_waits_for_stable_new_pdf(self):
        (self.inbox/'old.pdf').write_bytes(b'old')
        capture=self.Capture(self.inbox,inspect=lambda _:self.info)
        self.assertIsNone(capture.poll(self.item,self.site))
        path=self.inbox/'arbitrary-name.pdf'; path.write_bytes(b'new')
        self.assertIsNone(capture.poll(self.item,self.site))
        path.write_bytes(b'new still writing')
        self.assertIsNone(capture.poll(self.item,self.site))
        self.assertIsNone(capture.poll(self.item,self.site))
        self.assertEqual(capture.poll(self.item,self.site)[0],path.resolve())

    def test_multiple_new_files_and_wrong_document_are_rejected(self):
        capture=self.Capture(self.inbox,inspect=lambda _:self.info,stable_polls=1)
        (self.inbox/'one.pdf').write_bytes(b'one');(self.inbox/'two.pdf').write_bytes(b'two')
        with self.assertRaises(ValueError): capture.poll(self.item,self.site)

    def test_copy_preserves_source_and_does_not_overwrite_different_pdf(self):
        source=self.inbox/'source.pdf';source.write_bytes(b'new')
        store=self.Store(self.root/'dest');store.set_expected(self.item,[self.site])
        capture=self.Capture(self.inbox,inspect=lambda _:self.info)
        output=capture.save(self.item,self.site,source,self.info,store)
        self.assertEqual(output.read_bytes(),b'new');self.assertTrue(source.exists())
        source.write_bytes(b'changed source')
        other=capture.save(self.item,self.site,source,self.info,store)
        self.assertNotEqual(output,other);self.assertEqual(output.read_bytes(),b'new')

    def test_invalid_pdf_is_not_completed(self):
        from print_storage import read_pdf_info
        source=self.inbox/'broken.pdf';source.write_bytes(b'%PDF-1.4 not ready')
        with self.assertRaises(ValueError): read_pdf_info(source)


if __name__=='__main__':unittest.main()
