"""Schmale Windows-Helfer per ctypes. Keine Hooks, keine Tasteninhalte.

- ``letzte_eingabe_ms``: Zeitpunkt der letzten Eingabe (GetLastInputInfo) –
  sagt nur „irgendwas wurde gedrückt/bewegt“, nicht was.
- ``maustaste_gedrueckt``: nur die Maustasten (zur Unterscheidung Maus/Tastatur).
- ``vordergrund_programm``: Prozessname (+ Fenstertitel, wird nie geloggt).
- ``laufende_programme``: Namen aller laufenden Prozesse (Toolhelp-Snapshot).
- ``Pegelmesser``: Lautstärkepegel des Standard-Ausgabegeräts (wie die Anzeige im
  Lautstärkemixer) – nur „wie laut“, nie was.
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

    _user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_void_p]
    _user32.SetWindowLongPtrW.restype = ctypes.c_void_p

    def besitzer_setzen(hwnd: int, besitzer: int | None) -> None:
        """Besitzer-Fenster setzen (GWLP_HWNDPARENT): ein besessenes Fenster liegt
        immer vor seinem Besitzer – so bleibt der Avatar vor der Einrichten-Bühne."""
        _user32.SetWindowLongPtrW(wt.HWND(hwnd), -8, ctypes.c_void_p(besitzer or 0))

    class _PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wt.DWORD),
                    ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]

    _kernel32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    _kernel32.CreateToolhelp32Snapshot.restype = wt.HANDLE
    _kernel32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
    _kernel32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]

    def laufende_programme() -> set[str]:
        namen: set[str] = set()
        h = _kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
        if not h or h == wt.HANDLE(-1).value:
            return namen
        try:
            e = _PROCESSENTRY32W()
            e.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
            ok = _kernel32.Process32FirstW(h, ctypes.byref(e))
            while ok:
                namen.add(e.szExeFile.lower())
                ok = _kernel32.Process32NextW(h, ctypes.byref(e))
        finally:
            _kernel32.CloseHandle(h)
        return namen

    # --- Pegel des Ausgabegeräts (Core Audio, IAudioMeterInformation) ----------
    class _GUID(ctypes.Structure):
        _fields_ = [("d1", wt.DWORD), ("d2", wt.WORD), ("d3", wt.WORD), ("d4", ctypes.c_ubyte * 8)]

    _ole32 = ctypes.WinDLL("ole32")
    _ole32.CLSIDFromString.argtypes = [wt.LPCWSTR, ctypes.POINTER(_GUID)]
    _ole32.CoCreateInstance.argtypes = [ctypes.POINTER(_GUID), ctypes.c_void_p, wt.DWORD,
                                        ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
    _ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wt.DWORD]

    def _guid(text: str) -> _GUID:
        g = _GUID()
        _ole32.CLSIDFromString(text, ctypes.byref(g))
        return g

    _CLSID_ENUM = _guid("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
    _IID_ENUM = _guid("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
    _IID_METER = _guid("{C02216F6-8C67-4B5B-9D00-D008E73E0064}")

    def _methode(obj: int, index: int, *argtypes):
        vtabelle = ctypes.cast(ctypes.c_void_p(obj), ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
        return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(vtabelle[index])

    def _freigeben(obj: int | None) -> None:
        if obj:
            _methode(obj, 2)(obj)  # IUnknown::Release

    class Pegelmesser:
        """Spitzenpegel 0..1 des Standard-Wiedergabegeräts. Wechselt das Gerät
        (Headset ein/aus), wird alle 30 s und nach Fehlern neu verbunden."""

        NEU_VERBINDEN_S = 30.0

        def __init__(self) -> None:
            _ole32.CoInitializeEx(None, 0x2)   # STA; Qt hat COM meist schon gestartet
            self._meter: int | None = None
            self._alter = 0.0
            self._erster = True

        def _verbinden(self) -> None:
            self.schliessen()
            enum = ctypes.c_void_p()
            if _ole32.CoCreateInstance(ctypes.byref(_CLSID_ENUM), None, 0x17, ctypes.byref(_IID_ENUM),
                                       ctypes.byref(enum)) != 0 or not enum.value:
                return
            geraet = ctypes.c_void_p()
            try:
                # IMMDeviceEnumerator::GetDefaultAudioEndpoint(eRender=0, eMultimedia=1, **IMMDevice)
                if _methode(enum.value, 4, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))(
                        enum.value, 0, 1, ctypes.byref(geraet)) != 0 or not geraet.value:
                    return
                meter = ctypes.c_void_p()
                # IMMDevice::Activate(REFIID, CLSCTX_ALL, NULL, **IAudioMeterInformation)
                if _methode(geraet.value, 3, ctypes.POINTER(_GUID), wt.DWORD, ctypes.c_void_p,
                            ctypes.POINTER(ctypes.c_void_p))(
                        geraet.value, ctypes.byref(_IID_METER), 0x17, None, ctypes.byref(meter)) == 0:
                    self._meter = meter.value
            finally:
                _freigeben(geraet.value)
                _freigeben(enum.value)

        def pegel(self, dt: float) -> float:
            self._alter += dt
            # neu verbinden: beim ersten Mal, alle 30 s, ohne Gerät alle 5 s
            if self._erster or self._alter > (self.NEU_VERBINDEN_S if self._meter else 5.0):
                self._erster = False
                self._alter = 0.0
                self._verbinden()
            if self._meter is None:
                return 0.0
            wert = ctypes.c_float()
            # IAudioMeterInformation::GetPeakValue(float*)
            if _methode(self._meter, 3, ctypes.POINTER(ctypes.c_float))(self._meter, ctypes.byref(wert)) != 0:
                self.schliessen()
                return 0.0
            return float(wert.value)

        def schliessen(self) -> None:
            _freigeben(self._meter)
            self._meter = None

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

    def besitzer_setzen(hwnd: int, besitzer: int | None) -> None:
        pass

    def laufende_programme() -> set[str]:
        return set()

    class Pegelmesser:
        def pegel(self, dt: float) -> float:
            return 0.0

        def schliessen(self) -> None:
            pass
