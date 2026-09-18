ANIIMO PL - BUDOWANIE INSTALATORA EXE
=====================================

Wymagania
---------
- Windows 10 lub 11.
- Python 3.12 dodany do PATH albo podany parametrem -PythonExecutable.
- Dostęp do internetu przy pierwszym uruchomieniu, aby zainstalować zależności.

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

Skrypt tworzy lokalny katalog .venv i instaluje wersje PyInstaller, UnityPy,
Pillow, NumPy oraz biblioteki wymagane przez UnityPy określone w pliku
requirements-build.txt. Uszkodzone lub nieaktualne
.venv zostanie utworzone ponownie. Katalogi .venv, build i dist są wynikami
lokalnego budowania i można je później usunąć.

Zawartość pakietu
-----------------
- build_installer.ps1 - pełny skrypt budowania EXE.
- requirements-build.txt - wersje zależności potrzebnych do budowania.
- src\aniimo_pl_installer.py - kod instalatora.
- data\NewTextMap_pl.json - mapa polskich tekstów.
- data\Compress_pl.bin - polskie teksty.
- data\AITranslatedItems_pl.json - lista tłumaczonych identyfikatorów.

Instalator sam odnajduje bieżące bundle fontów i generuje polskie glify podczas
instalacji. Nie zawiera gotowych bundli ani zapisanych na stałe nazw i sum MD5.

Pakiet nie zawiera generatorów TSV, diffów, narzędzi tłumaczeniowych ani
usług internetowych. Służy wyłącznie do zbudowania gotowego instalatora EXE.
