"""GUI 공통 테마와 표시 포맷."""
import tkinter as tk
import tkinter.font as tkfont
import tkinter.ttk as ttk

import customtkinter as ctk


# ── 글꼴 ─────────────────────────────────────────────────────────────────
#
# 이 PC에는 macOS의 SF Pro가 없다. 그렇다고 라틴/한글 글꼴을 따로 지정할
# 필요는 없었다 — Windows 글꼴 링크(font linking)가 "Segoe UI"만 지정해도
# 한글 글자를 자동으로 맑은 고딕으로 대체해 그려준다는 걸 실제 렌더링해
# 확인했다(같은 문장을 "Segoe UI"로 찍은 것과 "맑은 고딕"으로 찍은 것이
# 한글 부분은 구별이 안 될 만큼 같았고, 숫자·영문 부분은 Segoe UI 쪽이
# 더 또렷했다 — 스캐폴드 스크린샷 font-test.png 기준). 그래서 라틴/한글을
# 나눠 관리하지 않고 이 한 글꼴만 쓴다. 이 상수를 바꾸면 apply_theme()의
# 전역 기본값과, 아래 표 셀 글꼴들이 한 번에 같이 바뀐다.
FONT_FAMILY = "Segoe UI"          # apply_theme() 에서 설치된 글꼴에 따라 바뀐다
FONT_PREFERENCE = ["Pretendard", "Noto Sans KR", "맑은 고딕", "Malgun Gothic", "Segoe UI"]

# 로그 타임스탬프·회사코드처럼 자릿수를 맞춰야 하는 곳에 쓰는 고정폭 글꼴.
# 일반 UI 글꼴과는 성격이 달라 FONT_FAMILY와 분리해 둔다.
FONT_FAMILY_MONO = "Consolas"


def pick_font():
    """설치된 글꼴 중 FONT_PREFERENCE 순으로 첫 번째. (Tk 루트가 필요해 임시 루트를 만들었다 지운다)"""
    try:
        import tkinter.font as tkfont
        root = tk.Tk(); root.withdraw()
        fams = set(tkfont.families(root)); root.destroy()
    except Exception:
        return "Segoe UI"
    for f in FONT_PREFERENCE:
        if f in fams:
            return f
    return "Segoe UI"


def apply_theme():
    """앱 시작 때 한 번 부른다. 글꼴을 고르고, customtkinter 기본 테마색을 보고서와 같은 남색·하늘색으로 바꾼다."""
    global FONT_FAMILY, TABLE_CELL_FONT, TABLE_HEADER_FONT
    FONT_FAMILY = pick_font()
    TABLE_CELL_FONT = (FONT_FAMILY, -13, "normal roman  ")
    TABLE_HEADER_FONT = (FONT_FAMILY, -12)
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")
    t = ctk.ThemeManager.theme
    t["CTkFont"]["family"] = FONT_FAMILY
    t["CTkFont"]["size"] = 12
    t["CTkButton"].update({"fg_color": [ACCENT, ACCENT], "hover_color": [ACCENT_HOVER, ACCENT_HOVER],
                           "text_color": ["#FFFFFF", "#FFFFFF"], "corner_radius": 6})
    t["CTkSegmentedButton"].update({"selected_color": [ACCENT, ACCENT], "selected_hover_color": [ACCENT_HOVER, ACCENT_HOVER],
                                    "unselected_color": [ACCENT_SOFT, ACCENT_SOFT], "unselected_hover_color": ["#B3C7E6", "#B3C7E6"],
                                    "fg_color": [ACCENT_SOFT, ACCENT_SOFT], "text_color": ["#FFFFFF", "#FFFFFF"], "corner_radius": 6})
    t["CTkCheckBox"].update({"fg_color": [ACCENT, ACCENT], "hover_color": [ACCENT_HOVER, ACCENT_HOVER], "border_color": ["#9AA8BF", "#9AA8BF"]})
    t["CTkOptionMenu"].update({"fg_color": [ACCENT, ACCENT], "button_color": [ACCENT_HOVER, ACCENT_HOVER],
                               "button_hover_color": [ACCENT_SOFT, ACCENT_SOFT], "text_color": ["#FFFFFF", "#FFFFFF"], "corner_radius": 6})
    t["CTkEntry"].update({"border_color": [BORDER, BORDER], "fg_color": [SURFACE, SURFACE]})
    t["CTkFrame"].update({"border_color": [BORDER, BORDER]})


def _rgb_hex_to_colorref(hex_color):
    """"#RRGGBB" → Win32 COLORREF(0x00BBGGRR) 정수로 바꾼다.

    COLORREF는 우리가 평소 쓰는 "#RRGGBB" 순서와 바이트 순서가 뒤집혀
    있다(0x00BBGGRR) — 이 변환을 건너뛰고 정수를 그대로 넘기면 R과 B가
    맞바뀐, 그럴듯하지만 틀린 색이 칠해진다(예: 파란 계열을 넣었는데
    주황/빨강이 나오는 식). apply_titlebar_theme()에서만 쓴다.
    """
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return (b << 16) | (g << 8) | r


