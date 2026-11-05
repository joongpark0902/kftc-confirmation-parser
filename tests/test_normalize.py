# -*- coding: utf-8 -*-
import unittest

from confirm_parser import normalize_amount, normalize_date, normalize_rate, clean_cell, is_no_txn


class NormalizeTest(unittest.TestCase):
    def test_amount_krw_paren(self):
        self.assertEqual(normalize_amount("KRW 152,381.00\n(152,381.00)"), ("KRW", 152381.0, 152381.0, False))

    def test_amount_plain_paren(self):
        self.assertEqual(normalize_amount("232.00 (0.00)"), ("KRW", 232.0, 0.0, False))

    def test_amount_currency_newline(self):
        self.assertEqual(normalize_amount("KRW\n25,000,000,000"), ("KRW", 25e9, None, False))

    def test_amount_split_digits_flagged(self):
        self.assertEqual(normalize_amount("25,000,000,000.0\n0"), ("KRW", 25e9, None, True))
        self.assertEqual(normalize_amount("12,345,678,91\n2"), ("KRW", 12345678912.0, None, True))
        self.assertEqual(normalize_amount("98,765,432,10\n0"), ("KRW", 98765432100.0, None, True))

    def test_amount_empty_or_text(self):
        self.assertEqual(normalize_amount(""), ("", None, None, False))
        self.assertEqual(normalize_amount("생략"), ("", None, None, False))

    def test_date(self):
        self.assertEqual(normalize_date("20251219"), "2025-12-19")
        self.assertIsNone(normalize_date("00010101"))
        self.assertIsNone(normalize_date("00000000"))
        self.assertIsNone(normalize_date(""))

    def test_rate(self):
        self.assertEqual(normalize_rate("5.4900"), 5.49)
        self.assertEqual(normalize_rate("0.0000"), 0.0)
        self.assertIsNone(normalize_rate("생략"))

    def test_clean_cell(self):
        self.assertEqual(clean_cell("다중이용업소화\n재배상책임보험"), "다중이용업소화재배상책임보험")
        self.assertEqual(clean_cell("열\n당사 거래회사 아님"), "당사 거래회사 아님")
        self.assertEqual(clean_cell("SCRIPT ERROR"), "")
        self.assertEqual(clean_cell(None), "")

    def test_no_txn(self):
        self.assertTrue(is_no_txn(["", "", "당행 거래회사 아\n님", ""]))
        self.assertTrue(is_no_txn(["", "해당 거래 없음"]))
        self.assertFalse(is_no_txn(["기업자유예금", "1005", "KRW 1.00"]))


if __name__ == "__main__":
    unittest.main()
