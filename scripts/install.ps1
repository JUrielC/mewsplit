# Instala mewsplit en Windows 10 / 11 (64 bits).
#
# En PowerShell:
#   irm https://github.com/JUrielC/mewsplit/releases/latest/download/install.ps1 | iex
#
# En CMD (Simbolo del sistema):
#   powershell -ExecutionPolicy Bypass -c "irm https://github.com/JUrielC/mewsplit/releases/latest/download/install.ps1 | iex"
#
# Por que un comando y no un .exe: SmartScreen bloquea los instaladores bajados
# con el navegador si no llevan un certificado de pago. Lo que instala uv desde
# la terminal no lleva esa marca, y el acceso directo lo crea este script en el
# propio equipo, asi que se abre con doble clic sin avisos.
#
# Los textos van sin tildes: GitHub sirve los archivos sin charset y Windows
# PowerShell 5.1 los decodificaria mal.
#
# Variables para probar sin publicar nada:
#   MEWSPLIT_WHEEL      ruta o URL del paquete (por defecto, la ultima release)
#   MEWSPLIT_NO_LAUNCH  no abrir mewsplit al terminar

$ErrorActionPreference = "Stop"
$Repo = "JUrielC/mewsplit"

Write-Host ""
Write-Host "Instalando mewsplit..." -ForegroundColor Yellow

# 1. uv instala Python y todo lo demas sin tocar el Python del sistema.
$UvPaths = @("$env:USERPROFILE\.local\bin", "$env:USERPROFILE\.cargo\bin")
function Add-UvToPath {
    foreach ($p in $UvPaths) {
        if ((Test-Path $p) -and ($env:Path -notlike "*$p*")) { $env:Path = "$p;$env:Path" }
    }
}
Add-UvToPath
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "-> Instalando uv (el instalador de Python de Astral)..."
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    Add-UvToPath
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "No se pudo instalar uv. Revisa tu conexion a internet y vuelve a intentarlo."
}

# 2. El wheel de la ultima release. /releases/latest nunca devuelve una
# pre-release: si no hay ninguna definitiva, se cae a la lista completa.
$Wheel = $env:MEWSPLIT_WHEEL
if ([string]::IsNullOrWhiteSpace($Wheel)) {
    $Headers = @{ "User-Agent" = "mewsplit-installer" }
    $Sources = @(
        "https://api.github.com/repos/$Repo/releases/latest",
        "https://api.github.com/repos/$Repo/releases?per_page=10"
    )
    foreach ($Source in $Sources) {
        try {
            foreach ($Release in @(Invoke-RestMethod -Uri $Source -Headers $Headers)) {
                $Asset = $Release.assets | Where-Object { $_.name -like "*.whl" } | Select-Object -First 1
                if ($Asset) { $Wheel = $Asset.browser_download_url; break }
            }
        } catch {}
        if (-not [string]::IsNullOrWhiteSpace($Wheel)) { break }
    }
    if ([string]::IsNullOrWhiteSpace($Wheel)) {
        throw "No se encontro ninguna version publicada de mewsplit."
    }
}

Write-Host "-> Instalando mewsplit. La primera vez baja varios cientos de MB (PyTorch); puede tardar unos minutos."
uv tool install --force --python 3.11 "$Wheel"
if ($LASTEXITCODE -ne 0) { throw "uv no pudo instalar mewsplit." }

# 3. pythonw.exe del entorno de la herramienta: abre mewsplit sin consola negra.
# --color never: uv pinta la ruta de color aun capturada.
$ToolDir = (uv tool dir --color never).Trim()
$Pythonw = Join-Path $ToolDir "mewsplit\Scripts\pythonw.exe"
if (-not (Test-Path $Pythonw)) { $Pythonw = Join-Path $ToolDir "mewsplit\Scripts\python.exe" }
if (-not (Test-Path $Pythonw)) {
    throw "La instalacion termino pero no se encuentra mewsplit en $ToolDir."
}