def apply_titlebar_theme(window):
    """네이티브 타이틀바를 라이트 팔레트 색으로 물들인다(Windows 11 22000+).

    macOS 스타일 트래픽라이트 버튼(오버레이 창)을 새로 그리는 대신,
    Windows 11의 DWM(Desktop Window Manager) API로 기존 네이티브
    타이틀바의 캡션/텍스트/테두리 색만 바꿔서 창 아래 라이트 배경
    (WINDOW_BG)과 이어져 보이게 한다 — 드래그·리사이즈·스냅·작업표시줄
    프리뷰 같은 네이티브 동작은 전부 그대로 남는다(overrideredirect를
    안 쓰므로).

    이 함수는 성공 여부와 무관하게 절대 예외를 던지지 않는다: DWM 캡션
    색 속성(DWMWA_CAPTION_COLOR 등)은 Windows 11 빌드 22000 이상에서만
    존재한다 — Windows 10, 그보다 낮은 11 빌드, 또는 Windows가 아닌
    플랫폼에서는 dwmapi 자체가 없거나 DwmSetWindowAttribute가 0이 아닌
    HRESULT(실패)를 돌려주는데, 이 모든 경우를 조용히 무시하고 그냥
    돌아온다 — 앱은 기본 타이틀바로 정상 실행된다.

    winfo_id()가 돌려주는 건 (Windows tkinter에서는) 실제 최상위 창이
    아니라 그 안의 자식 드로잉 서피스 HWND다 — 이 핸들을 그대로
    DwmSetWindowAttribute에 넘기면 "핸들이 잘못되었습니다"
    (invalid handle) OSError가 난다(직접 재현해 확인). 그래서
    user32.GetAncestor(hwnd, GA_ROOT)로 캡션·테두리를 실제로 소유한
    최상위 창 핸들을 한 번 더 구해서 그 핸들에 적용한다.
    """
    import sys

    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        DWMWA_BORDER_COLOR = 34
        DWMWA_CAPTION_COLOR = 35
        DWMWA_TEXT_COLOR = 36
        GA_ROOT = 2

        dwmapi = ctypes.WinDLL("dwmapi")
        user32 = ctypes.WinDLL("user32")

        # HWND는 64비트 Windows에서 포인터 크기 값이다 — argtypes/restype을
        # 명시하지 않으면 ctypes가 기본값(c_int)으로 반환값을 32비트로
        # 잘라내 버릴 수 있다. GetAncestor는 실제 반환 핸들 값이라 이
        # 잘림이 나면 엉뚱한(또는 0인) 창을 가리키게 된다.
        user32.GetAncestor.restype = wintypes.HWND
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        dwmapi.DwmSetWindowAttribute.restype = ctypes.HRESULT
        dwmapi.DwmSetWindowAttribute.argtypes = [
            wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
        ]

        child_hwnd = wintypes.HWND(window.winfo_id())
        root_hwnd = user32.GetAncestor(child_hwnd, GA_ROOT)
        if not root_hwnd:
            return
        hwnd = wintypes.HWND(root_hwnd)

        # 캡션(타이틀바 바탕) = WINDOW_BG로 창 본체와 한 면처럼 이어지게,
        # 캡션 글자 = TEXT_PRIMARY(본문 텍스트와 같은 색), 테두리 =
        # BORDER(헤어라인)로 앱 전체 라이트 팔레트와 맞춘다.
        attrs = (
            (DWMWA_CAPTION_COLOR, WINDOW_BG),
            (DWMWA_TEXT_COLOR, TEXT_PRIMARY),
            (DWMWA_BORDER_COLOR, BORDER),
        )
        for attr, hex_color in attrs:
            value = wintypes.DWORD(_rgb_hex_to_colorref(hex_color))
            hr = dwmapi.DwmSetWindowAttribute(
                hwnd, wintypes.DWORD(attr), ctypes.byref(value), ctypes.sizeof(value)
            )
            if hr != 0:
                return
    except Exception:
        # dwmapi가 없거나(구형 Windows), 로드에 실패하거나, 호출 자체가
        # 예외를 내는 어떤 경우든 타이틀바는 그냥 기본값으로 남고 앱은
        # 정상적으로 계속 뜬다.
        return


# ── 라이트 팔레트 ────────────────────────────────────────────────────────
#
# macOS 라이트 모드(Activity Monitor 참고 이미지의 라이트 버전) 값에서
# 출발해, 실제로 이 윈도우 PC 화면에 찍어 보고 눈으로 맞춘 값이다.
# 이론적인 macOS 값을 그대로 베끼지 않은 이유: Segoe UI/맑은 고딕은 SF Pro
# 보다 굵어 보여서 같은 명도 대비를 쓰면 더 진하게 느껴진다 — 그래서
# 보조 텍스트·구분선 쪽은 macOS 원본보다 살짝 연하게 조정했다.
# 보고서(WACC 시트)와 같은 남색·하늘색 팔레트
WINDOW_BG = "#EEF2F8"        # 창 바깥 배경
PANEL_BG = "#F7F9FC"         # 패널 표면
SURFACE = "#FFFFFF"          # 콘텐츠/표 표면
BORDER = "#D6DEEA"           # 헤어라인 테두리·구분선
TEXT_PRIMARY = "#1B2A41"     # 본문 텍스트(짙은 남색)
TEXT_SECONDARY = "#6B7A90"   # 보조·설명 텍스트
ACCENT = "#1F3864"           # 강조색 — 보고서 헤더 남색
ACCENT_HOVER = "#2C4C86"
ACCENT_SOFT = "#8FA6C8"      # 세그먼트 비선택
HEADER_FILL = "#C6D9F1"      # 표 헤더 하늘색(보고서와 동일)
HEADER_TEXT = "#002060"
SELECTION_FILL = ACCENT
SELECTION_TEXT = "#FFFFFF"
ROW_STRIPE = "#F4F7FB"       # 표 줄무늬
NEGATIVE = "#D64545"         # 음수·경고


