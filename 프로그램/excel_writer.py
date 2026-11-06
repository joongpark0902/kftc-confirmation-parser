# -*- coding: utf-8 -*-
"""ConfirmDoc 목록 → BC조서 xlsx.

시트 구성은 회계법인 BC조서 양식의 주제별 시트를 따른다.
CS(BC-100) · 완전성대사 · 예적금(130-1) · 유가증권(130-1-1) · 대출금(130-2) · 지급보증(130-3)
· 파생상품(130-4) · 담보제공(130-5) · 어음수표(130-6) · 담보보증내역(130-7) · 보증보험(130-8)
· 원본추출 · 처리로그
"""
from __future__ import annotations

import datetime as dt
import re
from collections import Counter
from pathlib import Path
from typing import Callable, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from confirm_parser import FORM_LABEL, FORM_ORDER, FORMS, NA_STATUS, SCAN_STATUS, SENT_STATUS, ConfirmDoc

FONT = "맑은 고딕"
HDR_FILL = PatternFill("solid", fgColor="2F3B4C")
SUB_FILL = PatternFill("solid", fgColor="D9E1F2")
YELLOW = PatternFill("solid", fgColor="FFFF00")
THIN = Side(style="thin", color="000000")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
F_BODY = Font(name=FONT, size=9)
F_HDR = Font(name=FONT, size=9, bold=True, color="FFFFFF")
F_TITLE = Font(name=FONT, size=16, bold=True)
F_SHEET = Font(name=FONT, size=12, bold=True)
F_BOLD = Font(name=FONT, size=9, bold=True)
F_RED = Font(name=FONT, size=9, bold=True, color="C00000")
F_NOTE = Font(name=FONT, size=8, italic=True, color="595959")
NUM_MONEY = '_-* #,##0_-;-* #,##0_-;_-* "-"_-;_-@_-'
NUM_MONEY2 = '_-* #,##0.00_-;-* #,##0.00_-;_-* "-"_-;_-@_-'
NUM_RATE = "0.00%"
NUM_DATE = "yyyy-mm-dd"
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
RIGHT = Alignment(horizontal="right", vertical="center")

Col = tuple  # (header, width, kind)  kind: text | money | date | rate | int | no | formula
ID_COLS: list[Col] = [("No", 8, "no"), ("조회대상회사", 20, "text"), ("금융기관", 14, "text"), ("지점", 16, "text")]
RATE_CCY = ["KRW", "USD", "JPY", "EUR", "HKD", "CNY"]
LEGEND = ("노란 음영 = 파서가 줄바꿈으로 쪼개진 숫자를 재조립한 값 또는 스캔본 OCR 추정(원문 PDF 확인 필요). "
          "감사인 검토 열·회사제시금액·환율표는 빈칸(작성자 입력).")


# ---------------------------------------------------------------------------
# 문서 정렬 · 번호
# ---------------------------------------------------------------------------
def _fallback_identity(doc: ConfirmDoc):
    """스캔본 등 헤더를 못 읽은 문서: 파일명 '회사-조회서(기관).pdf'에서 추정"""
    stem = Path(doc.source.inner_name or doc.source.path.name).stem
    company = re.split(r"[-_]", stem, 1)[0].strip() if re.search(r"[-_]", stem) else ""
    groups = [g.strip() for g in re.findall(r"\(([^()]+)\)", stem) if g.strip() not in ("주", "유", "유한")]
    inst = groups[-1] if groups else ""        # '(기관)별도문의'처럼 괄호 뒤에 글자가 붙어도 마지막 괄호
    return company, inst


def doc_company(doc: ConfirmDoc) -> str:
    """표시용 회사명. assign_numbers()가 정한 대표 표기(canonical)가 있으면 그것을 쓴다."""
    canon = getattr(doc, "canonical_company", None)
    if canon:
        return canon
    return doc.company or _fallback_identity(doc)[0]


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _name_key(s: str) -> str:
    s = re.sub(r"\(주\)|\(유\)|\(유한\)|㈜|주식회사|유한회사|[（）()]", "", s or "")
    return re.sub(r"[^0-9a-z가-힣]", "", s.lower())


def _biz(doc: ConfirmDoc) -> str:
    return re.sub(r"\D", "", (doc.header or {}).get("biz_no", "") or "")


def canonicalize_companies(docs: list[ConfirmDoc]) -> None:
    """같은 사업자번호의 문서는 한 이름으로(글꼴 깨짐·약칭·정식명칭 차이 흡수), 이후 공백 차이를 통일한다.
    회사명을 못 읽은 문서(스캔본 등)의 파일명 추정 이름도 알려진 회사명과 같으면 그 이름을 쓴다."""
    by_biz: dict[str, Counter] = {}
    for d in docs:
        if _biz(d) and d.company:
            by_biz.setdefault(_biz(d), Counter())[d.company] += 1
    known = {}
    for c in by_biz.values():
        name = c.most_common(1)[0][0]
        known.setdefault(_name_key(name), name)
    for d in docs:
        if d.company and not _biz(d):
            known.setdefault(_name_key(d.company), d.company)

    def base(d: ConfirmDoc) -> str:
        if _biz(d) in by_biz:
            return by_biz[_biz(d)].most_common(1)[0][0]
        if d.company:
            return d.company
        stem = Path(d.source.inner_name or d.source.path.name).stem
        for tok in re.split(r"[-_]", stem):     # '기관_회사.pdf'처럼 회사명이 뒤에 와도 알려진 회사명이면 채택
            if _name_key(tok) in known:
                return known[_name_key(tok)]
        guess = _fallback_identity(d)[0]
        return known.get(_name_key(guess), guess) if guess else ""

    names = {id(d): base(d) for d in docs}
    by_key: dict[str, Counter] = {}
    for d in docs:
        if names[id(d)]:
            by_key.setdefault(_squash(names[id(d)]), Counter())[names[id(d)]] += 1
    for d in docs:
        raw = names[id(d)]
        d.canonical_company = by_key[_squash(raw)].most_common(1)[0][0] if raw else ""


def doc_institution(doc: ConfirmDoc) -> str:
    return doc.institution or _fallback_identity(doc)[1]


def assign_numbers(docs: list[ConfirmDoc], client: Optional[str] = None, bc_map: Optional[dict] = None) -> tuple[list[ConfirmDoc], str]:
    """BC 번호 부여. 반환: (정렬된 docs, client명). doc.bc / doc.bc_label 속성을 붙인다.
    bc_map({sha256: 번호})을 주면 이미 번호가 있는 문서는 그대로, 새 문서는 뒤 번호를 이어 받는다(증분 재생성 시 W/P 참조 고정)."""
    canonicalize_companies(docs)
    parsed = [d for d in docs if d.status == "성공"]
    if not client:
        cnt = Counter(doc_company(d) for d in parsed if doc_company(d))
        client = cnt.most_common(1)[0][0] if cnt else (doc_company(docs[0]) if docs else "")
    else:
        # 사용자가 준 이름도 공백 무시로 대표 표기에 맞춘다
        match = [doc_company(d) for d in docs if _squash(doc_company(d)) == _squash(client)]
        client = match[0] if match else client

    def key(d: ConfirmDoc):
        comp = doc_company(d)
        return (0 if comp == client else 1, comp, FORM_ORDER.get(d.form or "", 9),
                doc_institution(d), d.footer.get("branch", ""), str(d.source.path))

    if bc_map is None:
        ordered = sorted(docs, key=key)
        for i, d in enumerate(ordered, start=1):
            d.bc = i
            d.bc_label = f"BC-{i}"
        return ordered, client
    nxt = max(bc_map.values(), default=0) + 1
    old = [d for d in docs if d.sha256 and d.sha256 in bc_map]
    new = sorted([d for d in docs if not (d.sha256 and d.sha256 in bc_map)], key=key)
    for d in old:
        d.bc = bc_map[d.sha256]
    for d in new:
        d.bc = nxt
        if d.sha256:
            bc_map[d.sha256] = nxt
        nxt += 1
    for d in docs:
        d.bc_label = f"BC-{d.bc}"
        d.is_new = d in new
    return sorted(docs, key=lambda d: d.bc), client


