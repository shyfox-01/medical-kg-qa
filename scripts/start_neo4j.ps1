# Starts the existing local Neo4j installation in the foreground.
param([string]$JavaHome = 'D:\PyCharm 2025.2\jbr')
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$neo = Join-Path (Split-Path -Parent $repo) 'neo4j\neo4j-community-5.26.0'
if ($env:JAVA_HOME -and (Test-Path "$env:JAVA_HOME\bin\java.exe")) { $JavaHome = $env:JAVA_HOME }
if (-not (Test-Path "$JavaHome\bin\java.exe")) { throw 'Set JAVA_HOME to JDK 21.' }
$env:JAVA_HOME = $JavaHome
& (Join-Path $neo 'bin\neo4j.bat') console