# tk.Listbox는 customtkinter가 감싸주지 않아 색을 직접 맞춘다. highlightthickness
# 로 얇은 테두리를 둘러 흰 바탕 카드 위에서도 목록 영역 경계가 보이게 한다
# (카드와 목록이 둘 다 SURFACE 흰색이라 테두리가 없으면 서로 묻힌다).
LISTBOX_STYLE = {
    "bg": SURFACE,
    "fg": TEXT_PRIMARY,
    "selectbackground": SELECTION_FILL,
    "selectforeground": SELECTION_TEXT,
    "activestyle": "none",
    "relief": "flat",
    "borderwidth": 0,
    "highlightthickness": 1,
    "highlightbackground": BORDER,
    "highlightcolor": BORDER,
    "font": (FONT_FAMILY_MONO, 10),
    "exportselection": False,
}


# ── 표 데이터 셀: 왜 CTkLabel이 아니라 tk.Label인가 ────────────────────────
#
# 실측(이 PC 기준):
#   순수 tk.Label     200개:      21 ms
#   CTkLabel(일반 프레임 안)  200개:    100 ms
#   CTkLabel(CTkScrollableFrame 안) 200개: 1,645 ms   ← 개당 8ms
#
# CTkLabel 하나는 내부적으로 캔버스 1개 + tkinter.Label 1개를 만들고
# 매번 둥근 사각형을 다시 그린다. 일반 프레임 안에서도 순수 tk.Label보다
# 5배 느리지만(200개=100ms), CTkScrollableFrame 안에서는 스크롤 영역 재계산이
# 겹쳐 개당 8ms까지 치솟는다 — 최대주주처럼 20행×6열=120개짜리 표면
# 화면 갱신 한 번에 메인 스레드가 거의 1초 멈춘다.
#
# 그래서 반복되는 행/열 루프로 찍어내는 "표 셀"만 tk.Label로 내린다.
# 제목·상태 메시지·표 헤더처럼 화면에 몇 개 안 되고 반복 렌더링되지
# 않는 위젯은 그대로 CTkLabel을 쓴다 — 비용이 무의미하기 때문이다.
#
# 문제는 tk.Label이 CTkLabel과 색·글꼴 지정 방식이 달라서(fg_color vs bg,
# text_color vs fg, CTkFont 객체 vs tk 폰트 튜플) 그냥 옮기면 어긋난다는
# 것. 아래 상수들은 이론(테마 JSON)이 아니라, 실제로 만들어진 CTkLabel의
# 내부 tkinter.Label에서 cget()으로 읽어낸 값을 그대로 박아 넣은 것이다
# (자세한 측정 과정은 .superpowers/sdd/gui-perf-report.md "표 셀 위젯
# 교체" 절 참고). 다음에 이 파일을 고치는 사람은 "tk.Label을 왜 안
# CTkLabel로 통일하지?"라고 묻기 전에 위 숫자부터 다시 재보길 바란다.

# CTkFont() 기본값(볼드 아님, 13px)이 customtkinter 내부에서
# _apply_font_scaling()을 거쳐 최종적으로 tkinter.Label에 넘어가는
# (family, size, style) 3-튜플 그대로다. widget_scaling=1.0(이 앱은
# scaling을 건드리지 않는다)일 때와 글자 그대로 같다. apply_theme()에서
# 기본 글꼴 family를 FONT_FAMILY로 바꿔치기했으므로, 라이트 팔레트로
# 옮기며 다시 실측해 family만 "Segoe UI"로 갱신했다(크기·스타일은 그대로).
TABLE_CELL_FONT = ("Segoe UI", -13, "normal roman  ")

# CTkLabel 기본 text_color 테마값(라이트/다크 튜플)의 라이트 쪽. 명시적으로
# text_color를 지정하지 않는 셀(예: capital.py의 발행일·발행형태 칸)은
# TEXT_PRIMARY 같은 임의값이 아니라 이 tk 색이름이어야 CTkLabel과 색이
# 정확히 같아진다(cget()으로 실측).
TABLE_CELL_DEFAULT_FG = "gray10"

# (예전엔 여기에 TABLE_CELL_BG_TRANSPARENT_SCROLL / TABLE_CELL_BG_DEFAULT_SCROLL
# 두 상수가 있었다 — CTkScrollableFrame을 만드는 방식(fg_color="transparent"로
# 만드는지, 기본값으로 만드는지)에 따라 스크롤 표 배경이 SURFACE와 "gray86"
# 두 가지로 갈라졌기 때문이다(analysis/equity.py만 후자라 다른 3개 탭과
# 표 배경 톤이 살짝 달랐다). 아래 ScrollFrame으로 스크롤 컨테이너를 직접
# 구현하면서 배경을 SURFACE 하나로 통일했으므로 이제 이 구분이 필요 없다
# — 표 셀은 그냥 SURFACE(또는 zebra_bg가 주는 SURFACE/ROW_STRIPE)를 쓴다.)

