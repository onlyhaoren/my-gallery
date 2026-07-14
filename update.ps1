# update.ps1 - 一键：压缩 → 生成索引 → 推送
# 双击运行 或 PowerShell 中 .\update.ps1
Set-Location $PSScriptRoot
Write-Host "`n===== 1/3 压缩图片 =====" -ForegroundColor Cyan
python compress.py
Write-Host "`n===== 2/3 生成索引 =====" -ForegroundColor Cyan
python generate_index.py
Write-Host "`n===== 3/3 推送到 GitHub =====" -ForegroundColor Cyan
Set-Location site
git add .
$date = Get-Date -Format "yyyy-MM-dd HH:mm"
git commit -m "更新图片 $date"
git push
Write-Host "`n✅ 全部完成! 等待约1分钟后网站自动更新" -ForegroundColor Green
Write-Host "网站地址: https://my-gallery.pages.dev`n" -ForegroundColor Yellow
Read-Host "按回车退出"