# -*- coding: utf-8 -*-
"""금융결제원 발급 금융거래조회서(은행/보험회사/보증기관) PDF 파서.

입력: PDF 또는 금결원 다운로드 zip(내부 PDF 1개)
출력: ConfirmDoc (헤더·꼬리·항목별 표 행)
"""
from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pdfplumber

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------
NO_TXN = ("해당거래없음", "당행거래회사아님", "당사거래회사아님", "담보보증내역없음", "해당사항없음")
NOISE_LINES = {"열", "람 용", "람용", "열 람 용", "열람용", "SCRIPT ERROR"}
SUBHEADER_TOKENS = {
    "약정한도액", "대출금액", "연이율", "연이자율", "최종이자지급일", "최종이자 지급일",
    "보장성보험료및 사업비", "보장성보험료 및 사업비", "이외", "시작", "종료",
    "대출·융자·투자금액", "매입금액", "매도금액", "회사(개인)", "대상 여신", "간",
}
FORM_LABEL = {"bank": "은행", "insurance": "보험회사", "guarantee": "보증기관"}
FORM_ORDER = {"bank": 0, "insurance": 1, "guarantee": 2}
SCAN_STATUS = "스캔본-수동입력필요"


@dataclass(frozen=True)
class Section:
    name: str
    header_re: str            # 헤더 행(공백 제거·이어붙임)에 대한 정규식
    columns: tuple            # 정규화 후 열 이름
    money: tuple = ()         # normalize_amount 적용 열
    dates: tuple = ()         # normalize_date 적용 열
    rates: tuple = ()         # normalize_rate 적용 열
    min_cols: int = 0         # 표 열 수가 이 값 이상이면 허용(0 = len(columns) 정확히)


_BANK_LOAN = Section(
    "대출", r"^대출종류금액",
    ("대출 종류", "약정한도액", "대출금액", "대출일", "최종만기일", "연이율", "최종이자지급일", "상환방법", "담보 보증 및 관련약정"),
    money=("약정한도액", "대출금액"), dates=("대출일", "최종만기일", "최종이자지급일"), rates=("연이율",))
_GUARANTEE_CMT_BANK = Section(
    "지급보증 및 기타약정", r"^내용한도액실행금액",
    ("내용", "한도액", "실행금액", "지급보증수수료율", "기간", "담보지급보증"),
    money=("한도액", "실행금액"), rates=("지급보증수수료율",))
_GUARANTEE_CMT_INS = Section(
    "지급보증 및 기타약정", r"^내용한도액실행금액",
    ("내용", "한도액", "실행금액", "지급보증수수료율", "기간", "담보지급보증", "비고"),
    money=("한도액", "실행금액"), rates=("지급보증수수료율",))
_THIRD_PARTY = Section(
    "타인을 위한 담보·연대보증", r"^내용연대보증",
    ("내용", "연대보증 등을 제공받은 회사(개인)", "연대보증 등의 대상 여신", "연대보증 등의 한도", "담보제공한 자산"),
    money=("연대보증 등의 한도",))
_NOTE_CUSTODY = Section(
    "담보·견질 어음수표", r"^구분(\(어음또는수표\))?번호금액",
    ("구분", "번호", "금액", "발행일자", "만기일자", "담보견질의 목적"),
    money=("금액",), dates=("발행일자", "만기일자"))
_COLLATERAL = Section(
    "담보·보증 내역", r"^구분담보·?보증의내용",
    ("구분", "담보보증의 내용", "소유자(제공자)", "감정금액", "설정금액", "설정순위", "선순위 설정금액"),
    money=("감정금액", "설정금액", "선순위 설정금액"))

