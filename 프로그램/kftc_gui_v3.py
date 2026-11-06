# -*- coding: utf-8 -*-
"""모두의프린터 출력 PDF 수집·대사와 저장 상태 표시를 추가한 화면."""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk

import customtkinter as ctk
import pdfplumber

from kftc_gui import HERE, KftcApp
from kftc_gui_v2 import KftcAppV2
from kftc_engine import Session, parse_site_list
from print_storage import PrintStore, PrintCapture, StorageStatus, read_pdf_info, save_json, plan_jobs
import mop_bridge
import ui_theme_v2 as theme

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
except Exception:  # 끌어다 놓기 모듈이 없으면 경로 입력·찾기만 쓴다.
    TkinterDnD = DND_FILES = None


HELP_SECTIONS = (
    ('01  사이트 연결',
     '[크롬 실행]을 누르면 조회서 사이트용 크롬 창이 열립니다. 그 창에서 공동인증서로 로그인한 뒤 [연결 확인]을 누르세요.\n'
     '연결 상태에 로그인 사용자가 보이면 준비가 끝난 것입니다. 이미 열어 둔 일반 크롬 창은 연결되지 않습니다.'),
    ('출력 설정 (처음 한 번)',
     '오른쪽 위 [출력 설정]에서 모두의프린터 실행파일 · PDF 저장 폴더 · 출력 프린터를 지정하고 [연결 시험]을 누르세요.\n'
     'PDF 저장 폴더는 모두의프린터 화면의 실제 저장 폴더와 같아야 합니다. 시험이 성공하면 01 구역에 확인 시간이 표시됩니다.'),
    ('02  저장 및 정리 설정',
     '저장 폴더: 출력본 PDF · 저장 이력 · BC조서가 모이는 곳입니다. 감사 건(회사)별로 폴더를 나누는 것을 권장합니다.\n'
     '월보 PDF: 은행연합회 신용공여 월보입니다(선택). 넣으면 대출·지급보증을 조회서 금액과 자동 대사합니다.'),
    ('03  발급된 조회서 → 출력본 저장',
     '① 회사명을 입력하고 [목록 조회]를 누릅니다(비우면 발급된 전체 목록).\n'
     '② 저장할 행을 선택하고 [선택 출력본 저장] 또는 [전체 출력본 저장]을 누릅니다. 이미 저장된 사업장은 건너뜁니다.\n'
     '③ 사이트에서 대기 창에 안내된 사업장의 출력 뷰어를 열고, 인쇄 버튼은 직접 누르세요(프린터: 모두의프린터).\n'
     '    현재는 인쇄를 자동으로 하지 않습니다. 시즌에 실제 화면을 확인한 뒤 자동화할 예정입니다.\n'
     '    새 PDF의 회사 · 기관 · 기준일 · 사업장이 맞으면 프로그램이 보관하고 다음 대상으로 넘어갑니다.\n'
     '④ "저장 후 BC조서 생성"이 체크되어 있으면 저장이 끝나는 대로 BC조서를 만듭니다.\n'
     '저장 상태 열: 출력본 있음 / 일부 저장 / 미저장 / 열람용만 있음 / 확인 필요'),
    ('BC조서만 다시 생성',
     '조회서가 추가됐거나 조서를 다시 만들 때 씁니다. 03 구역의 [BC조서만 다시 생성]을 누르면 창이 열립니다.\n'
     '① 회사를 고릅니다. 저장 폴더에 있는 출력본 중 그 회사 것만 씁니다.\n'
     '② 기존 BC조서 엑셀을 끌어다 놓거나 경로를 붙여 넣습니다. 비워 두면 같은 회사의 가장 최근 BC조서를 씁니다.\n'
     '③ [다시 생성]을 누르면 새 버전(_vN) 파일을 만들고, 기존 파일에 직접 입력한 검토값을 옮겨 옵니다. BC번호는 그대로 유지합니다.\n'
     '기존 BC조서 파일은 덮어쓰지 않습니다.'),
    ('자주 막히는 곳',
     '· 인쇄했는데 PDF가 안 잡힘 → [출력 설정]의 PDF 저장 폴더가 모두의프린터 실제 저장 폴더와 같은지 확인하세요.\n'
     '· "새 PDF가 여러 개입니다" → 출력 중에는 다른 문서를 인쇄하지 마세요. 정리 후 [대기 다시 시작].\n'
     '· 5분 동안 확인 못 함 → 인쇄 상태를 확인하고 [대기 다시 시작]을 누르세요.\n'
     '· 열람용으로 내려받은 PDF는 출력본으로 등록할 수 없습니다. 사이트 출력 기능으로 다시 저장하세요.\n'
     '· 이미 갖고 있는 출력본은 대기 창의 [기존 출력본 연결]로 등록합니다.'),
)


