# Starts the existing local Neo4j installation in the foreground.
# -BoltPort 7688 runs it on other ports (bolt 7688, http 7475) with a copied config, for
# when another Neo4j, such as a Docker project, already holds 7687.
param([string]$JavaHome = 'D:\PyCharm 2025.2\jbr', [int]$BoltPort = 7687)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$neo = Join-Path (Split-Path -Parent $repo) 'neo4j\neo4j-community-5.26.0'
if ($env:JAVA_HOME -and (Test-Path "$env:JAVA_HOME\bin\java.exe")) { $JavaHome = $env:JAVA_HOME }
if (-not (Test-Path "$JavaHome\bin\java.exe")) { throw 'Set JAVA_HOME to JDK 21.' }
$env:JAVA_HOME = $JavaHome
if ($BoltPort -ne 7687) {
    $conf = Join-Path $repo ".cache\neo4j-conf-$BoltPort"
    New-Item -ItemType Directory -Force $conf | Out-Null
    Copy-Item (Join-Path $neo 'conf\*') $conf -Force
    $file = Join-Path $conf 'neo4j.conf'
    $http = 7474 + ($BoltPort - 7687)
    $lines = (Get-Content $file) `
        -replace '^#?server\.bolt\.listen_address=.*', "server.bolt.listen_address=:$BoltPort" `
        -replace '^#?server\.http\.listen_address=.*', "server.http.listen_address=:$http"
    [IO.File]::WriteAllLines($file, $lines)   # UTF-8 without a byte-order mark
    $env:NEO4J_CONF = $conf
}
& (Join-Path $neo 'bin\neo4j.bat') console