FORMS: dict[str, dict[int, Section]] = {
    "bank": {
        1: Section("예적금", r"^금융상품의종류",
                   ("금융상품의 종류", "계좌번호", "금액", "연이자율", "최종이자지급일", "만기일", "인출제한 등"),
                   money=("금액",), dates=("최종이자지급일", "만기일"), rates=("연이자율",)),
        2: _BANK_LOAN,
        3: _GUARANTEE_CMT_BANK,
        4: Section("미결제 파생상품", r"^계약의종류",
                   ("계약의 종류", "계약일", "한도액", "당행의 매입금액", "당행의 매도금액", "계약실행일/만기일", "약정환율/이자율/주가지수 등", "평가금액"),
                   money=("한도액", "당행의 매입금액", "당행의 매도금액", "평가금액"), dates=("계약일",)),
        5: _THIRD_PARTY,
        6: Section("어음수표 교부", r"^교부일자매수",
                   ("구분", "교부일자", "매수", "일련번호"), dates=("교부일자",), min_cols=3),
        7: Section("미결제·미회수 어음수표", r"^(만기일자금액|교부일자매수)",
                   ("구분", "만기일자/교부일자", "금액/매수", "일련번호"), min_cols=3),
        8: _NOTE_CUSTODY,
        9: _COLLATERAL,
        10: Section("당좌거래명세", r"^구분일자입금금액",
                    ("구분", "일자", "입금금액", "지급금액", "일련번호", "적요"),
                    money=("입금금액", "지급금액"), dates=("일자",)),
    },
    "insurance": {
        1: Section("보험거래", r"^보험의종류증권번호",
                   ("보험의 종류", "증권번호", "부보금액", "연간보험료", "연간보험료 이외", "부보기간 시작", "부보기간 종료",
                    "누적 적립금", "해약환급금", "연이자율", "권리제한", "비고"),
                   money=("부보금액", "연간보험료", "연간보험료 이외", "누적 적립금", "해약환급금"),
                   dates=("부보기간 시작", "부보기간 종료"), rates=("연이자율",)),
        2: _BANK_LOAN,
        3: _GUARANTEE_CMT_INS,
        4: _NOTE_CUSTODY,
        5: _THIRD_PARTY,
        6: _COLLATERAL,
    },
    "guarantee": {
        1: Section("보증·보험", r"^보증\(보험\)의",
                   ("보증(보험)의 종류", "증권번호", "보증상대처(피보험자)", "보증금액(보험가입금액)", "보증잔액", "연간 보증(보험)료", "보증(보험)기간", "비고"),
                   money=("보증금액(보험가입금액)", "보증잔액", "연간 보증(보험)료")),
        2: Section("신용보험", r"^상품의종류증권번호보험대상자산",
                   ("상품의 종류", "증권번호", "보험 대상 자산", "보험금액(보증금액)", "연간보험료", "보험기간", "비고"),
                   money=("보험금액(보증금액)", "연간보험료")),
        3: Section("기타 공제·보험", r"^상품의종류증권번호보장금액",
                   ("상품의 종류", "증권번호", "보장 금액", "계약 공제(보험)료", "공제(보험)기간", "누적적립금", "해약환급금", "권리제한", "비고"),
                   money=("보장 금액", "계약 공제(보험)료", "누적적립금", "해약환급금")),
        4: Section("대출·융자·투자", r"^대출·융자·투자종류",
                   ("대출·융자·투자종류", "약정한도액", "대출·융자·투자금액", "대출·융자일", "최종만기일", "연이자율", "최종이자지급일", "상환방법", "담보·보증 및 관련 약정"),
                   money=("약정한도액", "대출·융자·투자금액"), dates=("대출·융자일", "최종만기일", "최종이자지급일"), rates=("연이자율",)),
        5: Section("출자금", r"^출자일출자금액",
                   ("출자일", "출자금액", "출자좌수", "평가금액", "지분율", "담보제공"),
                   money=("출자금액", "평가금액"), dates=("출자일",)),
        6: Section("한도거래 및 기타약정", r"^내용한도액실행금액기간",
                   ("내용", "한도액", "실행금액", "기간", "담보·지급보증", "비고"),
                   money=("한도액", "실행금액")),
        7: _NOTE_CUSTODY,
        8: Section("타인을 위한 담보·연대보증", r"^내용연대보증",
                   ("내용", "연대보증등을 제공 받은 회사(개인)", "연대보증 등의 대상 보증·융자 등", "연대보증 등의 한도", "담보제공한 자산"),
                   money=("연대보증 등의 한도",)),
        9: _COLLATERAL,
    },
}