# ---------------------------------------------------------------------------
# 셀 도우미
# ---------------------------------------------------------------------------
def _date(v):
    if isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        try:
            return dt.date.fromisoformat(v)
        except ValueError:          # 원문 '0000-00-00' 등
            return v
    return v if v else ""


def _money(row: dict, col: str):
    n = row.get("_n", {}).get(col)
    if n and n[1] is not None:
        return n[1]
    return row.get(col, "")


def _ccy(row: dict, col: str) -> str:
    n = row.get("_n", {}).get(col)
    return n[0] if n and n[0] else ""


def _krw(row: dict, col: str):
    n = row.get("_n", {}).get(col)
    return n[2] if n else None


def _rate(row: dict, col: str):
    v = row.get("_n", {}).get(col)
    if isinstance(v, (int, float)):
        return v / 100.0
    return row.get(col, "")


def _dt(row: dict, col: str):
    v = row.get("_n", {}).get(col)
    return _date(v) if v else (row.get(col, "") or "")


def _flag_set(row: dict) -> set:
    return {c for c, f in row.get("_flags", {}).items() if f}


def _ids(doc: ConfirmDoc) -> list:
    return [doc.bc_label, doc_company(doc), doc_institution(doc), doc.footer.get("branch", "")]


def _sec(doc: ConfirmDoc, n: int):
    return doc.sections.get(n) if doc.sections else None


def _rows_of(docs, form_secs: dict[str, int]):
    """form_secs: {"bank": 2, "insurance": 2, "guarantee": 4} → (doc, section_no, row) 반복"""
    for d in docs:
        if d.status != "성공" or d.form not in form_secs:
            continue
        s = _sec(d, form_secs[d.form])
        if not s:
            continue
        for r in s["rows"]:
            yield d, form_secs[d.form], r


# ---------------------------------------------------------------------------
# 시트 골격
# ---------------------------------------------------------------------------
class Ctx:
    def __init__(self, docs, client, wolbo=None):
        self.docs = docs
        self.client = client
        self.wolbo = wolbo                      # wolbo_parser.WolboDoc | None
        parsed = [d for d in docs if d.status == "성공"]
        self.firm = next((d.header.get("firm") for d in parsed if d.header.get("firm")), "")
        self.cpa = next((d.header.get("cpa") for d in parsed if d.header.get("cpa")), "")
        ye = Counter(d.header.get("ref_date") for d in parsed if d.header.get("ref_date"))
        self.year_end = ye.most_common(1)[0][0] if ye else ""
        self.biz_no = next((d.header.get("biz_no") for d in parsed if doc_company(d) == client and d.header.get("biz_no")), "")
        self.now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def _head(ws, ctx: Ctx, title: str, wp: str, ncols: int) -> int:
    ws.sheet_view.showGridLines = False
    ws["A1"] = ctx.firm or "회계법인"
    ws["A1"].font = F_TITLE
    c = ws.cell(1, max(ncols, 6), title)
    c.font = F_SHEET
    c.alignment = Alignment(horizontal="right")
    labels = [("Client:", ctx.client), ("법인등록번호:", ""), ("사업자등록번호:", ctx.biz_no), ("대표자:", ""), ("Prepared by", ctx.cpa)]
    for i, (k, v) in enumerate(labels, start=2):
        ws.cell(i, 1, k).font = F_BOLD
        ws.cell(i, 2, v).font = F_BODY
    rc = max(ncols, 6)
    ws.cell(2, rc, "Year end").font = F_BOLD
    ws.cell(3, rc, _date(ctx.year_end)).font = F_BODY
    ws.cell(3, rc).number_format = NUM_DATE
    ws.cell(3, rc).alignment = RIGHT
    ws.cell(6, max(rc - 2, 3), "Reviewed by").font = F_BOLD
    ws.cell(6, rc, "W/P reference").font = F_BOLD
    ws.cell(7, rc, wp).font = F_RED
    ws.cell(7, rc).alignment = RIGHT
    for col in range(1, rc + 1):
        ws.cell(6, col).border = Border(top=Side(style="medium"), bottom=Side(style="thin"))
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 20
    return 9


def _block(ws, r: int, title: str, cols: list[Col], rows: list[list], flags: Optional[list[set]] = None,
           subtotal: tuple = (), note: str = "") -> tuple[int, int, int]:
    """표 하나를 r행부터 쓴다. 반환: (다음 빈 행, 첫 데이터행, 마지막 데이터행)"""
    if title:
        ws.cell(r, 1, title).font = F_BOLD
        r += 1
    if note:
        ws.cell(r, 1, note).font = F_NOTE
        r += 1
    for j, (h, w, k) in enumerate(cols, start=1):
        c = ws.cell(r, j, h)
        c.font, c.fill, c.alignment, c.border = F_HDR, HDR_FILL, CENTER, BORDER
        letter = get_column_letter(j)
        cur = ws.column_dimensions[letter].width or 0
        if w > cur:
            ws.column_dimensions[letter].width = w
    ws.row_dimensions[r].height = 24
    r += 1
    first = r
    data = rows if rows else [[""] * len(cols)]
    for i, row in enumerate(data):
        fl = flags[i] if (flags and rows and i < len(flags)) else set()
        for j, (h, w, k) in enumerate(cols, start=1):
            v = row[j - 1] if j - 1 < len(row) else ""
            if callable(v):
                v = v(r)
            c = ws.cell(r, j, v if v is not None else "")
            c.border = BORDER
            c.font = F_RED if k == "no" else F_BODY
            if k in ("money", "formula"):
                c.number_format = NUM_MONEY
                c.alignment = RIGHT
            elif k == "date":
                c.number_format = NUM_DATE
                c.alignment = CENTER
            elif k == "rate":
                c.number_format = NUM_RATE
                c.alignment = RIGHT
            elif k in ("no", "int"):
                c.alignment = CENTER
            else:
                c.alignment = LEFT
            if h in fl:
                c.fill = YELLOW
        r += 1
    last = r - 1
    if subtotal and rows:
        ws.cell(r, 1, "합계").font = F_BOLD
        ws.cell(r, 1).alignment = CENTER
        for j, (h, w, k) in enumerate(cols, start=1):
            c = ws.cell(r, j)
            c.border = BORDER
            c.font = F_BOLD
            if h in subtotal:
                L = get_column_letter(j)
                c.value = f"=SUBTOTAL(9,{L}{first}:{L}{last})"
                c.number_format = NUM_MONEY
                c.alignment = RIGHT
        r += 1
    return r + 2, first, last


def _rate_table(ws, col: int, top: int = 2) -> str:
    """환율표(통화|환율)를 col 열에 쓰고 VLOOKUP용 절대참조 문자열을 돌려준다."""
    L1, L2 = get_column_letter(col), get_column_letter(col + 1)
    ws.cell(top - 1, col, "환율(결산일)").font = F_BOLD
    for i, ccy in enumerate(RATE_CCY):
        a = ws.cell(top + i, col, ccy)
        b = ws.cell(top + i, col + 1, 1.0 if ccy == "KRW" else None)
        a.font = b.font = F_BODY
        a.border = b.border = BORDER
        b.number_format = "#,##0.00"
    ws.column_dimensions[L1].width = max(ws.column_dimensions[L1].width or 0, 8)
    ws.column_dimensions[L2].width = max(ws.column_dimensions[L2].width or 0, 10)
    return f"${L1}${top}:${L2}${top + len(RATE_CCY) - 1}"


def _fx_formula(ccy_col: int, amt_col: int, rate_ref: str) -> Callable[[int], str]:
    C, A = get_column_letter(ccy_col), get_column_letter(amt_col)
    return lambda r: f'=IF({C}{r}="KRW",{A}{r},IFERROR({A}{r}*VLOOKUP({C}{r},{rate_ref},2,FALSE),""))'


# ---------------------------------------------------------------------------
# 시트별 작성
# ---------------------------------------------------------------------------
def _note_for(doc: ConfirmDoc) -> str:
    if doc.status == SCAN_STATUS:
        return SCAN_STATUS + (f" · {doc.message}" if doc.ocr_pages is not None else "")
    if doc.status in (NA_STATUS, SENT_STATUS):
        return doc.status
    if doc.status != "성공":
        return f"{doc.status}: {doc.message}"
    specs = FORMS[doc.form]
    parts = [f"{specs[n].name} {len(s['rows'])}건" for n, s in doc.sections.items() if s["rows"]]
    if not parts:
        return "전 항목 거래없음"
    return ", ".join(parts)