class KftcAppV3(KftcAppV2):
    def __init__(self,selftest=False):
        self.statuses={}
        self.queue_window=None
        self.regen_window=None
        self.help_window=None
        self.settings_window=None
        self._scan_timer=None
        self._scanning=False
        self._closed=False
        self._print_active=False
        self._print_timer=None
        self.settings_path=HERE/'설정'/'print_settings_v3.json'
        self.link_evidence=HERE/'설정'/'print_link_verified_v3.json'
        self.print_config=mop_bridge.defaults()
        self.config_error=''
        try:
            if self.settings_path.exists():
                self.print_config.update(json.loads(self.settings_path.read_text(encoding='utf-8')))
        except (ValueError,OSError) as exc:
            self.config_error=str(exc)
        super().__init__(selftest=selftest)
        self._dnd_ok=False
        if TkinterDnD is not None:
            try:
                TkinterDnD._require(self);self._dnd_ok=True
            except Exception:
                self._dnd_ok=False
        self.title('금융거래조회서 · 출력본 저장 v3')
        self.geometry('1360x880')
        self.minsize(1020,780)
        self._refresh_mop_status()
        self.dir_var.trace_add('write',self._destination_changed)
        self.protocol('WM_DELETE_WINDOW',self._close)
        if self.config_error:
            self.log('출력 설정 읽기 실패 · 기존 파일은 보존했습니다: '+self.config_error)

    def _close(self):
        if hasattr(self,'_theme_animator'):self._theme_animator.cancel()
        self._closed=True
        self._finish_queue(parse=False)
        self.destroy()

    def _toggle_dark_mode(self):
        from theme_transition import ThemeTransition
        if not hasattr(self,'_theme_animator'):self._theme_animator=ThemeTransition(self)
        self._theme_animator.start('dark' if self.dark_mode_var.get() else 'light')

    def _build_ui(self):
        super()._build_ui()
        settings=self.grid_slaves(row=2,column=0)[0]
        right=settings.grid_slaves(row=1,column=1)[0]
        for widget in right.winfo_children():
            if widget in self.job_controls:self.job_controls.remove(widget)
        right.destroy()
        fields=settings.grid_slaves(row=1,column=0)[0]
        fields.grid_configure(columnspan=2)
        note=fields.grid_slaves(row=2,column=1)[0]
        note.configure(text='월보는 선택 사항입니다. 기존 BC조서로 다시 만들 때는 03의 [BC조서만 다시 생성]을 쓰세요.')
        self.prev_var=tk.StringVar()
        actions=self.btn_list.master
        search=ctk.CTkFrame(actions,fg_color='transparent')
        search.pack(side='left',before=self.btn_list,padx=(0,12))
        ctk.CTkLabel(search,text='회사명',text_color=theme.MUTED).pack(side='left',padx=(0,8))
        self.filter_entry=ctk.CTkEntry(search,textvariable=self.filter_var,width=160,height=34)
        self.filter_entry.pack(side='left')
        self.job_controls.append(self.filter_entry)
        self.btn_parse=self._button(search,'BC조서만 다시 생성',self._do_parse_only,width=150)
        self.btn_parse.pack(side='left',padx=(8,0))
        header=self.grid_slaves(row=0,column=0)[0]
        self._button(header,'출력 설정',self._open_print_settings,width=104).grid(row=0,column=2,rowspan=2,padx=(16,0))
        self.btn_help=ctk.CTkButton(header,text='사용법',command=self._open_help,width=84,height=34,
                                    fg_color=theme.SURFACE,text_color=theme.TEXT,hover_color=theme.SELECT,
                                    border_width=1,border_color=theme.LINE)
        self.btn_help.grid(row=0,column=3,rowspan=2,padx=(8,0))
        columns=('no','company','bank','storage','type','ref','issued','project','note')
        self.tree.configure(columns=columns)
        for column,label,width in zip(columns,('No','회사명','금융기관','저장 상태','양식','조회기준일','발급일','프로젝트','비고'),
                                      (48,210,150,132,70,110,110,105,130)):
            self.tree.heading(column,text=label)
            self.tree.column(column,width=width,minwidth=width,stretch=column in ('company','bank','note'),
                             anchor='center' if column in ('no','storage','type','ref','issued') else 'w')
        self.btn_sel.configure(text='선택 출력본 저장')
        self.btn_all.configure(text='전체 출력본 저장')
        self.parse_check.configure(text='저장 후 BC조서 생성')
        connection=self.grid_slaves(row=1,column=0)[0]
        self.mop_status_var=tk.StringVar(value=mop_bridge.link_status(self.print_config,self.link_evidence))
        self.mop_link_label=ctk.CTkLabel(connection,textvariable=self.mop_status_var,text_color=theme.MUTED,
                                        anchor='w',height=30,wraplength=600,justify='left')
        self.mop_link_label.grid(row=2,column=0,columnspan=2,sticky='ew',padx=16,pady=(0,10))
        self.btn_mop=self._button(connection,'모두의프린터 실행',self._launch_mop,width=216)
        self.btn_mop.grid(row=2,column=2,columnspan=2,padx=(8,16),pady=(0,10),sticky='e')

    def _refresh_mop_status(self):
        status=mop_bridge.link_status(self.print_config,self.link_evidence)
        self.mop_status_var.set(status)
        self.mop_link_label.configure(text_color=('#217A52','#83D5AB') if '시험 성공' in status else theme.MUTED)

    def _browse_previous(self,parent=None):
        path=filedialog.askopenfilename(parent=parent or self,title='입력값을 옮겨올 기존 BC조서 엑셀 선택',
            filetypes=[('Excel BC조서','*.xlsx *.xlsm')])
        if path:self.prev_var.set(path)

    # ------------------------------------------------------------ 사용법
    def _open_help(self):
        if self.help_window is not None and self.help_window.winfo_exists():
            self._raise_settings(self.help_window);return
        win=ctk.CTkToplevel(self);self.help_window=win
        win.title('사용법 · 금융거래조회서');win.geometry('760x640');win.minsize(560,420)
        win.configure(fg_color=theme.BG);win.transient(self)
        win.grid_columnconfigure(0,weight=1);win.grid_rowconfigure(0,weight=1)
        body=ctk.CTkScrollableFrame(win,fg_color=theme.SURFACE)
        body.grid(row=0,column=0,sticky='nsew',padx=18,pady=(18,8))
        body.grid_columnconfigure(0,weight=1)
        row=0
        for title,text in HELP_SECTIONS:
            ctk.CTkLabel(body,text=title,font=ctk.CTkFont(size=14,weight='bold'),text_color=theme.ACCENT,
                         anchor='w').grid(row=row,column=0,sticky='ew',padx=12,pady=(14 if row else 6,4))
            ctk.CTkLabel(body,text=text,justify='left',anchor='w',wraplength=660,text_color=theme.TEXT).grid(
                row=row+1,column=0,sticky='ew',padx=12)
            row+=2
        ctk.CTkButton(win,text='닫기',width=90,command=win.destroy).grid(row=1,column=0,sticky='e',padx=18,pady=(0,16))
        theme.titlebar(win);self._raise_settings(win)

    # ------------------------------------------------------- BC조서 다시 생성
    @staticmethod
    def _clean_path(text):
        return (text or '').strip().strip('"').strip("'").strip()

    def _do_parse_only(self):
        if self._busy:
            self.log('현재 작업을 마친 후 다시 실행하세요.');return
        if self.regen_window is not None and self.regen_window.winfo_exists():
            self._raise_settings(self.regen_window);return
        from print_parse import companies,latest_for_company,workbook_company
        from print_storage import normalized
        folder=Path(self.dir_var.get()).resolve()
        try:
            names=companies(PrintStore(folder))
        except (ValueError,OSError) as exc:
            messagebox.showerror('저장 이력 확인 필요',str(exc),parent=self);return
        typed=self.filter_var.get().strip()
        default=next((n for n in names if typed and normalized(n)==normalized(typed)),
                     names[0] if len(names)==1 else '')
        win=ctk.CTkToplevel(self);self.regen_window=win
        win.title('기존 BC조서로 다시 생성');win.geometry('700x480');win.minsize(600,450)
        win.configure(fg_color=theme.BG);win.transient(self)
        win.grid_columnconfigure(1,weight=1)
        company_var=tk.StringVar(value=default)
        wolbo_var=tk.StringVar(value=self.wolbo_var.get())
        self.prev_var.set('')
        ctk.CTkLabel(win,text='회사').grid(row=0,column=0,padx=(18,8),pady=(18,6),sticky='w')
        combo=ctk.CTkComboBox(win,variable=company_var,values=names or [''],height=34,state='readonly')
        combo.grid(row=0,column=1,columnspan=2,sticky='ew',padx=(0,18),pady=(18,6))
        ctk.CTkLabel(win,text=f'저장 폴더: {folder}   ·   출력본이 있는 회사 {len(names)}곳',text_color=theme.MUTED,
                     font=ctk.CTkFont(size=11),anchor='w').grid(row=1,column=0,columnspan=3,sticky='ew',padx=18)
        drop=ctk.CTkFrame(win,height=110,fg_color=theme.SURFACE,border_width=2,border_color=theme.LINE)
        drop.grid(row=2,column=0,columnspan=3,sticky='ew',padx=18,pady=(12,8));drop.grid_propagate(False)
        drop.grid_columnconfigure(0,weight=1);drop.grid_rowconfigure(0,weight=1)
        drop_text=('기존 BC조서 엑셀을 여기로 끌어다 놓으세요' if self._dnd_ok
                   else '끌어다 놓기를 쓸 수 없습니다 (tkinterdnd2 없음) — 아래에 경로를 붙여 넣거나 [찾기]를 누르세요')
        drop_label=ctk.CTkLabel(drop,text=drop_text,text_color=theme.MUTED,wraplength=600)
        drop_label.grid(row=0,column=0)
        ctk.CTkLabel(win,text='경로').grid(row=3,column=0,padx=(18,8),pady=6,sticky='w')
        ctk.CTkEntry(win,textvariable=self.prev_var,height=34,
                     placeholder_text='경로 붙여넣기 · 비우면 같은 회사의 최신 BC조서').grid(row=3,column=1,sticky='ew',pady=6)
        ctk.CTkButton(win,text='찾기',width=64,command=lambda:self._browse_previous(win)).grid(row=3,column=2,padx=(8,18),pady=6)
        status=ctk.CTkLabel(win,text='',anchor='w',justify='left',wraplength=640)
        status.grid(row=4,column=0,columnspan=3,sticky='ew',padx=18,pady=(2,8))
        ctk.CTkLabel(win,text='월보 PDF').grid(row=5,column=0,padx=(18,8),pady=6,sticky='w')
        ctk.CTkEntry(win,textvariable=wolbo_var,height=34,placeholder_text='선택 사항').grid(row=5,column=1,sticky='ew',pady=6)
        def browse_wolbo():
            p=filedialog.askopenfilename(parent=win,title='월보 PDF',filetypes=[('PDF','*.pdf')])
            if p:wolbo_var.set(p)
        ctk.CTkButton(win,text='찾기',width=64,command=browse_wolbo).grid(row=5,column=2,padx=(8,18),pady=6)
        ctk.CTkLabel(win,text='기존 파일은 덮어쓰지 않습니다. 새 버전(_vN)을 만들고 기존 파일의 입력값을 옮기며 BC번호는 유지합니다.',
                     text_color=theme.MUTED,font=ctk.CTkFont(size=11),anchor='w',wraplength=640,justify='left').grid(
            row=6,column=0,columnspan=3,sticky='ew',padx=18,pady=(8,0))
        actions=ctk.CTkFrame(win,fg_color='transparent')
        actions.grid(row=7,column=0,columnspan=3,sticky='ew',padx=18,pady=16)
        state={'ok':True,'token':0}
        run_button=ctk.CTkButton(actions,text='다시 생성',width=110)
        run_button.pack(side='right')
        ctk.CTkButton(actions,text='취소',width=80,fg_color=theme.SURFACE,text_color=theme.TEXT,hover_color=theme.SELECT,
                      command=win.destroy).pack(side='right',padx=(0,8))

        def show(text,kind='muted'):
            if not win.winfo_exists():return
            color={'ok':('#217A52','#83D5AB'),'warn':theme.DANGER,'muted':theme.MUTED}[kind]
            status.configure(text=text,text_color=color)

        def check(*_):
            state['token']+=1;token=state['token']
            raw=self.prev_var.get();path=self._clean_path(raw)
            if path!=raw:
                self.prev_var.set(path)  # trace 안에서는 같은 변수 trace가 다시 불리지 않으므로 그대로 이어서 검사
            company=company_var.get().strip()
            if not path:
                state['ok']=True
                latest=latest_for_company(folder,company) if company else None
                show(('비워 두면 이 파일의 입력값을 옮깁니다: '+latest.name) if latest else
                     ('이 회사의 기존 BC조서가 저장 폴더에 없어 입력값 이식 없이 새로 만듭니다.' if company else
                      '회사를 먼저 고르세요.' if names else
                      '이 저장 폴더에는 저장된 출력본이 없습니다. 02의 저장 폴더를 확인하세요.'),
                     'muted' if names else 'warn')
                return
            p=Path(path)
            if not p.is_file() or p.suffix.lower() not in ('.xlsx','.xlsm'):
                state['ok']=False;show('파일을 찾지 못했거나 엑셀(.xlsx·.xlsm)이 아닙니다.','warn');return
            state['ok']=False;show('파일을 읽는 중입니다…')
            def read():
                try:
                    from carry_over import collect_inputs
                    count=sum(len(v) for v in collect_inputs(p).values());error=''
                except Exception as exc:
                    count=0;error=str(exc)
                def done():
                    if token!=state['token'] or not win.winfo_exists():return
                    if error:
                        state['ok']=False;show('이 엑셀을 BC조서로 읽지 못했습니다: '+error,'warn');return
                    state['ok']=True
                    owner=workbook_company(p)
                    if not company_var.get().strip() and owner:
                        match=next((n for n in names if normalized(n)==normalized(owner)),'')
                        if match:
                            company_var.set(match);return  # 회사 변경으로 다시 확인된다
                    text=f'읽음: {p.name} · 옮길 입력값 {count}건'
                    if owner and company_var.get() and normalized(owner)!=normalized(company_var.get()):
                        show(text+f'\n파일명의 회사({owner})와 선택한 회사가 다릅니다. 확인하세요.','warn')
                    else:show(text,'ok')
                if not self._closed:self.after(0,done)
            threading.Thread(target=read,daemon=True).start()

        def on_drop(event):
            files=self.tk.splitlist(event.data)
            if files:self.prev_var.set(files[0])
            drop.configure(border_color=theme.LINE)
            return event.action
        def enter(event):
            drop.configure(border_color=theme.ACCENT);return event.action
        def leave(event):
            drop.configure(border_color=theme.LINE);return event.action
        if self._dnd_ok:
            targets=[drop,drop_label]
            for parent in (drop,drop_label):targets+=parent.winfo_children()
            for widget in targets:
                try:
                    widget.drop_target_register(DND_FILES)
                    widget.dnd_bind('<<Drop>>',on_drop)
                    widget.dnd_bind('<<DropEnter>>',enter)
                    widget.dnd_bind('<<DropLeave>>',leave)
                except Exception:pass
        trace_prev=self.prev_var.trace_add('write',check)
        company_var.trace_add('write',check)
        def closed(event):
            if event.widget is win:
                try:self.prev_var.trace_remove('write',trace_prev)
                except Exception:pass
        win.bind('<Destroy>',closed)

        def start():
            company=company_var.get().strip()
            if names and not company:
                show('회사를 먼저 고르세요.','warn');return
            if not state['ok']:
                show('기존 BC조서 파일을 확인한 뒤 다시 누르세요.','warn');return
            prev=self._clean_path(self.prev_var.get())
            wolbo=self._clean_path(wolbo_var.get())
            self.wolbo_var.set(wolbo)
            win.destroy()
            self._regenerate(folder,company or None,Path(prev) if prev else None,Path(wolbo) if wolbo else None)
        run_button.configure(command=start)
        self._regen_start=start;self._regen_company=company_var;self._regen_status=status
        check()
        theme.titlebar(win);self._raise_settings(win)

    def _regenerate(self,folder,company,prev,wolbo):
        def run():
            self._set_busy(True)
            try:
                from print_parse import build_from_prints
                self.log(f'BC조서 다시 생성 · 회사: {company or "전체"}')
                self.log('기존 BC조서: '+(prev.name if prev else '같은 회사의 최신 파일 자동 선택'))
                result=build_from_prints(PrintStore(folder),log=self.log,wolbo=wolbo,prev=prev,company=company)
                self.log('출력본 BC조서: '+str(result))
            except Exception as exc:
                self.log('BC조서 생성 실패: '+str(exc))
            finally:
                self._set_busy(False)
        self._run_bg(run)

    def _launch_mop(self):
        try:
            mop_bridge.launch(self.print_config['executable'])
            self.log('모두의프린터 실행 요청 · 연결 시험 결과는 별도로 확인합니다.')
        except Exception as exc:
            self.log('모두의프린터 실행 실패: '+str(exc))
            self._open_print_settings()

    def _set_busy(self,busy):
        super()._set_busy(busy)
        if not busy and not self._closed:self.after(0,self._schedule_scan)

    def _fill(self,items):
        self.items=list(items)
        self.tree.delete(*self.tree.get_children())
        from kftc_engine import PRTP_LABEL
        for i,item in enumerate(items):
            self.tree.insert('','end',iid=str(i),values=(item.no,item.company,item.bank_name,'확인 필요',
                PRTP_LABEL.get(item.prtp_type,item.prtp_type),item.ref_date,item.bank_issue_date,item.project_code,item.note),
                tags=('stripe',) if i%2 else ())
        self.count_var.set(f'발급 목록 {len(items)}건')
        if items:
            self.empty_label.place_forget()
        else:
            self.empty_label.configure(text='표시할 조회서가 없습니다.\n회사명 필터와 사이트의 발급·결제 상태를 확인하세요.')
            self.empty_label.place(relx=.5,rely=.5,anchor='center')
        try:
            self._apply_store(PrintStore(self.dir_var.get()))
        except (ValueError,OSError) as exc:
            self.log('저장 이력 확인 필요: '+str(exc))
            self.statuses={}
            self._selection_changed()
        self._schedule_scan()

    def _selection_changed(self):
        selected=[self.statuses.get(i,StorageStatus('확인 필요')).label for i in self.tree.selection()]
        duplicate=selected.count('출력본 있음')
        review=sum(s in ('확인 필요','종류 확인 필요') for s in selected)
        self.selection_var.set(f'선택 {len(selected)} · 중복 {duplicate} · 추가 저장 {len(selected)-duplicate-review} · 확인 필요 {review}')

    def _apply_store(self,store):
        if store.folder!=Path(self.dir_var.get()).resolve():
            return
        self.statuses={}
        for iid in self.tree.get_children():
            state=store.status(self.items[int(iid)])
            self.statuses[iid]=state
            self.tree.set(iid,'storage',state.label)
        self._selection_changed()

    def _destination_changed(self,*_):
        self.statuses={}
        for iid in self.tree.get_children():
            self.tree.set(iid,'storage','확인 필요')
        self._selection_changed()
        self._schedule_scan()

    def _schedule_scan(self):
        if self._scan_timer:
            self.after_cancel(self._scan_timer)
        self._scan_timer=self.after(450,self._refresh_storage)

    def _refresh_storage(self):
        self._scan_timer=None
        if self._closed or not self.items:
            return
        if self._busy or self._scanning:
            self._schedule_scan()
            return
        folder=Path(self.dir_var.get()).resolve()
        snapshot=tuple((i.mstr_num,i.bank_code,i.ref_date) for i in self.items)
        self._scanning=True
        def run():
            try:
                store=PrintStore(folder)
                store.scan_local(stop=lambda:self._closed)
                def done():
                    self._scanning=False
                    if self._closed:return
                    if snapshot==tuple((i.mstr_num,i.bank_code,i.ref_date) for i in self.items):
                        self._apply_store(store)
                    if store.scan_errors:
                        self.log(f'기존 PDF {len(store.scan_errors)}개는 내용을 확인하지 못했습니다. 파일명을 근거로 중복 처리하지 않습니다.')
                if not self._closed:self.after(0,done)
            except Exception as exc:
                error=str(exc)
                def failed():
                    self._scanning=False
                    self.log('저장 상태 확인 실패: '+error)
                if not self._closed:self.after(0,failed)
        threading.Thread(target=run,daemon=True).start()

    def _open_print_settings(self):
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self._raise_settings(self.settings_window)
            return
        win=ctk.CTkToplevel(self)
        self.settings_window=win
        win.title('모두의프린터 연동 설정')
        win.geometry('780x460')
        win.configure(fg_color=theme.BG)
        win.transient(self)
        win.protocol('WM_DELETE_WINDOW',win.destroy)
        win.grid_columnconfigure(1,weight=1)
        variables={}
        for row,(key,label) in enumerate((('executable','실행파일'),('inbox','PDF 저장 폴더'),('printer','출력 프린터'))):
            ctk.CTkLabel(win,text=label).grid(row=row,column=0,padx=18,pady=(18,0),sticky='w')
            variable=tk.StringVar(value=self.print_config.get(key,''));variables[key]=variable
            if key=='printer':
                try: choices=[p['name'] for p in mop_bridge.printers()]
                except Exception:choices=[]
                entry=ctk.CTkComboBox(win,variable=variable,values=choices or [variable.get()])
            else:
                entry=ctk.CTkEntry(win,textvariable=variable)
            entry.grid(row=row,column=1,sticky='ew',padx=8,pady=(18,0))
            if key!='printer':
                def browse(k=key,v=variable):
                    p=filedialog.askopenfilename(parent=win,filetypes=[('실행파일','*.exe')]) if k=='executable' else filedialog.askdirectory(parent=win)
                    if p:v.set(p)
                ctk.CTkButton(win,text='찾기',command=browse,width=64).grid(row=row,column=2,padx=(0,18),pady=(18,0))
        ctk.CTkLabel(win,text='모두의프린터 화면의 실제 저장 폴더와 같게 지정하세요. 파일명은 자유롭게 바꾸셔도 됩니다.\n'
                     '인쇄는 사이트에서 한 건씩 진행합니다. 생성된 PDF를 대사한 뒤 출력본 폴더로 복사합니다.\n'
                     '열람용 문서·스캔본·다른 회사 문서는 자동 완료하지 않습니다.',
                     text_color=theme.MUTED,justify='left',wraplength=720).grid(row=3,column=0,columnspan=3,sticky='w',padx=18,pady=18)
        def save(close=True):
            config={k:v.get().strip() for k,v in variables.items()}
            if not Path(config['inbox']).is_dir():
                messagebox.showerror('저장 폴더 확인','실제로 존재하는 모두의프린터 PDF 저장 폴더를 선택하세요.',parent=win);return False
            try:
                save_json(self.settings_path,config)
            except Exception as exc:
                messagebox.showerror('설정 저장 실패',str(exc),parent=win);return False
            self.print_config=config
            self._refresh_mop_status()
            if close:win.destroy()
            return True
        actions=ctk.CTkFrame(win,fg_color='transparent')
        actions.grid(row=4,column=0,columnspan=3,padx=18,sticky='ew')
        def launch():
            if save(False):
                try:mop_bridge.launch(self.print_config['executable'])
                except Exception as exc:messagebox.showerror('실행 실패',str(exc),parent=win)
        ctk.CTkButton(actions,text='모두의프린터 실행',command=launch,width=150).pack(side='left',padx=(0,8))
        ctk.CTkButton(actions,text='연결 시험',command=lambda:self._test_mop(self.print_config['inbox'],self.print_config['printer']) if save(False) else None,width=100).pack(side='left')
        ctk.CTkButton(actions,text='저장',command=save,width=90).pack(side='right')
        other=ctk.CTkFrame(win,fg_color='transparent')
        other.grid(row=5,column=0,columnspan=3,sticky='ew',padx=18,pady=20)
        ctk.CTkButton(other,text='저장 상태 다시 확인',command=lambda:(win.destroy(),self._refresh_storage()),width=165).pack(side='left',padx=(0,10))
        def view_download():
            win.destroy()
            parse=self.parse_var.get()
            self.parse_var.set(False)
            try:KftcApp._do_download(self,selected=bool(self.tree.selection()))
            finally:self.parse_var.set(parse)
        ctk.CTkButton(other,text='열람용 PDF 다운로드',command=view_download,width=170,
                      fg_color=theme.SURFACE,text_color=theme.TEXT,hover_color=theme.SELECT).pack(side='left')
        theme.titlebar(win)
        self._raise_settings(win)

    def _raise_settings(self,win):
        win.deiconify()
        win.lift()
        # 창을 열 때만 앞으로 가져오고 다른 앱 사용을 방해하지 않도록 최상위 속성을 해제한다.
        win.attributes('-topmost',True)
        def ready():
            if win.winfo_exists():
                win.attributes('-topmost',False)
                win.lift()
                win.focus_set()
        win.after(150,ready)

    def _test_mop(self,inbox,printer):
        try:
            folder=Path(inbox)
            if not folder.is_dir():raise ValueError('저장 폴더가 없습니다')
            old={p.resolve():(p.stat().st_mtime_ns,p.stat().st_size) for p in folder.glob('*.pdf')}
            token=mop_bridge.test_page(printer)
            config=dict(self.print_config)
            self.mop_status_var.set('모두의프린터 · 연결 시험 중 — PDF 수신 대기')
        except Exception as exc:
            messagebox.showerror('연결 시험 실패',str(exc),parent=self);return
        self.log('시험 인쇄 전송 · 모두의프린터 변환 결과를 확인합니다.')
        deadline=time.monotonic()+60
        def check():
            for p in folder.glob('*.pdf'):
                try:
                    if old.get(p.resolve())==(p.stat().st_mtime_ns,p.stat().st_size):continue
                    with pdfplumber.open(p) as pdf:
                        if token in '\n'.join(page.extract_text() or '' for page in pdf.pages):
                            mop_bridge.confirm_test_pdf(config,p,token,self.link_evidence)
                            self._refresh_mop_status()
                            self.log('연결 시험 성공 · '+str(p));return
                except Exception:continue
            if time.monotonic()<deadline:self.after(1000,check)
            else:
                self.mop_status_var.set('모두의프린터 · 시험 PDF 확인 실패 — 저장 폴더·로그 확인 필요')
                self.log('시험 PDF 확인 못 함 · 모두의프린터 로그·실제 저장 폴더를 확인하세요.')
        self.after(1000,check)

    def _do_download(self,selected):
        if self._busy:
            self.log('현재 작업을 마친 후 다시 실행하세요.');return
        targets=[self.items[int(i)] for i in self.tree.selection()] if selected else list(self.items)
        if not targets:
            self.log('먼저 목록을 조회하고 출력할 행을 선택하세요.');return
        inbox=Path(self.print_config['inbox'])
        if not inbox.is_dir():
            self._open_print_settings();return
        folder=Path(self.dir_var.get()).resolve()
        self._set_busy(True)
        def run():
            try:
                store=PrintStore(folder)
                session=Session()
                groups=[]
                try:
                    for item in targets:
                        sites=parse_site_list(session.get(item.detail_url),item.mstr_num)
                        if not sites:
                            self.log(f'사업장 확인 필요: {item.company} / {item.bank_name}');continue
                        groups.append((item,sites))
                finally:session.close()
                jobs,duplicates,missing=plan_jobs(store,groups)
                missing+=len(targets)-len(groups)
                def ready():
                    self._set_busy(False);self._apply_store(store)
                    self.log(f'출력 대상 확인 · 사업장 중복 {duplicates} / 추가 저장 {len(jobs)} / 확인 필요 {missing}')
                    if jobs:self._open_queue(jobs,store,inbox)
                    else:self.log('새로 저장할 출력본이 없습니다.' if not missing else '확인하지 못한 사업장이 있어 전체 완료로 처리하지 않았습니다.')
                self.after(0,ready)
            except Exception as exc:
                error=str(exc)
                def failed():
                    self._set_busy(False);self.log('출력 대상 확인 실패: '+error)
                self.after(0,failed)
        threading.Thread(target=run,daemon=True).start()

    def _open_queue(self,jobs,store,inbox):
        self._jobs=list(jobs);self._job_index=0
        self._print_store=store;self._print_inbox=inbox
        self._queue_saved=0;self._print_active=True
        self._set_busy(True)
        win=ctk.CTkToplevel(self);self.queue_window=win
        win.title('모두의프린터 · 출력본 저장 대기');win.geometry('760x400');win.configure(fg_color=theme.BG)
        win.transient(self);win.grab_set();win.protocol('WM_DELETE_WINDOW',lambda:self._finish_queue(False))
        self.print_title=ctk.CTkLabel(win,text='',font=ctk.CTkFont(size=19,weight='bold'),wraplength=710,justify='left')
        self.print_title.pack(anchor='w',padx=24,pady=(22,8))
        self.print_detail=ctk.CTkLabel(win,text='',text_color=theme.MUTED,wraplength=710,justify='left')
        self.print_detail.pack(anchor='w',padx=24,pady=(0,12))
        ctk.CTkLabel(win,text='사이트에서 위 사업장의 출력 뷰어를 열고 인쇄하세요.\n프린터: '+self.print_config['printer']+
                      '\n다른 문서를 동시에 출력하지 마세요. PDF 생성 후 대사·복사하고 다음 대상으로 넘어갑니다.',
                      text_color=theme.TEXT,justify='left',wraplength=710).pack(anchor='w',padx=24)
        self.print_state=ctk.CTkLabel(win,text='',text_color=theme.ACCENT,wraplength=710,justify='left')
        self.print_state.pack(anchor='w',padx=24,pady=16)
        actions=ctk.CTkFrame(win,fg_color='transparent');actions.pack(fill='x',padx=24,pady=10)
        ctk.CTkButton(actions,text='기존 출력본 연결',width=140,command=self._attach_existing).pack(side='left',padx=(0,8))
        ctk.CTkButton(actions,text='대기 다시 시작',width=120,command=self._begin_capture).pack(side='left')
        ctk.CTkButton(actions,text='중지',width=80,command=lambda:self._finish_queue(False)).pack(side='right')
        self._begin_capture();theme.titlebar(win)

    def _begin_capture(self):
        if self._print_timer:
            self.after_cancel(self._print_timer);self._print_timer=None
        if not self._print_active:return
        if self._job_index>=len(self._jobs):
            self.log(f'출력본 저장 완료 · {self._queue_saved}개 사업장')
            self._finish_queue(parse=self.parse_var.get());return
        item,site=self._jobs[self._job_index]
        try:self._capture=PrintCapture(self._print_inbox)
        except Exception as exc:self.print_state.configure(text=str(exc));return
        self._deadline=time.monotonic()+300
        self.print_title.configure(text=f'{self._job_index+1} / {len(self._jobs)}  {item.company} · {item.bank_name}')
        self.print_detail.configure(text=f'사업장: {site.name}   사업자번호: {site.biz_no or "확인 필요"}\n조회기준일: {item.ref_date}   사업장 번호: {site.mngt_num}')
        self.print_state.configure(text='새 출력 PDF를 기다리는 중입니다. 저장 파일명은 상관없습니다.')
        self._print_timer=self.after(1000,self._watch_pdf)

    def _watch_pdf(self):
        self._print_timer=None
        if not self._print_active:return
        item,site=self._jobs[self._job_index]
        try:
            result=self._capture.poll(item,site)
            if result:
                self._save_capture(*result);return
        except Exception as exc:
            self.print_state.configure(text='확인 필요 · '+str(exc));return
        if time.monotonic()>=self._deadline:
            self.print_state.configure(text='5분 동안 출력본을 확인하지 못했습니다. 인쇄 상태 확인 후 대기를 다시 시작하세요.');return
        self._print_timer=self.after(1000,self._watch_pdf)

    def _save_capture(self,path,info):
        item,site=self._jobs[self._job_index]
        target=self._capture.save(item,site,path,info,self._print_store)
        self.log('출력본 저장: '+str(target))
        self._queue_saved+=1;self._job_index+=1
        self._apply_store(self._print_store)
        self._begin_capture()

    def _attach_existing(self):
        if not self._print_active:return
        p=filedialog.askopenfilename(parent=self.queue_window,title='현재 대상의 출력본 PDF 선택',filetypes=[('PDF','*.pdf')])
        if not p:return
        if not messagebox.askyesno('출력본 확인','사이트 출력 기능을 통해 저장한 PDF가 맞습니까? 열람용 다운로드 파일은 등록할 수 없습니다.',parent=self.queue_window):return
        try:
            info=read_pdf_info(p)
            if self._print_timer:self.after_cancel(self._print_timer);self._print_timer=None
            self._save_capture(Path(p),info)
        except Exception as exc:
            self.print_state.configure(text='기존 출력본 확인 필요 · '+str(exc))

    def _finish_queue(self,parse=False):
        if self._print_timer:
            self.after_cancel(self._print_timer);self._print_timer=None
        active=self._print_active;self._print_active=False
        if self.queue_window:
            self.queue_window.grab_release();self.queue_window.destroy();self.queue_window=None
        if active:
            self._set_busy(False)
            if parse and self._queue_saved:
                folder=self._print_store.folder
                wolbo=self.wolbo_var.get().strip()
                from print_storage import normalized
                names={normalized(item.company):item.company for item,site in self._jobs}
                company=next(iter(names.values())) if len(names)==1 else None
                def build():
                    try:
                        from print_parse import build_from_prints
                        path=build_from_prints(PrintStore(folder),log=self.log,wolbo=Path(wolbo) if wolbo else None,
                                              company=company)
                        self.log('출력본 BC조서: '+str(path))
                    except Exception as exc:self.log('출력본 BC조서 생성 실패: '+str(exc))
                self._run_bg(build)
            elif not self._closed:self.log('출력 대기를 마쳤습니다. 이미 저장한 PDF와 이력은 보존됩니다.')

    def _parse_now(self,out):
        from print_parse import build_from_prints
        wolbo=self.wolbo_var.get().strip()
        prev=self.prev_var.get().strip()
        self.log('출력 이력의 현재 유효 PDF로 BC조서를 생성합니다.')
        self.log('이전 BC조서: '+prev if prev else '이전 BC조서: 저장 폴더의 최신 파일 자동 선택')
        typed=self.filter_var.get().strip() or None
        result=build_from_prints(PrintStore(out),log=self.log,wolbo=Path(wolbo) if wolbo else None,
                                 prev=Path(prev) if prev else None,company=typed)
        self.log('출력본 BC조서: '+str(result))
        return result


def main():
    KftcAppV3(selftest='--selftest' in sys.argv).mainloop()


if __name__=='__main__':main()