# CTkLabel의 기본 height(모든 셀 호출부가 height= 를 안 주므로 실제로 쓰인
# 값). tk.Label은 같은 텍스트라도 자기 폰트 높이만큼만 차지해 그대로 두면
# 행이 눌린 것처럼 얇아진다 — grid_rowconfigure(minsize=...)로 행 높이를
# 강제해 세로 간격을 그대로 유지한다.
TABLE_ROW_MINSIZE = 28


def table_cell(parent, text, *, bg, fg=TABLE_CELL_DEFAULT_FG, anchor="w", **grid_kwargs):
    """표 데이터 셀 하나를 tk.Label로 만들어 grid까지 배치하고 돌려준다.

    CTkLabel(width=..., anchor=...)은 위젯 자체를 고정 픽셀 폭·28px 높이로
    그려 anchor로 그 안에서 글자 위치를 잡았다. tk.Label의 width/height는
    문자·줄 단위라 그대로 옮기면 어긋난다 — 대신 폭 지정은 같은 열의 헤더
    CTkLabel(그대로 유지)에 맡기고, 여기서는 sticky=anchor로 헤더가 잡아준
    열 폭 안에서 같은 가장자리에 붙이고, 행 높이는 grid_rowconfigure로
    직접 고정한다.
    """
    row = grid_kwargs.get("row")
    if row is not None:
        # CTkLabel은 pady와 별개로 그 자체가 28px였다 — 행 전체 높이는
        # 28 + pady*2 였다는 뜻이다. tk.Label은 폰트 높이만큼만 차지하므로
        # 같은 pady를 줘도 행이 얇아진다. minsize에 그 pady를 더해 보정한다.
        pady = grid_kwargs.get("pady", 0)
        pady = pady if isinstance(pady, int) else max(pady)
        parent.grid_rowconfigure(row, minsize=TABLE_ROW_MINSIZE + 2 * pady)
    lbl = tk.Label(
        parent, text=text, bg=bg, fg=fg, font=TABLE_CELL_FONT,
        anchor=anchor, bd=0, highlightthickness=0, padx=0, pady=0,
    )
    # sticky="ew"(기본값)로 열이 grid_columnconfigure(weight=...)를 받아
    # 넓어졌을 때도 이 셀이 그 폭을 꽉 채운다 — 안 그러면 열은 넓어져도
    # 셀(과 zebra_bg 배경)은 옛 폭에 머물러 줄무늬 오른쪽에 빈 틈이 생긴다.
    # 글자 위치는 anchor가 그대로 맡는다(가운데 문자열이 아니라 왼쪽/오른쪽
    # 정렬 그대로). 호출측이 sticky를 직접 넘기면 그 값이 우선한다.
    grid_kwargs.setdefault("sticky", "ew")
    lbl.grid(**grid_kwargs)
    return lbl


# ── 표 헤더 셀 / 줄무늬 / 구분선 ────────────────────────────────────────────
#
# 데이터 셀과 달리 헤더 셀은 표 하나에 열 개수만큼(보통 4~7개)만 만들어져
# 반복 렌더링 비용이 없다 — 그래서 여기는 tk.Label로 내리지 않고 그대로
# CTkLabel을 쓴다. Activity Monitor의 헤더 바("App Name", "Energy Impact"
# 같은 열 이름 줄)처럼 데이터보다 한 톤 옅고 작게 잡아, 굵은 헤더가 데이터를
# 누르지 않게 한다.
TABLE_HEADER_BG = HEADER_FILL
# (family, size) 2-튜플까지만 쓴다. TABLE_CELL_FONT처럼 스타일까지 넣은
# 3-튜플을 CTkLabel에 넘기면 customtkinter의 _apply_font_scaling()이
# 3번째 원소를 font[2:]로 슬라이스해 통째로 다시 튜플에 담아버려
# ("normal roman  ",)처럼 중첩 튜플이 되고, 그걸 그대로 tkinter.Label에
# 넘기면 "unknown font style" 예외가 난다(tk.Label에 직접 넘길 때는
# 이 스케일링 단계를 안 거치므로 문제없다 — table_cell이 3-튜플을 쓰는
# 이유). 헤더는 볼드가 필요 없으니 2-튜플로 그 버그를 원천적으로 피한다.
TABLE_HEADER_FONT = ("Segoe UI", -11)


