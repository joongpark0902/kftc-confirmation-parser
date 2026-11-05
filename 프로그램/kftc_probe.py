# -*- coding: utf-8 -*-
"""디버그 포트(9222)로 떠 있는 크롬에 붙어 현재 금결원 화면 구조를 덤프한다. (읽기 전용, 클릭 없음)

사용: python kftc_probe.py [출력폴더]
출력: <출력폴더>/probe_<시각>.txt  — 탭 URL, 프레임 트리, 프레임별 링크·폼·표 요약·본문 텍스트 앞부분
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9222"


def dump_frame(f, depth, out):
    ind = "  " * depth
    try:
        url = f.url
    except Exception:
        url = "?"
    out.append(f"{ind}[frame] name={f.name!r} url={url}")
    try:
        info = f.evaluate(
            """() => {
            const q = (s) => Array.from(document.querySelectorAll(s));
            const links = q('a').slice(0, 60).map(a => (a.innerText || '').trim().replace(/\\s+/g,' ').slice(0,40) + ' -> ' + (a.getAttribute('href')||'') + (a.getAttribute('onclick') ? ' onclick=' + a.getAttribute('onclick').slice(0,80) : ''));
            const forms = q('form').map(fm => fm.name + ' action=' + fm.getAttribute('action') + ' inputs=' + Array.from(fm.elements).slice(0,40).map(e => e.tagName + ':' + (e.name||e.id) + ':' + e.type).join(','));
            const tables = q('table').slice(0, 15).map(t => 'rows=' + t.rows.length + ' hdr=' + Array.from(t.rows[0]?.cells||[]).map(c => (c.innerText||'').trim().replace(/\\s+/g,' ').slice(0,20)).join('|'));
            const selects = q('select').map(s => s.name + ':' + Array.from(s.options).slice(0,12).map(o => o.value + '=' + o.text.trim()).join(','));
            const buttons = q('button, input[type=button], input[type=submit], img[onclick]').slice(0, 40).map(b => (b.tagName + ':' + (b.innerText || b.value || b.alt || b.id || '').trim().slice(0,30) + (b.getAttribute('onclick') ? ' onclick=' + b.getAttribute('onclick').slice(0,80) : '')));
            const text = (document.body ? document.body.innerText : '').replace(/\\s+/g,' ').slice(0, 1500);
            return {title: document.title, links, forms, tables, selects, buttons, text};
        }"""
        )
    except Exception as e:
        out.append(f"{ind}  (evaluate 실패: {e})")
        return
    out.append(f"{ind}  title={info['title']!r}")
    for k in ("forms", "selects", "tables", "buttons", "links"):
        if info[k]:
            out.append(f"{ind}  {k}:")
            for x in info[k]:
                out.append(f"{ind}    - {x}")
    out.append(f"{ind}  text: {info['text']}")


def main():
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "downloads" / "probe"
    out_dir.mkdir(parents=True, exist_ok=True)
    out: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP)
        for ci, ctx in enumerate(browser.contexts):
            for pi, page in enumerate(ctx.pages):
                out.append(f"=== context {ci} page {pi}: {page.url}")
                if "kftc" not in page.url:
                    continue
                for f in page.frames:
                    depth = 0
                    pf = f.parent_frame
                    while pf is not None:
                        depth += 1
                        pf = pf.parent_frame
                    dump_frame(f, depth, out)
    path = out_dir / f"probe_{dt.datetime.now():%Y%m%d-%H%M%S}.txt"
    path.write_text("\n".join(out), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
