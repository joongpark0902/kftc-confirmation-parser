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


class KftcAppV3(KftcAppV2):
    def __init__(self,selftest=False):
        self.statuses={}
        self.queue_window=None
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
        note.grid_configure(row=3)
        note.configure(text='월보·이전 엑셀은 선택 사항입니다. 이전 엑셀을 비우면 저장 폴더의 최신 BC조서를 사용합니다.')
        self.prev_var=tk.StringVar()
        ctk.CTkLabel(fields,text='이전 BC조서',text_color=theme.MUTED,width=72,anchor='w').grid(
            row=2,column=0,padx=(0,8),pady=4)
        self.prev_entry=ctk.CTkEntry(fields,textvariable=self.prev_var,height=34)
        self.prev_entry.grid(row=2,column=1,sticky='ew',pady=4)
        self.job_controls.append(self.prev_entry)
        self._button(fields,'찾기',self._browse_previous,width=58).grid(row=2,column=2,padx=(8,0),pady=4)
        self.btn_parse=self._button(settings,'BC조서만 다시 생성',self._do_parse_only,width=170)
        self.btn_parse.grid(row=0,column=1,padx=(8,16),pady=(8,4),sticky='e')
        actions=self.btn_list.master
        search=ctk.CTkFrame(actions,fg_color='transparent')
        search.pack(side='left',before=self.btn_list,padx=(0,12))
        ctk.CTkLabel(search,text='회사명',text_color=theme.MUTED).pack(side='left',padx=(0,8))
        self.filter_entry=ctk.CTkEntry(search,textvariable=self.filter_var,width=160,height=34)
        self.filter_entry.pack(side='left')
        self.job_controls.append(self.filter_entry)
        header=self.grid_slaves(row=0,column=0)[0]
        self._button(header,'출력 설정',self._open_print_settings,width=104).grid(row=0,column=2,rowspan=2,padx=(16,0))
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

    def _browse_previous(self):
        path=filedialog.askopenfilename(parent=self,title='입력값을 옮겨올 이전 BC조서 엑셀 선택',
            filetypes=[('Excel BC조서','*.xlsx *.xlsm')])
        if path:self.prev_var.set(path)

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
                prev=self.prev_var.get().strip()
                def build():
                    try:
                        from print_parse import build_from_prints
                        path=build_from_prints(PrintStore(folder),log=self.log,wolbo=Path(wolbo) if wolbo else None,
                                              prev=Path(prev) if prev else None)
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
        result=build_from_prints(PrintStore(out),log=self.log,wolbo=Path(wolbo) if wolbo else None,
                                 prev=Path(prev) if prev else None)
        self.log('출력본 BC조서: '+str(result))
        return result


def main():
    KftcAppV3(selftest='--selftest' in sys.argv).mainloop()


if __name__=='__main__':main()
