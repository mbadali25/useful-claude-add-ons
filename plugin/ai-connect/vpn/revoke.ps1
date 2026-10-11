# revoke: see README.md. All logic lives in tsadmin.py.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')
Invoke-VpnTsadmin -Arguments (@('revoke') + $args)
