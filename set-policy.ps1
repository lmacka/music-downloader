# Run this script as administrator
param([string]$Username = 'Kids')

$sid = (New-Object System.Security.Principal.NTAccount($Username)).Translate([System.Security.Principal.SecurityIdentifier]).Value
$path = "HKEY_USERS\$sid\Software\Microsoft\PowerShell\1\ShellIds\Microsoft.PowerShell"

# Create the PowerShell policy key if it doesn't exist
if (-not (Test-Path "Registry::HKEY_USERS\$sid\Software\Microsoft\PowerShell\1\ShellIds")) {
    New-Item -Path "Registry::HKEY_USERS\$sid\Software\Microsoft\PowerShell\1\ShellIds" -Force | Out-Null
}
if (-not (Test-Path "Registry::$path")) {
    New-Item -Path "Registry::$path" -Force | Out-Null
}

# Set the execution policy for the specific user
Set-ItemProperty -Path "Registry::$path" -Name "ExecutionPolicy" -Value "RemoteSigned"
Write-Host "Execution policy set to RemoteSigned for user $Username" -ForegroundColor Green 