import unittest

from confirm_parser import parse_footer


class FooterOfficerTest(unittest.TestCase):
    def test_officer_on_same_line(self):
        text = ('2026년 01월 13일 가나 은행 다라지점\n부·지점 담당자 : 홍길동\n'
                '(문의전화 : 02-123-4567 , e-mail : a@b.com)\n')
        f = parse_footer(text)
        self.assertEqual(f['officer'], '홍길동')
        self.assertEqual(f['phone'], '02-123-4567')

    def test_blank_officer_does_not_take_next_line(self):
        """담당자 칸이 빈 양식: 다음 줄 '(문의전화'를 담당자로 읽지 않는다."""
        text = ('2026년 01월 13일 가나 은행 부·지점\n부·지점 담당자 :\n'
                '(문의전화 : , e-mail : )\n본 조회서는 해당 은행에서 발급한 것이며\n')
        f = parse_footer(text)
        self.assertEqual(f['officer'], '')
        self.assertEqual(f['phone'], '')


if __name__ == '__main__':
    unittest.main()
