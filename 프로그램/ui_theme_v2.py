"""peer_wacc v2 / dart_fs를 참고한 별도 GUI 테마."""
import ctypes
import sys
import tkinter.font as tkfont
from ctypes import wintypes

import customtkinter as ctk

BG = ('#F1F3F5', '#20252D')
SURFACE = ('#FAFBFC', '#292F39')
SOFT = ('#EBEEF2', '#242A33')
LINE = ('#D8DFE7', '#3D4654')
TEXT = ('#2B3442', '#D7DCE3')
MUTED = ('#6D7786', '#A1AAB7')
ACCENT = ('#46668C', '#92ACCF')
ACCENT_HOVER = ('#395779', '#A6BCDA')
ACCENT_TEXT = ('#FAFBFC', '#202B3A')
SELECT = ('#E5EBF3', '#35465C')
DANGER = ('#A94F4F', '#DBA0A0')
FONT = '맑은 고딕'


def color(value):
    return value[ctk.get_appearance_mode().lower() == 'dark'] if isinstance(value, tuple) else value


def apply_theme():
    ctk.set_appearance_mode('light')
    ctk.set_default_color_theme('blue')
    theme = ctk.ThemeManager.theme
    theme['CTkFont'].update(family=FONT, size=13)
    theme['CTkLabel'].update(text_color=TEXT)
    theme['CTkFrame'].update(fg_color=SURFACE, border_color=LINE, corner_radius=12)
    theme['CTkEntry'].update(fg_color=SURFACE, text_color=TEXT, border_color=LINE,
                            placeholder_text_color=MUTED, corner_radius=7, border_width=1)
    theme['CTkButton'].update(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT,
                             corner_radius=7, border_width=0)
    theme['CTkCheckBox'].update(fg_color=ACCENT, hover_color=ACCENT_HOVER,
                               text_color=TEXT, border_color=MUTED, checkmark_color=ACCENT_TEXT)
    theme['CTkSwitch'].update(progress_color=ACCENT, text_color=MUTED)
    theme['CTkTextbox'].update(text_color=TEXT, fg_color=SOFT)


def pick_font(window):
    global FONT
    families = set(tkfont.families(window))
    FONT = next((f for f in ('Pretendard', 'Noto Sans KR', '맑은 고딕', 'Segoe UI') if f in families), FONT)
    ctk.ThemeManager.theme['CTkFont']['family'] = FONT


def refresh_native(app,palette=None):
    resolve=palette or color
    style = app.style
    if style.theme_use()!='clam':
        style.theme_use('clam')
    scale = app.tree.master._get_widget_scaling()
    style.configure('KftcV2.Treeview', background=resolve(SURFACE), fieldbackground=resolve(SURFACE),
                    foreground=resolve(TEXT), borderwidth=0, relief='flat', bordercolor=resolve(SURFACE),
                    lightcolor=resolve(SURFACE), darkcolor=resolve(SURFACE),
                    rowheight=round(34 * scale), font=(FONT, -round(13 * scale)))
    style.configure('KftcV2.Treeview.Heading', background=resolve(SOFT), foreground=resolve(MUTED),
                    font=(FONT, -round(12 * scale), 'bold'), relief='flat', borderwidth=0,
                    padding=(8, round(9 * scale)))
    style.map('KftcV2.Treeview', background=[('selected', resolve(SELECT))],
              foreground=[('selected', resolve(TEXT))])
    style.map('KftcV2.Treeview.Heading', background=[('active', resolve(SELECT))])
    for orientation in ('Vertical', 'Horizontal'):
        style.configure('KftcV2.' + orientation + '.TScrollbar', background=resolve(LINE),
                        troughcolor=resolve(SURFACE), bordercolor=resolve(SURFACE),
                        arrowcolor=resolve(MUTED), lightcolor=resolve(LINE), darkcolor=resolve(LINE))
    app.tree.tag_configure('stripe', background=resolve(SOFT))
    titlebar(app,palette=resolve)


def titlebar(window,palette=None):
    resolve=palette or color
    if sys.platform != 'win32':
        return
    try:
        user32 = ctypes.WinDLL('user32')
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        hwnd = user32.GetAncestor(window.winfo_id(), 2)
        dwm = ctypes.WinDLL('dwmapi')
        dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        for attr, value in ((35, BG), (36, TEXT), (34, LINE)):
            rgb = resolve(value).lstrip('#')
            ref = wintypes.DWORD(int(rgb[4:6] + rgb[2:4] + rgb[0:2], 16))
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(ref), ctypes.sizeof(ref))
    except (OSError, AttributeError):
        pass
