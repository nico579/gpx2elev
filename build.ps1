param([ValidateSet('all','tests','apk')][string]$Mode = 'all', [switch]$Live)
$ErrorActionPreference = 'Stop'
$projectDirectory = $PSScriptRoot
$buildJava = $env:JAVA_HOME
if (-not $buildJava -or -not (Test-Path -LiteralPath (Join-Path $buildJava 'bin\javac.exe'))) {
    $buildJava = Join-Path $env:USERPROFILE '.jdks\jbr-21.0.11'
}
if (-not (Test-Path -LiteralPath (Join-Path $buildJava 'bin\javac.exe'))) {
    throw 'Définissez JAVA_HOME vers un JDK 17 ou 21 (Gradle 8.7).'
}
$env:JAVA_HOME = $buildJava
$buildTasks = @(switch ($Mode) {
    'tests' { @('testDebugUnitTest') }
    'apk' { @('assembleRelease') }
    default { @('testDebugUnitTest','lintRelease','assembleRelease') }
})
if ($Live) { $buildTasks += '-PliveReaders=true' }
Push-Location $projectDirectory
try {
    & rtk proxy .\gradlew.bat @buildTasks --console=plain
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally { Pop-Location }