def sheet_cs(wb, ctx: Ctx):
    ws = wb.active
    ws.title = "CS"
    cols: list[Col] = [("번호", 6, "int"), ("조회대상회사", 20, "text"), ("상호(지점)", 26, "text"), ("조회처분류", 10, "text"),
                       ("주소", 12, "text"), ("담당자", 10, "text"), ("담당전화번호", 14, "text"), ("우편번호", 8, "text"),
                       ("발송여부", 8, "text"), ("회수여부(회수날짜)", 16, "text"), ("W/P", 8, "no"), ("비고", 34, "text")]
    # 조회기준일·원본파일·정리파일·SHA-256·처리일시는 검토자 피드백(9/16)으로 CS에서 빼고 처리로그에만 둔다.
    r = _head(ws, ctx, "금융기관조회서 ControlSheet", "BC-100", len(cols))
    ws.cell(r - 1, 1, LEGEND).font = F_NOTE
    ws.cell(r, 1, "1. 회수 Summary").font = F_BOLD
    n = len(ctx.docs)
    list_first = r + 7   # 요약 3행 + 빈 행 + 블록 제목 + 머리글
    list_last = list_first + max(n, 1) - 1
    for i, (k, f) in enumerate([("회수", f'=COUNTIF(J{list_first}:J{list_last},"V*")'),
                                ("미회수", f"=B{r + 3}-B{r + 1}"),
                                ("Total", f"=COUNTA(A{list_first}:A{list_last})")], start=1):
        a = ws.cell(r + i, 1, k)
        b = ws.cell(r + i, 2, f)
        a.font, a.fill, a.alignment, a.border = F_HDR, HDR_FILL, CENTER, BORDER
        b.font, b.border, b.alignment = F_BODY, BORDER, RIGHT
    r += 5
    rows, flags = [], []
    for d in ctx.docs:
        inst, br = doc_institution(d), d.footer.get("branch", "")
        received = f"V ({d.footer['issue_date']})" if d.footer.get("issue_date") else ("V (스캔본)" if d.is_scan else "V")
        if d.status == SENT_STATUS:
            received = "-"               # 회사가 보낸 요청 서식: 회신이 아님
        rows.append([d.bc, doc_company(d), f"{inst}({br})" if br else inst, d.form_label if d.form else ("미상" if d.is_scan else "-"),
                     ("전자조회" if d.form != "card" else "") if d.form else "", d.footer.get("officer", ""), d.footer.get("phone", ""), "",
                     "V", received, d.bc_label, _note_for(d)])
        flags.append({"비고"} if d.ocr_pages is not None else set())
    assert r + 2 == list_first, (r, list_first)
    _block(ws, r, "2. 발송 및 회수 리스트", cols, rows, flags)
    ws.freeze_panes = ws.cell(list_first, 4)


def sheet_completeness(wb, ctx: Ctx):
    ws = wb.create_sheet("완전성대사")
    r = _head(ws, ctx, "금융기관조회서 완전성 대사", "BC-100-1", 6)
    # 검토자 피드백(9/16): 당기 목록은 지점 괄호 없이 기관명만(나중에 XLOOKUP 키로 씀)
    rows = [[d.bc, doc_institution(d), doc_company(d), d.footer.get("branch", "")] for d in ctx.docs]
    r, first, last = _block(ws, r, "1. 당기 금융기관조회서 CS 목록 (자동)",
                            [("No", 8, "int"), ("당기 금융기관조회서 CS", 30, "text"), ("조회대상회사", 20, "text"), ("지점(참고)", 20, "text")], rows)
    key = f"$B${first}:$B${last}"

    def sent(col: str):      # 발송여부: 당기 목록에 있으면 발송, 빈칸이면 해당사항 없음, 없으면 미발송
        return lambda rr: f'=IF(ISERROR(VLOOKUP({col}{rr},{key},1,0)),IF({col}{rr}=0,"해당사항 없음","미발송"),"발송")'

    def reason(col: str):    # 사유: 미발송이면 입력 요구
        return lambda rr: f'=IF({col}{rr}="발송","-",IF({col}{rr}="해당사항 없음","-","사유 입력!!"))'

    n_blank = 20
    r, *_ = _block(ws, r, "2. 전기 금융기관조회서 CS와 대사",
                   [("전기 금융기관조회서 CS", 30, "text"), ("거래처명 수정", 24, "text"), ("발송여부", 10, "text"), ("사유", 50, "text")],
                   [["", "", sent("B"), reason("C")] for _ in range(n_blank)])
    winsts = ctx.wolbo.all_institutions() if ctx.wolbo else []
    r, *_ = _block(ws, r, "3. 은행연합회 자료와 대사" + (f"_{ctx.wolbo.base_month} 월보 기준 (자동)" if ctx.wolbo else "_12월 기준"),
                   [("은행연합회", 30, "text"), ("발송여부", 10, "text"), ("사유", 50, "text")],
                   [[n, sent("A"), reason("B")] for n in winsts] + [["", sent("A"), reason("B")] for _ in range(n_blank if not winsts else 5)])
    _block(ws, r, "4. 이자수익·이자비용 원장과 대사 (적요 검색: 캐피탈/은행/보험/저축/신용/리스/금고)",
           [("구분", 10, "text"), ("원장상 금융기관", 30, "text"), ("거래처명 수정", 24, "text"), ("발송여부", 10, "text"), ("사유", 50, "text")],
           [["", "", "", sent("C"), reason("D")] for _ in range(n_blank)])
    ws.cell(r - 1, 1, "2~4번 좌측 열(전기 CS·은행연합회·원장상 기관명·거래처명 수정)은 작성자 입력. 발송여부·사유는 1번 목록과 대조하는 수식.").font = F_NOTE


AUDIT_PROCEDURE = [
    "(a) 은행조회서 발송 시 은행연합회 \"기업신용정보 조회\" 최근 내역을 확인하여, 금융기관조회서 checklist의 완전성을 확인한다.",
    "(b) 기말감사 수행시 보고기간말 기준으로 은행연합회 기업신용정보 \"월보조회(*)\" 내역을 입수하여 누락될 수 있는 회사의 금융기관 차입금/담보/채무지급보증 등의 내역을 확인한다.",
    "    (*) 금융기관조회서에는 회사가 제공받은 지급보증만 조회된다. 은행연합회자료(월보)의 경우 회사가 금융기관으로부터 제공 받은 지급보증 및 타인에게 제공한 지급보증 내역도 확인 가능",
    "(c) \"은행연합회 자료 대사 Template\"에 은행연합회 내용을 기재하고 관련 금융기관조회서 reference number 및 최종 감사보고서(주석포함) number 등을 확인하여 기재한다.",
    "    동 절차 수행 시, 은행연합회 자료 중 차입금에 대하여는 완전성 및 정확성(단수차이 무시)까지 확인하고, 차입금 외 부외부채 성격의 정보(약정사항/지급보증/담보 등)의 경우에는 완전성 확인을 위한 기초정보로만 활용한다.",
    "(d) 금융기관조회서 상의 정보와 중요하게 차이가 나는 경우",
    "    i) 회사제시자료 = 은행조회 결과 > 은행연합회자료 인 경우, 별도의 추가 차이 분석은 진행하지 않음",
    "    ii) 회사제시자료 ≠ 은행조회결과 ≠ 은행연합회자료 or 은행조회결과 < 은행연합회자료 인 경우, 금융기관 담당자와 유선통화를 통해 차이 내역 제공 후 질의하고 조회서 오류의 경우 조회서를 재수령하고, 은행연합회자료 오류 시 유선확인 내용을 조서화하고 해당 절차를 완료한 관련 정보가 적절히 재무제표 및 주석에 반영될 수 있도록 한다.",
]