# ---------------------------------------------------------------------------
# 정규화
# ---------------------------------------------------------------------------
_NUM_FRAG = re.compile(r"-?[\d][\d,]*(?:\.\d+)?|-?\.\d+")


def _to_float(s: str) -> Optional[float]:
    s = s.replace(",", "").strip()
    if not s or s in {"-", "."}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def normalize_amount(s: Optional[str]):
    """'KRW 152,381.00\\n(152,381.00)' -> ('KRW', 152381.0, 152381.0, False)
    반환: (통화, 금액, 원화환산(괄호 안), 재조립플래그)"""
    if not s:
        return ("", None, None, False)
    text = str(s).strip()
    currency = ""
    m = re.match(r"^([A-Z]{3})\b", text)
    if m:
        currency = m.group(1)
        text = text[m.end():]
    krw = None
    pm = re.search(r"\(\s*(-?[\d,.]+)\s*\)", text)
    if pm:
        krw = _to_float(pm.group(1))
        text = text[:pm.start()] + text[pm.end():]
    frags = _NUM_FRAG.findall(text)
    if not frags:
        return (currency, None, krw, False)
    flag = len(frags) > 1
    amount = _to_float("".join(frags))
    if amount is not None and not currency:
        currency = "KRW"
    return (currency, amount, krw, flag)


def normalize_date(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    t = re.sub(r"[^\d]", "", str(s))
    if len(t) != 8:
        return None
    y, mo, d = int(t[:4]), int(t[4:6]), int(t[6:])
    if y < 1900 or not (1 <= mo <= 12) or not (1 <= d <= 31):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}"


