param(
    [string]$PythonExecutable = ""
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$venvPython = Join-Path $root ".venv\Scripts\python.exe"

function Resolve-Python {
    if ($PythonExecutable) {
        if (-not (Test-Path -LiteralPath $PythonExecutable)) {
            throw "Nie znaleziono interpretera Python: $PythonExecutable"
        }
        return @($PythonExecutable)
    }

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        return @($pyLauncher.Source, "-3")
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @($python.Source)
    }

    throw "Nie znaleziono Pythona 3. Zainstaluj Python 3.12 lub podaj -PythonExecutable."
}

if (Test-Path -LiteralPath $venvPython) {
    & $venvPython -c "import sys" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Remove-Item -LiteralPath (Join-Path $root ".venv") -Recurse -Force
    }
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    $pythonCommand = @(Resolve-Python)
    $command = $pythonCommand[0]
    $prefix = @($pythonCommand | Select-Object -Skip 1)
    & $command @prefix -m venv (Join-Path $root ".venv")
}

& $venvPython -m pip install -r (Join-Path $root "requirements-build.txt")

& $venvPython -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --console `
    --collect-data "UnityPy" `
    --hidden-import "UnityPy.resources" `
    --collect-all "fmod_toolkit" `
    --collect-data "archspec" `
    --name "Aniimo_PL_Installer" `
    --distpath (Join-Path $root "dist") `
    --workpath (Join-Path $root "build") `
    --specpath (Join-Path $root "build") `
    --add-data "$(Join-Path $root 'data');data" `
    (Join-Path $root "src\aniimo_pl_installer.py")

Write-Host "Gotowe: $(Join-Path $root 'dist\Aniimo_PL_Installer.exe')"