def sheet_monthly(wb, ctx: Ctx):
    """BC-200 은행연합회(월보) 계정과목별 대사. 기관별 블록: 월보·회사금액은 입력, 조회서금액은 대출금/지급보증 시트 SUMIFS."""
    ws = wb.create_sheet("월보대사")
    cols: list[Col] = [("대출과목명", 14, "text"), ("세부", 22, "text"), ("은행연합회(월보)", 16, "money"), ("회사금액", 16, "money"),
                       ("조회서금액", 16, "money"), ("차이(회사-조회서)", 16, "money"), ("차이(월보-조회서)", 16, "money"), ("Ref", 8, "no"), ("비고", 40, "text")]
    r = _head(ws, ctx, "은행연합회 계정과목별조회(월보) 대사", "BC-200", len(cols))
    c = ws.cell(r, 1, "Audit procedure")
    c.font, c.fill = F_HDR, HDR_FILL
    r += 1
    for line in AUDIT_PROCEDURE:
        ws.cell(r, 1, line).font = F_BODY
        r += 1
    r += 1
    c = ws.cell(r, 1, "Audit memo")
    c.font, c.fill = F_HDR, HDR_FILL
    r += 1
    w = ctx.wolbo
    memo = [("기업명", ctx.client, "조회 ID / 조회자", w.viewer if w else ""),
            ("사업자등록번호", ctx.biz_no, "조회일시", w.query_ts if w else ""),
            ("여신조회 기준년월", w.base_month if w else (ctx.year_end or "")[:7], "최종변경일", w.changed_date if w else ""),
            ("월보 파일", w.path.name if w else "(없음 — 월보 PDF를 입력 폴더에 넣거나 --wolbo 로 지정)", "월보 번호", w.nice_no if w else "")]
    for a, b, cc, d in memo:
        ws.cell(r, 1, a).font = F_BOLD
        ws.cell(r, 2, b).font = F_BODY
        ws.cell(r, 4, cc).font = F_BOLD
        ws.cell(r, 5, d).font = F_BODY
        r += 1
    if w:
        ws.cell(r, 1, f"(단위: 원) 은행연합회(월보) 열은 월보 PDF({w.unit} 단위)를 원으로 환산한 값(×1,000,000) → 단수차이 100만원 미만은 무시. "
                      "회사금액은 작성자 입력. 조회서금액 '계' 행은 대출금·지급보증 시트 SUMIFS.").font = F_NOTE
    else:
        ws.cell(r, 1, "(단위: 원) 은행연합회(월보)·회사금액은 작성자 입력. 조회서금액의 '계' 행은 대출금·지급보증 시트에서 SUMIFS로 끌어온 값(세부 분류는 작성자가 나눔).").font = F_NOTE
    r += 2
    from wolbo_parser import UNIT, match_institution
    winsts = w.all_institutions() if w else []
    targets = [d for d in ctx.docs if d.status == "성공" and (doc_company(d) == ctx.client
               or any(_sec(d, n) and _sec(d, n)["rows"] for n in ({"bank": (2, 3), "insurance": (2, 3), "guarantee": (4, 6), "securities": (3, 4), "card": (1,)}[d.form])))]
    blocks: list[tuple] = []          # (기관표시명, 회사, doc|None, 월보기관명|None)
    used = set()
    for d in targets:
        wi = match_institution(doc_institution(d), winsts) if w else None
        if wi:
            used.add(wi)
        blocks.append((doc_institution(d), doc_company(d), d, wi))
    for wi in winsts:
        if wi not in used:
            blocks.append((wi, ctx.client, None, wi))
    if not blocks:
        ws.cell(r, 1, "대상 조회서·월보 없음").font = F_NOTE
        return
    q = lambda s: s.replace('"', '""')
    for inst, comp, d, wi in blocks:
        tag = d.form_label if d else "조회서 미수령"
        ws.cell(r, 1, f"- 신용공여 잔액 : {inst}  ({comp}, {tag}{', 월보: ' + wi if wi and wi != inst else ''})").font = F_BOLD
        r += 1
        hdr = r
        blk = list(cols)
        blk[2] = (inst, 16, "money")
        for j, (h, ww, k) in enumerate(blk, start=1):
            cell = ws.cell(r, j, h)
            cell.font, cell.fill, cell.alignment, cell.border = F_HDR, HDR_FILL, CENTER, BORDER
            L = get_column_letter(j)
            if ww > (ws.column_dimensions[L].width or 0):
                ws.column_dimensions[L].width = ww
        r += 1
        loan_sumifs = f'=SUMIFS(대출금!$I:$I,대출금!$B:$B,"{q(comp)}",대출금!$C:$C,"{q(inst)}")'
        if d is not None and d.form == "guarantee" and getattr(ctx, "gua_block", None):
            # 보증기관: 월보 '지급보증' = 보증(보험) 잔액 → 보증보험 시트 1번 블록 보증금액(H열) 합
            gf, gl = ctx.gua_block
            gua_sumifs = f'=SUMIFS(보증보험!$H${gf}:$H${gl},보증보험!$B${gf}:$B${gl},"{q(comp)}",보증보험!$C${gf}:$C${gl},"{q(inst)}")'
        else:
            gua_sumifs = f'=SUMIFS(지급보증!$G:$G,지급보증!$B:$B,"{q(comp)}",지급보증!$C:$C,"{q(inst)}")'
        cl = w.credit_lines(wi) if (w and wi) else None
        mv = (lambda v: v * UNIT if v is not None else None)
        if cl and (cl["loan_items"] or cl["gua_items"] or cl["total"] is not None):
            lines = [("대출채권", it, None, mv(v)) for it, v in cl["loan_items"]] or [("대출채권", "(월보 대출채권 없음)", None, None)]
            lines.append(("대출채권", "대출채권계", "loan", mv(cl["loan_total"])))
            lines += [("지급보증 등", it, None, mv(v)) for it, v in cl["gua_items"]] or [("지급보증 등", "(월보 지급보증 없음)", None, None)]
            lines.append(("지급보증 등", "지급보증등계", "gua", mv(cl["gua_total"])))
            lines.append(("신용공여 합계", "합계", "total", mv(cl["total"])))
            wol_values = True
        else:
            lines = [("대출채권", "신용대출", None, None), ("대출채권", "담보대출", None, None), ("대출채권", "운용리스", None, None), ("대출채권", "기타", None, None),
                     ("대출채권", "대출채권계", "loan", None),
                     ("지급보증 등", "이행지보", None, None), ("지급보증 등", "기타", None, None), ("지급보증 등", "지급보증등계", "gua", None),
                     ("신용공여 합계", "합계", "total", None)]
            wol_values = False
        first = r
        sub_rows = {}
        for a, b, kind, wval in lines:
            ws.cell(r, 1, a).font = F_BODY
            ws.cell(r, 2, b).font = F_BOLD if kind else F_BODY
            for j in range(1, len(cols) + 1):
                ws.cell(r, j).border = BORDER
                if 3 <= j <= 7:
                    ws.cell(r, j).number_format = NUM_MONEY
                    ws.cell(r, j).alignment = RIGHT
                    ws.cell(r, j).font = F_BOLD if kind else F_BODY
            if wol_values:
                ws.cell(r, 3, wval)
            if kind == "loan":
                if not wol_values:
                    ws.cell(r, 3, f"=SUM(C{first}:C{r - 1})")
                ws.cell(r, 4, f"=SUM(D{first}:D{r - 1})")
                ws.cell(r, 5, loan_sumifs)
                sub_rows["loan"] = r
            elif kind == "gua":
                g0 = sub_rows["loan"] + 1
                if not wol_values:
                    ws.cell(r, 3, f"=SUM(C{g0}:C{r - 1})")
                ws.cell(r, 4, f"=SUM(D{g0}:D{r - 1})")
                ws.cell(r, 5, gua_sumifs)
                sub_rows["gua"] = r
            elif kind == "total":
                for j in ((4, 5) if wol_values else (3, 4, 5)):
                    L = get_column_letter(j)
                    ws.cell(r, j, f"={L}{sub_rows['loan']}+{L}{sub_rows['gua']}")
                sub_rows["total"] = r
            if kind:
                ws.cell(r, 6, f"=D{r}-E{r}")
                ws.cell(r, 7, f"=C{r}-E{r}")
            r += 1
        ref = ws.cell(hdr + 1, 8, d.bc_label if d else "조회서 없음")
        ref.font, ref.alignment = F_RED, CENTER
        if d is None:
            ws.cell(hdr + 1, 9, "월보에는 있으나 조회서 미수령 → 완전성 확인(발송 누락?)").font = F_RED
        elif w and not wi:
            ws.cell(hdr + 1, 9, "월보에 없음(신용공여 없음이거나 기관명 불일치 — 확인)").font = F_BODY
        ws.cell(r, 2, "조회서 대사").font = F_BOLD
        v = ws.cell(r, 4, f"=D{sub_rows['total']}=E{sub_rows['total']}")
        v.font, v.alignment, v.border = F_BOLD, CENTER, BORDER
        ws.cell(r, 5, "← 회사금액 = 조회서금액").font = F_NOTE
        if wol_values:
            v2 = ws.cell(r, 7, f"=ABS(G{sub_rows['total']})<{UNIT}")
            v2.font, v2.alignment, v2.border = F_BOLD, CENTER, BORDER
            ws.cell(r, 8, "← 월보-조회서 단수차이 이내").font = F_NOTE
        r += 3
    # 월보 참고 표: 한도 잔액·담보 잔액 (원문 단위 그대로)
    if w:
        for sec, title in (("한도", "[참고] 한도 잔액"), ("담보", "[참고] 담보 잔액")):
            rows = [x for x in w.rows if x.section == sec]
            if not rows:
                continue
            heads = []
            for x in rows:
                for h in x.values:
                    if h not in heads:
                        heads.append(h)
            rcols = [("구분", 12, "text"), ("과목", 30, "text")] + [(h, 14, "money") for h in heads]
            r, *_ = _block(ws, r, f"{title} — 월보 {w.base_month} (단위: {w.unit}, 원문 그대로)", rcols,
                           [[x.category, x.item] + [x.values.get(h) for h in heads] for x in rows])


