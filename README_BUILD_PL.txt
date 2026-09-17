ANIIMO PL - BUDOWANIE INSTALATORA EXE
=====================================

Wymagania
---------
- Windows 10 lub 11.
- Python 3.12 dodany do PATH albo podany parametrem -PythonExecutable.
- Dostęp do internetu przy pierwszym uruchomieniu, aby zainstalować PyInstaller.

Budowanie
---------
1. Otwórz PowerShell w katalogu SelfBuild.
2. Uruchom:

   powershell -ExecutionPolicy Bypass -File .\build_installer.ps1

   Jeżeli Python nie jest dostępny w PATH:

   powershell -ExecutionPolicy Bypass -File .\build_installer.ps1 `
     -PythonExecutable "C:\sciezka\do\python.exe"

3. Gotowy plik powstanie tutaj:

   dist\Aniimo_PL_Installer.exe

Skrypt przy pierwszym uruchomieniu tworzy lokalny katalog .venv i instaluje
wersję PyInstaller określoną w requirements-build.txt. Katalogi .venv, build
i dist są wynikami lokalnego budowania i można je później usunąć.

Zawartość pakietu
-----------------
- build_installer.ps1 - pełny skrypt budowania EXE.
- requirements-build.txt - wersja PyInstaller.
- src\aniimo_pl_installer.py - kod instalatora.
- data\NewTextMap_pl.json - mapa polskich tekstów.
- data\Compress_pl.bin - polskie teksty.
- data\AITranslatedItems_pl.json - lista tłumaczonych identyfikatorów.
- data\font_patch_main\*.uab - poprawione fonty z polskimi znakami.

Pakiet nie zawiera generatorów TSV, diffów, narzędzi tłumaczeniowych ani
usług internetowych. Służy wyłącznie do zbudowania gotowego instalatora EXE.
