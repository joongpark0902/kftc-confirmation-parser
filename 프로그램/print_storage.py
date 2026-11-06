"""출력 PDF의 식별·보관·중복 확인. 원본 문서와 기존 이력은 보존한다."""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import re
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import pdfplumber
from confirm_parser import parse_header, parse_footer
from wolbo_parser import inst_key


def backup_file(path: Path, reason='update'):
    path = Path(path)
    if not path.exists():
        return None
    stamp = dt.datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y%m%d_%H%M%S_%f')
    target = path.with_name(f'backup_{stamp}_{reason}_{path.name}')
    counter = 2
    while target.exists():
        target = path.with_name(f'backup_{stamp}_{reason}_{counter}_{path.name}')
        counter += 1
    shutil.copy2(path, target)
    if digest(path) != digest(target):
        raise OSError('백업 해시 확인 실패')
    return target


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, value):
    path = Path(path)
    payload = json.dumps(value, ensure_ascii=False, indent=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_file(path, 'history')
    path.write_text(payload, encoding='utf-8')
    if json.loads(path.read_text(encoding='utf-8')) != value:
        raise OSError('저장 결과 확인 실패')


def normalized(text):
    text = re.sub(r'주식회사|유한회사|\(주\)|㈜', '', text or '')
    return re.sub(r'[^0-9a-z가-힣]', '', text.lower())


@dataclass(frozen=True)
class PdfInfo:
    company: str
    biz_no: str
    bank: str
    ref_date: str
    is_view: bool
    pages: int


def read_pdf_info(path):
    data = Path(path).read_bytes()
    if not data.startswith(b'%PDF-') or not data.rstrip().endswith(b'%%EOF'):
        raise ValueError('완성된 PDF 파일이 아닙니다')
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        if not pdf.pages:
            raise ValueError('PDF 페이지가 없습니다')
        first = pdf.pages[0].extract_text() or ''
        last = pdf.pages[-1].extract_text() or ''
        header, footer = parse_header(first), parse_footer(last)
        text = re.sub(r'\s+', '', first + last)
        return PdfInfo(header.get('company',''), re.sub(r'\D','',header.get('biz_no','')),
                       footer.get('institution',''), header.get('ref_date',''), '열람용' in text, len(pdf.pages))


def matches(info, item, site=None):
    if not info.bank or not item.bank_name or inst_key(info.bank) != inst_key(item.bank_name):
        return False
    if not info.ref_date or not item.ref_date or info.ref_date != item.ref_date:
        return False
    biz = re.sub(r'\D', '', site.biz_no) if site else ''
    if biz:
        return info.biz_no == biz
    return bool(info.company) and normalized(info.company) == normalized(site.name if site and site.name else item.company)


@dataclass(frozen=True)
class StorageStatus:
    label: str
    outputs: int = 0
    expected: int = 0
    files: tuple = ()


class PrintStore:
    def __init__(self, folder):
        self.folder = Path(folder).resolve()
        self.path = self.folder / 'output_history_v3.json'
        self.data = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {'version':1,'items':{},'records':{}}
        if not isinstance(self.data.get('items'),dict) or not isinstance(self.data.get('records'),dict):
            raise ValueError('출력 이력 형식 오류: 원본을 보존하고 확인해야 합니다')
        if any(not isinstance(r,dict) or not isinstance(r.get('file'),str) or not isinstance(r.get('info'),dict)
               for r in self.data['records'].values()):
            raise ValueError('출력 이력 항목 오류: 원본을 보존하고 확인해야 합니다')
        self.local = []
        self.scan_errors = []

    def _save(self):
        save_json(self.path, self.data)

    @staticmethod
    def item_key(item):
        return f'{item.mstr_num}|{item.bank_code}|{item.prtp_type}|{item.ref_date}'

    def site_key(self,item,site):
        return self.item_key(item) + '|' + site.mngt_num

    def set_expected(self,item,sites):
        self.data['items'][self.item_key(item)] = [s.mngt_num for s in sites]
        self._save()

    def record(self,item,site,path,info,kind='print'):
        path = Path(path).resolve()
        if not path.is_relative_to(self.folder):
            raise ValueError('선택한 저장 폴더 밖의 파일입니다')
        if kind not in ('print','view') or not matches(info,item,site) or (kind=='print' and info.is_view):
            raise ValueError('조회 대상과 문서가 다르거나 열람용 PDF입니다')
        key = self.site_key(item,site) + '|' + kind
        self.data['records'][key] = {'item_key':self.item_key(item),'site':site.mngt_num,'kind':kind,
            'company':item.company or '',
            'file':str(path.relative_to(self.folder)),'sha256':digest(path),'info':asdict(info),
            'saved_at':dt.datetime.now().isoformat(timespec='seconds')}
        self._save()

    def _valid(self,record):
        path = (self.folder / record.get('file','')).resolve()
        try:
            return path.is_relative_to(self.folder) and path.is_file() and digest(path)==record.get('sha256')
        except OSError:
            return False

    def has_output(self,item,site):
        record=self.data['records'].get(self.site_key(item,site)+'|print')
        try:
            return bool(record and self._valid(record) and matches(PdfInfo(**record['info']),item,site))
        except (TypeError,KeyError):
            return False

    def scan_local(self, stop=lambda:False):
        """직접 저장한 PDF도 본문 기준으로 찾되 출력본으로 단정하지 않는다."""
        self.local, self.scan_errors = [], []
        if not self.folder.exists():
            return
        known={r.get('file') for r in self.data['records'].values() if self._valid(r)}
        for path in sorted(self.folder.rglob('*.pdf')):
            if stop():
                return
            relative=path.relative_to(self.folder)
            if relative.as_posix() in known or str(relative) in known or any(p in ('probe','_mop_inbox','_출력대상') for p in relative.parts):
                continue
            try:
                self.local.append((path,read_pdf_info(path)))
            except Exception as exc:
                self.scan_errors.append((str(path),str(exc)))

    def status(self,item):
        key=self.item_key(item)
        records=[r for r in self.data['records'].values() if r.get('item_key')==key]
        valid=[r for r in records if self._valid(r)]
        outputs={r['site'] for r in valid if r.get('kind')=='print'}
        expected=set(self.data['items'].get(key,[]))
        files=tuple(str(self.folder/r['file']) for r in valid)
        if outputs:
            if expected and expected.issubset(outputs):
                return StorageStatus('출력본 있음',len(outputs),len(expected),files)
            return StorageStatus('일부 저장',len(outputs),len(expected),files)
        if len(valid)!=len(records):
            return StorageStatus('확인 필요',0,len(expected),files)
        local=[(p,info) for p,info in self.local if matches(info,item)]
        if any(not info.is_view for p,info in local):
            return StorageStatus('종류 확인 필요',0,len(expected),tuple(str(p) for p,info in local))
        if self.scan_errors or any(not info.company or not info.bank or not info.ref_date for p,info in self.local):
            return StorageStatus('확인 필요',0,len(expected),files)
        if valid or local:
            return StorageStatus('열람용만 있음',0,len(expected),files+tuple(str(p) for p,info in local))
        # 이전 열람용 ZIP 다운로드 이력도 표시. 출력본 중복으로 쓰지는 않는다.
        legacy=self.folder/'download_history.json'
        if legacy.exists():
            try:
                rows=json.loads(legacy.read_text(encoding='utf-8')).values()
                for r in rows:
                    p=Path(r.get('file',''))
                    if (r.get('mstr_num')==item.mstr_num and r.get('bank_code')==item.bank_code
                        and p.resolve().is_relative_to(self.folder) and p.is_file()):
                        return StorageStatus('열람용만 있음',0,len(expected),(str(p),))
            except (ValueError,OSError,AttributeError):
                return StorageStatus('확인 필요')
        return StorageStatus('미저장',0,len(expected))


def plan_jobs(store,groups):
    jobs=[];duplicates=0;review=0
    for item,sites in groups:
        if not sites:
            review+=1
            continue
        store.set_expected(item,sites)
        for site in sites:
            if not site.mngt_num or re.sub(r'\s+','',site.issue_status)!='발급완료':
                review+=1
            elif store.has_output(item,site):
                duplicates+=1
            else:
                jobs.append((item,site))
    return jobs,duplicates,review


class PrintCapture:
    def __init__(self,inbox, *, inspect=read_pdf_info, stable_polls=3):
        self.inbox=Path(inbox).resolve()
        if not self.inbox.is_dir():
            raise ValueError('모두의프린터 PDF 저장 폴더를 먼저 선택하세요')
        self.inspect=inspect
        self.stable_polls=stable_polls
        self.baseline={p.resolve():(p.stat().st_mtime_ns,p.stat().st_size) for p in self.inbox.glob('*.pdf')}
        self.samples={}

    def poll(self,item,site):
        """새 출력이 한 개이고 안정화·내용 대사가 끝난 경우에만 반환한다."""
        paths=[]
        for path in self.inbox.glob('*.pdf'):
            path=path.resolve()
            try:
                signature=(path.stat().st_mtime_ns,path.stat().st_size)
            except OSError:
                continue
            if self.baseline.get(path)==signature:
                continue
            paths.append(path)
            old,count=self.samples.get(path,(None,0))
            self.samples[path]=(signature,count+1 if signature==old else 1)
        if len(paths)>1:
            raise ValueError('새 PDF가 여러 개입니다. 다른 인쇄와 섞였는지 확인하세요')
        if not paths or self.samples[paths[0]][1]<self.stable_polls:
            return None
        try:
            info=self.inspect(paths[0])
        except (OSError,ValueError):
            return None
        if info.is_view or not matches(info,item,site):
            raise ValueError('출력 PDF의 회사·기관·기준일·사업장이 다르거나 열람용입니다')
        return paths[0],info

    def save(self,item,site,source,info,store):
        # UI/변환이 파일을 바꿨을 수 있으므로 복사 직전 다시 검증한다.
        current=self.inspect(source)
        if current!=info or current.is_view or not matches(current,item,site):
            raise ValueError('보관 전 문서 확인 실패')
        directory=store.folder/'출력본'
        directory.mkdir(parents=True,exist_ok=True)
        name=re.sub(r'[\\/:*?"<>|]', '_',f'{info.company}_{info.bank}_{info.ref_date}_{site.mngt_num}_출력본.pdf')
        target=directory/name
        counter=2
        while target.exists():
            if digest(target)==digest(source):
                break
            target=directory/f'{Path(name).stem}_{counter}.pdf'
            counter+=1
        if not target.exists():
            shutil.copy2(source,target)
        if digest(source)!=digest(target):
            raise OSError('출력본 복사 해시 불일치')
        store.record(item,site,target,info)
        return target
