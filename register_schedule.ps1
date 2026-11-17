param(
    [ValidateSet("weekly", "daily")]
    [string]$Freq = "weekly",
    [string]$Time = "09:00",
    [switch]$Force
)

# 2026-11-15：用户要求「抓取的定期计划去除」，Windows 计划任务
# KB-Monitor-Update 已经从系统里删掉了，应用里的定时抓取入口也一并移除。
# 这个脚本保留下来，是因为有人可能想把自动抓取加回来；
# 但为了避免误触，现在必须先显式加 -Force 才会真正注册。

if (-not $Force) {
    Write-Host "自动抓取已停用（2026-11-15 移除了计划任务 KB-Monitor-Update）。"
    Write-Host "应用里的抓取改为手动：文献库页 → 抓取新论文。"
    Write-Host "确实要恢复定时抓取，请执行： .\register_schedule.ps1 -Force"
    exit 1
}

$py = (Get-Command pythonw).Source
$script = (Resolve-Path (Join-Path $PSScriptRoot "kbscan.py")).Path
$tr = '"' + $py + '" "' + $script + '"'
$task = "KB-Monitor-Update"

if ($Freq -eq "weekly") {
    schtasks /Create /F /TN $task /TR $tr /SC WEEKLY /D SUN /ST $Time
} else {
    schtasks /Create /F /TN $task /TR $tr /SC DAILY /ST $Time
}

Write-Host "任务已注册: $task （$Freq $Time）。测试请先运行: python $script --dry-run"