Param(
    [string]$DbName = "sml_db",
    [string]$DbUser = "sml_user",
    [string]$DbHost = "192.168.29.213",
    [string]$DjangoSettings = "spoorthi_macs.settings"
)

# === Secure password prompt ===
Write-Host "Using DB: $DbName user: $DbUser host: $DbHost Django settings: $DjangoSettings"
$securePwd = Read-Host -AsSecureString "MySQL password for $DbUser"
$BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePwd)
$PlainPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)

# Export DJANGO_SETTINGS_MODULE
$env:DJANGO_SETTINGS_MODULE = $DjangoSettings

# 1. Show current migrations
Write-Host "=== Existing migrations ==="
python .\manage.py showmigrations

# 2. Delete old migration files (except __init__.py)
Write-Host "=== Deleting old migrations and caches ==="
Get-ChildItem -Recurse -Directory -Filter migrations | ForEach-Object {
    Get-ChildItem $_.FullName -File -Include *.py | Where-Object { $_.Name -ne "__init__.py" } | Remove-Item -Force -Verbose
    Get-ChildItem $_.FullName -File -Include *.pyc | Remove-Item -Force -Verbose
}
# Remove __pycache__ folders
Get-ChildItem -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -Verbose

# 3. Drop and recreate database
Write-Host "=== Dropping and recreating database '$DbName' ==="
$dropCreateSql = "DROP DATABASE IF EXISTS $DbName; CREATE DATABASE $DbName CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
# Assumes mysql is in PATH
& mysql -h $DbHost -u $DbUser -p$PlainPassword -e $dropCreateSql

# 4. Make & apply migrations
Write-Host "=== Making migrations ==="
python .\manage.py makemigrations
Write-Host "=== Applying migrations ==="
python .\manage.py migrate --no-input

# 5. Create superuser (interactive)
Write-Host "=== Creating superuser (you can skip with Ctrl+C) ==="
python .\manage.py createsuperuser

Write-Host "✅ Reset and migration complete."