def table_header(parent, text, *, anchor="w", width=None, **grid_kwargs):
    """표 열 헤더 한 칸을 tk.Label로 만들어 grid까지 배치하고 돌려준다.

    호출측이 넘긴 padx는 grid 바깥 여백이 아니라 라벨 안쪽 패딩으로 옮긴다 —
    헤더 배경(TABLE_HEADER_BG)이 바탕색과 다르므로 바깥 여백을 두면 칸 사이가
    끊겨 조각난 칩처럼 보인다. 안쪽 패딩이면 글자 위치는 같고 칸끼리 맞닿아
    띠 하나로 이어진다. (CTkLabel은 안쪽 패딩을 지원하지 않아 tk.Label을 쓴다.)

    width를 주면 열 폭을 픽셀로 고정한다(표 데이터 셀은 대개 폭을 직접
    잡지 않고 같은 열의 헤더가 잡아 준 폭 안에서 sticky=anchor로 정렬만
    맞춘다 — table_cell 참고). tk.Label의 width는 글자 수 단위라 열의
    grid minsize로 대신 잡는다.
    """
    padx = grid_kwargs.pop("padx", 0)
    if isinstance(padx, int):
        padx = (padx, padx)
    # tk.Label의 padx는 좌우 대칭이라 (0, 8) 같은 비대칭 여백을 못 준다.
    # 배경색 프레임 안에 라벨을 pack(padx=(l, r))으로 넣으면 여백 자리도
    # 같은 색으로 칠해지면서 글자 위치는 호출측이 준 그대로 유지된다.
    box = tk.Frame(parent, bg=TABLE_HEADER_BG, bd=0, highlightthickness=0)
    lbl = tk.Label(
        box, text=text, bg=TABLE_HEADER_BG, fg=HEADER_TEXT,
        font=TABLE_HEADER_FONT, anchor=anchor, bd=0, highlightthickness=0,
        padx=0, pady=2,
    )
    lbl.pack(fill="x", padx=padx)
    if width is not None and "column" in grid_kwargs:
        parent.grid_columnconfigure(grid_kwargs["column"], minsize=width)
    # table_cell과 같은 이유로 sticky 기본값을 "ew"로 둔다 — 열이 넓어지면
    # 헤더 배경(TABLE_HEADER_BG)도 그 폭을 꽉 채워야 데이터 행 줄무늬와
    # 오른쪽 경계가 어긋나 보이지 않는다.
    grid_kwargs.setdefault("sticky", "ew")
    box.grid(padx=0, **grid_kwargs)
    return lbl


def zebra_bg(row_index, base=SURFACE, stripe=ROW_STRIPE):
    """표 행 배경을 얼룩무늬(zebra)로 돌려준다. 짝수 행은 표 바탕색(base),
    홀수 행은 한 단계 어두운 줄무늬색(stripe)이다. table_cell(bg=...)에
    그대로 넘기면 된다.
    """
    return base if row_index % 2 == 0 else stripe


def table_separator(parent, **grid_kwargs):
    """표 안 헤어라인 구분선 한 칸을 만들어 grid까지 배치하고 돌려준다.

    가로선(헤더 밑줄 등)은 sticky="ew", 세로선(열 사이 구분)은 sticky="ns"로
    호출측에서 지정한다 — 방향에 맞춰 두께 1px을 폭/높이 중 알맞은 쪽에
    준다. sticky를 안 넘기면 가로선("ew")으로 취급한다(grid_kwargs.
    setdefault로 실제 grid() 호출에도 같은 기본값이 들어가게 한다 —
    두께 판단에만 쓰고 grid에는 안 넘기면 sticky 없이 배치돼 선이 안
    늘어나는 버그가 난다).
    """
    grid_kwargs.setdefault("sticky", "ew")
    sticky = grid_kwargs["sticky"]
    sep = ctk.CTkFrame(parent, fg_color=BORDER, corner_radius=0)
    if "n" in sticky or "s" in sticky:
        sep.configure(width=1)
    else:
        sep.configure(height=1)
    sep.grid(**grid_kwargs)
    return sep


# ── 표 전체를 캔버스 한 장에 그리는 Table ────────────────────────────────────
#
# 실측(이 PC 기준): Tk 위젯 하나를 화면에 붙이는 데 5~10ms가 걸린다.
# 글꼴·색과 무관하고, Tk를 거치지 않은 순수 Win32 자식창 생성도 개당 5ms였다
# — 위젯(=HWND) 개수 자체가 비용이다. 셀마다 tk.Label을 만들면 핵심재무
# (6행×4열, 헤더·구분선 포함 약 40개)만으로 4.9초가 걸렸다.
#
# 그래서 표 하나를 tk.Canvas 한 장(창 1개)에 create_rectangle/create_text로
# 그린다. 캔버스 아이템은 창이 아니라서 수백 개를 그려도 수십 ms다.
# 헤더 띠·줄무늬·구분선·셀별 글자색(음수 빨강, 지분율 구간색)은 라벨 방식
# 그대로 지원한다. 열 폭은 "제목·내용 중 가장 넓은 것"과 minsize 중 큰 쪽을
# 바닥으로 잡고, 캔버스가 그보다 넓어지면 weight 비율로 남는 폭을 나눠 준다
# (grid_columnconfigure(weight, minsize)와 같은 규칙).
TABLE_HEADER_H = 30      # 헤더 띠 높이(예전 헤더 라벨 22px + pady 4×2)
TABLE_ROW_H = 32         # 데이터 행 높이
TABLE_SEP_H = 5          # 구분선 칸 높이(선 1px + 위아래 2px)
TABLE_PADX = 6           # 셀 안쪽 좌우 여백


