# -*- coding: utf-8 -*-
"""금융거래조회서 v2. 기존 다운로드·파서 작업을 재사용하는 별도 화면."""
import sys
import threading
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from kftc_gui import HERE, KftcApp
import ui_theme_v2 as theme


class KftcAppV2(KftcApp):
    def __init__(self, selftest=False):
        theme.apply_theme()
        ctk.CTk.__init__(self)
        theme.pick_font(self)
        self.title('금융거래조회서 · v2')
        self.geometry('1280x820')
        self.minsize(960, 700)
        self.configure(fg_color=theme.BG)
        self.items, self.engine, self._busy = [], None, False
        self.job_controls = []
        self._build_ui()
        theme.refresh_native(self)
        self.after(100, lambda: theme.titlebar(self))
        if selftest:
            self.after(1500, self.destroy)

    def _button(self, parent, text, command, *, primary=False, width=100):
        options = {} if primary else dict(fg_color=theme.SURFACE, text_color=theme.TEXT,
                                          hover_color=theme.SELECT, border_width=1, border_color=theme.LINE)
        button = ctk.CTkButton(parent, text=text, command=command, width=width, height=34, **options)
        self.job_controls.append(button)
        return button

    def _panel(self, row, *, stretch=False):
        panel = ctk.CTkFrame(self, border_width=1)
        panel.grid(row=row, column=0, sticky='nsew' if stretch else 'ew', padx=24, pady=(0, 12))
        panel.grid_columnconfigure(0, weight=1)
        return panel

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        header = ctk.CTkFrame(self, fg_color='transparent')
        header.grid(row=0, column=0, sticky='ew', padx=26, pady=(16, 12))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text='금융거래조회서', font=ctk.CTkFont(size=24, weight='bold'),
                     text_color=theme.ACCENT, anchor='w').grid(row=0, column=0, sticky='w')
        ctk.CTkLabel(header, text='발급된 조회서 다운로드 · BC조서 정리', text_color=theme.MUTED,
                     anchor='w').grid(row=1, column=0, sticky='w')
        self.dark_mode_var = tk.BooleanVar(value=False)
        ctk.CTkSwitch(header, text='다크모드', variable=self.dark_mode_var,
                      command=self._toggle_dark_mode).grid(row=0, column=1, rowspan=2)

        connection = self._panel(1)
        connection.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(connection, text='01  사이트 연결', font=ctk.CTkFont(weight='bold'),
                     anchor='w').grid(row=0, column=0, padx=16, pady=(10, 0), sticky='w')
        self.conn_var = tk.StringVar(value='미연결 · 크롬에서 공동인증서 로그인 후 연결을 확인하세요')
        ctk.CTkLabel(connection, textvariable=self.conn_var, text_color=theme.MUTED,
                     anchor='w').grid(row=1, column=0, columnspan=2, sticky='w', padx=16, pady=(0, 10))
        self.btn_chrome = self._button(connection, '크롬 실행', self._launch_chrome)
        self.btn_chrome.grid(row=0, column=2, rowspan=2, padx=(8, 8), pady=14)
        self.btn_connect = self._button(connection, '연결 확인', self._check_connection)
        self.btn_connect.grid(row=0, column=3, rowspan=2, padx=(0, 16), pady=14)

        settings = self._panel(2)
        settings.grid_columnconfigure(0, weight=1)
        settings.grid_columnconfigure(1, weight=0)
        ctk.CTkLabel(settings, text='02  저장 및 정리 설정', font=ctk.CTkFont(weight='bold'),
                     anchor='w').grid(row=0, column=0, columnspan=2, sticky='w', padx=16, pady=(10, 4))
        fields = ctk.CTkFrame(settings, fg_color='transparent')
        fields.grid(row=1, column=0, sticky='ew', padx=16, pady=(0, 12))
        fields.grid_columnconfigure(1, weight=1)
        self.dir_var = tk.StringVar(value=str(HERE / 'downloads'))
        self.wolbo_var = tk.StringVar()
        for row, (label, variable, command) in enumerate((('저장 폴더', self.dir_var, self._browse),
                                                          ('월보 PDF', self.wolbo_var, self._browse_wolbo))):
            ctk.CTkLabel(fields, text=label, text_color=theme.MUTED, width=72,
                         anchor='w').grid(row=row, column=0, padx=(0, 8), pady=4)
            entry = ctk.CTkEntry(fields, textvariable=variable, height=34)
            entry.grid(row=row, column=1, sticky='ew', pady=4)
            self.job_controls.append(entry)
            self._button(fields, '찾기', command, width=58).grid(row=row, column=2, padx=(8, 0), pady=4)
        ctk.CTkLabel(fields, text='월보는 선택 사항입니다. 비워두면 조회서 원본 폴더(raw_zip)에서 찾습니다.',
                     text_color=theme.MUTED, font=ctk.CTkFont(size=11), anchor='w').grid(
                         row=2, column=1, columnspan=2, sticky='w')
        right = ctk.CTkFrame(settings, fg_color='transparent')
        right.grid(row=1, column=1, padx=(0, 16), pady=(0, 12), sticky='ns')
        ctk.CTkLabel(right, text='회사명 필터', text_color=theme.MUTED, anchor='w').grid(row=0, column=0, sticky='w')
        self.filter_var = tk.StringVar()
        entry = ctk.CTkEntry(right, textvariable=self.filter_var, width=188, height=34)
        entry.grid(row=1, column=0, sticky='ew', pady=(0, 8))
        self.job_controls.append(entry)
        self.btn_parse = self._button(right, 'BC조서만 다시 생성', self._do_parse_only, width=188)
        self.btn_parse.grid(row=2, column=0, sticky='ew')

        listing = self._panel(3, stretch=True)
        listing.grid_rowconfigure(2, weight=1)
        title = ctk.CTkFrame(listing, fg_color='transparent')
        title.grid(row=0, column=0, sticky='ew', padx=16, pady=(10, 4))
        ctk.CTkLabel(title, text='03  발급된 조회서', font=ctk.CTkFont(weight='bold')).pack(side='left')
        self.count_var = tk.StringVar(value='목록 조회 전')
        ctk.CTkLabel(title, textvariable=self.count_var, text_color=theme.MUTED).pack(side='left', padx=12)
        self.selection_var = tk.StringVar(value='선택 0건')
        ctk.CTkLabel(title, textvariable=self.selection_var, text_color=theme.ACCENT).pack(side='right')
        actions = ctk.CTkFrame(listing, fg_color='transparent')
        actions.grid(row=1, column=0, sticky='ew', padx=16, pady=(0, 10))
        self.btn_list = self._button(actions, '목록 조회', self._do_list)
        self.btn_sel = self._button(actions, '선택 다운로드', lambda: self._do_download(True), primary=True, width=132)
        self.btn_all = self._button(actions, '전체 다운로드', lambda: self._do_download(False), width=118)
        for button in (self.btn_list, self.btn_sel, self.btn_all):
            button.pack(side='left', padx=(0, 8))
        self.btn_stop = ctk.CTkButton(actions, text='중지', command=self._stop, width=64, height=34,
                                     fg_color=theme.SOFT, text_color=theme.DANGER, hover_color=theme.SELECT,
                                     state='disabled')
        self.btn_stop.pack(side='left')
        self.parse_var = tk.BooleanVar(value=True)
        self.parse_check = ctk.CTkCheckBox(actions, text='다운로드 후 BC조서 생성', variable=self.parse_var,
                                           font=ctk.CTkFont(size=12), checkbox_width=18, checkbox_height=18)
        self.parse_check.pack(side='right', padx=(12, 0))
        self.job_controls.append(self.parse_check)

        table = ctk.CTkFrame(listing, fg_color=theme.SURFACE, corner_radius=0)
        table.grid(row=2, column=0, sticky='nsew', padx=16)
        table.grid_columnconfigure(0, weight=1)
        table.grid_rowconfigure(0, weight=1)
        self.style = ttk.Style(self)
        cols = ('no', 'company', 'bank', 'type', 'ref', 'issued', 'project', 'note')
        self.tree = ttk.Treeview(table, columns=cols, show='headings', selectmode='extended',
                                 style='KftcV2.Treeview', height=5)
        for col, heading, width in zip(cols, ('No', '회사명', '금융기관', '양식', '조회기준일', '발급일', '프로젝트', '비고'),
                                       (48, 230, 160, 80, 110, 110, 110, 130)):
            self.tree.heading(col, text=heading)
            self.tree.column(col, width=width, minwidth=width, stretch=col in ('company', 'bank', 'note'),
                             anchor='center' if col in ('no', 'type', 'ref', 'issued') else 'w')
        self.tree.grid(row=0, column=0, sticky='nsew')
        vertical = ctk.CTkScrollbar(table, orientation='vertical', command=self.tree.yview, width=14,
                                     fg_color=theme.SURFACE, button_color=theme.LINE, button_hover_color=theme.MUTED)
        horizontal = ctk.CTkScrollbar(table, orientation='horizontal', command=self.tree.xview, height=14,
                                       fg_color=theme.SURFACE, button_color=theme.LINE, button_hover_color=theme.MUTED)
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.tree.bind('<<TreeviewSelect>>', lambda _: self._selection_changed())
        self.empty_label = ctk.CTkLabel(table, text='연결을 확인한 뒤 목록을 조회하세요.\n발급·결제가 완료된 조회서가 여기에 표시됩니다.',
                                        text_color=theme.MUTED, fg_color=theme.SURFACE, justify='center')
        self.empty_label.place(relx=.5, rely=.5, anchor='center')
        ctk.CTkLabel(listing, text='Ctrl / Shift로 여러 행 선택   ·   발급 요청 및 결제는 금융결제원 사이트에서 먼저 진행하세요.',
                     text_color=theme.MUTED, font=ctk.CTkFont(size=11), anchor='w').grid(
                         row=3, column=0, sticky='w', padx=16, pady=(4, 8))

        logs = self._panel(4)
        log_header = ctk.CTkFrame(logs, fg_color='transparent')
        log_header.grid(row=0, column=0, sticky='ew', padx=16, pady=(6, 2))
        ctk.CTkLabel(log_header, text='작업 로그', font=ctk.CTkFont(weight='bold')).pack(side='left')
        self._button(log_header, '보조 도구', self._open_tools, width=84).pack(side='right')
        self.log_box = ctk.CTkTextbox(logs, height=72, font=('Consolas', 11), fg_color=theme.SOFT,
                                      text_color=theme.TEXT, wrap='word')
        self.log_box.grid(row=1, column=0, sticky='ew', padx=12, pady=(0, 10))
        self.log('준비 · 크롬 실행 → 인증서 로그인 → 연결 확인 → 목록 조회 → 다운로드')

    def _toggle_dark_mode(self):
        ctk.set_appearance_mode('dark' if self.dark_mode_var.get() else 'light')
        theme.refresh_native(self)

    def _selection_changed(self):
        self.selection_var.set(f'선택 {len(self.tree.selection())}건')

    def _fill(self, items):
        super()._fill(items)
        for i, iid in enumerate(self.tree.get_children()):
            self.tree.item(iid, tags=('stripe',) if i % 2 else ())
        self._selection_changed()
        if items:
            self.empty_label.place_forget()
        else:
            self.empty_label.configure(text='표시할 조회서가 없습니다.\n회사명 필터와 사이트의 발급·결제 상태를 확인하세요.')
            self.empty_label.place(relx=.5, rely=.5, anchor='center')

    def _set_busy(self, busy):
        self._busy = busy

        def update():
            for widget in self.job_controls:
                widget.configure(state='disabled' if busy else 'normal')
            self.btn_stop.configure(state='normal' if busy and self.engine else 'disabled')
        if threading.current_thread() is threading.main_thread():
            update()
        else:
            self.after(0, update)

    def _run_bg(self, fn):
        if self._busy:
            self.log('작업 중입니다. 끝나거나 중지한 뒤 다시 시도하세요.')
            return
        self._set_busy(True)

        def run():
            try:
                fn()
            finally:
                self._set_busy(False)
        threading.Thread(target=run, daemon=True).start()
        self._poll_stop_button()

    def _poll_stop_button(self):
        self.btn_stop.configure(state='normal' if self._busy and self.engine else 'disabled')
        if self._busy:
            self.after(150, self._poll_stop_button)

    def _open_tools(self):
        tools = ctk.CTkToplevel(self)
        tools.title('보조 도구')
        tools.geometry('480x220')
        tools.configure(fg_color=theme.BG)
        ctk.CTkLabel(tools, text='화면 구조 확인', font=ctk.CTkFont(size=17, weight='bold')).pack(anchor='w', padx=24, pady=(20, 8))
        ctk.CTkLabel(tools, text='실제 발급 건이 있을 때 사이트 구조를 저장합니다.\n저장 위치: 선택한 저장 폴더 아래 probe\n로그인된 화면 정보가 포함될 수 있습니다.',
                     text_color=theme.MUTED, justify='left').pack(anchor='w', padx=24)
        button = self._button(tools, '화면 구조 저장', lambda: (tools.destroy(), self._do_probe()), primary=True, width=150)
        button.pack(anchor='e', padx=24, pady=16)
        # 보조 창이 닫혀도 작업 컨트롤 목록에는 유효한 위젯만 남긴다.
        def cleanup(event):
            if event.widget is button and button in self.job_controls:
                self.job_controls.remove(button)
        button.bind('<Destroy>', cleanup)
        theme.titlebar(tools)


def main():
    app = KftcAppV2(selftest='--selftest' in sys.argv)
    app.mainloop()


if __name__ == '__main__':
    main()
