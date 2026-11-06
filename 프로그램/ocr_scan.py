# -*- coding: utf-8 -*-
"""스캔본(텍스트 레이어 없는 PDF) OCR — Windows 내장 OCR(한국어) + pypdfium2 렌더.

결과는 '추정'이다. 금액 시트에 자동 기입하지 않고 OCR판독 시트·CS 비고에 참고로만 쓴다.
winocr·pypdfium2가 없거나 Windows 한국어 OCR이 없으면 None을 돌려주고 조용히 건너뛴다.
"""
from __future__ import annotations

import re
from typing import Optional

MAX_PAGES = 15
SCALE = 200 / 72          # 200dpi 상당
_NO_TXN_PAT = re.compile(r"해\s*당\s*(사\s*항|거\s*래)\s*없\s*음|거\s*래\s*없\s*음|당\s*사\s*거\s*래\s*회\s*사\s*아\s*님")
_AMOUNT_PAT = re.compile(r"(?<![\d,])\d{1,3}(?:,\d{3})+(?![\d,])")

_state: dict = {}


def available() -> bool:
    if "ok" not in _state:
        try:
            import pypdfium2  # noqa: F401
            import winocr  # noqa: F401
            _state["ok"] = True
        except Exception:
            _state["ok"] = False
    return _state["ok"]


def ocr_pdf(pdf_bytes: bytes, max_pages: int = MAX_PAGES) -> Optional[list[str]]:
    """페이지별 OCR 텍스트. 사용할 수 없으면 None."""
    if not available():
        return None
    try:
        import pypdfium2 as pdfium
        import winocr
        pdf = pdfium.PdfDocument(pdf_bytes)
        pages = []
        try:
            for i in range(min(len(pdf), max_pages)):
                img = pdf[i].render(scale=SCALE).to_pil()
                pages.append(winocr.recognize_pil_sync(img, "ko").get("text", "") or "")
        finally:
            pdf.close()
        return pages
    except Exception:
        return None


def summarize(pages: list[str]) -> dict:
    """OCR 텍스트에서 '거래없음' 문구 수와 금액 후보(1,000 이상, 쉼표 표기)를 뽑는다."""
    text = "\n".join(pages)
    amounts = []
    for a in _AMOUNT_PAT.findall(text):
        if a not in amounts:
            amounts.append(a)
    return {"no_txn": len(_NO_TXN_PAT.findall(text)), "amounts": amounts, "chars": len(text)}


def hint(summary: dict) -> str:
    """CS 비고용 한 줄."""
    if not summary or not summary.get("chars"):
        return "OCR 판독 실패"
    parts = []
    if summary["no_txn"]:
        parts.append(f"'해당사항 없음' 문구 {summary['no_txn']}회")
    if summary["amounts"]:
        shown = ", ".join(summary["amounts"][:4]) + (" 외" if len(summary["amounts"]) > 4 else "")
        parts.append(f"금액 후보 {len(summary['amounts'])}개({shown})")
    return "OCR 추정: " + (" · ".join(parts) if parts else "금액·거래없음 문구 못 찾음") + " — 원문 확인"
