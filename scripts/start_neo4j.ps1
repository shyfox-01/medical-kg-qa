# 启动本地 Neo4j。前台运行，Ctrl+C 停止。
#
# Neo4j 5.26 需要 JDK 17 或 21。如果机器上没单独装 JDK，PyCharm 自带的 JBR 就是 JDK 21，
# 直接拿来用即可，不用另外下载安装。
#
# 注意：这个文件必须存成 **UTF-8 with BOM**。Windows PowerShell 5.1 遇到没有 BOM 的
# 脚本会按系统 ANSI 代码页（简体中文机器上是 GBK）解码，上面这几行中文注释被误读之后
# 会凭空冒出引号和反引号，整个脚本连解析都过不去 —— 报的还是 "字符串缺少终止符"
# 这种和真实原因毫不相干的错。v1 就踩了这个坑。

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

# v2 是原项目的子目录，几百 MB 的 Neo4j 发行版没必要复制一份：
# 本目录找不到就往上一级找，版本号也不写死。
$neo4jHome = $null
foreach ($base in @($root, (Split-Path -Parent $root))) {
    $dir = Join-Path $base "neo4j"
    if (Test-Path $dir) {
        $found = Get-ChildItem -Path $dir -Filter "neo4j-community-*" -Directory `
                     -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) { $neo4jHome = $found.FullName; break }
    }
}
if (-not $neo4jHome) {
    throw @"
找不到 Neo4j（在 $root 和上一级都没有 neo4j\neo4j-community-*）。

本仓库不包含 Neo4j 发行版（社区版约 460MB，GPLv3）。请自行下载：
  https://neo4j.com/deployment-center/  ->  Community Edition 5.26
解压后放成 $root\neo4j\neo4j-community-5.26.0\ 这样的结构再重跑本脚本。
"@
}
Write-Host "NEO4J_HOME = $neo4jHome"

# 找一个可用的 JDK：先看 JAVA_HOME，再看 PATH，最后退到 PyCharm / IDEA 自带的 JBR
function Find-Java {
    if ($env:JAVA_HOME -and (Test-Path "$env:JAVA_HOME\bin\java.exe")) { return $env:JAVA_HOME }
    $onPath = Get-Command java -ErrorAction SilentlyContinue
    if ($onPath) { return (Split-Path -Parent (Split-Path -Parent $onPath.Source)) }
    $candidates = @()
    foreach ($drive in @("C:", "D:", "E:")) {
        $candidates += Get-ChildItem -Path "$drive\" -Filter "jbr" -Recurse -Depth 3 `
            -Directory -ErrorAction SilentlyContinue |
            Where-Object { Test-Path (Join-Path $_.FullName "bin\java.exe") }
    }
    if ($candidates.Count -gt 0) { return $candidates[0].FullName }
    return $null
}

$java = Find-Java
if (-not $java) {
    throw "没找到 JDK。请安装 JDK 21（https://adoptium.net/），或设置 JAVA_HOME。"
}

$env:JAVA_HOME = $java
Write-Host "JAVA_HOME = $java"
& "$java\bin\java.exe" -version
Write-Host "`n启动 Neo4j ... 浏览器界面 http://localhost:7474  Bolt 端口 7687`n"

& (Join-Path $neo4jHome "bin\neo4j.bat") console
