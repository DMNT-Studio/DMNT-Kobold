"""Schmale Windows-Helfer per ctypes. Keine Hooks, keine Tasteninhalte.

- ``letzte_eingabe_ms``: Zeitpunkt der letzten Eingabe (GetLastInputInfo) –
  sagt nur „irgendwas wurde gedrückt/bewegt“, nicht was.
- ``maustaste_gedrueckt``: nur die Maustasten (zur Unterscheidung Maus/Tastatur).
- ``vordergrund_programm``: Prozessname (+ Fenstertitel, wird nie geloggt).
Auf anderen Systemen liefern alle Funktionen neutrale Werte.
"""
from __future__ import annotations

import ctypes
import os
import sys

IST_WINDOWS = sys.platform == "win32"

if IST_WINDOWS:
    import ctypes.wintypes as wt

    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32

    class _LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]

    _user32.GetForegroundWindow.restype = wt.HWND
    _user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wt.DWORD
    _user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    _user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, wt.UINT]
    _user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    _user32.GetAsyncKeyState.restype = ctypes.c_short
    _kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    _kernel32.OpenProcess.restype = wt.HANDLE
    _kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR,
                                                     ctypes.POINTER(wt.DWORD)]
    _kernel32.CloseHandle.argtypes = [wt.HANDLE]
    _kernel32.GetTickCount.restype = wt.DWORD

    _HWND_TOPMOST = wt.HWND(-1)
    _SWP = 0x0001 | 0x0002 | 0x0010 | 0x0200  # NOSIZE | NOMOVE | NOACTIVATE | NOOWNERZORDER
    _MAUSTASTEN = (0x01, 0x02, 0x04, 0x05, 0x06)

    def letzte_eingabe_ms() -> int:
        info = _LASTINPUTINFO(ctypes.sizeof(_LASTINPUTINFO), 0)
        _user32.GetLastInputInfo(ctypes.byref(info))
        return int(info.dwTime)

    def leerlauf_s() -> float:
        return ((_kernel32.GetTickCount() - letzte_eingabe_ms()) & 0xFFFFFFFF) / 1000.0

    def maustaste_gedrueckt() -> bool:
        return any(_user32.GetAsyncKeyState(vk) & 0x8000 for vk in _MAUSTASTEN)

    def vordergrund_programm() -> tuple[str, str, int] | None:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = wt.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        titel = ctypes.create_unicode_buffer(256)
        _user32.GetWindowTextW(hwnd, titel, 256)
        name = ""
        h = _kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if h:
            try:
                puffer = ctypes.create_unicode_buffer(1024)
                groesse = wt.DWORD(1024)
                if _kernel32.QueryFullProcessImageNameW(h, 0, puffer, ctypes.byref(groesse)):
                    name = os.path.basename(puffer.value).lower()
            finally:
                _kernel32.CloseHandle(h)
        return name, titel.value, int(pid.value)

    def ganz_nach_vorne(hwnd: int) -> None:
        _user32.SetWindowPos(wt.HWND(hwnd), _HWND_TOPMOST, 0, 0, 0, 0, _SWP)

else:
    def letzte_eingabe_ms() -> int:
        return 0

    def leerlauf_s() -> float:
        return 0.0

    def maustaste_gedrueckt() -> bool:
        return False

    def vordergrund_programm() -> tuple[str, str, int] | None:
        return None

    def ganz_nach_vorne(hwnd: int) -> None:
        pass