def normalize_rate(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    return _to_float(str(s).replace("%", ""))


def clean_cell(s: Optional[str], keep_newlines: bool = False) -> str:
    """잡음 줄(워터마크·SCRIPT ERROR) 제거 후 줄을 이어붙임.
    keep_newlines=True면 줄바꿈을 보존(금액 재조립 판정용)."""
    if s is None:
        return ""
    lines = []
    for ln in str(s).replace("\r", "").split("\n"):
        ln = ln.strip()
        if ln in NOISE_LINES or not ln:
            continue
        ln = ln.replace("SCRIPT ERROR", "").strip()
        lines.append(ln)
    out = ("\n" if keep_newlines else "").join(lines)
    return out.strip()


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def is_no_txn(row) -> bool:
    for c in row:
        t = _squash(clean_cell(c))
        if any(k in t for k in NO_TXN):
            return True
    return False


# ---------------------------------------------------------------------------
# 양식 판별 · 헤더 · 꼬리
# ---------------------------------------------------------------------------
def detect_form(text: str) -> Optional[str]:
    t = _squash(text or "")
    if "당은행에대한금융상품" in t:
        return "bank"
    if "당사에대한보험거래" in t:
        return "insurance"
    if "제공한보증(보험)의내용" in t:
        return "guarantee"
    return None


_HEADER_RE = re.compile(
    r"조회대상\s*회사\s*[:：]\s*(?P<company>.+?)\s*사\s*업자등록번호\s*[:：]\s*(?P<biz>[\d\-]+)"
    r"\s*조회기준일\s*[:：]\s*(?P<y>\d{4})\s*년\s*(?P<m>\d{1,2})\s*월\s*(?P<d>\d{1,2})\s*일")


_FIRM_RE = re.compile(r"(?P<firm>\S+)\s*담당공인회계사\s*[:：]?\s*(?P<cpa>\S+)\s*귀\s*중")


def parse_header(text: str) -> dict:
    out = {"company": "", "biz_no": "", "ref_date": None, "firm": "", "cpa": ""}
    fm = _FIRM_RE.search(text or "")
    if fm:
        out["firm"], out["cpa"] = fm.group("firm"), fm.group("cpa")
    m = _HEADER_RE.search(text or "")
    if m:
        out["company"] = re.sub(r"\s+", " ", m.group("company")).strip()
        out["biz_no"] = m.group("biz")
        out["ref_date"] = f"{int(m.group('y')):04d}-{int(m.group('m')):02d}-{int(m.group('d')):02d}"
    return out


_FOOTER_RE = re.compile(r"(?P<y>\d{4})년\s*(?P<m>\d{1,2})월\s*(?P<d>\d{1,2})일\s+(?P<body>.+?)\s*부·지점")


def parse_footer(text: str) -> dict:
    out = {"issue_date": None, "institution": "", "branch": "", "officer": "", "phone": "", "email": ""}
    t = text or ""
    m = _FOOTER_RE.search(t)
    if m:
        out["issue_date"] = f"{int(m.group('y')):04d}-{int(m.group('m')):02d}-{int(m.group('d')):02d}"
        body = re.sub(r"\s+", " ", m.group("body")).strip()
        bm = re.match(r"^(\S+)\s+은행\s*(.*)$", body)
        if bm:
            out["institution"] = bm.group(1) + "은행"
            out["branch"] = bm.group(2).strip()
        else:
            parts = body.split(" ", 1)
            out["institution"] = parts[0]
            out["branch"] = parts[1].strip() if len(parts) > 1 else ""
    om = re.search(r"담당자\s*[:：]\s*(\S+)", t)
    if om:
        out["officer"] = om.group(1)
    pm = re.search(r"문의전화\s*[:：]\s*([\d\-\s]+?)\s*,", t)
    if pm:
        out["phone"] = pm.group(1).strip()
    em = re.search(r"e-?mail\s*[:：]\s*([^\s\)]*)", t, re.I)
    if em:
        out["email"] = em.group(1).strip()
    return out


# ---------------------------------------------------------------------------
# 항목별 표 추출
# ---------------------------------------------------------------------------
_TITLE_RE = re.compile(r"^\s*(\d{1,2})\.\s+\S")
_GROUP_LABEL_RE = re.compile(r"^\(.*\)$")
_ROW_LABELS = ("전자어음", "수표·어음", "미결제 전자어음", "수표어음")


def _new_result():
    return {"rows": [], "no_txn": False, "pages": [], "raw": [], "note": "", "extra": {}}


def _match_sections(form: str, header_key: str) -> list[int]:
    return [n for n, spec in FORMS[form].items() if re.search(spec.header_re, header_key)]


def _normalize_row(spec: Section, cells: list[str], raw_cells: Optional[list[str]] = None) -> dict:
    """cells: 줄바꿈 제거본(표시용), raw_cells: 줄바꿈 보존본(금액 재조립 판정용)"""
    raw_cells = raw_cells or cells
    row = {}
    raw = {}
    for i, col in enumerate(spec.columns):
        row[col] = cells[i] if i < len(cells) else ""
        raw[col] = raw_cells[i] if i < len(raw_cells) else ""
    n = {}
    flags = {}
    for col in spec.money:
        cur, amt, krw, flag = normalize_amount(raw.get(col, ""))
        n[col] = (cur, amt, krw)
        flags[col] = flag
    for col in spec.dates:
        n[col] = normalize_date(row.get(col, ""))
    for col in spec.rates:
        n[col] = normalize_rate(row.get(col, ""))
    row["_n"] = n
    row["_flags"] = flags
    return row


def extract_sections(pdf, form: str, institution: str = "") -> dict[int, dict]:
    specs = FORMS[form]
    results = {n: _new_result() for n in specs}
    cur: Optional[int] = None
    inst_key = _squash(institution)
    for pi, page in enumerate(pdf.pages, start=1):
        titles = []
        for ln in page.extract_text_lines():
            m = _TITLE_RE.match(ln["text"])
            if m and 1 <= int(m.group(1)) <= len(specs):
                titles.append((ln["top"], int(m.group(1))))
        for tbl in page.find_tables():
            raw = tbl.extract()
            if not raw:
                continue
            rows_nl = [[clean_cell(c, keep_newlines=True) for c in r] for r in raw]
            rows = [[c.replace("\n", "") for c in r] for r in rows_nl]
            above = [n for (y, n) in titles if y < tbl.bbox[1]]
            attributed = above[-1] if above else cur
            r0 = rows[0]
            # 2단 헤더 여부
            two = len(rows) > 1 and any(_squash(c) in {_squash(t) for t in SUBHEADER_TOKENS} for c in rows[1] if c)
            hdr_rows = rows[:2] if two else rows[:1]
            header_key = _squash("".join(r0))
            # '총 한도액' 부속 표
            if header_key.startswith("총한도액"):
                sec = attributed if attributed in specs else None
                if sec is not None:
                    results[sec]["extra"]["총 한도액"] = rows[0][-1] if len(rows[0]) > 1 else ""
                continue
            cands = _match_sections(form, header_key)
            if attributed in cands:
                sec = attributed
            elif len(cands) == 1:
                sec = cands[0]
            else:
                continue
            spec = specs[sec]
            res = results[sec]
            # 빈 헤더 열 제거 (어음수표 표처럼 첫 열이 행 라벨('전자어음' 등)인 경우는 유지)
            label_first = (not r0[0]) and len(rows) > 1 and rows[1][0] in _ROW_LABELS
            keep = [j for j in range(len(r0))
                    if (j == 0 and label_first) or any(j < len(h) and h[j] for h in hdr_rows)]
            if not keep:
                continue
            data = rows[len(hdr_rows):]
            data_nl = rows_nl[len(hdr_rows):]
            res["raw"].extend(rows)
            lo = spec.min_cols or len(spec.columns)
            width_ok = lo <= len(keep) <= len(spec.columns)
            if not width_ok and "열수불일치" not in res["note"]:
                res["note"] += f"열수불일치(p{pi}: {len(keep)}≠{len(spec.columns)}); "
            group = ""
            carry_first = ""
            for r, r_nl in zip(data, data_nl):
                cells = [r[j] if j < len(r) else "" for j in keep]
                cells_nl = [r_nl[j] if j < len(r_nl) else "" for j in keep]
                nonempty = [c for c in cells if c]
                if not nonempty:
                    continue
                if any("확인자" in c or "소속및성명" in _squash(c) for c in cells):
                    continue
                if len(nonempty) == 1 and inst_key and _squash(nonempty[0]) == inst_key:
                    continue
                if is_no_txn(cells):
                    res["no_txn"] = True
                    continue
                if _squash(cells[0]) == "합계":
                    res["note"] += "합계행 제외: " + " | ".join(cells) + "; "
                    continue
                if _GROUP_LABEL_RE.match(cells[0]) and all(c in ("", "0") for c in cells[1:]):
                    group = cells[0]
                    continue
                if not cells[0] and carry_first and len(nonempty) >= 2:
                    cells[0] = carry_first
                elif cells[0] and len(nonempty) == 1 and sec in (6, 7) and form == "bank":
                    carry_first = cells[0]
                    continue
                row = _normalize_row(spec, cells, cells_nl)
                row["_group"] = group
                row["_page"] = pi
                res["rows"].append(row)
                if pi not in res["pages"]:
                    res["pages"].append(pi)
        if titles:
            cur = titles[-1][1]
    for res in results.values():
        if res["rows"]:
            res["no_txn"] = False
    return results


# ---------------------------------------------------------------------------
# 입력 · 파일 단위 파싱
# ---------------------------------------------------------------------------
@dataclass
class InputFile:
    path: Path
    kind: str                 # "pdf" | "zip"
    pdf_bytes: bytes
    inner_name: Optional[str] = None


@dataclass
class ConfirmDoc:
    source: InputFile
    form: Optional[str] = None
    header: dict = field(default_factory=dict)
    footer: dict = field(default_factory=dict)
    sections: dict = field(default_factory=dict)
    pages: int = 0
    is_scan: bool = False
    status: str = ""
    message: str = ""
    sha256: str = ""
    zip_sha256: str = ""
    saved_path: Optional[Path] = None

    @property
    def company(self) -> str:
        return self.header.get("company", "") or ""

    @property
    def institution(self) -> str:
        return self.footer.get("institution", "") or ""

    @property
    def form_label(self) -> str:
        return FORM_LABEL.get(self.form or "", "기타")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _zip_names(zf: zipfile.ZipFile):
    for info in zf.infolist():
        name = info.filename
        if info.flag_bits & 0x800 == 0:
            try:
                name = info.filename.encode("cp437").decode("cp949")
            except Exception:
                pass
        yield info, name


def iter_inputs(folder: Path) -> list[InputFile]:
    folder = Path(folder)
    out: list[InputFile] = []
    for p in sorted(folder.rglob("*")):
        if not p.is_file() or any(part.endswith("_정리") for part in p.relative_to(folder).parts[:-1]):
            continue
        ext = p.suffix.lower()
        if ext == ".pdf":
            out.append(InputFile(p, "pdf", p.read_bytes()))
        elif ext == ".zip":
            try:
                with zipfile.ZipFile(p) as zf:
                    for info, name in _zip_names(zf):
                        if name.lower().endswith(".pdf"):
                            out.append(InputFile(p, "zip", zf.read(info), name))
                            break
                    else:
                        out.append(InputFile(p, "zip", b"", None))
            except zipfile.BadZipFile:
                out.append(InputFile(p, "zip", b"", None))
    return out


def parse_file(inp: InputFile) -> ConfirmDoc:
    doc = ConfirmDoc(source=inp)
    if inp.kind == "zip":
        doc.zip_sha256 = sha256_bytes(inp.path.read_bytes())
    if not inp.pdf_bytes:
        doc.status, doc.message = "오류", "zip 안에 PDF 없음"
        return doc
    doc.sha256 = sha256_bytes(inp.pdf_bytes)
    try:
        with pdfplumber.open(io.BytesIO(inp.pdf_bytes)) as pdf:
            doc.pages = len(pdf.pages)
            first = pdf.pages[0].extract_text() or ""
            if len(first.strip()) < 30:
                doc.is_scan = True
                doc.status = SCAN_STATUS
                doc.message = "텍스트 레이어 없음"
                return doc
            doc.form = detect_form(first)
            doc.header = parse_header(first)
            doc.footer = parse_footer(pdf.pages[-1].extract_text() or "")
            if doc.form is None:
                doc.status, doc.message = "양식미상", "은행/보험/보증 양식 키워드 없음"
                return doc
            doc.sections = extract_sections(pdf, doc.form, doc.institution)
            notes = [f"{n}:{r['note']}" for n, r in doc.sections.items() if r["note"]]
            doc.status = "성공"
            doc.message = "; ".join(notes)
    except Exception as e:  # 파일 단위로 흡수
        doc.status, doc.message = "오류", f"{type(e).__name__}: {e}"
    return doc


_BAD_CHARS = re.compile(r'[\\/:*?"<>|]')


def tidy_name(doc: ConfirmDoc, with_branch: bool = False) -> str:
    company = doc.company or doc.source.path.stem
    kind = "은행조회서" if doc.form == "bank" else "금융거래조회서"
    inst = doc.institution or "기관미상"
    if with_branch and doc.footer.get("branch"):
        inst = f"{inst} {doc.footer['branch']}"
    return _BAD_CHARS.sub("_", f"{company}-{kind}({inst}).pdf")


def save_tidy(doc: ConfirmDoc, out_dir: Path, used: set) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = tidy_name(doc)
    if name in used or (out_dir / name).exists():
        name = tidy_name(doc, with_branch=True)
    base, k = name, 2
    while name in used or (out_dir / name).exists():
        name = base[:-4] + f"_{k}.pdf"
        k += 1
    target = out_dir / name
    target.write_bytes(doc.source.pdf_bytes)
    used.add(name)
    doc.saved_path = target
    return target
