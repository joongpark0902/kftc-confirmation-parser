# -*- coding: utf-8 -*-
"""금융거래조회서 PDF/zip 폴더 → BC조서 엑셀 (누적 재생성 + 이전 버전 입력값 이식).

사용법:
  python run_parser.py <입력폴더> [--out <출력폴더>] [--client <회사명>] [--no-copy] [--wolbo <월보PDF>] [--prev <이전엑셀>|--fresh] [--no-ocr]

- 원본 PDF·zip은 건드리지 않는다. zip 안 PDF는 <입력폴더>_정리/ 에
  '<조회대상회사>-<은행조회서|금융거래조회서>(<기관>).pdf' 로 풀어 저장(--no-copy 면 생략).
- 엑셀은 <출력폴더>/BC조서_<Client>_v<N>_<YYYYMMDD-HHMM>.xlsx (기본 출력폴더 = <입력폴더>_정리). 이전 파일은 그대로 둔다.
- 입력 폴더 안의 월보 PDF("[월보] 금융기관별 계정과목별 조회")는 자동으로 골라 월보대사·완전성대사에 쓴다. --wolbo 로 직접 지정 가능.
- 출력폴더에 이전 BC조서가 있으면(--fresh 가 아니면) 작성자 입력 열을 읽어 새 파일에 옮기고, 못 옮긴 건 '이식실패' 시트에 남긴다.
- BC 번호는 출력폴더의 bc_numbers.json 으로 고정(새 조회서는 뒤 번호를 이어 받음).
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import re
import sys
from pathlib import Path

import pdfplumber

from confirm_parser import NA_STATUS, SCAN_STATUS, SENT_STATUS, dedupe_inputs, iter_inputs, parse_file, save_tidy
from excel_writer import assign_numbers, write_workbook
from wolbo_parser import is_wolbo_pdf, parse_wolbo


def _is_wolbo(inp) -> bool:
    if inp.kind != "pdf" or not inp.pdf_bytes:
        return False
    try:
        with pdfplumber.open(io.BytesIO(inp.pdf_bytes)) as pdf:
            return is_wolbo_pdf(pdf.pages[0].extract_text() or "")
    except Exception:
        return False


def _latest_workbook(out_dir: Path):
    files = sorted(out_dir.glob("BC조서_*.xlsx"), key=lambda p: p.stat().st_mtime)
    files = [f for f in files if not f.name.startswith("~$")]
    return files[-1] if files else None


def run(folder: Path, out_dir: Path | None = None, client: str | None = None, copy: bool = True, log=print,
        wolbo: Path | None = None, prev: Path | None = None, fresh: bool = False, no_prev: bool = False, ocr: bool = True) -> Path:
    folder = Path(folder)
    if not folder.is_dir():
        raise SystemExit(f"입력 폴더 없음: {folder}")
    tidy_dir = folder.parent / (folder.name + "_정리")
    out_dir = Path(out_dir) if out_dir else tidy_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    inputs = iter_inputs(folder)
    wolbo_inputs = [i for i in inputs if _is_wolbo(i)]
    inputs = [i for i in inputs if i not in wolbo_inputs]
    inputs, dups = dedupe_inputs(inputs)
    if dups:
        log(f"내용이 같은 PDF {len(dups)}건은 한 번만 넣었습니다(폴더와 zip에 중복 등): "
            + ", ".join((d.inner_name or d.path.name) for d in dups[:5]) + (" 외" if len(dups) > 5 else ""))
    log(f"입력 {len(inputs)}건 (pdf {sum(i.kind == 'pdf' for i in inputs)}, zip {sum(i.kind == 'zip' for i in inputs)})"
        + (f", 월보 PDF {len(wolbo_inputs)}건" if wolbo_inputs else ""))
    # 월보
    wdoc = None
    wpath = Path(wolbo) if wolbo else (max((i.path for i in wolbo_inputs), key=lambda p: p.stat().st_mtime) if wolbo_inputs else None)
    if wpath:
        try:
            wdoc = parse_wolbo(wpath)
            log(f"월보: {wpath.name} — {wdoc.company} 기준 {wdoc.base_month}, 기관 {len(wdoc.all_institutions())}개 ({', '.join(wdoc.all_institutions())})")
            if len(wolbo_inputs) > 1 and not wolbo:
                log(f"  월보 PDF가 {len(wolbo_inputs)}개라 가장 최근 파일을 썼습니다. 다른 걸 쓰려면 --wolbo 로 지정.")
        except Exception as e:
            log(f"월보 파싱 실패: {e}")
    # 조회서
    docs = []
    used: set[str] = set()
    for i, inp in enumerate(inputs, start=1):
        doc = parse_file(inp, ocr=ocr)
        if copy and inp.kind == "zip" and inp.pdf_bytes:
            save_tidy(doc, tidy_dir, used)
        docs.append(doc)
        tag = doc.status if doc.status != "성공" else f"{doc.form_label} {doc.company} / {doc.institution}"
        log(f"[{i:3d}/{len(inputs)}] {inp.path.name[:50]:50s} → {tag}")
    # 번호 고정 + 이전 버전 입력값
    map_path = out_dir / "bc_numbers.json"
    bc_map = json.loads(map_path.read_text(encoding="utf-8")) if (map_path.exists() and not fresh) else {}
    ordered, client_name = assign_numbers(docs, client, bc_map)
    map_path.write_text(json.dumps(bc_map, ensure_ascii=False, indent=1), encoding="utf-8")
    prev_path = None if (fresh or no_prev) else (Path(prev) if prev else _latest_workbook(out_dir))
    inputs_prev = None
    if prev_path and prev_path.exists():
        from carry_over import collect_inputs
        try:
            inputs_prev = collect_inputs(prev_path)
            n_in = sum(len(v) for v in inputs_prev.values())
            log(f"이전 버전 입력값 {n_in}건 읽음: {prev_path.name}")
        except Exception as e:
            log(f"이전 버전 읽기 실패(이식 생략): {e}")
    new_cnt = sum(getattr(d, "is_new", False) for d in ordered)
    safe = re.sub(r'[\\/:*?"<>|]', "_", client_name or folder.name)
    ver = len([f for f in out_dir.glob("BC조서_*.xlsx") if not f.name.startswith("~$")]) + 1
    out_path = out_dir / f"BC조서_{safe}_v{ver}_{dt.datetime.now():%Y%m%d-%H%M}.xlsx"
    stats: dict = {}
    write_workbook(ordered, out_path, client_name, wolbo=wdoc, inputs=inputs_prev, bc_map=bc_map, stats=stats)
    ok = sum(d.status == "성공" for d in docs)
    scan = sum(d.status == SCAN_STATUS for d in docs)
    ocred = sum(d.status == SCAN_STATUS and d.ocr_pages is not None for d in docs)
    skip = sum(d.status in (NA_STATUS, SENT_STATUS) for d in docs)
    err = len(docs) - ok - scan - skip
    log(f"완료: 성공 {ok} / 스캔본(수동입력) {scan}" + (f"(OCR 판독 {ocred})" if scan else "")
        + f" / 대상아님·발송본 {skip} / 오류·양식미상 {err} / 이번에 새로 번호 받은 조회서 {new_cnt}건")
    if scan and ocr and not ocred:
        log("  OCR을 쓰지 못했습니다(winocr·pypdfium2 또는 Windows 한국어 OCR 없음). 스캔본은 수동 입력하세요.")
    if inputs_prev is not None:
        log(f"입력값 이식: {stats.get('carried', 0)}셀 적용, 실패 {stats.get('carry_failed', 0)}건" + (" → '이식실패' 시트 확인" if stats.get("carry_failed") else ""))
    log(f"엑셀: {out_path}")
    if copy:
        log(f"정리 PDF: {tidy_dir}")
    return out_path


def main(argv=None):
    ap = argparse.ArgumentParser(description="금융거래조회서 PDF → BC조서 엑셀")
    ap.add_argument("folder", help="조회서 PDF/zip 폴더")
    ap.add_argument("--out", help="엑셀 출력 폴더 (기본: <입력폴더>_정리)")
    ap.add_argument("--client", help="Client 회사명 (기본: 문서에서 가장 많이 나온 조회대상회사)")
    ap.add_argument("--no-copy", action="store_true", help="zip 안 PDF를 정리 폴더로 풀지 않음")
    ap.add_argument("--wolbo", help="월보 PDF 경로 (기본: 입력 폴더에서 자동 탐지)")
    ap.add_argument("--prev", help="입력값을 옮겨올 이전 BC조서 (기본: 출력폴더의 최신 파일)")
    ap.add_argument("--fresh", action="store_true", help="이전 버전 무시(입력값 이식·번호 고정 안 함)")
    ap.add_argument("--no-ocr", action="store_true", help="스캔본 OCR 판독 끄기")
    a = ap.parse_args(argv)
    run(Path(a.folder), Path(a.out) if a.out else None, a.client, not a.no_copy, wolbo=a.wolbo, prev=a.prev, fresh=a.fresh,
        ocr=not a.no_ocr)


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
