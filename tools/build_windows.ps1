param(
  [Parameter(Mandatory=$true)][string]$SdkRoot,
  [Parameter(Mandatory=$true)][string]$BoostRoot
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path "$SdkRoot/include/dev/devs.hpp")) { throw 'Private SDK root is invalid' }
if (-not ((Test-Path "$BoostRoot/boost/json/src.hpp") -or (Test-Path "$BoostRoot/include/boost/json/src.hpp"))) {
  throw 'Boost >= 1.75 headers (including boost/json/src.hpp) are required'
}
$env:LIBDEV_ROOT = (Resolve-Path $SdkRoot).Path
$env:BOOST_ROOT = (Resolve-Path $BoostRoot).Path
Push-Location $Root
try {
  cmake -S native -B build -A x64
  if ($LASTEXITCODE -ne 0) { throw 'CMake configuration failed' }
  cmake --build build --config Release
  if ($LASTEXITCODE -ne 0) { throw 'Native build failed' }
  $env:TAIL2_PROBE = (Resolve-Path 'build/Release/tail2_probe.exe').Path
  python -m unittest discover -s tests -v
  if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
} finally { Pop-Location }
