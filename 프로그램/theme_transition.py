"""현재 위젯을 유지하고 색만 짧게 보간하여 테마 전환의 번쩍임을 줄인다."""
import time
import tkinter as tk
import customtkinter as ctk
import ui_theme_v2 as theme


COLOR_OPTIONS=('fg_color','bg_color','border_color','text_color','text_color_disabled',
    'placeholder_text_color','hover_color','button_color','button_hover_color','progress_color',
    'checkmark_color','dropdown_fg_color','dropdown_hover_color','dropdown_text_color',
    'selected_color','selected_hover_color','unselected_color','unselected_hover_color')


class ThemeTransition:
    def __init__(self,app,duration=.22):
        self.app=app
        self.duration=duration
        self.running=False
        self.timer=None
        self.originals={}
        self.native={}
        self.rgb_cache={}

    def _rgb(self,value):
        if value not in self.rgb_cache:
            self.rgb_cache[value]=tuple(v//257 for v in self.app.winfo_rgb(value))
        return self.rgb_cache[value]

    def _mix(self,a,b,t):
        first,last=self._rgb(a),self._rgb(b)
        return '#'+''.join(f'{round(x+(y-x)*t):02x}' for x,y in zip(first,last))

    def _widgets(self,parent):
        yield parent
        for child in parent.winfo_children():
            yield from self._widgets(child)

    def start(self,mode):
        if self.timer:
            self.app.after_cancel(self.timer);self.timer=None
        old_index=int(ctk.get_appearance_mode().lower()=='dark')
        self.index=int(mode.lower()=='dark')
        self.changes=[]
        for widget in self._widgets(self.app):
            values={}
            for option in COLOR_OPTIONS:
                try:
                    current=widget.cget(option)
                except (ValueError,TypeError,tk.TclError,AttributeError):
                    continue
                key=(widget,option)
                original=self.originals.get(key,current)
                if not isinstance(original,(tuple,list)) or len(original)!=2:
                    continue
                if not all(isinstance(c,str) and c!='transparent' for c in original):
                    continue
                first=current[old_index] if isinstance(current,(tuple,list)) else current
                try:self._rgb(first);self._rgb(original[self.index])
                except (tk.TclError,TypeError):continue
                self.originals[key]=original
                values[option]=(first,original[self.index])
            if values:self.changes.append((widget,values))
        if not self.native:
            self.native={tuple(value):theme.color(value) for value in vars(theme).values()
                         if isinstance(value,tuple) and len(value)==2 and all(isinstance(c,str) and c.startswith('#') for c in value)}
        self.native_from=dict(self.native)
        self.running=True
        self._paint(0)
        ctk.set_appearance_mode(mode)
        self.started=time.monotonic()
        self.timer=self.app.after(16,self._step)

    def _paint(self,t):
        for widget,options in self.changes:
            try:
                if widget.winfo_exists():
                    widget.configure(**{key:self._mix(a,b,t) for key,(a,b) in options.items()})
            except tk.TclError:continue
        self.native={value:self._mix(start,value[self.index],t) for value,start in self.native_from.items()}
        theme.refresh_native(self.app,palette=lambda value:self.native.get(tuple(value),theme.color(value))
                             if isinstance(value,(tuple,list)) else value)

    def _step(self):
        self.timer=None
        if not self.app.winfo_exists():self.running=False;return
        position=min(1,(time.monotonic()-self.started)/self.duration)
        self._paint(position*position*(3-2*position))
        if position>=1:
            self.cancel()
            return
        self.timer=self.app.after(16,self._step)

    def cancel(self):
        if self.timer:
            self.app.after_cancel(self.timer);self.timer=None
        grouped={}
        for (widget,option),value in self.originals.items():
            grouped.setdefault(widget,{})[option]=value
        for widget,values in grouped.items():
            try:
                if widget.winfo_exists():widget.configure(**values)
            except tk.TclError:continue
        self.originals={}
        self.native={}
        self.running=False
        if self.app.winfo_exists():theme.refresh_native(self.app)
