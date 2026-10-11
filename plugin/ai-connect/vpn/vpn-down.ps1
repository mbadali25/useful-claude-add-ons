# vpn-down: see README.md. All logic lives in tsadmin.py.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')
Invoke-VpnTsadmin -Arguments (@('vpn-down') + $args)
