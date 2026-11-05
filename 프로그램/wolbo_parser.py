# -*- coding: utf-8 -*-
"""은행연합회(한국신용정보원/NICE) "[월보] 금융기관별 계정과목별 조회 (잔액)" PDF 파서.

구조(참고/월보샘플_*.pdf, OZ Report Viewer 출력):
- 머리: 법인명 | 사업자등록번호 | 기준일자(YYYY.MM) | 최종 변경일자 | 조회자ID/조회자 | 조회일시 | NICE 번호
- 절: "신용공여 잔액(<그룹>N) (단위: 백만원)", "한도 잔액(은행N)", "담보 잔액(은행N)"
  표: 대출과목명 | (구분/과목 2단 라벨 또는 1단) | 기관1 | 계열합계 | 기관2 | 계열합계 | 총계
  표가 페이지를 넘어가면 다음 페이지 첫 표는 머리글 없이 이어진다.
- 금액 단위 백만원, "-"는 없음.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pdfplumber

UNIT = 1_000_000  # 백만원 → 원

_TITLE_RE = re.compile(r"^(?P<kind>신용공여\s*잔액|한도\s*잔액|담보\s*잔액)\s*\((?P<grp>.+?)\)\s*(?:\(단위\s*[:：]\s*(?P<unit>[^)]+)\))?\s*$")
_SUBTOTAL_RE = re.compile(r"(계|총계)$")
_TOTAL_ITEM_RE = re.compile(r"(소계|계|합계)$")


@dataclass
class WolboRow:
    section: str            # 신용공여 / 한도 / 담보
    group: str              # 은행 / 보험 / 특수금융기관 / 정부산하공단 / 여신전문금융 ...
    category: str           # 구분(대출채권/주석/신용공여합계/재산권/보증/기타…)
    item: str               # 과목명(원화대출금 운전자금, 대출채권계, 합계…)
    values: dict            # {열이름: 백만원 float|None} — 기관 열과 계열합계 열 모두
    is_total: bool = False  # 소계·계·합계 행

    def amount(self, inst: str) -> Optional[float]:
        return self.values.get(inst)


@dataclass
class WolboDoc:
    path: Path
    company: str = ""
    biz_no: str = ""
    base_month: str = ""     # "2026.06"
    changed_date: str = ""
    viewer: str = ""         # "user01 / 홍길동"
    query_ts: str = ""
    nice_no: str = ""
    unit: str = "백만원"
    rows: list = field(default_factory=list)
    institutions: dict = field(default_factory=dict)   # {group: [기관명...]} (계열합계 열 제외)
    notes: list = field(default_factory=list)

    # -- 조회 도우미 --
    def all_institutions(self) -> list[str]:
        seen, out = set(), []
        for g, lst in self.institutions.items():
            for n in lst:
                if n not in seen:
                    seen.add(n); out.append(n)
        return out

    def rows_for(self, inst: str, section: str = "신용공여") -> list[WolboRow]:
        return [r for r in self.rows if r.section == section and inst in r.values and r.values.get(inst) is not None]

    def credit_lines(self, inst: str) -> dict:
        """기관별 요약: 대출채권 세부/계, 주석(지급보증) 세부/계, 합계 (백만원)"""
        out = {"loan_items": [], "loan_total": None, "gua_items": [], "gua_total": None, "total": None}
        for r in self.rows:
            if r.section != "신용공여" or inst not in r.values:
                continue
            v = r.values.get(inst)
            cat = r.category.replace(" ", "")
            if cat == "대출채권":
                if r.item.endswith("대출채권계"):
                    out["loan_total"] = v
                elif not r.is_total:
                    out["loan_items"].append((r.item, v))
            elif cat.startswith("주석"):
                if r.item.endswith("주석계") or r.item.endswith("지급보증등계"):
                    out["gua_total"] = v
                elif not r.is_total:
                    out["gua_items"].append((r.item, v))
            elif cat.startswith("신용공여"):
                if r.item == "합계":
                    out["total"] = v
                elif r.item.startswith("대출채권") and out["loan_total"] is None:
                    out["loan_total"] = v
                elif r.item.startswith(("주석", "지급보증")) and out["gua_total"] is None:
                    out["gua_total"] = v
        return out


def _amt(s: Optional[str]) -> Optional[float]:
    if s is None:
        return None
    t = str(s).replace("\n", "").replace(",", "").replace("△", "-").strip()
    if t in ("", "-", "－"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _clean(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\n", " ")).strip()


def is_wolbo_pdf(first_page_text: str) -> bool:
    t = first_page_text or ""
    return "[월보]" in t and "계정과목별" in t


def parse_wolbo(path) -> WolboDoc:
    path = Path(path)
    doc = WolboDoc(path=path)
    cur_title: Optional[tuple[str, str]] = None      # (section, group)
    cur_headers: list[str] = []                       # 값 열 이름(기관·계열합계)
    cur_label_cols = 2
    carry_cat = ""
    with pdfplumber.open(path) as pdf:
        first = pdf.pages[0].extract_text() or ""
        if not is_wolbo_pdf(first):
            doc.notes.append("월보 양식 키워드 없음")
        _parse_header(first, doc)
        for pi, page in enumerate(pdf.pages, start=1):
            titles = []
            for ln in page.extract_text_lines():
                m = _TITLE_RE.match(ln["text"].strip())
                if m:
                    grp = m.group("grp")
                    grp = re.sub(r"\d+$", "", grp).strip()
                    grp = grp.split("(")[0].strip()
                    sec = m.group("kind").replace(" ", "").replace("잔액", "")
                    titles.append((ln["top"], (sec, grp), (m.group("unit") or "").strip()))
            for tbl in page.find_tables():
                raw = tbl.extract()
                if not raw:
                    continue
                rows = [[_clean(c) for c in r] for r in raw]
                r0 = rows[0]
                above = [t for t in titles if t[0] < tbl.bbox[1]]
                if r0 and r0[0] == "대출과목명":
                    if not above and cur_title is None:
                        continue
                    if above:
                        cur_title = above[-1][1]
                        if above[-1][2]:
                            doc.unit = above[-1][2]
                    cur_label_cols = 2 if len(r0) > 1 and r0[1] == "" else 1
                    cur_headers = r0[cur_label_cols:]
                    insts = [h for h in cur_headers if h and h != "-" and not _SUBTOTAL_RE.search(h)]
                    doc.institutions.setdefault(cur_title[1], [])
                    for n in insts:
                        if n not in doc.institutions[cur_title[1]]:
                            doc.institutions[cur_title[1]].append(n)
                    data = rows[1:]
                    carry_cat = ""
                elif cur_title is not None and not above and rows and len(r0) >= len(cur_headers) + 1 \
                        and r0[0] not in ("[월보]", "법인명") and "유의사항" not in "".join(r0):
                    data = rows          # 페이지 넘어온 이어짐 표
                else:
                    continue
                sec, grp = cur_title
                for r in data:
                    if len(r) == len(cur_headers) + cur_label_cols:
                        labels, vals = r[:cur_label_cols], r[cur_label_cols:]
                    elif len(r) == len(cur_headers) + 1:
                        labels, vals = [carry_cat, r[0]], r[1:]
                    else:
                        continue
                    if cur_label_cols == 2:
                        cat, item = labels[0], labels[1]
                        if cat:
                            carry_cat = cat
                        else:
                            cat = carry_cat
                    else:
                        cat, item = "", labels[0]
                    if not item or set(item) <= {"-"}:
                        continue
                    values = {h: _amt(v) for h, v in zip(cur_headers, vals) if h and h != "-"}
                    is_total = bool(_TOTAL_ITEM_RE.search(item)) or cat.replace(" ", "").startswith("신용공여")
                    doc.rows.append(WolboRow(sec, grp, cat, item, values, is_total))
    return doc


def _parse_header(text: str, doc: WolboDoc):
    t = text or ""
    m = re.search(r"법인명\s+(.+?)\s+사업자등록번호\s+([\d\-]+)", t)
    if m:
        doc.company, doc.biz_no = m.group(1).strip(), m.group(2)
    m = re.search(r"기준일자\s+([\d.]+)\s+최종\s*변경일자\s+([\d.]+)", t)
    if m:
        doc.base_month, doc.changed_date = m.group(1), m.group(2)
    m = re.search(r"조회자ID/조회자\s+(.+?)\s+조회일시\s+([\d.]+\s+[\d:]+)", t)
    if m:
        doc.viewer, doc.query_ts = m.group(1).strip(), m.group(2)
    m = re.search(r"(NICE-[\d\-]+)", t)
    if m:
        doc.nice_no = m.group(1)
    m = re.search(r"단위\s*[:：]\s*(\S+?)\)", t)
    if m:
        doc.unit = m.group(1)


# ---------------------------------------------------------------------------
# 기관명 매칭 (조회서 꼬리의 기관명 ↔ 월보 열 이름)
# ---------------------------------------------------------------------------
_ALIASES = {
    "현대해상": "현대해상화재보험", "케이비손해보험": "KB손해보험", "디비손해보험": "DB손해보험",
    "중소기업진흥공단": "중소벤처기업진흥공단", "KEB하나은행": "하나은행", "KB국민은행": "국민은행",
    "IBK기업은행": "기업은행", "NH농협은행": "농협은행", "SC제일은행": "SC은행", "우리금융캐피탈": "우리금융캐피탈",
}


def inst_key(name: str) -> str:
    n = re.sub(r"\s+", "", name or "")
    n = re.sub(r"주식회사|\(주\)|㈜|\(유\)", "", n)
    n = re.sub(r"\(.*?\)$", "", n)           # 뒤 괄호 지점 등
    n = _ALIASES.get(n, n)
    return n.upper()


def match_institution(name: str, candidates: list[str]) -> Optional[str]:
    k = inst_key(name)
    if not k:
        return None
    for c in candidates:
        if inst_key(c) == k:
            return c
    for c in candidates:                     # 부분 일치(한쪽이 다른 쪽을 포함)
        ck = inst_key(c)
        if len(k) >= 3 and len(ck) >= 3 and (k in ck or ck in k):
            return c
    return None
