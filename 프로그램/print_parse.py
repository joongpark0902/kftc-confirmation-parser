"""출력 이력의 현재 유효 PDF만 사용해 BC조서를 재생성한다."""
import datetime as dt
import shutil
from pathlib import Path
from print_storage import backup_file,digest


def prepare_inputs(store):
    invalid=[r for r in store.data['records'].values() if r.get('kind')=='print' and not store._valid(r)]
    if invalid:
        raise ValueError(f'출력 이력 중 파일 누락·변경 {len(invalid)}건을 먼저 확인하세요.')
    records=[r for r in store.data['records'].values() if r.get('kind')=='print' and store._valid(r)]
    if not records:
        raise ValueError('유효한 출력본이 없습니다. 출력본을 저장하거나 기존 출력본을 연결하세요.')
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


def build_from_prints(store,*,wolbo=None,prev=None,log=print):
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
    folder=prepare_inputs(store)
    return run(folder,out_dir=store.folder,copy=False,log=log,wolbo=wolbo,prev=prev)
