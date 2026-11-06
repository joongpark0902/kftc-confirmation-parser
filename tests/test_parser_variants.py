"""실제 조회서에서 발견된 양식 변형(가짜 문구로 재현)."""
import datetime as dt
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from confirm_parser import (ConfirmDoc, InputFile, clean_company, dedupe_inputs, detect_form, iter_inputs,
                            parse_footer, parse_header)


class HeaderVariantTest(unittest.TestCase):
    def test_spaced_business_number_label(self):
        for label in ('사업 자 등록번호', '사 업 자등록번호', '사업자등록번호'):
            h = parse_header(f'조회대상 회사: （주）가나다 {label} : 123-45-67890 조회기준일 : 2025 년 12월 31 일 현재')
            self.assertEqual((h['company'], h['biz_no'], h['ref_date']), ('(주)가나다', '123-45-67890', '2025-12-31'), label)

    def test_broken_font_company_is_blank_but_biz_no_kept(self):
        h = parse_header('조회대상 회사: （주）））））））））사）업）자）등록번호 : 123-45-67890 조회기준일 : 2025 년 12월 31 일 현재')
        self.assertEqual((h['company'], h['biz_no'], h['ref_date']), ('', '123-45-67890', '2025-12-31'))

    def test_clean_company(self):
        self.assertEqual(clean_company('（유）가나다'), '(유)가나다')
        self.assertEqual(clean_company('（주）））））'), '')
        self.assertEqual(clean_company('㈜가나다'), '(주)가나다')

    def test_zero_issue_date_and_placeholder_branch(self):
        f = parse_footer('0000년 00월 00일 가나증권 ＣＣＣＣＣＣ 부·지점\n부·지점 담당자 :\n(문의전화 : 02-000-0000 , e-mail : )')
        self.assertIsNone(f['issue_date'])
        self.assertEqual((f['institution'], f['branch']), ('가나증권', ''))

    def test_detect_new_forms(self):
        self.assertEqual(detect_form('1. 조회기준일 현재 당사가 보유하고 있는 조회대상회사의 유가증권 등 금융상품의 내용은'), 'securities')
        self.assertEqual(detect_form('가나카드 금융거래조회서 고객사항 거래내역 법인카드 2025.12'), 'card')


class ZipAndDedupeTest(unittest.TestCase):
    def test_all_pdfs_in_zip_and_duplicates_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'a.pdf').write_bytes(b'%PDF-a')
            with zipfile.ZipFile(folder / 'z.zip', 'w') as zf:
                zf.writestr('a.pdf', b'%PDF-a')      # 폴더의 a.pdf와 같은 내용
                zf.writestr('b.pdf', b'%PDF-b')
                zf.writestr('c.pdf', b'%PDF-c')
            inputs = iter_inputs(folder)
            self.assertEqual(len(inputs), 4)
            keep, dup = dedupe_inputs(inputs)
            self.assertEqual(len(keep), 3)
            self.assertEqual(len(dup), 1)


class WriterVariantTest(unittest.TestCase):
    def _doc(self, company, biz, name):
        d = ConfirmDoc(source=InputFile(Path(name), 'pdf', b''))
        d.header = {'company': company, 'biz_no': biz}
        d.status = '성공'
        return d

    def test_company_names_unified_by_business_number(self):
        from excel_writer import canonicalize_companies, doc_company
        docs = [self._doc('(주)가나', '111-11-11111', 'x1.pdf'), self._doc('(주)가나', '111-11-11111', 'x2.pdf'),
                self._doc('주식회사 가나정식명', '111-11-11111', 'x3.pdf'), self._doc('', '111-11-11111', 'x4.pdf'),
                self._doc('', '', '가나_은행.pdf'), self._doc('(주)다른', '222-22-22222', 'y.pdf')]
        canonicalize_companies(docs)
        self.assertEqual([doc_company(d) for d in docs], ['(주)가나'] * 5 + ['(주)다른'])

    def test_invalid_date_text_kept(self):
        from excel_writer import _date
        self.assertEqual(_date('0000-00-00'), '0000-00-00')
        self.assertEqual(_date('2025-12-31'), dt.date(2025, 12, 31))


if __name__ == '__main__':
    unittest.main()
