# Market Sentiment Analysis — Windows Task Scheduler kurulumu
# Yonetici olarak calistir: PowerShell'i "Yonetici olarak ac" ile ac, sonra bu scripti calistir.

$BASE = "C:\MarketSentimentAnalysis"
$PYTHON = "$BASE\venv\Scripts\python.exe"

# -------------------------------------------------------
# 1. Saatlik fiyat guncellemesi (her saat basi)
# -------------------------------------------------------
$priceAction  = New-ScheduledTaskAction `
    -Execute $PYTHON `
    -Argument "$BASE\scripts\auto_price_update.py" `
    -WorkingDirectory $BASE

$priceTrigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Hours 1) -Once -At "00:00"

$priceSettings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

Register-ScheduledTask `
    -TaskName "MarketSentiment_PriceUpdate" `
    -Action $priceAction `
    -Trigger $priceTrigger `
    -Settings $priceSettings `
    -RunLevel Highest `
    -Force | Out-Null

Write-Host "[OK] Saatlik fiyat gorevi kuruldu: MarketSentiment_PriceUpdate"

# -------------------------------------------------------
# 2. 2 saatlik tweet guncellemesi (gunde 12 kez)
# -------------------------------------------------------
$tweetAction  = New-ScheduledTaskAction `
    -Execute $PYTHON `
    -Argument "$BASE\scripts\auto_tweet_update.py" `
    -WorkingDirectory $BASE

$tweetTrigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Hours 2) -Once -At "00:30"

$tweetSettings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

Register-ScheduledTask `
    -TaskName "MarketSentiment_TweetUpdate" `
    -Action $tweetAction `
    -Trigger $tweetTrigger `
    -Settings $tweetSettings `
    -RunLevel Highest `
    -Force | Out-Null

Write-Host "[OK] 2 saatlik tweet gorevi kuruldu: MarketSentiment_TweetUpdate"

Write-Host ""
Write-Host "Gorevleri kontrol et: Get-ScheduledTask -TaskName 'MarketSentiment_*'"
Write-Host "Manuel test: Start-ScheduledTask -TaskName 'MarketSentiment_PriceUpdate'"
