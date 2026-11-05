# -*- coding: utf-8 -*-
"""금결원 기발급 조회서 일괄 다운로드 CLI.

  python run_kftc.py --list                       결제완료 목록만 출력(다운로드 없음)
  python run_kftc.py --download --out <폴더>       목록 전체를 내려받아 <폴더>/raw_zip 에 저장 (+이력 JSON)
  python run_kftc.py --download --company 테스트    회사명으로 목록 필터
  python run_kftc.py --parse                      다운로드 후 1단계 파서로 BC조서 엑셀까지 생성

사전 조건: 최상위 크롬실행.cmd 로 띄운 크롬에서 인증서 로그인 완료.
수수료가 드는 재발급·결제 경로는 호출하지 않는다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from kftc_engine import PRTP_LABEL, KftcEngine, Session


def main(argv=None):
    ap = argparse.ArgumentParser(description="금결원 기발급 조회서 다운로드")
    ap.add_argument("--list", action="store_true", help="결제완료 목록만 출력")
    ap.add_argument("--download", action="store_true", help="목록을 내려받음")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "downloads"), help="저장 폴더 (기본 프로젝트의 downloads)")
    ap.add_argument("--company", default="", help="회사명 필터(사이트 검색)")
    ap.add_argument("--parse", action="store_true", help="다운로드 후 run_parser 실행")
    a = ap.parse_args(argv)
    if not (a.list or a.download):
        ap.print_help()
        return
    s = Session()
    print(f"로그인 사용자: {s.user}")
    eng = KftcEngine(s, Path(a.out))
    try:
        items = eng.list_paid(filter_sel="E" if a.company else "", filter_val=a.company)
        print(f"결제완료 목록 {len(items)}건")
        for it in items:
            print(f"  {it.no:>3} {it.company[:20]:20s} {it.bank_name[:14]:14s} {PRTP_LABEL.get(it.prtp_type, it.prtp_type):4s} 기준일 {it.ref_date} 발급 {it.bank_issue_date} MSTR {it.mstr_num}/{it.bank_code} {it.note}")
        if a.download and items:
            results = eng.run(items)
            print(f"결과: {len(results)}건 처리, 파일은 {eng.raw_dir}")
            if a.parse:
                from run_parser import run as parse_run
                parse_run(eng.raw_dir)
    finally:
        s.close()


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
