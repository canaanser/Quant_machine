schtasks /delete /tn QuantDbOnLogon /f >nul 2>&1
schtasks /create /tn QuantDbOnLogon /tr "\"powershell.exe\" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"E:\stockgate\Quant_Alpha_System\tools\start_stockdb.ps1\"" /sc onlogon /f
schtasks /delete /tn QuantDutyOnLogon /f >nul 2>&1
schtasks /create /tn QuantDutyOnLogon /tr "\"E:\python\量化看守.exe\" -B \"E:\stockgate\Quant_Alpha_System\duty\duty_engine.py\"" /sc onlogon /f
schtasks /delete /tn QuantTrayOnLogon /f >nul 2>&1
schtasks /create /tn QuantTrayOnLogon /tr "\"E:\python\量化看守.exe\" -B \"E:\stockgate\Quant_Alpha_System\duty\tray_guard.py\"" /sc onlogon /f
schtasks /delete /tn QuantWatchDog /f >nul 2>&1
schtasks /create /tn QuantWatchDog /tr "\"E:\python\量化看守.exe\" -B \"E:\stockgate\Quant_Alpha_System\scripts\watch_all_dog.py\"" /sc minute /mo 5 /f
schtasks /delete /tn QuantDataSync /f >nul 2>&1
schtasks /create /tn QuantDataSync /tr "\"E:\python\量化看守.exe\" -B \"E:\stockgate\Quant_Alpha_System\scripts\run_data_sync.py\"" /sc daily /st 20:00 /f
schtasks /delete /tn QuantDailyScan /f >nul 2>&1
schtasks /create /tn QuantDailyScan /tr "\"E:\python\量化看守.exe\" -B \"E:\stockgate\Quant_Alpha_System\scripts\gen_next_plan.py --save-json\"" /sc weekly /d MON,TUE,WED,THU,FRI /st 20:15 /f
schtasks /delete /tn QuantDailyPlan /f >nul 2>&1
schtasks /create /tn QuantDailyPlan /tr "\"E:\python\量化看守.exe\" -B \"E:\stockgate\Quant_Alpha_System\scripts\compose_daily_plan.py --write\"" /sc weekly /d MON,TUE,WED,THU,FRI /st 20:40 /f