def sheet_deposits(wb, ctx: Ctx):
    ws = wb.create_sheet("예적금")
    cols = ID_COLS + [("구분", 26, "text"), ("계좌번호", 18, "text"), ("통화", 6, "text"), ("조회서회신액", 16, "money"),
                      ("외화환산금액", 16, "formula"), ("이자율", 8, "rate"), ("최종이자지급일", 12, "date"), ("만기일", 12, "date"),
                      ("인출제한등", 14, "text"), ("검토메모", 24, "text"), ("", 2, "text"),
                      ("현금및현금성자산", 16, "money"), ("단기금융상품", 14, "money"), ("장기금융상품", 14, "money"), ("퇴직신탁", 12, "money")]
    r = _head(ws, ctx, "금융거래조회서 Control Sheet_예적금 등", "BC-130-1", len(cols))
    rate_ref = _rate_table(ws, len(cols) + 2)
    ccy_col, amt_col = 7, 8
    rows, flags = [], []
    for d, n, row in _rows_of(ctx.docs, {"bank": 1}):
        memo = []
        if _ccy(row, "금액") not in ("", "KRW") and _krw(row, "금액") is not None:
            memo.append(f"조회서 원화환산 {_krw(row, '금액'):,.0f}")
        if row["_flags"].get("금액"):
            memo.append("금액 재조립")
        rows.append(_ids(d) + [row["금융상품의 종류"], row["계좌번호"], _ccy(row, "금액") or "KRW", _money(row, "금액"),
                               _fx_formula(ccy_col, amt_col, rate_ref), _rate(row, "연이자율"), _dt(row, "최종이자지급일"),
                               _dt(row, "만기일"), row["인출제한 등"], "; ".join(memo)])
        flags.append({"조회서회신액"} if row["_flags"].get("금액") else set())
    r2, first, last = _block(ws, r, "1. 조회기준일 현재 조회대상회사의 당 은행에 대한 금융상품의 내용은 다음과 같습니다.", cols, rows, flags,
                             subtotal=("외화환산금액", "현금및현금성자산", "단기금융상품", "장기금융상품", "퇴직신탁"))
    ws.cell(r - 1, 1, "우측 '감사인 검토' 4개 열은 작성자가 계정 분류 후 입력. 외화환산금액은 환율표(우측) VLOOKUP 수식.").font = F_NOTE
    # 검토자 피드백(9/16): 대출금처럼 조회서금액·회사제시금액·차이 비교 블록 (계정별 4열 + 외화환산 합계)
    if rows:
        fx_col = 9
        cat_cols = list(range(len(cols) - 3, len(cols) + 1))          # 현금성·단기·장기·퇴직신탁
        lab = len(cols) - 5
        ws.cell(r2, lab, "조회서금액").font = F_BOLD
        ws.cell(r2 + 1, lab, "회사제시금액").font = F_BOLD
        ws.cell(r2 + 2, lab, "차이").font = F_BOLD
        ws.cell(r2 + 3, lab, "합계검증").font = F_BOLD
        for cc in cat_cols + [fx_col]:
            L = get_column_letter(cc)
            a = ws.cell(r2, cc, f"=SUBTOTAL(9,{L}{first}:{L}{last})")
            b = ws.cell(r2 + 1, cc, None)
            d = ws.cell(r2 + 2, cc, f"={L}{r2}-{L}{r2 + 1}")
            for c in (a, b, d):
                c.number_format, c.border, c.font, c.alignment = NUM_MONEY, BORDER, F_BODY, RIGHT
        P, S, I = get_column_letter(cat_cols[0]), get_column_letter(cat_cols[-1]), get_column_letter(fx_col)
        v = ws.cell(r2 + 3, cat_cols[0], f"=SUM({P}{r2}:{S}{r2})={I}{r2}")
        v.font, v.border, v.alignment = F_BODY, BORDER, CENTER
        ws.cell(r2 + 3, cat_cols[0] + 1, "← 계정별 조회서금액 합 = 외화환산금액 합계").font = F_NOTE
        for i, t in enumerate(["(*1) 현금및현금성자산: ", "(*2) 단기금융상품: ", "(*3) 장기금융상품: "]):
            ws.cell(r2 + 5 + i, 1, t).font = F_BOLD
        ws.cell(r2 + 8, 1, "회사제시금액과 (*1)~(*3) 차이 설명은 작성자 입력. 유가증권 시트 합계액이 있으면 (*1)에 참조.").font = F_NOTE


def sheet_securities(wb, ctx: Ctx):
    ws = wb.create_sheet("유가증권")
    cols1 = ID_COLS + [("계좌번호", 18, "text"), ("금융상품의 종류", 18, "text"), ("금융상품 금액", 16, "money"), ("예수금", 14, "money"),
                       ("신용설정 보증금", 14, "money"), ("미수금액", 14, "money"), ("담보제공 및 처분제한 등", 20, "text")]
    r = _head(ws, ctx, "금융거래조회서 Control Sheet_유가증권 등", "BC-130-1-1", len(cols1))
    s1 = FORMS["securities"][1]
    rows, flags = [], []
    for d, n, row in _rows_of(ctx.docs, {"securities": 1}):
        rows.append(_ids(d) + [row["계좌번호"], row["금융상품의 종류"], _money(row, "금융상품 금액"), _money(row, "예수금"),
                               _money(row, "신용설정 보증금"), _money(row, "미수금액"), row["담보제공 및 처분제한 등"]])
        flags.append(_flag_set(row))
    r, *_ = _block(ws, r, "1. 조회기준일 현재 당사가 보유하고 있는 조회대상회사의 유가증권 등 금융상품의 내용은 다음과 같습니다.", cols1, rows, flags,
                   subtotal=("금융상품 금액", "예수금", "신용설정 보증금", "미수금액"),
                   note="증권회사 조회서 9번(기중 거래내역)은 원본추출 시트에 있습니다.")
    cols2 = ID_COLS + [("계좌번호", 18, "text"), ("종목명", 24, "text"), ("수량", 12, "money"), ("액면금액", 14, "money"), ("기준가", 12, "money"),
                       ("평가액", 16, "money"), ("만기일", 12, "date"), ("담보제공", 10, "text"), ("비고", 16, "text")]
    rows, flags = [], []
    for d, n, row in _rows_of(ctx.docs, {"securities": 2}):
        rows.append(_ids(d) + [row["계좌번호"], row["종목명"], _money(row, "수량"), _money(row, "액면금액"), _money(row, "기준가"),
                               _money(row, "평가액"), _dt(row, "만기일"), row["담보제공 내역"], row["비고"]])
        flags.append(_flag_set(row))
    _block(ws, r, "2. 조회기준일 현재 당사가 보유하고 있는 조회대상회사의 유가증권 등 금융상품의 상세명세는 다음과 같습니다.", cols2, rows, flags,
           subtotal=("평가액",))


