ANIIMO PL - BUDOWANIE INSTALATORA EXE
=====================================

Wymagania
---------
- Windows 10 lub 11.
- Python 3.12 dodany do PATH albo podany parametrem -PythonExecutable.
- Dostęp do internetu przy pierwszym uruchomieniu w celu pobrania zależności.

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

Skrypt tworzy lokalne środowisko .venv, instaluje zależności zapisane w
requirements-build.txt i uruchamia PyInstaller. Katalogi .venv, build i dist są
wynikami lokalnego budowania i nie są wymagane w repozytorium źródłowym.

Zawartość wymagana do budowania
-------------------------------
- build_installer.ps1
- requirements-build.txt
- src\aniimo_pl_installer.py
- data\NewTextMap_pl.json
- data\Compress_pl.bin
- data\AITranslatedItems_pl.json

Instalator sam odnajduje bieżące bundle fontów i generuje polskie glify podczas
instalacji. Nie zawiera gotowych bundli, przeglądarki ani usług internetowych.
