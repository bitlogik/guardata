<#

	﻿From PowerShelf
	Copyright (c) 2012-2020 Roman Kuzmin
	(inspired by Lee Holmes's Invoke-CmdScript.ps1)

	Licensed under the Apache License, Version 2.0 (the "License"); you may not use
	this file except in compliance with the License.
	Unless required by applicable law or agreed to in writing, software distributed
	under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
	CONDITIONS OF ANY KIND, either express or implied. See the License for the
	specific language governing permissions and limitations under the License.

	.Link
		https://github.com/nightroman/PowerShelf

#>

param
(
	[Parameter(Mandatory=1)][string]$Command,
	[switch]$Output,
	[switch]$Force
)

$stream = if ($Output) { ($temp = [IO.Path]::GetTempFileName()) } else { 'nul' }
$operator = if ($Force) {'&'} else {'&&'}

foreach($_ in cmd /c " $Command > `"$stream`" 2>&1 $operator SET") {
	if ($_ -match '^([^=]+)=(.*)') {
		[System.Environment]::SetEnvironmentVariable($matches[1], $matches[2])
	}
}

if ($Output) {
	Get-Content -LiteralPath $temp
	Remove-Item -LiteralPath $temp
}