class Table(tk.Canvas):
    """표 하나를 캔버스 한 장에 그린다.

    columns: [(제목, anchor, weight, minsize), ...]  anchor는 "w"/"e"/"center".
    add_row(cells)의 cells는 열마다 문자열 또는 (문자열, 글자색) 튜플.
    add_separator()는 헤어라인 구분선 한 줄. 다 넣은 뒤 draw()를 부르고
    grid()로 배치한다. 부모가 준 폭이 자연 폭보다 넓으면 <Configure>에서
    weight 열을 늘려 다시 그린다.
    """

    def __init__(self, parent, columns, *, row_height=TABLE_ROW_H, zebra=True, **kw):
        kw.setdefault("bg", SURFACE)
        super().__init__(parent, bd=0, highlightthickness=0, **kw)
        self._cols = list(columns)
        self._rows = []            # ("row", [(text, fg), ...], bg) | ("sep",)
        self._row_h = row_height
        self._zebra = zebra
        self._n_data = 0
        self._cell_font = tkfont.Font(family=FONT_FAMILY, size=-13)
        self._hdr_font = tkfont.Font(family=FONT_FAMILY, size=-12)
        self._drawn_width = None
        self.bind("<Configure>", self._on_configure)

    # ── 내용 넣기 ──
    def add_row(self, cells, *, bg=None, fg=None):
        norm = []
        for c in cells:
            if isinstance(c, tuple):
                text, color = c
            else:
                text, color = c, None
            norm.append(("" if text is None else str(text), color or fg or TEXT_PRIMARY))
        if bg is None:
            bg = zebra_bg(self._n_data) if self._zebra else SURFACE
        self._rows.append(("row", norm, bg))
        self._n_data += 1

    def add_separator(self):
        self._rows.append(("sep",))

    # ── 크기 계산 ──
    def _natural_widths(self):
        widths = []
        for ci, (title, _anchor, _weight, minsize) in enumerate(self._cols):
            w = self._hdr_font.measure(title)
            for r in self._rows:
                if r[0] == "row" and ci < len(r[1]):
                    w = max(w, self._cell_font.measure(r[1][ci][0]))
            widths.append(max(w + 2 * TABLE_PADX, minsize))
        return widths

    def _content_height(self):
        h = TABLE_HEADER_H + TABLE_SEP_H
        for r in self._rows:
            h += self._row_h if r[0] == "row" else TABLE_SEP_H
        return h

    def draw(self):
        """자연 폭·높이로 캔버스 크기를 잡고 한 번 그린다."""
        nat = self._natural_widths()
        self.configure(width=sum(nat), height=self._content_height())
        self._render(nat)
        self._drawn_width = None      # 첫 <Configure>에서 실제 폭으로 다시 그린다

    def _on_configure(self, event):
        if event.width == self._drawn_width:
            return
        self._drawn_width = event.width
        nat = self._natural_widths()
        extra = event.width - sum(nat)
        total_weight = sum(c[2] for c in self._cols)
        if extra > 0 and total_weight:
            widths = [w + extra * c[2] / total_weight for w, c in zip(nat, self._cols)]
        else:
            widths = nat
        self._render(widths)

    # ── 그리기 ──
    def _render(self, widths):
        self.delete("all")
        total_w = max(sum(widths), self.winfo_width())
        xs = [0]
        for w in widths:
            xs.append(xs[-1] + w)

        def put_text(ci, y_mid, text, fill, font):
            anchor = self._cols[ci][1]
            if anchor == "e":
                self.create_text(xs[ci + 1] - TABLE_PADX, y_mid, text=text, fill=fill, font=font, anchor="e")
            elif anchor == "center":
                self.create_text((xs[ci] + xs[ci + 1]) / 2, y_mid, text=text, fill=fill, font=font, anchor="center")
            else:
                self.create_text(xs[ci] + TABLE_PADX, y_mid, text=text, fill=fill, font=font, anchor="w")

        y = 0
        self.create_rectangle(0, 0, total_w, TABLE_HEADER_H, fill=HEADER_FILL, outline="")
        for ci, (title, *_rest) in enumerate(self._cols):
            put_text(ci, TABLE_HEADER_H / 2, title, HEADER_TEXT, self._hdr_font)
        y += TABLE_HEADER_H
        self.create_line(0, y + 2, total_w, y + 2, fill=BORDER)
        y += TABLE_SEP_H

        for r in self._rows:
            if r[0] == "sep":
                self.create_line(0, y + 2, total_w, y + 2, fill=BORDER)
                y += TABLE_SEP_H
                continue
            _tag, cells, bg = r
            if bg != SURFACE:
                self.create_rectangle(0, y, total_w, y + self._row_h, fill=bg, outline="")
            for ci, (text, fg) in enumerate(cells[:len(self._cols)]):
                put_text(ci, y + self._row_h / 2, text, fg, self._cell_font)
            y += self._row_h


# ── 스크롤 컨테이너: CTkScrollableFrame 대체 (성능) ─────────────────────────
#
# 실측(이 PC 기준, 탭 내용이 이미 그려진 상태에서 탭만 전환): 최대주주
# (20행×5열) 833ms, 감사 382ms, 자본변동 260ms, 나머지도 200ms대. 표 셀을
# tk.Label로 내려도(위 table_cell 참고) 이 비용은 그대로였다 — 프로파일러로
# 잡아 보니 CTkScrollbar._draw()가 <Configure> 이벤트마다 다시 그려지는
# 것이 원인이었다(스크롤바 하나가 매 전환마다 스스로를 다시 그리는데,
# 그 비용이 표 크기에 비례해 늘어난다). CTkScrollableFrame 자체를 순수
# tkinter로 다시 짠 아래 ScrollFrame으로 바꿔 이 비용을 없앤다.
_SCROLLBAR_STYLE = "Light.Vertical.TScrollbar"
_scrollbar_style_ready = False


