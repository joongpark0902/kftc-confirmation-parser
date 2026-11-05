# -*- coding: utf-8 -*-
"""kftc_engine 단위 테스트 — 실제 사이트 대신 mock HTML + FakeSession"""
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from kftc_engine import KftcEngine, PaidItem, parse_paid_list, parse_site_list

MOCK = Path(__file__).parent / "mock"


def _zip_bytes(name="audit_x.pdf", content=b"%PDF-1.4 mock"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, content)
    return buf.getvalue()


class FakeSession:
    """get(path)는 mock HTML, fetch(path)는 생성요청/다운로드 흉내. 호출 기록을 남긴다."""

    def __init__(self):
        self.calls = []
        self.requested = set()

    def get(self, path):
        self.calls.append(("get", path))
        if path.startswith("/auditor/getPayCompleteList.do"):
            page = "2" if "strCurrentPage=2" in path else "1"
            return (MOCK / f"paylist_p{page}.html").read_text(encoding="utf-8")
        if "getBmanList" in path:
            return (MOCK / ("bmanlist_after.html" if "2" in self.requested else "bmanlist_before.html")).read_text(encoding="utf-8")
        raise AssertionError("unexpected get " + path)

    def fetch(self, path):
        self.calls.append(("fetch", path))
        if path.startswith("/auditor/exportRequest.do"):
            assert "MNGT_NUM=2" in path
            self.requested.add("2")
            return 200, b"<html>ok</html>", {"content-type": "text/html"}
        if path.startswith("/auditor/downloadPdf.do"):
            mngt = path.split("MNGT_NUM=")[1]
            return 200, _zip_bytes(), {"content-type": "application/zip",
                                       "content-disposition": f"attachment; filename=\"audit_%ED%85%8C%EC%8A%A4%ED%8A%B8_{mngt}_004.zip\""}
        raise AssertionError("unexpected fetch " + path)


class ParseTest(unittest.TestCase):
    def test_paid_list(self):
        items, total, last = parse_paid_list((MOCK / "paylist_p1.html").read_text(encoding="utf-8"))
        self.assertEqual(total, 3)
        self.assertEqual(last, 2)
        self.assertEqual(len(items), 2)
        a = items[0]
        self.assertEqual((a.mstr_num, a.bank_code, a.prtp_type, a.company, a.bank_name, a.ref_date, a.bank_issue_date, a.project_code),
                         ("202601090000001", "004", "1", "주식회사 테스트", "국민은행", "2025-12-31", "2026-01-12", "PJ-001"))
        self.assertEqual(a.detail_url, "/auditor/getBmanList.do?MSTR_NUM=202601090000001&BANK_CODE=004")
        self.assertEqual(items[1].detail_url, "/auditor/getBmanListIns.do?MSTR_NUM=202603110000002&BANK_CODE=442")
        self.assertEqual(items[1].note, "재발급")

    def test_kdb_exception(self):
        it = PaidItem(mstr_num="1", bank_code="002", sub_bank_code="005", issue_dt="20160101")
        self.assertEqual(it.effective_bank_code, "005")
        it2 = PaidItem(mstr_num="1", bank_code="002", sub_bank_code="005", issue_dt="20170101")
        self.assertEqual(it2.effective_bank_code, "002")

    def test_site_list(self):
        rows = parse_site_list((MOCK / "bmanlist_before.html").read_text(encoding="utf-8"))
        self.assertEqual([r.mngt_num for r in rows], ["1", "2", "3"])
        self.assertEqual(rows[0].mstr_num, "202601090000001")
        self.assertEqual((rows[0].name, rows[0].biz_no, rows[0].issue_status, rows[0].pdf_state), ("주식회사 테스트", "123-45-67890", "발급완료", "생성완료"))
        self.assertTrue(rows[0].can_download and not rows[0].can_request)
        self.assertTrue(rows[1].can_request and not rows[1].can_download)
        self.assertFalse(rows[2].can_request or rows[2].can_download)
        after = parse_site_list((MOCK / "bmanlist_after.html").read_text(encoding="utf-8"))
        self.assertTrue(after[1].can_download and after[1].can_cancel)


class EngineTest(unittest.TestCase):
    def test_run_end_to_end(self):
        s = FakeSession()
        with tempfile.TemporaryDirectory() as td:
            logs = []
            eng = KftcEngine(s, Path(td), log_fn=logs.append, delay=(0, 0), poll_sec=0, poll_max=3, sleep=lambda _: None)
            items = eng.list_paid()
            self.assertEqual(len(items), 3)
            results = eng.run(items)
            st = {r["key"]: r["status"] for r in results}
            # 국민은행: 1=바로 다운로드, 2=생성요청 후 다운로드, 3=불가
            self.assertEqual(st["202601090000001_004_1"], "완료")
            self.assertEqual(st["202601090000001_004_2"], "완료")
            self.assertTrue(st["202601090000001_004_3"].startswith("다운로드 불가"))
            # DB손해보험은 PDF 미제공
            self.assertTrue(any(v.startswith("PDF미제공") for k, v in st.items() if k.startswith("202603120000003")))
            # mock 상세 페이지는 국민·현대해상 두 건에 같은 3행을 돌려주므로 완료 4건(2건×2행)
            self.assertEqual(sum(v == "완료" for v in st.values()), 4)
            files = sorted(p.name for p in (Path(td) / "raw_zip").iterdir())
            self.assertEqual(files, ["audit_테스트_1_004.zip", "audit_테스트_2_004.zip"])   # 서버 파일명(URL 인코딩) 복원
            hist = json.loads((Path(td) / "download_history.json").read_text(encoding="utf-8"))
            self.assertEqual(hist["202601090000001_004_1"]["status"], "완료")
            self.assertEqual(len(hist["202601090000001_004_1"]["sha256"]), 64)
            # 생성요청은 MNGT 2에만, 첫 항목에서 1회(이후 mock은 생성완료 상태)
            self.assertEqual(sum(1 for c in s.calls if c[0] == "fetch" and "exportRequest" in c[1]), 1)
            # 수수료 경로 호출 없음
            self.assertFalse(any("reIssue" in c[1] or "PayWait" in c[1] or "choicePobs" in c[1] for c in s.calls))
            # 재실행 시 이미받음, 추가 다운로드 없음
            n_dl = sum(1 for c in s.calls if c[0] == "fetch" and "downloadPdf" in c[1])
            self.assertEqual(n_dl, 4)
            results2 = eng.run(items)
            self.assertEqual(sum(r["status"] == "이미받음" for r in results2), 4)
            self.assertEqual(sum(1 for c in s.calls if c[0] == "fetch" and "downloadPdf" in c[1]), n_dl)


if __name__ == "__main__":
    unittest.main()
