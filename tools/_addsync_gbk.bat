@echo off
schtasks /create /tn QuantDataSync /tr "\"D:\a数据\stockdb\数据更新.exe\"" /sc daily /st 20:00 /f
