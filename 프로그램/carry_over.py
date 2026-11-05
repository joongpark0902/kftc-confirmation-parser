# -*- coding: utf-8 -*-
"""이전 버전 BC조서에서 작성자가 입력한 셀을 읽어 새로 만든 워크북의 같은 자리에 옮긴다.

원칙: 파서가 채우는 열은 건드리지 않고, '작성자 입력 열'만 키(회사·기관·계좌번호 등)로 맞춰 복사.
키가 안 맞는 입력은 '이식실패' 시트에 모아 잃어버리지 않게 한다.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import openpyxl
from openpyxl.utils import get_column_letter

# 시트별: 키 열, 입력 열(작성자), 블록 구분 방식
SPECS = {
    "CS": {"key": ["조회대상회사", "상호(지점)"], "inputs": ["주소", "담당자", "담당전화번호", "우편번호", "비고"], "first_header": "번호"},
    "예적금": {"key": ["조회대상회사", "금융기관", "계좌번호"], "inputs": ["검토메모", "현금및현금성자산", "단기금융상품", "장기금융상품", "퇴직신탁"], "first_header": "No",
             "extra_rows": ["회사제시금액", "(*1) 현금및현금성자산: ", "(*2) 단기금융상품: ", "(*3) 장기금융상품: "]},
    "대출금": {"key": ["조회대상회사", "금융기관", "대출종류", "대출일", "대출금액"], "inputs": ["연대보증인", "비고", "유동성장기부채", "장기차입금"], "first_header": "No",
             "extra_rows": ["회사제시금액"]},
    "지급보증": {"key": ["조회대상회사", "금융기관", "내용", "한도액"], "inputs": ["비고"], "first_header": "No"},
    "담보제공": {"key": ["조회대상회사", "금융기관", "내용", "연대보증 등의 한도"], "inputs": ["완전성 검토_주석 REF", "금액 대사_계약서 및 명세서"], "first_header": "No"},
    "담보보증내역": {"key": ["조회대상회사", "금융기관", "구분", "내용", "설정금액"], "inputs": ["완전성 검토_주석 REF", "금액 대사_계약서 및 명세서"], "first_header": "No"},
    "보증보험": {"key": ["조회대상회사", "금융기관", "증권번호"], "inputs": ["비고", "완전성 검토_주석 REF"], "first_header": "No"},
    "월보대사": {"key": ["_block", "세부"], "inputs": ["은행연합회(월보)", "회사금액", "비고"], "first_header": "대출과목명", "block_header_col": 3,
              "memo_cells": ["조회 ID / 조회자", "조회일시", "최종변경일"]},
    "완전성대사": {"blocks": {"2. 전기 금융기관조회서 CS와 대사": ["전기 금융기관조회서 CS", "거래처명 수정"],
                            "3. 은행연합회 자료와 대사_12월 기준": ["은행연합회"],
                            "4. 이자수익·이자비용 원장과 대사 (적요 검색: 캐피탈/은행/보험/저축/신용/리스/금고)": ["구분", "원장상 금융기관", "거래처명 수정"]}},
}


def _norm(v) -> str:
    if v is None:
        return ""
    if hasattr(v, "strftime"):                 # date/datetime — 파일에서 읽으면 datetime, 생성 직후는 date
        return v.strftime("%Y-%m-%d")
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"\s+", " ", str(v)).strip()


def _is_user_value(v) -> bool:
    return v is not None and _norm(v) != "" and not (isinstance(v, str) and v.startswith("="))


def _tables(ws, first_header: str):
    """first_header가 A열인 머리글 행마다 (header_row, {헤더명: 열번호}, [데이터행번호…]) 생성"""
    for r in range(1, ws.max_row + 1):
        if _norm(ws.cell(r, 1).value) == first_header:
            cols = {}
            for c in range(1, ws.max_column + 1):
                h = _norm(ws.cell(r, c).value)
                if h and h not in cols:
                    cols[h] = c
            rows = []
            rr = r + 1
            while rr <= ws.max_row and _norm(ws.cell(rr, 1).value) not in ("", "합계"):
                rows.append(rr)
                rr += 1
            yield r, cols, rows


def _row_key(ws, r, cols, key_cols, block_id="") -> Optional[tuple]:
    parts = []
    for k in key_cols:
        if k == "_block":
            parts.append(block_id)
            continue
        c = cols.get(k)
        if c is None:
            return None
        parts.append(_norm(ws.cell(r, c).value))
    return tuple(parts)


def collect_inputs(prev_path: Path) -> dict:
    """이전 워크북에서 작성자 입력을 {sheet: {key: {col: value}}} 로 모은다."""
    wb = openpyxl.load_workbook(prev_path, data_only=False)
    out: dict = {}
    for sheet, spec in SPECS.items():
        if sheet not in wb.sheetnames:
            continue
        ws = wb[sheet]
        store = out.setdefault(sheet, {})
        if "blocks" in spec:
            for title, cols_in in spec["blocks"].items():
                rows = []
                for r in range(1, ws.max_row + 1):
                    if _norm(ws.cell(r, 1).value) == title:
                        hdr = r + 1
                        heads = {_norm(ws.cell(hdr, c).value): c for c in range(1, ws.max_column + 1)}
                        rr = hdr + 1
                        while rr <= ws.max_row and any(_is_user_value(ws.cell(rr, heads[h]).value) for h in cols_in if h in heads):
                            rows.append({h: ws.cell(rr, heads[h]).value for h in cols_in if h in heads})
                            rr += 1
                        break
                if rows:
                    store[title] = rows
            continue
        block_i = 0
        for hdr, cols, rows in _tables(ws, spec["first_header"]):
            block_i += 1
            block_id = _norm(ws.cell(hdr, spec["block_header_col"]).value) if spec.get("block_header_col") else str(block_i)
            for r in rows:
                key = _row_key(ws, r, cols, spec["key"], block_id)
                if key is None:
                    continue
                vals = {}
                for col in spec["inputs"]:
                    c = cols.get(col)
                    if c and _is_user_value(ws.cell(r, c).value):
                        vals[col] = ws.cell(r, c).value
                if vals:
                    store[key] = vals
            # 표 아래 라벨 행(회사제시금액, (*1)… )
            for label in spec.get("extra_rows", []):
                for r in range(hdr, min(ws.max_row, hdr + len(rows) + 15) + 1):
                    for c in range(1, ws.max_column + 1):
                        if _norm(ws.cell(r, c).value) == _norm(label):
                            vals = {}
                            for cc in range(c + 1, ws.max_column + 1):
                                v = ws.cell(r, cc).value
                                if _is_user_value(v):
                                    vals[cc - c] = v
                            if label.startswith("(*"):
                                v = ws.cell(r, c).value
                                if _norm(v) != _norm(label):
                                    vals[0] = v
                            if vals:
                                store[("_extra", block_id, label)] = vals
        if spec.get("memo_cells"):
            for label in spec["memo_cells"]:
                for r in range(1, min(ws.max_row, 40) + 1):
                    for c in range(1, 8):
                        if _norm(ws.cell(r, c).value) == label and _is_user_value(ws.cell(r, c + 1).value):
                            store[("_memo", label)] = ws.cell(r, c + 1).value
    wb.close()
    return out


def apply_inputs(wb, inputs: dict) -> tuple[int, list]:
    """새 워크북(openpyxl Workbook)에 inputs를 넣는다. 반환: (적용 셀 수, 실패 목록[(sheet, key, {col: v})])"""
    applied = 0
    failed: list = []
    for sheet, store in inputs.items():
        if sheet not in wb.sheetnames:
            failed.extend((sheet, k, v) for k, v in store.items())
            continue
        ws = wb[sheet]
        spec = SPECS[sheet]
        if "blocks" in spec:
            for title, rows in store.items():
                placed = False
                for r in range(1, ws.max_row + 1):
                    if _norm(ws.cell(r, 1).value) == title:
                        hdr = r + 1
                        heads = {_norm(ws.cell(hdr, c).value): c for c in range(1, ws.max_column + 1)}
                        for i, rowvals in enumerate(rows):
                            rr = hdr + 1 + i
                            for h, v in rowvals.items():
                                if h in heads and v is not None:
                                    ws.cell(rr, heads[h], v)
                                    applied += 1
                        placed = True
                        break
                if not placed:
                    failed.append((sheet, title, {"rows": len(rows)}))
            continue
        index: dict = {}
        blocks: dict = {}
        for hdr, cols, rows in _tables(ws, spec["first_header"]):
            block_id = _norm(ws.cell(hdr, spec["block_header_col"]).value) if spec.get("block_header_col") else str(len(blocks) + 1)
            blocks[block_id] = (hdr, cols, rows)
            for r in rows:
                key = _row_key(ws, r, cols, spec["key"], block_id)
                if key is not None and key not in index:
                    index[key] = (r, cols)
        for key, vals in store.items():
            if isinstance(key, tuple) and key and key[0] == "_extra":
                _, block_id, label = key
                blk = blocks.get(block_id) or (next(iter(blocks.values())) if blocks else None)
                if not blk:
                    failed.append((sheet, key, vals)); continue
                hdr, cols, rows = blk
                hit = False
                for r in range(hdr, min(ws.max_row, hdr + len(rows) + 15) + 1):
                    for c in range(1, ws.max_column + 1):
                        if _norm(ws.cell(r, c).value) == _norm(label):
                            for off, v in vals.items():
                                ws.cell(r, c + off, v); applied += 1
                            hit = True
                            break
                    if hit:
                        break
                if not hit:
                    failed.append((sheet, key, vals))
                continue
            if isinstance(key, tuple) and key and key[0] == "_memo":
                label = key[1]
                hit = False
                for r in range(1, min(ws.max_row, 40) + 1):
                    for c in range(1, 8):
                        if _norm(ws.cell(r, c).value) == label:
                            ws.cell(r, c + 1, vals); applied += 1; hit = True; break
                    if hit:
                        break
                if not hit:
                    failed.append((sheet, key, vals))
                continue
            found = index.get(key)
            if not found:
                failed.append((sheet, key, vals))
                continue
            r, cols = found
            for col, v in vals.items():
                c = cols.get(col)
                if c:
                    ws.cell(r, c, v); applied += 1
    if failed:
        ws = wb.create_sheet("이식실패")
        ws.append(["시트", "키", "입력값(이전 버전에서 못 옮긴 것 — 수동 반영)"])
        for sheet, key, vals in failed:
            ws.append([sheet, " | ".join(str(k) for k in key) if isinstance(key, tuple) else str(key), str(vals)])
        for i, w in enumerate([14, 60, 80], start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
    return applied, failed