def sheet_loans(wb, ctx: Ctx):
    ws = wb.create_sheet("대출금")
    cols = ID_COLS + [("대출종류", 26, "text"), ("통화", 6, "text"), ("약정한도액", 16, "money"), ("대출금액", 16, "money"),
                      ("외화환산후", 16, "formula"), ("대출일", 11, "date"), ("최종만기일", 11, "date"), ("연이자율", 8, "rate"),
                      ("최종이자지급일", 12, "date"), ("상환방법", 14, "text"), ("담보종류", 30, "text"), ("연대보증인", 12, "text"),
                      ("비고", 22, "text"), ("", 2, "text"), ("유동성장기부채", 16, "money"), ("장기차입금", 16, "money")]
    r = _head(ws, ctx, "금융거래조회서 Control Sheet_대출금 등", "BC-130-2", len(cols))
    rate_ref = _rate_table(ws, len(cols) + 2)
    rows, flags = [], []
    seen = set()
    for d, n, row in _rows_of(ctx.docs, {"bank": 2, "insurance": 2, "guarantee": 4, "securities": 3}):
        spec = FORMS[d.form][n]
        cols9 = spec.columns[1:] if spec.columns[0] == "계좌번호" else spec.columns
        v = [row[c] for c in cols9]                 # 9열 위치 고정: 종류, 한도, 금액, 대출일, 만기, 이율, 이자지급일, 상환, 담보
        k_lim, k_amt, k_d1, k_d2, k_rt, k_d3 = cols9[1], cols9[2], cols9[3], cols9[4], cols9[5], cols9[6]
        memo = f"계좌 {row['계좌번호']}" if spec.columns[0] == "계좌번호" and row.get("계좌번호") else ""
        if id(d) not in seen and _sec(d, n)["extra"].get("총 한도액"):
            memo = (memo + "; " if memo else "") + f"총 한도액: {_sec(d, n)['extra']['총 한도액']}"
        seen.add(id(d))
        rows.append(_ids(d) + [v[0], _ccy(row, k_amt) or _ccy(row, k_lim) or "KRW", _money(row, k_lim), _money(row, k_amt),
                               _fx_formula(6, 8, rate_ref), _dt(row, k_d1), _dt(row, k_d2), _rate(row, k_rt), _dt(row, k_d3),
                               v[7], v[8], "", memo])
        fl = set()
        if row["_flags"].get(k_lim):
            fl.add("약정한도액")
        if row["_flags"].get(k_amt):
            fl.add("대출금액")
        flags.append(fl)
    r2, first, last = _block(ws, r, "1. [총 한도액] 조회기준일 현재 조회대상회사에 대한 당 은행(당사)의 대출거래의 내용은 다음과 같습니다.",
                             cols, rows, flags, subtotal=("약정한도액", "대출금액", "외화환산후", "유동성장기부채", "장기차입금"))
    if rows:
        lab = len(cols) - 3
        VL = get_column_letter(lab + 1)
        for i, (k, f) in enumerate([("조회서금액", f"=SUBTOTAL(9,I{first}:I{last})"), ("회사제시금액", None), ("차이(*1)", f"={VL}{r2}-{VL}{r2 + 1}")]):
            ws.cell(r2 + i, lab, k).font = F_BOLD
            ws.cell(r2 + i, lab).alignment = RIGHT
            c = ws.cell(r2 + i, lab + 1, f)
            c.number_format, c.border, c.font = NUM_MONEY, BORDER, F_BODY
        ws.cell(r2 + 3, lab, "(*1) 회사제시금액은 작성자 입력 후 차이 확인").font = F_NOTE


def sheet_guarantees(wb, ctx: Ctx):
    ws = wb.create_sheet("지급보증")
    cols = ID_COLS + [("내용", 30, "text"), ("한도액", 16, "money"), ("실행금액", 16, "money"), ("지급보증수수료율", 10, "rate"),
                      ("기간", 18, "text"), ("담보지급보증", 20, "text"), ("비고", 20, "text")]
    r = _head(ws, ctx, "금융거래조회서 Control Sheet_지급보증 및 기타약정", "BC-130-3", len(cols))
    rows, flags = [], []
    for d, n, row in _rows_of(ctx.docs, {"bank": 3, "insurance": 3, "guarantee": 6, "securities": 4, "card": 1}):
        rows.append(_ids(d) + [row.get("내용", ""), _money(row, "한도액"), _money(row, "실행금액"), _rate(row, "지급보증수수료율"),
                               row.get("기간", ""), row.get("담보지급보증", row.get("담보·지급보증", "")), row.get("비고", "")])
        flags.append({h for h in ("한도액", "실행금액") if row["_flags"].get(h)})
    _block(ws, r, "1. 조회기준일 현재 조회대상회사에 대한 지급보증 및 기타 약정사항(한도거래 포함)의 내용은 다음과 같습니다.",
           cols, rows, flags, subtotal=("한도액", "실행금액"))


def sheet_derivatives(wb, ctx: Ctx):
    ws = wb.create_sheet("파생상품")
    spec = FORMS["bank"][4]
    cols = ID_COLS + [(c, 16, "money" if c in spec.money else ("date" if c in spec.dates else "text")) for c in spec.columns]
    r = _head(ws, ctx, "금융거래조회서 Control Sheet_미결제 파생상품계약 등", "BC-130-4", len(cols))
    rows, flags = [], []
    for d, n, row in _rows_of(ctx.docs, {"bank": 4}):
        rows.append(_ids(d) + [_money(row, c) if c in spec.money else (_dt(row, c) if c in spec.dates else row[c]) for c in spec.columns])
        flags.append(_flag_set(row))
    r, *_ = _block(ws, r, "1. 조회기준일 현재 조회대상회사의 미결제파생상품계약 등(선물환, 스왑, 옵션 등)의 내용은 다음과 같습니다.", cols, rows, flags)
    s5 = FORMS["securities"][5]
    cols = ID_COLS + [(c, 16, "money" if c in s5.money else ("date" if c in s5.dates else "text")) for c in s5.columns]
    rows, flags = [], []
    for d, n, row in _rows_of(ctx.docs, {"securities": 5}):
        rows.append(_ids(d) + [_money(row, c) if c in s5.money else (_dt(row, c) if c in s5.dates else row[c]) for c in s5.columns])
        flags.append(_flag_set(row))
    _block(ws, r, "2. [증권회사] 조회기준일 현재 조회대상회사의 미결제 파생상품 계약 등의 내용은 다음과 같습니다.", cols, rows, flags)


def sheet_third_party(wb, ctx: Ctx):
    ws = wb.create_sheet("담보제공")
    cols = ID_COLS + [("내용", 24, "text"), ("연대보증 등을 제공받은 회사(개인)", 26, "text"), ("연대보증 등의 대상 여신", 22, "text"),
                      ("연대보증 등의 한도", 16, "money"), ("담보제공한 자산", 26, "text"), ("완전성 검토_주석 REF", 14, "text"),
                      ("금액 대사_계약서 및 명세서", 16, "text")]
    r = _head(ws, ctx, "금융거래조회서 Control Sheet_담보 및 연대보증(제공)", "BC-130-5", len(cols))
    rows, flags = [], []
    for d, n, row in _rows_of(ctx.docs, {"bank": 5, "insurance": 5, "guarantee": 8, "securities": 6}):
        spec = FORMS[d.form][n]
        v = [row[c] for c in spec.columns]
        rows.append(_ids(d) + [v[0], v[1], v[2], _money(row, spec.columns[3]), v[4], "", ""])
        flags.append({"연대보증 등의 한도"} if row["_flags"].get(spec.columns[3]) else set())
    _block(ws, r, "1. 조회기준일 현재 조회대상회사가 타 법인(개인)을 위하여 제공한 담보 및 연대보증의 내용은 다음과 같습니다.",
           cols, rows, flags, subtotal=("연대보증 등의 한도",))