def _ensure_scrollbar_style():
    """ttk 스크롤바 스타일을 앱 생애주기 동안 한 번만 등록한다.

    Windows 기본 ttk 테마("vista"/"xpnative")는 스크롤바를 OS 네이티브
    위젯으로 그려 background/troughcolor 같은 색 옵션을 대부분 무시한다
    — 라이트 팔레트 색을 실제로 입히려면 색을 커스터마이즈할 수 있는
    "clam" 테마로 바꿔야 한다. 이 앱에서 ttk 위젯은 이 스크롤바 하나뿐이라
    (grep으로 확인) 전역 ttk 테마를 바꿔도 다른 위젯에 영향이 없다.
    """
    global _scrollbar_style_ready
    if _scrollbar_style_ready:
        return
    style = ttk.Style()
    style.theme_use("clam")
    style.configure(
        _SCROLLBAR_STYLE,
        background=BORDER, troughcolor=SURFACE, bordercolor=SURFACE,
        arrowcolor=TEXT_SECONDARY, relief="flat", arrowsize=13, width=12,
    )
    style.map(_SCROLLBAR_STYLE, background=[("active", TEXT_SECONDARY)])
    _scrollbar_style_ready = True


class ScrollFrame(tk.Frame):
    """CTkScrollableFrame을 대신하는 순수 tkinter 스크롤 컨테이너.

    tk.Canvas 위에 내용 프레임을 얹고, 내용이 넘칠 때만 스크롤바를 붙이는
    표준 레시피다. 반환되는 객체 자신이 "내용을 담는 프레임"이다 —
    지금까지 CTkScrollableFrame을 쓰던 곳과 똑같이 이 위에 자식 위젯을
    만들고 grid()하면 된다(analysis/*.py의 render()들이 `ctx.content`를
    그냥 부모 삼아 자식을 추가/파괴하는 기존 코드를 한 글자도 안 고쳐도
    되게 하기 위한 설계다). 다만 이 프레임을 부모 위젯 안에 배치하는
    grid() 호출만은, 실제로는 캔버스+스크롤바를 감싼 바깥 컨테이너
    (self._outer)에 적용되도록 오버라이드했다.

    가로 스크롤: 안쪽 프레임의 폭은 "캔버스 폭"과 "내용이 실제로 필요한
    최소 폭"(grid_columnconfigure의 minsize·실제 셀 내용이 요구하는 폭
    중 큰 쪽 — self.winfo_reqwidth())의 더 큰 값으로 잡는다(_on_canvas_
    configure). 캔버스가 더 넓으면 안쪽 프레임이 캔버스 폭까지 늘어나
    (weight를 받은 열이 늘고 줄어) 오른쪽 정렬 셀이 진짜 가장자리에
    붙는다. 반대로 창을 좁혀도 표가 최소 폭 아래로는 안 줄어들고, 그
    최소 폭이 캔버스보다 넓어지는 순간(=weight=0 열의 minsize와 실제
    셀 내용만으로도 이미 캔버스보다 넓을 때)만 가로 스크롤바가 나타나
    표를 옆으로 밀어 볼 수 있게 한다 — 화면 밖으로 조용히 잘리는 대신.
    """

    def __init__(self, parent, bg=SURFACE, **kwargs):
        _ensure_scrollbar_style()

        self._outer = tk.Frame(parent, bg=bg, highlightthickness=0, bd=0)
        self._outer.grid_columnconfigure(0, weight=1)
        self._outer.grid_rowconfigure(0, weight=1)

        self._canvas = tk.Canvas(self._outer, bg=bg, highlightthickness=0, bd=0)
        self._canvas.grid(row=0, column=0, sticky="nsew")

        self._vbar = ttk.Scrollbar(
            self._outer, orient="vertical", command=self._canvas.yview,
            style=_SCROLLBAR_STYLE,
        )
        self._vbar_visible = False
        self._canvas.configure(yscrollcommand=self._vbar.set)

        # 가로 스크롤바: 표가 최소 폭에서도 캔버스보다 넓을 때만(_sync_
        # hscrollbar) row=1에 붙는다 — 세로 스크롤바처럼 기본은 숨김이다.
        self._hbar = ttk.Scrollbar(
            self._outer, orient="horizontal", command=self._canvas.xview,
            style=_SCROLLBAR_STYLE,
        )
        self._hbar_visible = False
        self._canvas.configure(xscrollcommand=self._hbar.set)

        kwargs.setdefault("bg", bg)
        super().__init__(self._canvas, **kwargs)
        self._window_id = self._canvas.create_window((0, 0), window=self, anchor="nw")

        self.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        # 마우스 휠: 포인터가 이 캔버스 위에 있는 동안만 전역으로 휠을
        # 받고, 벗어나면 즉시 풀어준다 — 다른 스크롤 영역(다른 탭이나
        # 좌측 패널 목록창) 위에서 휠을 굴렸을 때 이 컨테이너까지 같이
        # 움직이는 사고를 막는다(전역 bind_all을 상시로 걸어 두는 것이
        # 흔한 버그라 여기서는 Enter/Leave에 걸어 뒀다 뗐다 한다).
        self._canvas.bind("<Enter>", self._on_canvas_enter)
        self._canvas.bind("<Leave>", self._on_canvas_leave)

    # ── 배치: 실제로는 바깥 컨테이너(캔버스+스크롤바)를 옮긴다 ──
    def grid(self, **kwargs):
        self._outer.grid(**kwargs)

    def grid_forget(self):
        self._outer.grid_forget()

    def grid_remove(self):
        self._outer.grid_remove()

    # ── 내부 동작 ──
    def _on_canvas_enter(self, _event=None):
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_canvas_leave(self, _event=None):
        self._canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _bind_wheel(self, widget):
        """자식 위젯 전체에도 같은 휠 핸들러를 개별 바인딩한다.

        Enter/Leave 크로싱 이벤트는 캔버스 → 자식 위젯 경계를 넘어갈
        때도 발생한다(부모/자식 전환도 하나의 크로싱으로 잡힌다) — 그래서
        위 Enter/Leave만으로는 표 안 라벨 위에 커서가 있을 때 bind_all이
        풀려 휠이 안 먹는 경우가 실측으로 확인됐다. 자식마다 직접 같은
        핸들러를 걸어, 컨테이너 안 어느 위젯 위에 있든 이 스크롤 영역이
        움직이게 한다(다른 컨테이너까지 같이 움직이지는 않는다 — 바인딩이
        위젯별로 국한되어 있으므로).
        """
        widget.bind("<MouseWheel>", self._on_mousewheel)
        for child in widget.winfo_children():
            self._bind_wheel(child)

    def _on_inner_configure(self, _event=None):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        self._sync_vscrollbar()
        self._bind_wheel(self)

    def _on_canvas_configure(self, event):
        # 안쪽 프레임 폭 = max(캔버스 폭, 내용이 실제로 필요한 최소 폭).
        # self.winfo_reqwidth()는 self의 grid 자식들(표 프레임 f/sub 등)이
        # grid_columnconfigure(minsize=...)·실제 셀 내용으로 요구하는
        # "자연스러운" 최소 폭이다 — 이 값은 캔버스 아이템에 폭을 강제로
        # 줬던 과거 호출과 무관하게 항상 자식 기준으로 다시 계산된다
        # (self는 canvas.create_window로 배치되어 place처럼 외부에서 크기가
        # 정해지지만, self 내부의 grid_propagate는 그대로 켜져 있어
        # winfo_reqwidth()는 이 시점의 자식 요구 폭을 그대로 돌려준다).
        self.update_idletasks()
        min_w = self.winfo_reqwidth()
        width = max(event.width, min_w)
        self._canvas.itemconfigure(self._window_id, width=width)
        self._sync_vscrollbar()
        self._sync_hscrollbar(need=min_w > event.width)

    def _sync_vscrollbar(self):
        """내용이 세로로 넘칠 때만 세로 스크롤바를 붙이고, 아니면 뗀다.

        grid()/grid_forget()는 표시 상태가 실제로 바뀔 때만 부른다
        (self._vbar_visible로 판단). 무조건 매번 토글하면 스크롤바
        유무가 캔버스 크기를 바꾸고, 그게 다시 <Configure>를 불러 크기가
        바뀌고 또 유무 판단이 바뀌는 무한 루프(레이아웃 지터)에 빠진다.
        """
        self._canvas.update_idletasks()
        bbox = self._canvas.bbox("all")
        content_h = (bbox[3] - bbox[1]) if bbox else 0
        need = content_h > self._canvas.winfo_height()
        if need and not self._vbar_visible:
            self._vbar.grid(row=0, column=1, sticky="ns")
            self._vbar_visible = True
        elif not need and self._vbar_visible:
            self._vbar.grid_forget()
            self._vbar_visible = False

    def _sync_hscrollbar(self, need):
        """표가 최소 폭에서도 캔버스보다 넓을 때만(need) 가로 스크롤바를
        붙인다 — _sync_vscrollbar와 같은 이유로 표시 상태가 바뀔 때만
        grid()/grid_forget()를 부른다. 이 조건을 만족하는 탭이 실제로는
        거의 없다(아주 좁은 창에서만 닿는 탭이 있을 수 있다) — 그래서
        대부분의 탭에서는 이 스크롤바가 한 번도 나타나지 않는다.
        """
        if need and not self._hbar_visible:
            self._hbar.grid(row=1, column=0, sticky="ew")
            self._hbar_visible = True
        elif not need and self._hbar_visible:
            self._hbar.grid_forget()
            self._hbar_visible = False