# 4. Accesos directos en el Menu Inicio y en el Escritorio.
$Icon = Join-Path $ToolDir "mewsplit\Lib\site-packages\mewsplit\assets\mewsplit.ico"
if (Test-Path $Icon) { $IconLocation = "$Icon,0" } else { $IconLocation = "$env:SystemRoot\System32\shell32.dll,21" }

# Igual que WINDOWS_APP_ID en mewsplit/app.py: asi la barra de tareas une la ventana con este acceso directo
$AppId = "app.mewsplit.launcher"
if (-not ("MewsplitShortcut" -as [type])) {
    try {
        Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public static class MewsplitShortcut
{
    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IPropertyStore
    {
        void GetCount(out uint count);
        void GetAt(uint index, out PropertyKey key);
        void GetValue(ref PropertyKey key, out PropVariant value);
        void SetValue(ref PropertyKey key, ref PropVariant value);
        void Commit();
    }

    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    private struct PropertyKey
    {
        public Guid FormatId;
        public uint PropertyId;
    }

    [StructLayout(LayoutKind.Explicit, Size = 24)]
    private struct PropVariant
    {
        [FieldOffset(0)] public ushort Type;
        [FieldOffset(8)] public IntPtr Value;
    }

    [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
    private static extern void SHGetPropertyStoreFromParsingName(string path, IntPtr bindContext, int flags, ref Guid iid, out IPropertyStore store);

    public static void SetAppId(string path, string appId)
    {
        Guid iid = typeof(IPropertyStore).GUID;
        IPropertyStore store;
        SHGetPropertyStoreFromParsingName(path, IntPtr.Zero, 2, ref iid, out store);
        PropertyKey key = new PropertyKey { FormatId = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), PropertyId = 5 };
        PropVariant value = new PropVariant { Type = 31, Value = Marshal.StringToCoTaskMemUni(appId) };
        try
        {
            store.SetValue(ref key, ref value);
            store.Commit();
        }
        finally
        {
            Marshal.FreeCoTaskMem(value.Value);
            Marshal.ReleaseComObject(store);
        }
    }
}
"@
    } catch {}
}

$WshShell = New-Object -ComObject WScript.Shell
$StartMenuShortcut = Join-Path ([Environment]::GetFolderPath("Programs")) "mewsplit.lnk"
$DesktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "mewsplit.lnk"

foreach ($ShortcutPath in @($StartMenuShortcut, $DesktopShortcut)) {
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $Pythonw
    $Shortcut.Arguments = "-m mewsplit.app"
    $Shortcut.WorkingDirectory = $env:USERPROFILE
    $Shortcut.Description = "mewsplit - separacion de pistas y acordes"
    $Shortcut.IconLocation = $IconLocation
    $Shortcut.Save()
    try { [MewsplitShortcut]::SetAppId($ShortcutPath, $AppId) } catch {}
}

Write-Host ""
Write-Host "Listo. mewsplit quedo instalado:" -ForegroundColor Green
Write-Host "  - Acceso directo en tu Escritorio (mewsplit)"
Write-Host "  - En el Menu Inicio (pulsa la tecla Windows y escribe 'mewsplit')"
Write-Host "La primera cancion tarda un poco mas: se descargan los modelos (~100 MB)."
Write-Host "mewsplit avisa cuando hay una version nueva y se actualiza desde la app."
Write-Host ""
Write-Host "Para desinstalarlo (tus proyectos quedan en $env:LOCALAPPDATA\mewsplit):"
Write-Host '  uv tool uninstall mewsplit; Remove-Item "$env:USERPROFILE\Desktop\mewsplit.lnk", "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\mewsplit.lnk", "$env:USERPROFILE\.cache\mewsplit" -Recurse -Force -ErrorAction SilentlyContinue'

if ([string]::IsNullOrWhiteSpace($env:MEWSPLIT_NO_LAUNCH)) {
    Start-Process -FilePath $Pythonw -ArgumentList "-m mewsplit.app"
}