def sheet_notes(wb, ctx: Ctx):
    ws = wb.create_sheet("어음수표")
    r = _head(ws, ctx, "금융거래조회서 Control Sheet_어음·수표", "BC-130-6", 10)
    blocks = [
        ("1. 기중 조회대상회사에 교부한 전자어음·어음수표 용지", {"bank": 6},
         [("구분", 14, "text"), ("교부일자", 12, "date"), ("매수", 8, "int"), ("일련번호", 24, "text")]),
        ("2. 조회기준일 현재 미발행·미결제 전자어음 및 미회수 어음수표", {"bank": 7},
         [("구분", 14, "text"), ("만기일자/교부일자", 14, "text"), ("금액/매수", 14, "text"), ("일련번호", 24, "text")]),
        ("3. 조회기준일 현재 담보·견질 목적으로 보관 중인 어음수표", {"bank": 8, "insurance": 4, "guarantee": 7, "securities": 7},
         [("구분", 14, "text"), ("번호", 16, "text"), ("금액", 16, "money"), ("발행일자", 12, "date"), ("만기일자", 12, "date"), ("담보견질의 목적", 24, "text")]),
        ("4. 기중 당좌거래명세", {"bank": 10},
         [("구분", 12, "text"), ("일자", 12, "date"), ("입금금액", 16, "money"), ("지급금액", 16, "money"), ("일련번호", 16, "text"), ("적요", 24, "text")]),
    ]
    for title, fs, extra in blocks:
        cols = ID_COLS + extra
        rows, flags = [], []
        for d, n, row in _rows_of(ctx.docs, fs):
            spec = FORMS[d.form][n]
            vals = []
            for c in spec.columns:
                if c in spec.money:
                    vals.append(_money(row, c))
                elif c in spec.dates:
                    vals.append(_dt(row, c))
                else:
                    vals.append(row.get(c, ""))
            rows.append(_ids(d) + vals)
            flags.append(_flag_set(row))
        r, *_ = _block(ws, r, title, cols, rows, flags)


def sheet_collateral(wb, ctx: Ctx):
    ws = wb.create_sheet("담보보증내역")
    cols = ID_COLS + [("제공자구분", 12, "text"), ("구분", 22, "text"), ("내용", 24, "text"), ("단위", 6, "text"), ("소유자(제공자)", 20, "text"),
                      ("감정금액", 16, "money"), ("설정금액", 16, "money"), ("설정순위", 8, "text"), ("선순위설정금액", 16, "money"),
                      ("완전성 검토_주석 REF", 14, "text"), ("금액 대사_계약서 및 명세서", 16, "text")]
    r = _head(ws, ctx, "금융거래조회서 Control Sheet_담보·보증 내역(연대보증 등)", "BC-130-7", len(cols))
    rows, flags = [], []
    for d, n, row in _rows_of(ctx.docs, {"bank": 9, "insurance": 6, "guarantee": 9, "securities": 8}):
        rows.append(_ids(d) + [row.get("_group", ""), row["구분"], row["담보보증의 내용"], _ccy(row, "설정금액") or "KRW", row["소유자(제공자)"],
                               _money(row, "감정금액"), _money(row, "설정금액"), row["설정순위"], _money(row, "선순위 설정금액"), "", ""])
        flags.append({h for h in ("감정금액", "설정금액") if row["_flags"].get(h)} | ({"선순위설정금액"} if row["_flags"].get("선순위 설정금액") else set()))
    _block(ws, r, "1. 조회기준일 현재 조회대상회사의 자산 등이 담보와 보증 등으로 제공된 내역과 제3자로부터 제공받은 담보와 보증 등의 내역은 다음과 같습니다. (참고 목적, 정확성 미보증)",
           cols, rows, flags, subtotal=("감정금액", "설정금액", "선순위설정금액"))


def sheet_insurance(wb, ctx: Ctx):
    ws = wb.create_sheet("보증보험")
    r = _head(ws, ctx, "금융거래조회서 Control Sheet_보증·보험", "BC-130-8", 12)
    # 1. 보증(보험) — 보증기관 1
    g1 = FORMS["guarantee"][1]
    cols = ID_COLS + [("보증(보험)의 종류", 16, "text"), ("증권번호", 14, "text"), ("보증상대처(피보험자)", 18, "text"), ("보증금액(보험가입금액)", 18, "money"),
                      ("보증잔액", 14, "money"), ("연간 보증(보험)료", 14, "money"), ("보증(보험)기간", 18, "text"), ("비고", 20, "text"), ("완전성 검토_주석 REF", 14, "text")]
    rows, flags = [], []
    for d, n, row in _rows_of(ctx.docs, {"guarantee": 1}):
        rows.append(_ids(d) + [row[g1.columns[0]], row["증권번호"], row["보증상대처(피보험자)"], _money(row, "보증금액(보험가입금액)"),
                               _money(row, "보증잔액"), _money(row, "연간 보증(보험)료"), row["보증(보험)기간"], row["비고"], ""])
        flags.append({"보증금액(보험가입금액)"} if row["_flags"].get("보증금액(보험가입금액)") else set())
    r, g_first, g_last = _block(ws, r, "1. 조회기준일 현재 조회대상회사의 대출, 채무, 의무 이행 등을 보증하기 위하여 당사가 제공한 보증(보험)의 내용은 다음과 같습니다.",
                                cols, rows, flags, subtotal=("보증금액(보험가입금액)", "보증잔액", "연간 보증(보험)료"))
    ctx.gua_block = (g_first, g_last)          # 월보대사 SUMIFS 범위(보증기관 보증금액 = 8열 H)
    # 2. 보험거래 — 보험회사 1
    i1 = FORMS["insurance"][1]
    cols = ID_COLS + [("보험의 종류", 22, "text"), ("증권번호", 16, "text"), ("부보금액", 16, "money"), ("연간보험료_보장성보험료 및 사업비", 16, "money"),
                      ("연간보험료_이외", 12, "money"), ("부보기간_시작", 12, "date"), ("부보기간_종료", 12, "date"), ("누적 적립금", 14, "money"),
                      ("해약환급금", 14, "money"), ("연이자율", 8, "rate"), ("권리제한", 12, "text"), ("비고", 20, "text")]
    rows, flags = [], []
    for d, n, row in _rows_of(ctx.docs, {"insurance": 1}):
        rows.append(_ids(d) + [row["보험의 종류"], row["증권번호"], _money(row, "부보금액"), _money(row, "연간보험료"), _money(row, "연간보험료 이외"),
                               _dt(row, "부보기간 시작"), _dt(row, "부보기간 종료"), _money(row, "누적 적립금"), _money(row, "해약환급금"),
                               _rate(row, "연이자율"), row["권리제한"], row["비고"]])
        fl = set()
        for src, dst in (("부보금액", "부보금액"), ("연간보험료", "연간보험료_보장성보험료 및 사업비"), ("연간보험료 이외", "연간보험료_이외"),
                         ("누적 적립금", "누적 적립금"), ("해약환급금", "해약환급금")):
            if row["_flags"].get(src):
                fl.add(dst)
        flags.append(fl)
    r, *_ = _block(ws, r, "2. 조회기준일 현재 조회대상회사의 당사에 대한 보험거래 내용은 다음과 같습니다.", cols, rows, flags,
                   subtotal=("부보금액", "연간보험료_보장성보험료 및 사업비", "연간보험료_이외", "누적 적립금", "해약환급금"))
    # 3. 신용보험 + 기타 공제·보험 — 보증기관 2·3
    cols = ID_COLS + [("구분", 10, "text"), ("상품의 종류", 20, "text"), ("증권번호", 14, "text"), ("보험 대상 자산", 18, "text"),
                      ("보험금액(보증금액)/보장금액", 18, "money"), ("연간보험료/계약 공제(보험)료", 16, "money"), ("보험(공제)기간", 18, "text"),
                      ("누적적립금", 14, "money"), ("해약환급금", 14, "money"), ("권리제한", 12, "text"), ("비고", 20, "text")]
    rows, flags = [], []
    for d, n, row in list(_rows_of(ctx.docs, {"guarantee": 2})) + list(_rows_of(ctx.docs, {"guarantee": 3})):
        if n == 2:
            rows.append(_ids(d) + ["신용보험", row["상품의 종류"], row["증권번호"], row["보험 대상 자산"], _money(row, "보험금액(보증금액)"),
                                   _money(row, "연간보험료"), row["보험기간"], "", "", "", row["비고"]])
        else:
            rows.append(_ids(d) + ["기타 공제·보험", row["상품의 종류"], row["증권번호"], "", _money(row, "보장 금액"), _money(row, "계약 공제(보험)료"),
                                   row["공제(보험)기간"], _money(row, "누적적립금"), _money(row, "해약환급금"), row["권리제한"], row["비고"]])
        flags.append(set())
    r, *_ = _block(ws, r, "3. 신용보강을 위한 신용보험 및 손해 보상을 위한 기타 공제·보험 상품의 내용은 다음과 같습니다.", cols, rows, flags)
    # 4. 출자금 — 보증기관 5
    cols = ID_COLS + [("출자일", 12, "date"), ("출자금액", 16, "money"), ("출자좌수", 12, "text"), ("평가금액", 16, "money"), ("지분율", 10, "text"), ("담보제공", 12, "text")]
    rows = [_ids(d) + [_dt(row, "출자일"), _money(row, "출자금액"), row["출자좌수"], _money(row, "평가금액"), row["지분율"], row["담보제공"]]
            for d, n, row in _rows_of(ctx.docs, {"guarantee": 5})]
    _block(ws, r, "4. 조회기준일 현재 조회대상회사의 당사에 대한 출자금 등의 내용은 다음과 같습니다.", cols, rows)


