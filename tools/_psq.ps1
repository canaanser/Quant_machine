Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*看守*' } | ForEach-Object { Write-Output ($_.ProcessId.ToString() + " :: " + $_.CommandLine) }