def fmt_val(val):
    """금액 포맷 + 색상. (표시문자열, 텍스트 색상) 반환."""
    if val is None:
        return "N/A", TEXT_SECONDARY
    trillion = 1_000_000_000_000
    billion  = 100_000_000
    abs_val  = abs(val)
    if abs_val >= trillion:
        s = f"{abs_val / trillion:.2f}조"
    elif abs_val >= billion:
        s = f"{abs_val / billion:.0f}억"
    else:
        s = f"{abs_val:,}원"
    if val < 0:
        return f"-{s}", NEGATIVE
    return s, TEXT_PRIMARY


def fmt_div_val(val, key):
    """배당 항목별 포맷 + 색상. (표시문자열, 텍스트 색상) 반환."""
    if val is None:
        return "N/A", TEXT_SECONDARY
    if "%" in key:
        color = NEGATIVE if val < 0 else TEXT_PRIMARY
        return f"{val:.2f}%", color
    if "백만원" in key:
        return fmt_val(int(val) * 1_000_000)   # 백만원→원 변환 후 조/억 표시
    return f"{int(val):,}원", TEXT_PRIMARY


def fmt_ratio_val(val):
    """재무비율 포맷 + 색상. (표시문자열, 텍스트 색상) 반환."""
    if val is None:
        return "N/A", TEXT_SECONDARY
    color = NEGATIVE if val < 0 else TEXT_PRIMARY
    return f"{val:.2f}%", color
