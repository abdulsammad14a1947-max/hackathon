# Portable PostgreSQL (no admin rights, no winget): download zonky embedded binaries,
# initdb, start on port 5433, create the hcm_lite database.
$ErrorActionPreference = "Stop"
$root = "C:\Users\Rrs computers\Downloads\simt\.pglocal"
$zipDir = Join-Path $root "zips"
$dataDir = Join-Path $root "data"
New-Item -ItemType Directory -Force -Path $zipDir | Out-Null

$metaUrl = "https://repo1.maven.org/maven2/io/zonky/test/postgres/embedded-postgres-binaries-windows-amd64/maven-metadata.xml"
[xml]$meta = (Invoke-WebRequest -Uri $metaUrl -UseBasicParsing).Content
# Prefer a 17.x release; fall back to latest available.
$versions = @($meta.metadata.versioning.versions.version) | Where-Object { $_ -like "17.*" }
if (-not $versions) { $versions = @($meta.metadata.versioning.latest) }
$ver = $versions[-1]
Write-Output "Using embedded-postgres $ver"

$jar = Join-Path $zipDir "epg-$ver.jar"
if (-not (Test-Path $jar)) {
    Invoke-WebRequest -Uri "https://repo1.maven.org/maven2/io/zonky/test/postgres/embedded-postgres-binaries-windows-amd64/$ver/embedded-postgres-binaries-windows-amd64-$ver.jar" -OutFile $jar -UseBasicParsing
}
$unzip = Join-Path $zipDir "unz"
if (Test-Path $unzip) { Remove-Item $unzip -Recurse -Force }
# A .jar is a zip — copy to .zip so Expand-Archive accepts it.
$jarAsZip = Join-Path $zipDir "epg-$ver.zip"
Copy-Item $jar $jarAsZip -Force
Expand-Archive -Path $jarAsZip -DestinationPath $unzip -Force
$txz = Get-ChildItem $unzip -Filter *.txz -Recurse | Select-Object -First 1
if (-not $txz) { throw "No postgres .txz payload found in jar" }
Write-Output "Inner archive: $($txz.Name)"
$pg = Join-Path $root "pgsql"
if (Test-Path $pg) { Remove-Item $pg -Recurse -Force }
# Windows tar.exe lacks xz; Python's tarfile+lzma handles .txz natively.
python "C:\Users\Rrs computers\Downloads\simt\_extract_txz.py" $txz.FullName $pg
if ($LASTEXITCODE -ne 0) { throw "python txz extraction failed" }
# The zip may contain a top-level folder; locate bin/initdb.exe
$initdb = Get-ChildItem $pg -Filter initdb.exe -Recurse | Select-Object -First 1
$binDir = Split-Path $initdb.FullName -Parent
Write-Output "bin: $binDir"

if (Test-Path $dataDir) { Remove-Item $dataDir -Recurse -Force }
& (Join-Path $binDir "initdb.exe") -D $dataDir -U postgres -A trust -E UTF8 --locale=C | Out-Null
if ($LASTEXITCODE -ne 0) { throw "initdb failed" }
& (Join-Path $binDir "pg_ctl.exe") -D $dataDir -l (Join-Path $root "pg.log") -o "-p 5433 -c listen_addresses=127.0.0.1" start
if ($LASTEXITCODE -ne 0) { throw "pg_ctl start failed" }
# No psql in this build — create the DB via Python + psycopg.
python "C:\Users\Rrs computers\Downloads\simt\_pg_init.py"
if ($LASTEXITCODE -ne 0) { throw "database creation failed" }
Write-Output "POSTGRES_READY on 127.0.0.1:5433 db=hcm_lite user=postgres"
