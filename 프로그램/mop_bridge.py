"""모두의프린터 실행·가상 프린터 점검. 기본 프린터/기존 프로필 변경 없음."""
import os
import subprocess
import uuid
import json
import datetime as dt
from pathlib import Path


def printers():
    import win32print
    rows=win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS,None,2)
    return [{'name':r['pPrinterName'],'port':r['pPortName'],'driver':r['pDriverName']} for r in rows
            if r['pPortName'].startswith('127.') and 'PS' in r['pDriverName'].upper()]


def launch(executable):
    path=Path(executable)
    if not path.is_file() or path.suffix.lower()!='.exe':
        raise ValueError('모두의프린터 실행파일을 선택하세요')
    try:
        # Windows Shell을 통해 UAC 승인을 요청한다. 승인 여부는 사용자가 결정한다.
        return os.startfile(str(path),'runas',cwd=str(path.parent),show_cmd=1)
    except OSError as exc:
        if getattr(exc,'winerror',None)==1223:
            raise RuntimeError('관리자 권한 실행을 취소했습니다. 실행하려면 Windows 승인 창에서 허용하세요.') from exc
        raise


def test_page(printer):
    """실제 드라이버를 거쳐 개인 정보 없는 시험 문서를 인쇄한다."""
    import win32ui
    if printer not in {p['name'] for p in printers()}:
        raise ValueError('루프백 PS 가상 프린터만 연결 시험을 할 수 있습니다')
    token='KFTC-LINK-'+uuid.uuid4().hex[:12].upper()
    dc=win32ui.CreateDC()
    dc.CreatePrinterDC(printer)
    try:
        dc.StartDoc(token)
        try:
            dc.StartPage()
            font=win32ui.CreateFont({'name':'Arial','height':100,'weight':400})
            dc.SelectObject(font)
            dc.TextOut(200,200,'Financial confirmation print link test')
            dc.TextOut(200,400,token)
            dc.EndPage()
            dc.EndDoc()
        except Exception:
            dc.AbortDoc()
            raise
    finally:
        dc.DeleteDC()
    return token


def defaults():
    return {'executable':str(Path.home()/'Desktop'/'ebp348_x64.exe'),
            'inbox':str(Path.home()/'Documents'/'모두의 프린터'),
            'printer':'Samsung CLX-6240 Series PS'}


def config_key(config):
    return {key:str(config.get(key,'')) for key in ('inbox','executable','printer')}


def confirm_test_pdf(config,path,token,evidence):
    import pdfplumber
    from print_storage import save_json,digest
    with pdfplumber.open(path) as pdf:
        if not token.startswith('KFTC-LINK-') or token not in '\n'.join(page.extract_text() or '' for page in pdf.pages):
            raise ValueError('시험 PDF의 고유 문구를 확인하지 못했습니다')
        pages=len(pdf.pages)
    value={'config':config_key(config),'verified_at':dt.datetime.now().isoformat(timespec='seconds'),
           'file':str(path),'sha256':digest(path),'token':token,'pages':pages}
    save_json(evidence,value)
    return value


def link_status(config,evidence):
    path=Path(evidence)
    if not path.exists():return '모두의프린터 · 미검증 — 출력 설정에서 연결 시험을 해주세요'
    try:
        value=json.loads(path.read_text(encoding='utf-8'))
        if value.get('config')!=config_key(config):return '모두의프린터 · 설정 변경 — 재시험 필요'
        if not value.get('token','').startswith('KFTC-LINK-') or not value.get('verified_at'):
            raise ValueError('시험 이력 확인 실패')
        return '모두의프린터 · 연결 시험 성공 ('+value['verified_at'].replace('T',' ')+') · PS'
    except (OSError,ValueError,KeyError,TypeError):
        return '모두의프린터 · 시험 이력 확인 필요 — 재시험 필요'
