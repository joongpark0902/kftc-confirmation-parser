# -*- coding: utf-8 -*-
"""금결원 조회서 일괄 다운로드 GUI (CustomTkinter, DART 다운로더 틀 재사용).

흐름: [크롬 실행] → 형님이 인증서 로그인 → [연결 확인] → [목록 조회] → 행 선택 → [선택 다운로드]/[전체 다운로드]
      → (옵션) 다운로드 후 BC조서 엑셀 생성.  [화면 구조 덤프]는 시즌에 파서 확인용.
수수료가 드는 경로(재발급·결제)는 어디에도 없다.
"""
from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
import threading
import tkinter as tk
import tkinter.ttk as ttk
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

import ui_theme
from kftc_engine import PRTP_LABEL, KftcEngine, Session

CODE_DIR = Path(__file__).resolve().parent
HERE = CODE_DIR.parent


class KftcApp(ctk.CTk):
    def __init__(self, selftest: bool = False):
        ui_theme.apply_theme()
        super().__init__()
        self.configure(fg_color=ui_theme.WINDOW_BG)
        self.title("금융거래조회서 일괄 다운로드 (금융결제원)")
        self.geometry("1180x720")
        self.minsize(960, 600)
        self.items = []
        self.engine: KftcEngine | None = None
        self._busy = False
        self._build_ui()
        ui_theme.apply_titlebar_theme(self)
        if selftest:
            self.after(1500, self.destroy)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=3)
        self.grid_rowconfigure(2, weight=2)
        top = ctk.CTkFrame(self, fg_color=ui_theme.SURFACE, border_width=1)
        top.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        for c in range(8):
            top.grid_columnconfigure(c, weight=0)
        top.grid_columnconfigure(5, weight=1)

        ctk.CTkButton(top, text="1. 크롬 실행", width=110, command=self._launch_chrome).grid(row=0, column=0, padx=(10, 4), pady=8)
        ctk.CTkButton(top, text="2. 연결 확인", width=110, command=self._check_connection).grid(row=0, column=1, padx=4, pady=8)
        self.conn_var = tk.StringVar(value="미연결 — 크롬 창에서 공동인증서로 로그인하세요")
        ctk.CTkLabel(top, textvariable=self.conn_var, text_color=ui_theme.TEXT_SECONDARY).grid(row=0, column=2, columnspan=4, sticky="w", padx=8)

        ctk.CTkLabel(top, text="저장 폴더").grid(row=1, column=0, padx=(10, 4), pady=(0, 8), sticky="e")
        self.dir_var = tk.StringVar(value=str(HERE / "downloads"))
        ctk.CTkEntry(top, textvariable=self.dir_var).grid(row=1, column=1, columnspan=4, sticky="ew", padx=4, pady=(0, 8))
        ctk.CTkButton(top, text="찾기", width=60, command=self._browse).grid(row=1, column=5, sticky="w", padx=4, pady=(0, 8))
        ctk.CTkLabel(top, text="회사명 필터").grid(row=1, column=6, padx=(12, 4), pady=(0, 8), sticky="e")
        self.filter_var = tk.StringVar()
        ctk.CTkEntry(top, textvariable=self.filter_var, width=160).grid(row=1, column=7, padx=(0, 10), pady=(0, 8))
        ctk.CTkLabel(top, text="월보 PDF(선택)").grid(row=2, column=0, padx=(10, 4), pady=(0, 8), sticky="e")
        self.wolbo_var = tk.StringVar()
        ctk.CTkEntry(top, textvariable=self.wolbo_var, placeholder_text="은행연합회 월보 PDF — 비우면 저장 폴더에서 자동 탐지").grid(row=2, column=1, columnspan=4, sticky="ew", padx=4, pady=(0, 8))
        ctk.CTkButton(top, text="찾기", width=60, command=self._browse_wolbo).grid(row=2, column=5, sticky="w", padx=4, pady=(0, 8))
        ctk.CTkButton(top, text="BC조서만 다시 생성", width=150, fg_color=ui_theme.ACCENT_SOFT, hover_color="#B3C7E6", command=self._do_parse_only).grid(row=2, column=6, columnspan=2, sticky="e", padx=(4, 10), pady=(0, 8))

        mid = ctk.CTkFrame(self, fg_color=ui_theme.SURFACE, border_width=1)
        mid.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)
        mid.grid_rowconfigure(1, weight=1)
        mid.grid_columnconfigure(0, weight=1)
        bar = ctk.CTkFrame(mid, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        self.btn_list = ctk.CTkButton(bar, text="3. 목록 조회", width=110, command=self._do_list)
        self.btn_list.pack(side="left", padx=(0, 6))
        self.btn_sel = ctk.CTkButton(bar, text="4. 선택 다운로드", width=130, command=lambda: self._do_download(selected=True))
        self.btn_sel.pack(side="left", padx=6)
        self.btn_all = ctk.CTkButton(bar, text="전체 다운로드", width=110, command=lambda: self._do_download(selected=False))
        self.btn_all.pack(side="left", padx=6)
        self.btn_stop = ctk.CTkButton(bar, text="중지", width=70, fg_color="#B04040", hover_color="#8E3333", command=self._stop, state="disabled")
        self.btn_stop.pack(side="left", padx=6)
        self.parse_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(bar, text="다운로드 후 BC조서 엑셀 생성", variable=self.parse_var).pack(side="left", padx=14)
        ctk.CTkButton(bar, text="화면 구조 덤프", width=110, fg_color=ui_theme.ACCENT_SOFT, hover_color="#B3C7E6", command=self._do_probe).pack(side="right")
        self.count_var = tk.StringVar(value="결제완료 목록: -")
        ctk.CTkLabel(bar, textvariable=self.count_var, text_color=ui_theme.TEXT_SECONDARY).pack(side="right", padx=12)

        cols = ("no", "company", "bank", "type", "ref", "issued", "project", "note")
        heads = {"no": "No", "company": "회사명", "bank": "금융기관", "type": "양식", "ref": "조회기준일", "issued": "발급일", "project": "프로젝트", "note": "비고"}
        widths = {"no": 45, "company": 240, "bank": 160, "type": 70, "ref": 95, "issued": 95, "project": 110, "note": 160}
        style = ttk.Style(self)
        style.configure("Kftc.Treeview", font=ui_theme.TABLE_CELL_FONT, rowheight=24, background=ui_theme.SURFACE, fieldbackground=ui_theme.SURFACE)
        style.configure("Kftc.Treeview.Heading", font=ui_theme.TABLE_HEADER_FONT)
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="extended", style="Kftc.Treeview")
        for c in cols:
            self.tree.heading(c, text=heads[c])
            self.tree.column(c, width=widths[c], anchor="center" if c in ("no", "type", "ref", "issued") else "w")
        self.tree.grid(row=1, column=0, sticky="nsew", padx=(8, 0), pady=(0, 8))
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        sb.grid(row=1, column=1, sticky="ns", pady=(0, 8), padx=(0, 8))
        self.tree.configure(yscrollcommand=sb.set)

        bottom = ctk.CTkFrame(self, fg_color=ui_theme.SURFACE, border_width=1)
        bottom.grid(row=2, column=0, sticky="nsew", padx=12, pady=(6, 12))
        bottom.grid_rowconfigure(0, weight=1)
        bottom.grid_columnconfigure(0, weight=1)
        self.log_box = ctk.CTkTextbox(bottom, font=(ui_theme.FONT_FAMILY_MONO, 11), fg_color=ui_theme.SURFACE)
        self.log_box.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.log("준비. 순서: 크롬 실행 → 로그인 → 연결 확인 → 목록 조회 → 다운로드. 기발급 목록은 발급일 기준 3개월까지만 사이트에 남습니다.")

    # -------------------------------------------------------------- helpers
    def log(self, msg: str):
        ts = dt.datetime.now().strftime("%H:%M:%S")

        def _upd():
            self.log_box.insert("end", f"[{ts}] {msg}\n")
            self.log_box.see("end")
        self.after(0, _upd)

    def _set_busy(self, busy: bool):
        self._busy = busy

        def _upd():
            st = "disabled" if busy else "normal"
            for b in (self.btn_list, self.btn_sel, self.btn_all):
                b.configure(state=st)
            self.btn_stop.configure(state="normal" if busy else "disabled")
        self.after(0, _upd)

    def _run_bg(self, fn):
        if self._busy:
            self.log("작업 중입니다. 끝나거나 중지한 뒤 다시 시도하세요.")
            return
        threading.Thread(target=fn, daemon=True).start()

    def _browse(self):
        p = filedialog.askdirectory(initialdir=self.dir_var.get())
        if p:
            self.dir_var.set(p)

    def _browse_wolbo(self):
        p = filedialog.askopenfilename(title="월보 PDF", filetypes=[("PDF", "*.pdf")])
        if p:
            self.wolbo_var.set(p)

    def _parse_now(self, out: Path):
        """raw_zip 폴더의 조회서 전체(+월보)로 BC조서를 새 버전으로 만든다(이전 버전 입력값 이식)."""
        from run_parser import run as parse_run
        raw = out / "raw_zip"
        if not raw.exists():
            self.log(f"조회서 폴더가 없습니다: {raw}")
            return None
        w = self.wolbo_var.get().strip() or None
        self.log("BC조서 엑셀 생성 중... (이전 버전이 있으면 입력값을 옮깁니다)")
        xlsx = parse_run(raw, out_dir=out, wolbo=Path(w) if w else None, log=self.log)
        self.log(f"BC조서: {xlsx}")
        return xlsx

    def _do_parse_only(self):
        out = Path(self.dir_var.get())

        def run():
            self._set_busy(True)
            try:
                self._parse_now(out)
            except Exception as e:
                self.log(f"BC조서 생성 실패: {e}")
            finally:
                self._set_busy(False)
        self._run_bg(run)

    # -------------------------------------------------------------- actions
    def _launch_chrome(self):
        cmd = HERE / "크롬실행.cmd"
        try:
            subprocess.Popen(["cmd", "/c", str(cmd)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.log("크롬(디버그 포트 9222)을 띄웠습니다. 그 창에서 공동인증서로 로그인한 뒤 [연결 확인]을 누르세요.")
        except Exception as e:
            self.log(f"크롬 실행 실패: {e} — 크롬실행.cmd를 직접 실행하세요.")

    def _check_connection(self):
        def run():
            try:
                s = Session()
                try:
                    self.after(0, lambda: self.conn_var.set(f"연결됨 — 로그인 사용자: {s.user}"))
                    self.log(f"연결 확인: {s.user} 님 로그인 상태")
                finally:
                    s.close()
            except Exception as e:
                self.after(0, lambda: self.conn_var.set("미연결"))
                self.log(f"연결 실패: {e}")
        self._run_bg(run)

    def _do_list(self):
        def run():
            self._set_busy(True)
            try:
                s = Session()
                try:
                    eng = KftcEngine(s, Path(self.dir_var.get()), log_fn=self.log)
                    f = self.filter_var.get().strip()
                    items = eng.list_paid(filter_sel="E" if f else "", filter_val=f)
                finally:
                    s.close()
                self.items = items
                self.after(0, lambda: self._fill(items))
            except Exception as e:
                self.log(f"목록 조회 실패: {e}")
            finally:
                self._set_busy(False)
        self._run_bg(run)

    def _fill(self, items):
        self.tree.delete(*self.tree.get_children())
        for i, it in enumerate(items):
            self.tree.insert("", "end", iid=str(i), values=(it.no, it.company, it.bank_name, PRTP_LABEL.get(it.prtp_type, it.prtp_type),
                                                            it.ref_date, it.bank_issue_date, it.project_code, it.note))
        self.count_var.set(f"결제완료 목록: {len(items)}건")
        if not items:
            self.log("결제완료 목록이 비어 있습니다. (발급 후 3개월이 지난 건은 사이트에서 삭제됩니다)")

    def _do_download(self, selected: bool):
        if not self.items:
            self.log("먼저 [목록 조회]를 하세요.")
            return
        if selected:
            idx = [int(i) for i in self.tree.selection()]
            if not idx:
                self.log("표에서 내려받을 행을 선택하세요. (Ctrl/Shift로 여러 행)")
                return
            targets = [self.items[i] for i in idx]
        else:
            targets = list(self.items)
        out = Path(self.dir_var.get())
        do_parse = self.parse_var.get()

        def run():
            self._set_busy(True)
            try:
                s = Session()
                try:
                    self.engine = KftcEngine(s, out, log_fn=self.log)
                    results = self.engine.run(targets)
                finally:
                    s.close()
                done = sum(r.get("status") == "완료" for r in results)
                self.log(f"다운로드 결과: 완료 {done} / 전체 {len(results)} → {out / 'raw_zip'}")
                if do_parse and done:
                    self._parse_now(out)
            except Exception as e:
                self.log(f"다운로드 실패: {e}")
            finally:
                self.engine = None
                self._set_busy(False)
        self._run_bg(run)

    def _stop(self):
        if self.engine:
            self.engine.stop_flag = True
            self.log("중지 요청 — 진행 중인 건이 끝나면 멈춥니다.")

    def _do_probe(self):
        def run():
            try:
                out_dir = Path(self.dir_var.get()) / "probe"
                r = subprocess.run([sys.executable, str(CODE_DIR / "kftc_probe.py"), str(out_dir)], capture_output=True, text=True, encoding="utf-8", errors="replace")
                self.log(("구조 덤프 저장: " + r.stdout.strip()) if r.returncode == 0 else ("덤프 실패: " + (r.stderr or r.stdout)[-400:]))
            except Exception as e:
                self.log(f"덤프 실패: {e}")
        self._run_bg(run)


def main():
    app = KftcApp(selftest="--selftest" in sys.argv)
    app.mainloop()


if __name__ == "__main__":
    main()
