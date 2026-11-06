"""출력 이력의 현재 유효 PDF만 사용해 BC조서를 재생성한다."""
import datetime as dt
import shutil
from pathlib import Path
import re
from print_storage import backup_file,digest,normalized


def record_company(record):
    """조회 목록의 회사명(감사 대상). 예전 이력처럼 없으면 PDF 머리의 회사명.
    PDF 머리 회사명은 사업장마다 다를 수 있어 회사 구분에는 목록 회사명을 우선한다."""
    return record.get('company') or (record.get('info') or {}).get('company','')


def _same_company(record,company):
    return not company or normalized(record_company(record))==normalized(company)


def companies(store):
    """출력 이력에 있는 회사명(중복 제거, 처음 나온 표기)."""
    seen={}
    for r in store.data['records'].values():
        name=record_company(r)
        if r.get('kind')=='print' and name and normalized(name) not in seen:
            seen[normalized(name)]=name
    return sorted(seen.values())


def workbook_company(path):
    """BC조서_<회사>_vN_날짜.xlsx 파일명에서 회사명을 읽는다. 형식이 다르면 빈 문자열."""
    m=re.match(r'BC조서_(.+)_v\d+_\d{8}-\d{4}$',Path(path).stem)
    return m.group(1) if m else ''


def latest_for_company(folder,company):
    files=[f for f in Path(folder).glob('BC조서_*.xlsx') if not f.name.startswith('~$')
           and normalized(workbook_company(f))==normalized(company)]
    return max(files,key=lambda f:f.stat().st_mtime) if files else None


def prepare_inputs(store,company=None):
    invalid=[r for r in store.data['records'].values() if r.get('kind')=='print' and _same_company(r,company) and not store._valid(r)]
    if invalid:
        raise ValueError(f'출력 이력 중 파일 누락·변경 {len(invalid)}건을 먼저 확인하세요.')
    records=[r for r in store.data['records'].values() if r.get('kind')=='print' and _same_company(r,company) and store._valid(r)]
    if not records:
        raise ValueError(('선택한 회사('+company+')의 ' if company else '')+'유효한 출력본이 없습니다. 출력본을 저장하거나 기존 출력본을 연결하세요.')
    folder=store.folder/'_출력대상'/dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    folder.mkdir(parents=True,exist_ok=False)
    for index,record in enumerate(records,1):
        source=store.folder/record['file']
        target=folder/f'{index:04d}_{source.name}'
        shutil.copy2(source,target)
        if digest(target)!=record['sha256'] or digest(source)!=record['sha256']:
            raise OSError('출력본 대사 불일치: '+str(source))
    backup_file(store.folder/'bc_numbers.json','print_parse')
    return folder


def build_from_prints(store,*,wolbo=None,prev=None,company=None,log=print):
    """company를 주면 그 회사 출력본만 쓴다. 이전 조서를 비우면 같은 회사의 최신 BC조서를 쓴다."""
    from run_parser import run
    if prev is not None:
        prev=Path(prev)
        if not prev.is_file() or prev.suffix.lower() not in ('.xlsx','.xlsm'):
            raise ValueError('선택한 이전 BC조서 엑셀 파일을 확인하세요.')
        try:
            from carry_over import collect_inputs
            collect_inputs(prev)
        except Exception as exc:
            raise ValueError('선택한 이전 BC조서 엑셀을 읽지 못했습니다: '+str(exc)) from exc
    no_prev=False
    if company and prev is None:
        prev=latest_for_company(store.folder,company)
        if prev is None:
            no_prev=True
            log(f'{company}의 이전 BC조서가 없어 입력값 이식 없이 새로 만듭니다.')
    folder=prepare_inputs(store,company)
    return run(folder,out_dir=store.folder,client=company or None,copy=False,log=log,wolbo=wolbo,prev=prev,no_prev=no_prev)
