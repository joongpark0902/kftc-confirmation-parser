# -*- coding: utf-8 -*-
"""금결원 audit.kftc.or.kr — 기발급(결제완료) 조회서 일괄 다운로드 엔진.

원칙
- 로그인은 사용자가 디버그 포트(9222) 크롬에서 직접. 엔진은 connect_over_cdp로 붙기만 한다.
- 수수료가 드는 경로(재발급 요청 reIssueConfirm.do, 수수료 결제 selectPayWaitList.do)는 절대 호출하지 않는다.
- 호출하는 URL은 목록/상세 조회(GET), PDF 생성요청(exportRequest.do), PDF 다운로드(downloadPdf.do)뿐.
- 원본 zip은 서버 파일명 그대로 저장, SHA-256·일시를 이력 JSON에 기록. 이미 받은 건은 건너뜀.

화면 구조 근거: docs/superpowers/specs/2026-09-16-kftc-site-survey.md
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import random
import re
import time
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode
from typing import Callable, Optional

BASE = "https://audit.kftc.or.kr"
CDP = "http://127.0.0.1:9222"
LIST_URL = "/auditor/getPayCompleteList.do"
DETAIL_URL = {"1": "/auditor/getBmanList.do", "2": "/auditor/getBmanListSb.do", "3": "/auditor/getBmanListIns.do", "4": "/auditor/getBmanListGi.do"}
PRTP_LABEL = {"1": "은행", "2": "증권", "3": "보험", "4": "보증기관"}
NO_PDF_BANKS = ("삼성증권", "DB손해보험")          # 사이트 안내: PDF 다운로드 미제공(뷰어 전용)
VIEW_HOURS = (dt.time(0, 30), dt.time(23, 50))    # 열람·출력 가능 시간


# ---------------------------------------------------------------------------
# 데이터
# ---------------------------------------------------------------------------
@dataclass
class PaidItem:
    """결제완료 목록 1행 (= 조회서 1건, MSTR_NUM+BANK_CODE)"""
    mstr_num: str
    bank_code: str
    sub_bank_code: str = ""
    issue_dt: str = ""
    prtp_type: str = "1"
    issu_type: str = ""
    entp_cpno: str = ""
    no: str = ""
    company: str = ""
    bank_name: str = ""
    ref_date: str = ""
    cpa_date: str = ""
    bank_issue_date: str = ""
    project_code: str = ""
    note: str = ""

    @property
    def key(self) -> str:
        return f"{self.mstr_num}_{self.bank_code}"

    @property
    def effective_bank_code(self) -> str:
        # 사이트 bmanlist() 예외: 구 KDB(005) 2016-05-31 이전 발급분
        if self.sub_bank_code == "005" and self.issue_dt and self.issue_dt <= "20160531":
            return "005"
        return self.bank_code

    @property
    def detail_url(self) -> str:
        return f"{DETAIL_URL.get(self.prtp_type, DETAIL_URL['1'])}?MSTR_NUM={self.mstr_num}&BANK_CODE={self.effective_bank_code}"


@dataclass
class SiteRow:
    """상세(사업장 리스트) 1행 (= PDF 1개, MNGT_NUM)"""
    mstr_num: str
    mngt_num: str
    prtp_type: str = "1"
    prt_cnt: str = ""
    no: str = ""
    name: str = ""
    biz_no: str = ""
    issue_status: str = ""
    pdf_state: str = ""
    can_request: bool = False
    can_download: bool = False
    can_cancel: bool = False


# ---------------------------------------------------------------------------
# HTML 파싱 (표준 라이브러리만)
# ---------------------------------------------------------------------------
class _TableRows(HTMLParser):
    """form[name=mainFrm] 안 tbody의 각 tr을 {'inputs': {name: value}, 'tds': [text], 'onclicks': [str]}로 수집"""

    def __init__(self):
        super().__init__()
        self.in_main = False
        self.in_tbody = False
        self.rows: list[dict] = []
        self.cur: Optional[dict] = None
        self.td_open = False
        self.buf: list[str] = []
        self.form_inputs: dict[str, str] = {}
        self.page_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form" and a.get("name") == "mainFrm":
            self.in_main = True
        if not self.in_main:
            return
        if tag == "tbody":
            self.in_tbody = True
        elif tag == "tr" and self.in_tbody:
            self.cur = {"inputs": {}, "tds": [], "onclicks": []}
        elif tag == "td" and self.cur is not None:
            self.td_open = True
            self.buf = []
        elif tag == "input":
            name, value = a.get("name", ""), a.get("value", "")
            if self.cur is not None:
                if name and name != "chk":
                    self.cur["inputs"][name] = value
            elif name:
                self.form_inputs[name] = value
        if (tag in ("button", "a", "img", "input")) and a.get("onclick") and self.cur is not None:
            self.cur["onclicks"].append(a["onclick"])

    def handle_endtag(self, tag):
        if not self.in_main:
            return
        if tag == "td" and self.cur is not None and self.td_open:
            self.cur["tds"].append(re.sub(r"\s+", " ", "".join(self.buf)).strip())
            self.td_open = False
        elif tag == "tr" and self.cur is not None:
            if self.cur["tds"]:
                self.rows.append(self.cur)
            self.cur = None
        elif tag == "tbody":
            self.in_tbody = False
        elif tag == "form":
            self.in_main = False

    def handle_data(self, data):
        if self.td_open:
            self.buf.append(data)
        self.page_text.append(data)


def _total_count(html: str) -> Optional[int]:
    m = re.search(r"총\s*[:：]\s*([\d,]+)\s*[개건]", html)
    return int(m.group(1).replace(",", "")) if m else None


def _max_page(html: str) -> int:
    pages = [int(x) for x in re.findall(r"strCurrentPage=(\d+)", html)]
    pages += [int(x) for x in re.findall(r"go_paging\((\d+)\)", html)]
    return max(pages) if pages else 1


def parse_paid_list(html: str) -> tuple[list[PaidItem], Optional[int], int]:
    """결제완료 목록 HTML → (항목들, 총건수, 마지막 페이지번호)"""
    p = _TableRows()
    p.feed(html)
    items: list[PaidItem] = []
    for r in p.rows:
        inp = r["inputs"]
        tds = [t for t in r["tds"]]
        if len(tds) >= 9:
            tds = tds[-8:]          # 체크박스 셀 제외
        elif len(tds) == 8 and not inp.get("MSTR_NUM"):
            continue
        cells = (tds + [""] * 8)[:8]
        if not inp.get("MSTR_NUM"):
            continue
        items.append(PaidItem(
            mstr_num=inp.get("MSTR_NUM", ""), bank_code=inp.get("BANK_CODE", ""), sub_bank_code=inp.get("SUB_BANK_CODE", ""),
            issue_dt=inp.get("INQRF_ISSU_DT", ""), prtp_type=inp.get("PRTP_TYPE_CODE", "1") or "1", issu_type=inp.get("ISSU_TYPE", ""),
            entp_cpno=inp.get("ENTP_CPNO", ""), no=cells[0], company=cells[1], bank_name=cells[2], ref_date=cells[3],
            cpa_date=cells[4], bank_issue_date=cells[5], project_code=cells[6], note=cells[7]))
    return items, _total_count(html), _max_page(html)


_CALL_RE = re.compile(r"(requestPdf|downloadPdf|cancelPdf)\s*\(\s*['\"]?(\w+)['\"]?\s*,\s*['\"]?(\w+)['\"]?(?:\s*,\s*['\"]?(\w+)['\"]?)?")


def parse_site_list(html: str, mstr_num: str = "") -> list[SiteRow]:
    """상세(사업장 리스트) HTML → SiteRow 목록. 버튼 onclick으로 요청/다운로드 가능 여부 판정."""
    p = _TableRows()
    p.feed(html)
    mstr_num = mstr_num or p.form_inputs.get("MSTR_NUM", "")
    rows: list[SiteRow] = []
    for r in p.rows:
        inp = r["inputs"]
        tds = r["tds"]
        if len(tds) >= 7:
            tds = tds[-6:]
        cells = (tds + [""] * 6)[:6]
        calls = {m.group(1): m for oc in r["onclicks"] for m in [_CALL_RE.search(oc)] if m}
        mngt = inp.get("MNGT_NUM") or (next(iter(calls.values())).group(3) if calls else "")
        if not mngt and not inp:
            continue
        rows.append(SiteRow(
            mstr_num=inp.get("MSTR_NUM", mstr_num) or mstr_num, mngt_num=mngt, prtp_type=inp.get("PRTP_TYPE_CODE", "1") or "1",
            prt_cnt=inp.get("PRT_CNT", ""), no=cells[0], name=cells[1], biz_no=cells[2], issue_status=cells[3],
            pdf_state=cells[5] or cells[4], can_request="requestPdf" in calls, can_download="downloadPdf" in calls,
            can_cancel="cancelPdf" in calls))
    return rows


# ---------------------------------------------------------------------------
# 세션 (Playwright CDP) — 테스트에서는 FakeSession으로 대체
# ---------------------------------------------------------------------------
class Session:
    """디버그 포트 크롬의 로그인된 금결원 탭. get()은 mainFrame 이동, fetch()는 쿠키를 공유하는 API 요청."""

    def __init__(self, cdp: str = CDP):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.connect_over_cdp(cdp)
        pages = [pg for c in self.browser.contexts for pg in c.pages if "audit.kftc.or.kr" in pg.url]
        if not pages:
            raise RuntimeError("금결원 탭이 없습니다. 크롬실행.cmd로 크롬을 띄우고 로그인하세요.")
        self.page = pages[0]
        self.context = self.page.context
        self.user = self.whoami()
        if not self.user:
            raise RuntimeError("로그인 상태가 아닙니다. 크롬 창에서 인증서 로그인 후 다시 실행하세요.")

    def _main(self):
        fr = [f for f in self.page.frames if f.name == "mainFrame"]
        return fr[0] if fr else self.page.main_frame

    def whoami(self) -> str:
        txt = self._main().evaluate("() => document.body ? document.body.innerText : ''")
        m = re.search(r"(\S+)\s*님\s*로그인하셨습니다", txt)
        return m.group(1) if m else ""

    def get(self, path: str) -> str:
        self._main().goto(BASE + path, wait_until="load", timeout=60000)
        time.sleep(0.8)
        return self._main().content()

    def fetch(self, path: str) -> tuple[int, bytes, dict]:
        r = self.context.request.get(BASE + path, timeout=120000)
        return r.status, r.body(), dict(r.headers)

    def close(self):
        try:
            self._pw.stop()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 엔진
# ---------------------------------------------------------------------------
class KftcEngine:
    def __init__(self, session, out_dir: Path, log_fn: Callable[[str], None] = print,
                 delay: tuple[float, float] = (1.0, 2.0), poll_sec: float = 5.0, poll_max: int = 24, sleep=time.sleep):
        self.s = session
        self.out_dir = Path(out_dir)
        self.raw_dir = self.out_dir / "raw_zip"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.history_path = self.out_dir / "download_history.json"
        self.history: dict = json.loads(self.history_path.read_text(encoding="utf-8")) if self.history_path.exists() else {}
        self.log = log_fn
        self.delay = delay
        self.poll_sec, self.poll_max = poll_sec, poll_max
        self.sleep = sleep
        self.stop_flag = False

    # -- 공통 --
    def _pause(self):
        self.sleep(random.uniform(*self.delay))

    def _save_history(self):
        self.history_path.write_text(json.dumps(self.history, ensure_ascii=False, indent=1), encoding="utf-8")

    @staticmethod
    def in_view_hours(now: Optional[dt.datetime] = None) -> bool:
        t = (now or dt.datetime.now()).time()
        return VIEW_HOURS[0] <= t <= VIEW_HOURS[1]

    # -- 1) 결제완료 목록 --
    def list_paid(self, record_size: int = 50, filter_sel: str = "", filter_val: str = "") -> list[PaidItem]:
        items: list[PaidItem] = []
        page_no = 1
        while True:
            params = {'strCurrentPage':page_no,'strRecordSize':record_size}
            if filter_val:
                params.update(filter_sel=filter_sel or 'E',filter_val=filter_val)
            q = LIST_URL + '?' + urlencode(params,encoding='euc-kr',errors='strict')
            html = self.s.get(q)
            got, total, last = parse_paid_list(html)
            items.extend(got)
            self.log(f"목록 {page_no}쪽: {len(got)}건 (총 {total if total is not None else '?'}건)")
            if not got or page_no >= last or (total is not None and len(items) >= total):
                break
            page_no += 1
            self._pause()
        return items

    # -- 2) 상세(사업장) --
    def list_sites(self, item: PaidItem) -> list[SiteRow]:
        html = self.s.get(item.detail_url)
        rows = parse_site_list(html, item.mstr_num)
        return rows

    # -- 3) PDF 확보 --
    def _zip_name(self, headers: dict, item: PaidItem, site: SiteRow) -> str:
        cd = headers.get("content-disposition", "") or headers.get("Content-Disposition", "")
        m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", cd)
        name = m.group(1) if m else ""
        try:
            from urllib.parse import unquote
            name = unquote(name)
            if not name.isascii():
                pass
            else:
                try:
                    name = name.encode("latin-1").decode("utf-8")
                except Exception:
                    pass
        except Exception:
            pass
        name = re.sub(r'[\\/:*?"<>|]', "_", name).strip()
        return name or f"audit_{item.mstr_num}_{site.mngt_num}_{item.bank_code}.zip"

    def download_site(self, item: PaidItem, site: SiteRow) -> dict:
        key = f"{item.key}_{site.mngt_num}"
        rec = {"key": key, "company": site.name or item.company, "bank": item.bank_name, "bank_code": item.bank_code,
               "mstr_num": item.mstr_num, "mngt_num": site.mngt_num, "ref_date": item.ref_date, "ts": dt.datetime.now().isoformat(timespec="seconds")}
        if key in self.history and self.history[key].get("status") == "완료" and Path(self.history[key].get("file", "")).exists():
            rec.update(self.history[key]); rec["status"] = "이미받음"
            return rec
        if any(b in item.bank_name for b in NO_PDF_BANKS):
            rec["status"] = "PDF미제공(뷰어전용)"
            self.history[key] = rec; self._save_history()
            return rec
        if not site.can_download and site.can_request:
            self.log(f"  PDF 생성요청: {site.name} (MNGT {site.mngt_num})")
            st, _, _ = self.s.fetch(f"/auditor/exportRequest.do?BANK_CODE={item.effective_bank_code}&MSTR_NUM={item.mstr_num}&MNGT_NUM={site.mngt_num}&PRTP_TYPE_CODE={site.prtp_type}")
            if st != 200:
                rec["status"] = f"생성요청 실패 HTTP {st}"
                self.history[key] = rec; self._save_history()
                return rec
            for i in range(self.poll_max):
                if self.stop_flag:
                    rec["status"] = "중단"; return rec
                self.sleep(self.poll_sec)
                rows = {r.mngt_num: r for r in self.list_sites(item)}
                cur = rows.get(site.mngt_num)
                if cur and cur.can_download:
                    site = cur
                    break
                self.log(f"  생성 대기 {i + 1}/{self.poll_max}: {cur.pdf_state if cur else '행 없음'}")
        if not site.can_download:
            rec["status"] = f"다운로드 불가 (생성상태: {site.pdf_state or '-'})"
            self.history[key] = rec; self._save_history()
            return rec
        st, body, headers = self.s.fetch(f"/auditor/downloadPdf.do?BANK_CODE={item.effective_bank_code}&MSTR_NUM={item.mstr_num}&MNGT_NUM={site.mngt_num}")
        ctype = (headers.get("content-type") or headers.get("Content-Type") or "").lower()
        if st != 200 or not body or ("zip" not in ctype and "pdf" not in ctype and "octet" not in ctype and not body.startswith(b"PK") and not body.startswith(b"%PDF")):
            rec["status"] = f"다운로드 실패 HTTP {st} type={ctype[:40]}"
            self.history[key] = rec; self._save_history()
            return rec
        name = self._zip_name(headers, item, site)
        if body.startswith(b"%PDF") and not name.lower().endswith(".pdf"):
            name = name.rsplit(".", 1)[0] + ".pdf"
        target = self.raw_dir / name
        k = 2
        while target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != hashlib.sha256(body).hexdigest():
            target = self.raw_dir / f"{Path(name).stem}_{k}{Path(name).suffix}"
            k += 1
        target.write_bytes(body)
        rec.update({"status": "완료", "file": str(target), "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)})
        self.history[key] = rec; self._save_history()
        self.log(f"  저장: {target.name} ({len(body):,} bytes)")
        return rec

    # -- 4) 전체 실행 --
    def run(self, items: Optional[list[PaidItem]] = None, only_keys: Optional[set] = None) -> list[dict]:
        if not self.in_view_hours():
            self.log("열람·출력 가능 시간(00:30~23:50)이 아닙니다.")
            return []
        items = items if items is not None else self.list_paid()
        results: list[dict] = []
        for i, item in enumerate(items, start=1):
            if self.stop_flag:
                break
            if only_keys is not None and item.key not in only_keys:
                continue
            self.log(f"[{i}/{len(items)}] {item.company} / {item.bank_name} ({PRTP_LABEL.get(item.prtp_type, item.prtp_type)}, 기준일 {item.ref_date})")
            try:
                sites = self.list_sites(item)
                if not sites:
                    results.append({"key": item.key, "company": item.company, "bank": item.bank_name, "status": "사업장 행 없음"})
                    continue
                for site in sites:
                    if self.stop_flag:
                        break
                    results.append(self.download_site(item, site))
                    self._pause()
            except Exception as e:
                self.log(f"  오류: {type(e).__name__}: {e}")
                results.append({"key": item.key, "company": item.company, "bank": item.bank_name, "status": f"오류 {type(e).__name__}: {e}"})
            self._pause()
        done = sum(r.get("status") == "완료" for r in results)
        self.log(f"완료 {done} / 이미받음 {sum(r.get('status') == '이미받음' for r in results)} / 기타 {len(results) - done - sum(r.get('status') == '이미받음' for r in results)}")
        return results