def sheet_raw(wb, ctx: Ctx):
    ws = wb.create_sheet("원본추출")
    ws.sheet_view.showGridLines = False
    cols = [("조회대상회사", 20, "text"), ("No", 8, "no"), ("금융기관", 14, "text"), ("지점", 14, "text"), ("양식", 8, "text"), ("항목번호", 6, "int"),
            ("항목명", 20, "text"), ("행번호", 6, "int"), ("열명", 22, "text"), ("원문값", 30, "text"), ("정규화값", 20, "text"),
            ("검토플래그", 8, "text"), ("원본파일", 34, "text"), ("페이지", 6, "int")]
    rows = []
    for d in ctx.docs:
        if d.status != "성공":
            continue
        specs = FORMS[d.form]
        base = [doc_company(d), d.bc_label, doc_institution(d), d.footer.get("branch", ""), d.form_label]
        for n, s in d.sections.items():
            name = specs[n].name
            if not s["rows"]:
                rows.append(base + [n, name, 0, "", "거래없음" if s["no_txn"] else "(표 없음)", "", "", d.source.path.name, ""])
                continue
            for i, row in enumerate(s["rows"], start=1):
                for c in specs[n].columns:
                    nv = row["_n"].get(c)
                    if isinstance(nv, tuple):
                        nv = " ".join(str(x) for x in nv if x is not None and x != "")
                    rows.append(base + [n, name, i, c, row[c], nv if nv is not None else "", "Y" if row["_flags"].get(c) else "",
                                        d.source.path.name, row.get("_page", "")])
    _block(ws, 1, "", cols, rows)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{max(len(rows), 1) + 1}"


def sheet_ocr(wb, ctx: Ctx):
    docs = [d for d in ctx.docs if d.ocr_pages is not None]
    if not docs:
        return
    ws = wb.create_sheet("OCR판독")
    ws.sheet_view.showGridLines = False
    ws.cell(1, 1, "스캔본 OCR 결과(Windows 내장 OCR, 추정) — 금액·거래 여부는 반드시 원문 PDF로 확인하고 해당 시트에 직접 입력. "
                  "OCR 값은 다른 시트에 자동 반영하지 않습니다.").font = F_NOTE
    cols = [("No", 8, "no"), ("조회대상회사", 20, "text"), ("금융기관(파일명 추정)", 18, "text"), ("원본파일", 34, "text"),
            ("'해당사항 없음' 문구", 10, "int"), ("금액 후보", 30, "text"), ("페이지", 6, "int"), ("OCR 텍스트", 100, "text")]
    rows, flags = [], []
    for d in docs:
        sm = d.ocr_summary or {}
        name = d.source.path.name + (f" ▸ {d.source.inner_name}" if d.source.inner_name else "")
        for i, text in enumerate(d.ocr_pages or [""], start=1):
            rows.append([d.bc_label, doc_company(d), doc_institution(d), name, sm.get("no_txn", 0) if i == 1 else "",
                         ", ".join(sm.get("amounts", [])) if i == 1 else "", i, (text or "")[:32000]])
            flags.append({"'해당사항 없음' 문구", "금액 후보"} if i == 1 else set())
    _block(ws, 2, "", cols, rows, flags)
    ws.freeze_panes = "A4"


def sheet_log(wb, ctx: Ctx):
    ws = wb.create_sheet("처리로그")
    ws.sheet_view.showGridLines = False
    cols = [("파일", 40, "text"), ("종류", 6, "text"), ("양식", 8, "text"), ("조회대상회사", 20, "text"), ("금융기관", 14, "text"), ("지점", 14, "text"),
            ("페이지수", 7, "int"), ("텍스트여부", 8, "text"), ("결과", 16, "text"), ("항목별 행수", 40, "text"), ("메시지", 40, "text"),
            ("정리파일", 34, "text"), ("SHA-256", 24, "text"), ("zip SHA-256", 24, "text"), ("처리일시", 16, "text"),
            ("조회기준일", 11, "date"), ("발급일", 11, "date"), ("No", 8, "no")]
    rows = []
    for d in ctx.docs:
        counts = ""
        if d.sections:
            specs = FORMS[d.form]
            counts = ", ".join(f"{n}.{specs[n].name}:{len(s['rows'])}{'(거래없음)' if s['no_txn'] else ''}" for n, s in d.sections.items())
        rows.append([d.source.path.name + (f" ▸ {d.source.inner_name}" if d.source.inner_name else ""), d.source.kind,
                     d.form_label if d.form else "", doc_company(d), doc_institution(d), d.footer.get("branch", ""), d.pages,
                     "N" if d.is_scan else "Y", d.status, counts, d.message, d.saved_path.name if d.saved_path else "",
                     d.sha256, d.zip_sha256, ctx.now, _date(d.header.get("ref_date")), _date(d.footer.get("issue_date")), d.bc_label])
    _block(ws, 1, "", cols, rows)
    ws.freeze_panes = "A2"


# ---------------------------------------------------------------------------
def write_workbook(docs: list[ConfirmDoc], out_path: Path, client: Optional[str] = None, wolbo=None,
                   inputs: Optional[dict] = None, bc_map: Optional[dict] = None, stats: Optional[dict] = None) -> Path:
    """docs → xlsx. wolbo: WolboDoc(월보), inputs: carry_over.collect_inputs() 결과(이전 버전 입력값), bc_map: 번호 고정용."""
    ordered, client = assign_numbers(docs, client, bc_map)
    ctx = Ctx(ordered, client, wolbo)
    wb = Workbook()
    sheet_cs(wb, ctx)
    sheet_completeness(wb, ctx)
    sheet_deposits(wb, ctx)
    sheet_securities(wb, ctx)
    sheet_loans(wb, ctx)
    sheet_guarantees(wb, ctx)
    sheet_derivatives(wb, ctx)
    sheet_third_party(wb, ctx)
    sheet_notes(wb, ctx)
    sheet_collateral(wb, ctx)
    sheet_insurance(wb, ctx)
    sheet_monthly(wb, ctx)                     # 보증보험 시트 범위를 참조하므로 그 뒤에 만들고 3번째 자리로 옮긴다
    wb.move_sheet("월보대사", offset=2 - wb.sheetnames.index("월보대사"))
    sheet_raw(wb, ctx)
    sheet_ocr(wb, ctx)
    sheet_log(wb, ctx)
    if inputs:
        from carry_over import apply_inputs
        applied, failed = apply_inputs(wb, inputs)
        if stats is not None:
            stats["carried"], stats["carry_failed"] = applied, len(failed)
    # 의도치 않은 수식 방지: '='로 시작하는 문자열 중 우리가 만든 수식(SUBTOTAL/IF/COUNT) 외는 문자열로
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.data_type == "f" and not re.match(r"^=(SUBTOTAL|SUM(IFS?)?\(|ABS\(|IF|IFERROR|COUNT|COUNTA|COUNTIF|AND|[A-Z]{1,2}\d+[-+=])", str(c.value)):
                    c.value = "'" + str(c.value)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path
