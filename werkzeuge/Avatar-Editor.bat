@echo off
rem Avatar-Editor starten (Doppelklick)
cd /d "%~dp0.."
start "" ".venv\Scripts\pythonw.exe" werkzeuge\avatar_editor.py
