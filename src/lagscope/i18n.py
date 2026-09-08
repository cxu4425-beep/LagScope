"""Translations, kept dependency free so probes and tests can import it.

The first three languages are columns of one table: every key is a
``(zh_CN, zh_TW, en)`` tuple. Japanese and Korean arrived later and live in
``translations.py`` as dictionaries keyed the same way, because widening 278
tuples would have meant every future string had to be written in five
languages before the app would run.

The practical difference is the fallback. A key missing from an overlay
language falls back to English, so an untranslated string looks unpolished
rather than crashing or showing a bare ``some.key`` on screen.
"""

from __future__ import annotations

import locale
import os
from typing import Iterable

from .translations import OVERLAYS

# The order of the tuple columns in STRINGS, then the overlay languages.
BASE_LANGUAGES = ("zh_CN", "zh_TW", "en")
LANGUAGES = BASE_LANGUAGES + tuple(OVERLAYS)
LANGUAGE_NAMES = {
    "zh_CN": "简体中文", "zh_TW": "繁體中文", "en": "English",
    "ja": "日本語", "ko": "한국어",
}

_current = "zh_CN"

# key: (zh_CN, zh_TW, en)
STRINGS: dict[str, tuple[str, str, str]] = {
    "app.title": ("哔哩哔哩延迟监视器", "嗶哩嗶哩延遲監視器", "LagScope"),
    "app.short": ("B站延迟", "B站延遲", "Bili Latency"),
    "app.short_generic": ("网络延迟", "網路延遲", "Latency"),

    "menu.show_overlay": ("显示悬浮窗", "顯示懸浮視窗", "Show overlay"),
    "menu.lock": ("锁定位置", "鎖定位置", "Lock position"),
    "menu.click_through": ("鼠标穿透", "滑鼠穿透", "Click-through"),
    "menu.pause": ("暂停监测", "暫停監測", "Pause monitoring"),
    "menu.resume": ("继续监测", "繼續監測", "Resume monitoring"),
    "menu.reset_position": ("重置窗口位置", "重設視窗位置", "Reset overlay position"),
    "menu.settings": ("设置…", "設定…", "Settings…"),
    "menu.copy_diag": ("复制诊断信息", "複製診斷資訊", "Copy diagnostics"),
    "menu.open_config": ("打开配置目录", "開啟設定目錄", "Open config folder"),
    "menu.about": ("关于", "關於", "About"),
    "menu.quit": ("退出", "結束", "Quit"),

    "label.total": ("总延迟", "總延遲", "Total"),
    "label.network": ("网络", "網路", "Network"),
    "label.stream": ("推流", "推流", "Stream"),
    "label.display": ("显示", "顯示", "Display"),
    "label.avg": ("均值", "均值", "avg"),
    "label.p95": ("P95", "P95", "p95"),
    "label.jitter": ("抖动", "抖動", "jitter"),
    "label.range": ("范围", "範圍", "range"),
    "label.room": ("房间", "房間", "Room"),
    "label.video": ("视频", "影片", "Video"),
    "label.startup": ("起播", "起播", "Startup"),
    "label.speed": ("带宽", "頻寬", "Speed"),
    "label.latency": ("延迟", "延遲", "Latency"),
    "label.connections": ("连接数", "連線數", "Sockets"),
    "label.app": ("应用", "應用", "App"),
    "label.target": ("目标", "目標", "Target"),
    "label.down": ("下载", "下載", "Down"),
    "label.up": ("上传", "上傳", "Up"),
    "label.measured": ("实测", "實測", "measured"),
    "label.estimated": ("估算", "估算", "estimated"),
    "label.auto": ("自动", "自動", "auto"),

    "status.no_room": ("未设置房间号", "未設定房間號", "No room configured"),
    "status.offline": ("主播未开播", "主播未開播", "Stream offline"),
    "status.connecting": ("连接中…", "連線中…", "Connecting…"),
    "status.paused": ("已暂停", "已暫停", "Paused"),
    "status.error": ("探测失败", "偵測失敗", "Probe failed"),
    "status.network_only": ("仅网络模式", "僅網路模式", "Network-only mode"),

    "status.no_video": ("未设置视频", "未設定影片", "No video configured"),
    "status.no_app": ("未选择应用", "未選擇應用", "No app selected"),
    "status.no_connections": (
        "该应用当前没有网络连接", "該應用目前沒有網路連線", "That app has no connections right now",
    ),
    "status.unreachable": ("目标无法连通", "目標無法連通", "Target unreachable"),
    "status.no_reply": (
        "该应用的服务器不回应探测（可能屏蔽了 ping）",
        "該應用的伺服器不回應偵測（可能封鎖了 ping）",
        "That app's servers do not answer probes (ping may be blocked)",
    ),
    "status.detecting": ("正在识别观看页面…", "正在辨識觀看頁面…", "Looking for what you are watching…"),

    "menu.diagnose": ("网络体检…", "網路體檢…", "Diagnose my network…"),
    "diag.title": ("网络体检", "網路體檢", "Network check"),
    "diag.running": ("正在检测各段延迟…（约 10 秒）", "正在檢測各段延遲…（約 10 秒）",
                     "Measuring each segment… (about 10 seconds)"),
    "diag.you_router": ("你 → 路由器", "你 → 路由器", "You → router"),
    "diag.router_isp": ("路由器 → 电信商", "路由器 → 電信商", "Router → ISP"),
    "diag.to_target": ("→ 目标服务器", "→ 目標伺服器", "→ target server"),
    "diag.wifi": ("Wi-Fi", "Wi-Fi", "Wi-Fi"),
    "diag.loss": ("丢包", "丟包", "loss"),
    "diag.dns": ("域名解析", "網域解析", "Name lookup"),
    "diag.no_gateway": ("找不到默认网关", "找不到預設閘道", "No default gateway found"),
    "diag.gateway_silent": (
        "路由器不回应 ping（很多路由器默认如此，不代表有问题）",
        "路由器不回應 ping（很多路由器預設如此，不代表有問題）",
        "The router ignores ping - common, and not a fault by itself",
    ),

    "verdict.ok": (
        "网络看起来正常", "網路看起來正常", "Your network looks fine",
    ),
    "verdict.wifi": (
        "延迟主要卡在你和路由器之间，而且 Wi-Fi 信号偏弱——靠近路由器或改用网线会明显改善。",
        "延遲主要卡在你和路由器之間，而且 Wi-Fi 訊號偏弱——靠近路由器或改用網線會明顯改善。",
        "Most of the delay is between you and the router, and the Wi-Fi signal is weak - "
        "move closer to it or use a cable.",
    ),
    "verdict.home": (
        "延迟主要卡在你家网络（你↔路由器）。检查 Wi-Fi、路由器是否过载，或换成网线。",
        "延遲主要卡在你家網路（你↔路由器）。檢查 Wi-Fi、路由器是否過載，或換成網線。",
        "Most of the delay is inside your own network (you to the router). Check the Wi-Fi or "
        "the router's load, or use a cable.",
    ),
    "verdict.isp": (
        "你家网络正常，延迟是从电信商那一段开始变大的——这一段你改不了，可以拿这份报告去问客服。",
        "你家網路正常，延遲是從電信商那一段開始變大的——這一段你改不了，可以拿這份報告去問客服。",
        "Your own network is fine; the delay appears once traffic reaches your provider. "
        "That part is not yours to fix - this report is what to show them.",
    ),
    "verdict.server": (
        "你的线路正常，延迟主要来自服务器距离或路由——换个服务器／节点通常最有效。",
        "你的線路正常，延遲主要來自伺服器距離或路由——換個伺服器／節點通常最有效。",
        "Your line is fine; the delay comes from how far away the server is. Picking a closer "
        "server or node is usually what helps.",
    ),
    "verdict.loss": (
        "有封包丢失——这比延迟更影响游戏和通话，优先处理。",
        "有封包遺失——這比延遲更影響遊戲和通話，優先處理。",
        "Packets are being lost - that hurts games and calls more than latency does.",
    ),
    "verdict.target_down": (
        "目标没有回应（可能挡了 ping 或已离线），但你的网络本身正常。",
        "目標沒有回應（可能擋了 ping 或已離線），但你的網路本身正常。",
        "The target did not answer (it may block ping, or be down) - your own network is fine.",
    ),
    "verdict.no_ping": (
        "这台电脑上找不到可用的 ping 命令，无法做分段诊断（其它功能不受影响）。",
        "這台電腦上找不到可用的 ping 指令，無法做分段診斷（其它功能不受影響）。",
        "No usable ping command on this machine, so the path cannot be split up "
        "(everything else still works).",
    ),
    "verdict.dns": (
        "线路本身正常，但域名解析很慢——网页和游戏都要等它才开始。"
        "把 DNS 改成 8.8.8.8 或 223.5.5.5 通常立刻见效。",
        "線路本身正常，但網域解析很慢——網頁和遊戲都要等它才開始。"
        "把 DNS 改成 8.8.8.8 或 1.1.1.1 通常立刻見效。",
        "The line itself is fine, but name lookups are slow - nothing starts until they "
        "come back. Switching your DNS to 8.8.8.8 or 1.1.1.1 usually fixes it immediately.",
    ),
    "verdict.unknown": ("资料不足，无法判断", "資料不足，無法判斷", "Not enough data to tell"),

    "settings.title": ("设置", "設定", "Settings"),
    "settings.tab.general": ("常规", "一般", "General"),
    "settings.tab.overlay": ("显示", "顯示", "Overlay"),
    "settings.tab.advanced": ("高级", "進階", "Advanced"),
    "settings.tab.about": ("关于", "關於", "About"),

    "general.target": ("监测对象", "監測對象", "What to monitor"),
    "general.target.auto": (
        "自动跟随我正在看的页面", "自動跟隨我正在看的頁面", "Follow whatever I am watching",
    ),
    "general.target.live": ("手动指定直播间", "手動指定直播間", "A live room I pick"),
    "general.target.video": ("手动指定视频", "手動指定影片", "A video I pick"),
    "general.target.app": ("任意应用程序（游戏／通话／浏览器…）", "任意應用程式（遊戲／通話／瀏覽器…）",
                           "Any application (games, calls, browsers…)"),
    "general.target.custom": ("自定义服务器地址", "自訂伺服器位址", "A server address I type"),
    "general.app_name": ("应用程序", "應用程式", "Application"),
    "general.app_follow": (
        "自动跟随当前使用的程序", "自動跟隨目前使用的程式", "Follow whichever app is in front",
    ),
    "general.app_hint": (
        "选一个正在联网的程序，监视器会找出它连的服务器并持续测延迟；"
        "UDP 的游戏会自动改用 ping。",
        "選一個正在連網的程式，監視器會找出它連的伺服器並持續測延遲；"
        "UDP 的遊戲會自動改用 ping。",
        "Pick a program that is on the network: the monitor finds the servers it talks to and "
        "keeps timing them, falling back to ping for UDP games.",
    ),
    "general.app_refresh": ("刷新列表", "重新整理", "Refresh"),
    "general.target_host": ("服务器地址", "伺服器位址", "Server address"),
    "general.target_port": ("端口", "連接埠", "Port"),
    "general.target_hint": (
        "例如游戏服务器、公司 VPN、8.8.8.8。先试 TCP，连不上就用 ping。",
        "例如遊戲伺服器、公司 VPN、8.8.8.8。先試 TCP，連不上就用 ping。",
        "A game server, a VPN gateway, 8.8.8.8 - TCP first, ping if that is refused.",
    ),
    "general.netspeed": (
        "显示全机上传／下载速度", "顯示全機上傳／下載速度", "Show machine upload / download speed",
    ),
    "general.video": ("视频号或链接", "影片編號或連結", "Video ID or URL"),
    "general.video_hint": (
        "支持 BV 号、av 号，或直接粘贴 https://www.bilibili.com/video/BV… （分P 用 ?p=2）。",
        "支援 BV 號、av 號，或直接貼上 https://www.bilibili.com/video/BV…（分P 用 ?p=2）。",
        "A BV id, an av number, or a https://www.bilibili.com/video/BV… URL (?p=2 for a part).",
    ),
    "general.room": ("直播间号或链接", "直播間號或連結", "Room ID or URL"),
    "general.room_hint": (
        "支持粘贴 https://live.bilibili.com/123456 或直接填 123456；留空则只测网络延迟。",
        "支援貼上 https://live.bilibili.com/123456 或直接填 123456；留空則只測網路延遲。",
        "Paste https://live.bilibili.com/123456 or just 123456. Leave empty for network-only mode.",
    ),
    "general.interval": ("探测间隔 (毫秒)", "偵測間隔 (毫秒)", "Probe interval (ms)"),
    "general.sample_window": ("统计窗口 (样本数)", "統計視窗 (樣本數)", "Stats window (samples)"),
    "general.language": ("界面语言", "介面語言", "Language"),
    "general.language_auto": ("跟随系统", "跟隨系統", "System default"),
    "general.autostart": ("开机自动启动", "開機自動啟動", "Start with the system"),
    "general.autostart_unsupported": (
        "当前系统不支持自动设置开机启动，请参考 README。",
        "目前系統不支援自動設定開機啟動，請參考 README。",
        "Automatic autostart is unsupported here; see the README.",
    ),

    "detect.group": ("自动检测", "自動偵測", "Auto-detection"),
    "detect.history": (
        "读取浏览器历史记录（只读）",
        "讀取瀏覽器歷史紀錄（唯讀）",
        "Read the browser history (read-only)",
    ),
    "detect.titles": (
        "用窗口标题识别当前标签页",
        "用視窗標題辨識目前分頁",
        "Match open window titles (Windows)",
    ),
    "detect.bridge": (
        "接收油猴脚本上报（最准）",
        "接收油猴腳本回報（最準）",
        "Accept userscript reports (most accurate)",
    ),
    "detect.client": (
        "读取官方PC客户端正在播放的内容",
        "讀取官方PC用戶端正在播放的內容",
        "Read what the official desktop client is playing",
    ),
    "detect.clipboard": (
        "识别复制的链接（客户端用）",
        "辨識複製的連結（用戶端適用）",
        "Watch for copied links (desktop client)",
    ),
    "detect.remember_titles": (
        "记住窗口标题对应的房间",
        "記住視窗標題對應的房間",
        "Remember which window title is which room",
    ),
    "detect.client_hint": (
        "用官方 PC 客户端时，监视器会直接读客户端自己的记录，不用你动手。"
        "万一读不到（客户端版本不同），在客户端点「分享 → 复制链接」也能立刻切过去。"
        "用命令行加 --detect-report 可以看到到底读到了什么。",
        "用官方 PC 用戶端時，監視器會直接讀用戶端自己的紀錄，不用你動手。"
        "萬一讀不到（用戶端版本不同），在用戶端點「分享 → 複製連結」也能立刻切過去。"
        "用命令列加 --detect-report 可以看到到底讀到了什麼。",
        "With the official desktop client the monitor reads the client's own records, so "
        "there is nothing to do. If a client build stores things differently, share -> copy "
        "link still switches over instantly. Run with --detect-report to see what was found.",
    ),
    "detect.bridge_port": ("脚本上报端口", "腳本回報連接埠", "Bridge port"),
    "detect.window": ("历史记录时间窗口（分钟）", "歷史紀錄時間視窗（分鐘）", "History window (minutes)"),
    "detect.follow_videos": ("也跟随普通视频", "也跟隨一般影片", "Follow ordinary videos too"),
    "detect.interval": ("检测间隔（秒）", "偵測間隔（秒）", "Detection interval (s)"),
    "detect.privacy": (
        "检测只在你的电脑上进行：历史记录会被复制成临时文件后只读打开，只筛选 bilibili.com 的网址，"
        "不会写回、不会上传，也不需要登录。不想用可以关掉这一项。",
        "偵測只在你的電腦上進行：歷史紀錄會被複製成暫存檔後唯讀開啟，只篩選 bilibili.com 的網址，"
        "不會寫回、不會上傳，也不需要登入。不想用可以關掉這一項。",
        "Detection stays on your machine: the history file is copied, opened read-only and filtered "
        "to bilibili.com URLs. Nothing is written back or uploaded, and no login is used. "
        "Turn it off if you would rather not.",
    ),
    "detect.source.manual": ("手动", "手動", "manual"),
    "detect.source.clipboard": ("复制的链接", "複製的連結", "copied link"),
    "detect.source.title": ("窗口标题", "視窗標題", "window title"),
    "menu.phone": ("手机网址…", "手機網址…", "Phone dashboard…"),
    "extras.group": ("同时监测（附加）", "同時監測（附加）", "Also watch"),
    "extras.hint": (
        "除了主要对象，再盯几个目标，一眼看出「只有这个卡」还是「整条线都卡」。"
        "最多 4 个，轮流测量所以不会拖慢主要数字。",
        "除了主要對象，再盯幾個目標，一眼看出「只有這個卡」還是「整條線都卡」。"
        "最多 4 個，輪流量測所以不會拖慢主要數字。",
        "Watch a few more targets beside the main one, to tell \"only this is laggy\" from "
        "\"the whole line is\". Up to four, measured in turn so the main figure stays fast.",
    ),
    "extras.add": ("新增…", "新增…", "Add…"),
    "extras.remove": ("移除", "移除", "Remove"),
    "extras.add_router": ("＋路由器", "＋路由器", "+ Router"),
    "extras.add_dns": ("＋DNS", "＋DNS", "+ DNS"),
    "extras.router": ("路由器", "路由器", "Router"),
    "extras.dns": ("DNS", "DNS", "DNS"),
    "extras.dialog": ("新增监测目标", "新增監測目標", "Add a watch"),
    "extras.kind": ("类型", "類型", "Type"),
    "extras.kind.target": ("服务器地址", "伺服器位址", "Server address"),
    "extras.kind.app": ("应用程序", "應用程式", "Application"),
    "extras.ident": ("地址／程序名", "位址／程式名", "Address or process"),
    "extras.label": ("显示名称", "顯示名稱", "Label"),
    "extras.full": ("最多只能加 4 个", "最多只能加 4 個", "Four is the limit"),
    "extras.no_router": ("找不到路由器地址", "找不到路由器位址", "Could not find the router"),

    "web.group": ("手机仪表板", "手機儀表板", "Phone dashboard"),
    "web.enabled": (
        "让同一网络下的手机也能看", "讓同一網路下的手機也能看", "Let a phone on this network watch",
    ),
    "web.port": ("端口", "連接埠", "Port"),
    "web.code": ("访问码（留空＝不需要）", "存取碼（留空＝不需要）", "Access code (empty = none)"),
    "web.hint": (
        "打开后，手机浏览器输入下面的网址就能看到同一份实时数字，不用装 App，iPhone 安卓都可以。"
        "只读：手机上改不了任何设置。网址只在你的局域网内有效。",
        "開啟後，手機瀏覽器輸入下面的網址就能看到同一份即時數字，不用裝 App，iPhone 安卓都可以。"
        "唯讀：手機上改不了任何設定。網址只在你的區域網路內有效。",
        "Open the address below in a phone browser to watch the same live numbers - no app to "
        "install, iPhone and Android alike. Read-only: nothing can be changed from the phone, "
        "and the address only works on your own network.",
    ),
    "web.url_label": ("手机上打开：", "手機上開啟：", "Open on your phone:"),
    "web.off": ("未开启（在设置里打开）", "未開啟（在設定裡開啟）", "Not enabled (turn it on in Settings)"),
    "web.copied": ("网址已复制到剪贴板", "網址已複製到剪貼簿", "Address copied to the clipboard"),
    "menu.read_clipboard": ("读取剪贴板里的链接", "讀取剪貼簿裡的連結", "Read link from clipboard"),
    "notice.clipboard_read": (
        "已读取剪贴板。若里面是B站链接，马上就会切过去。",
        "已讀取剪貼簿。若裡面是B站連結，馬上就會切過去。",
        "Clipboard read. If it held a Bilibili link, the monitor is switching now.",
    ),
    "detect.source.history": ("历史记录", "歷史紀錄", "history"),
    "detect.source.history+title": ("当前标签页", "目前分頁", "current tab"),
    "detect.source.bridge": ("脚本", "腳本", "userscript"),
    "menu.auto_detect": ("自动跟随观看页面", "自動跟隨觀看頁面", "Follow what I watch"),

    "overlay.enabled": ("显示悬浮窗", "顯示懸浮視窗", "Show overlay window"),
    "overlay.anchor": ("位置模式", "位置模式", "Position mode"),
    "overlay.anchor.free": ("自由拖动", "自由拖曳", "Free (drag me)"),
    "overlay.anchor.screen": ("吸附屏幕角落", "吸附螢幕角落", "Pin to screen corner"),
    "overlay.anchor.window": ("跟随B站窗口", "跟隨B站視窗", "Follow the Bilibili window"),
    "overlay.corner": ("角落", "角落", "Corner"),
    "overlay.corner.top-left": ("左上", "左上", "Top left"),
    "overlay.corner.top-right": ("右上", "右上", "Top right"),
    "overlay.corner.bottom-left": ("左下", "左下", "Bottom left"),
    "overlay.corner.bottom-right": ("右下", "右下", "Bottom right"),
    "overlay.screen": ("屏幕", "螢幕", "Screen"),
    "overlay.screen_primary": ("主屏幕", "主螢幕", "Primary screen"),
    "overlay.offset_x": ("水平偏移", "水平偏移", "Offset X"),
    "overlay.offset_y": ("垂直偏移", "垂直偏移", "Offset Y"),
    "overlay.opacity": ("不透明度", "不透明度", "Opacity"),
    "overlay.scale": ("缩放", "縮放", "Scale"),
    "overlay.on_top": ("总在最前", "總在最前", "Always on top"),
    "overlay.click_through": ("鼠标穿透 (不挡操作)", "滑鼠穿透 (不擋操作)", "Click-through"),
    "overlay.lock": ("锁定位置", "鎖定位置", "Lock position"),
    "overlay.theme": ("主题", "主題", "Theme"),
    "overlay.theme.dark": ("深色", "深色", "Dark"),
    "overlay.theme.light": ("浅色", "淺色", "Light"),
    "overlay.theme.pink": ("粉色", "粉色", "Pink"),
    "overlay.compact": ("紧凑模式 (只显示总延迟)", "緊湊模式 (只顯示總延遲)", "Compact (total only)"),
    "overlay.show_server": ("显示伺服器位置", "顯示伺服器位置", "Show server location"),
    "overlay.show_breakdown": ("显示分项延迟", "顯示分項延遲", "Show breakdown"),
    "overlay.show_sparkline": ("显示折线图", "顯示折線圖", "Show sparkline"),
    "overlay.show_stats": ("显示统计行", "顯示統計行", "Show statistics row"),
    "overlay.follow_keyword": ("窗口标题关键字", "視窗標題關鍵字", "Window title keyword"),
    "overlay.window_unsupported": (
        "跟随窗口目前仅支持 Windows，其它系统会退回到屏幕角落模式。",
        "跟隨視窗目前僅支援 Windows，其它系統會退回螢幕角落模式。",
        "Window following works on Windows only; other systems fall back to a screen corner.",
    ),
    "tray.enabled": ("显示状态栏 (托盘) 图标", "顯示狀態列 (系統匣) 圖示", "Show status bar / tray icon"),
    "tray.show_value": ("在图标上显示数值", "在圖示上顯示數值", "Draw the value on the icon"),

    "advanced.timeout": ("请求超时 (毫秒)", "請求逾時 (毫秒)", "Request timeout (ms)"),
    "advanced.playurl_refresh": ("播放地址刷新 (秒)", "播放位址更新 (秒)", "Play URL refresh (s)"),
    "advanced.rtt_host": ("RTT 探测主机", "RTT 偵測主機", "RTT probe host"),
    "advanced.prefer_hls": ("优先使用 HLS (更精确)", "優先使用 HLS (更精確)", "Prefer HLS (more accurate)"),
    "advanced.auto_cdn": (
        "自动选最快的 CDN 节点", "自動選最快的 CDN 節點", "Pick the fastest CDN edge",
    ),
    "advanced.auto_cdn_hint": (
        "B 站同一个直播间由好几个 CDN 节点提供，播放器只会拿到第一个——快慢差几十毫秒是常事。"
        "打开后会定期比较所有节点，发现明显更快的（快 25ms 且快 20% 以上）就自动换过去，"
        "最短 3 分钟才会再换一次，不会来回跳。只影响本程序的测量，不会改变你播放器用的节点。",
        "B 站同一個直播間由好幾個 CDN 節點提供，播放器只會拿到第一個——快慢差幾十毫秒是常事。"
        "開啟後會定期比較所有節點，發現明顯更快的（快 25ms 且快 20% 以上）就自動換過去，"
        "最短 3 分鐘才會再換一次，不會來回跳。只影響本程式的量測，不會改變你播放器用的節點。",
        "Bilibili serves the same room from several CDN edges and the player takes the first "
        "one, which is often tens of milliseconds slower than the best. This compares them "
        "periodically and moves when one is clearly faster (25 ms and 20% better), at most "
        "once every three minutes so two similar edges cannot trade it back and forth. It "
        "changes what this tool measures, not what your player is using.",
    ),
    "advanced.buffer_segments": ("播放器缓冲分片数", "播放器緩衝分片數", "Player buffer segments"),
    "advanced.frames_in_flight": ("合成器排队帧数", "合成器排隊影格數", "Frames in flight"),
    "advanced.manual_offset": ("显示器输入延迟补偿 (毫秒)", "顯示器輸入延遲補償 (毫秒)", "Panel input lag offset (ms)"),
    "advanced.include_display": ("总延迟包含显示延迟", "總延遲包含顯示延遲", "Include display latency in total"),
    "advanced.audio_offset": ("蓝牙耳机延迟 (毫秒)", "藍牙耳機延遲 (毫秒)", "Bluetooth headset delay (ms)"),
    "advanced.include_audio": ("总延迟包含耳机延迟", "總延遲包含耳機延遲", "Include headset delay in total"),
    "advanced.calibrate_audio": ("校正…", "校正…", "Calibrate..."),
    "advanced.audio_never": ("尚未校正", "尚未校正", "not calibrated yet"),

    # -- the calibration dialog -------------------------------------------
    "audio.title": ("蓝牙耳机延迟校正", "藍牙耳機延遲校正", "Bluetooth delay calibration"),
    "audio.intro": (
        "蓝牙耳机会让声音比画面晚到，通常晚 100 到 250 毫秒。没有任何操作系统会告诉你这个数字，"
        "所以这里用你的耳朵量：先响一声，再闪一下，你调到两者同时发生为止。",
        "藍牙耳機會讓聲音比畫面晚到，通常晚 100 到 250 毫秒。沒有任何作業系統會告訴你這個數字，"
        "所以這裡用你的耳朵量：先響一聲，再閃一下，你調到兩者同時發生為止。",
        "Bluetooth headphones make sound arrive later than the picture, usually by 100-250 ms. "
        "No operating system will tell you that number, so this measures it with your ear: a click "
        "plays, then the panel flashes, and you shift one until the two land together.",
    ),
    "audio.steps": (
        "1. 戴上要量的那副耳机，把音量调到平常听的大小。\n"
        "2. 按「开始」，会听到规律的「哒」声，画面也会规律地闪。\n"
        "3. 拖滑杆，直到你听到的和看到的同时发生。\n"
        "4. 按「保存」。",
        "1. 戴上要量的那副耳機，把音量調到平常聽的大小。\n"
        "2. 按「開始」，會聽到規律的「噠」聲，畫面也會規律地閃。\n"
        "3. 拖滑桿，直到你聽到的和看到的同時發生。\n"
        "4. 按「儲存」。",
        "1. Put on the headphones you want to measure, at the volume you normally use.\n"
        "2. Press Start: you will hear a steady click and see a steady flash.\n"
        "3. Drag the slider until the click and the flash happen at the same moment.\n"
        "4. Press Save.",
    ),
    "audio.watch_here": ("看这里", "看這裡", "Watch here"),
    "audio.start": ("开始", "開始", "Start"),
    "audio.stop": ("停止", "停止", "Stop"),
    "audio.offset_label": ("声音比画面晚", "聲音比畫面晚", "Sound arrives later by"),
    "audio.readout": ("{ms} 毫秒", "{ms} 毫秒", "{ms} ms"),
    "audio.hint_zero": (
        "现在闪光和声音是同时送出的。如果你用蓝牙耳机，应该会先看到闪、后听到声。",
        "現在閃光和聲音是同時送出的。如果你用藍牙耳機，應該會先看到閃、後聽到聲。",
        "Right now the flash and the click are sent together. On Bluetooth you should see the "
        "flash first and hear the click after it.",
    ),
    "audio.hint_adjusting": (
        "调大 = 闪光更晚。调到「闪」和「哒」重合为止。",
        "調大 = 閃光更晚。調到「閃」和「噠」重合為止。",
        "Larger = the flash comes later. Stop when the flash and the click coincide.",
    ),
    "audio.device_note": ("这是哪副耳机", "這是哪副耳機", "Which headphones"),
    "audio.device_hint": ("例如：WH-1000XM4", "例如：WH-1000XM4", "e.g. WH-1000XM4"),
    "audio.save": ("保存", "儲存", "Save"),
    "audio.clear": ("清除校正", "清除校正", "Clear"),
    "audio.close": ("取消", "取消", "Cancel"),
    "audio.unavailable": (
        "这台机器上找不到可以放音的程序，无法校正。",
        "這台機器上找不到可以放音的程式，無法校正。",
        "No way to play a sound was found on this machine, so calibration cannot run.",
    ),
    "audio.failed": (
        "没有声音送出来，所以校正停下来了——对着无声调整只会得到一个错的数字。",
        "沒有聲音送出來，所以校正停下來了——對著無聲調整只會得到一個錯的數字。",
        "No sound came out, so the calibration stopped: adjusting against silence would "
        "only produce a wrong number.",
    ),
    "audio.spawn_caveat": (
        "注意：在这个系统上，每次响声都要另外启动一个播放程序，那段启动时间（数十毫秒）会被算进结果里，"
        "所以量出来的数字会偏大。Windows 上没有这个问题。",
        "注意：在這個系統上，每次響聲都要另外啟動一個播放程式，那段啟動時間（數十毫秒）會被算進結果裡，"
        "所以量出來的數字會偏大。Windows 上沒有這個問題。",
        "Note: on this system each click launches a separate player process, and that startup time "
        "(tens of milliseconds) is counted into the result, so the number will read high. "
        "This does not happen on Windows.",
    ),
    "audio.accuracy": (
        "人耳大约能分辨 20 到 40 毫秒的不同步，所以这个数字的精度就在那个范围。它量的是"
        "「声音比画面晚多少」，不是耳机内部的绝对延迟。",
        "人耳大約能分辨 20 到 40 毫秒的不同步，所以這個數字的精度就在那個範圍。它量的是"
        "「聲音比畫面晚多少」，不是耳機內部的絕對延遲。",
        "People can tell picture and sound apart at around 20-40 ms, so that is the precision of "
        "this number. It measures how much later the sound arrives than the picture, not the "
        "headset's absolute internal delay.",
    ),
    "label.audio": ("耳机", "耳機", "Headset"),
    "label.server": ("伺服器", "伺服器", "Server"),
    "server.at_most_km": ("至多 {km} km", "至多 {km} km", "within {km} km"),
    "server.title": ("目前连到哪里", "目前連到哪裡", "Where you are connected"),
    "server.unknown": ("看不出来", "看不出來", "cannot tell"),
    "server.how": (
        "位置有两个来源。主机名称说得出的时候是准的，但租用公有云的节点和 PCDN 都不会说。"
        "往返时间则对每一台伺服器都有效，不过它只给上限——光速是固定的，"
        "所以回应花了多久，就限制了它最远能在多远。",
        "位置有兩個來源。主機名稱說得出的時候是準的，但租用公有雲的節點和 PCDN 都不會說。"
        "往返時間則對每一台伺服器都有效，不過它只給上限——光速是固定的，"
        "所以回應花了多久，就限制了它最遠能在多遠。",
        "Location comes from two places. The hostname is exact when it says anything, but a "
        "cloud-rented node and a PCDN peer both say nothing. The round trip works for every "
        "server, but only sets a ceiling - light has a fixed speed, so how long the reply took "
        "limits how far away it can be.",
    ),
    "server.ceiling_note": (
        "「至多 N km」是上限，不是估计值。它假设一条笔直的光纤、设备完全不花时间——"
        "两者都不可能——所以真实距离一定更近。",
        "「至多 N km」是上限，不是估計值。它假設一條筆直的光纖、設備完全不花時間——"
        "兩者都不可能——所以真實距離一定更近。",
        "A ceiling, not an estimate. It assumes a dead-straight fibre and equipment that takes "
        "no time at all - neither is ever true - so the real distance is always shorter.",
    ),
    "advanced.csv": ("记录到 CSV 文件", "記錄到 CSV 檔案", "Log samples to CSV"),
    "advanced.csv_hint": (
        "文件位于配置目录的 logs 子目录，自动轮转。",
        "檔案位於設定目錄的 logs 子目錄，會自動輪替。",
        "Written to the logs folder next to the config, with rotation.",
    ),
    "advanced.good": ("绿色阈值 (毫秒)", "綠色門檻 (毫秒)", "Good threshold (ms)"),
    "advanced.warn": ("黄色阈值 (毫秒)", "黃色門檻 (毫秒)", "Warning threshold (ms)"),

    "about.body": (
        "开源、免费、无需登录。测量哔哩哔哩直播从服务器到客户端再到画面的延迟。",
        "開源、免費、無需登入。測量嗶哩嗶哩直播從伺服器到用戶端再到畫面的延遲。",
        "Free and open source, no login required. Measures Bilibili live delay from server to client to screen.",
    ),
    "about.repo": ("项目主页", "專案首頁", "Project page"),
    "about.version": ("版本", "版本", "Version"),

    "button.ok": ("确定", "確定", "OK"),
    "button.cancel": ("取消", "取消", "Cancel"),
    "button.apply": ("应用", "套用", "Apply"),
    "button.defaults": ("恢复默认", "恢復預設", "Restore defaults"),

    "notice.tray_missing": (
        "系统托盘不可用，已改为只显示悬浮窗。",
        "系統匣不可用，已改為只顯示懸浮視窗。",
        "No system tray available; showing the overlay only.",
    ),
    "notice.copied": ("诊断信息已复制到剪贴板。", "診斷資訊已複製到剪貼簿。", "Diagnostics copied to the clipboard."),
    "tray.tooltip": (
        "{title}\n总延迟 {total}\n网络 {network} / 推流 {stream} / 显示 {display}\n{status}",
        "{title}\n總延遲 {total}\n網路 {network} / 推流 {stream} / 顯示 {display}\n{status}",
        "{title}\nTotal {total}\nNetwork {network} / Stream {stream} / Display {display}\n{status}",
    ),
    "tray.tooltip_video": (
        "{title}\n视频总延迟 {total}\n网络 {network} / 起播 {stream} / 显示 {display}\n带宽 {speed}\n{status}",
        "{title}\n影片總延遲 {total}\n網路 {network} / 起播 {stream} / 顯示 {display}\n頻寬 {speed}\n{status}",
        "{title}\nVideo total {total}\nNetwork {network} / Startup {stream} / Display {display}\n"
        "Speed {speed}\n{status}",
    ),
    "tray.tooltip_app": (
        "{title}\n延迟 {total}\n服务器 {host}\n连接 {conns}   ↓{down} ↑{up}\n{status}",
        "{title}\n延遲 {total}\n伺服器 {host}\n連線 {conns}   ↓{down} ↑{up}\n{status}",
        "{title}\nLatency {total}\nServer {host}\nSockets {conns}   ↓{down} ↑{up}\n{status}",
    ),
    "notice.stall": (
        "监测中断：连不上服务器，正在重试…",
        "監測中斷：連不上伺服器，正在重試…",
        "Lost the server — retrying…",
    ),
    "notice.spike": (
        "延迟突增：{value}（平常约 {baseline}）",
        "延遲突增：{value}（平常約 {baseline}）",
        "Latency spike: {value} (normally around {baseline})",
    ),
    "general.notify": (
        "卡顿／延迟突增时弹出提示", "卡頓／延遲突增時彈出提示", "Notify me about stalls and spikes",
    ),
    "notice.hidden_hint": (
        "悬浮窗已隐藏，可从托盘图标重新打开。",
        "懸浮視窗已隱藏，可從系統匣圖示重新開啟。",
        "Overlay hidden. Reopen it from the tray icon.",
    ),

    # --------------------------------------------------------- history window
    "menu.history": ("延迟历史…", "延遲歷史…", "Latency history…"),
    "menu.report": ("导出体检报告…", "匯出體檢報告…", "Export a health report…"),
    "history.title": ("延迟历史", "延遲歷史", "Latency history"),
    "history.range.1h": ("1 小时", "1 小時", "1 hour"),
    "history.range.6h": ("6 小时", "6 小時", "6 hours"),
    "history.range.24h": ("24 小时", "24 小時", "24 hours"),
    "history.range.all": ("全部", "全部", "All"),
    "history.export": ("导出体检报告", "匯出體檢報告", "Export report"),
    "history.copy": ("复制摘要", "複製摘要", "Copy summary"),
    "history.empty": (
        "还没有历史数据。让它跑几分钟，这里就会出现走势。",
        "還沒有歷史資料。讓它跑幾分鐘，這裡就會出現走勢。",
        "No history yet. Leave it running for a few minutes and the trend appears here.",
    ),
    "history.group": ("历史记录", "歷史紀錄", "History"),
    "history.enabled": (
        "保存延迟历史（用于走势图和体检报告）",
        "儲存延遲歷史（用於走勢圖和體檢報告）",
        "Keep a latency history (for the chart and the report)",
    ),
    "history.keep": ("保留时长（小时）", "保留時長（小時）", "Keep for (hours)"),
    "history.clear": ("清空历史", "清空歷史", "Clear history"),
    "history.hint": (
        "每分钟只存一行摘要（均值／最好／最差／丢失），所以一天约 130 KB，"
        "关掉程序也不会丢。文件在配置目录里，随时可以删。",
        "每分鐘只存一行摘要（均值／最好／最差／遺失），所以一天約 130 KB，"
        "關掉程式也不會丟。檔案在設定目錄裡，隨時可以刪。",
        "One summary row per minute (average, best, worst, loss), so a day costs about "
        "130 KB and survives a restart. The file sits in the config folder and can be "
        "deleted at any time.",
    ),

    # ---------------------------------------------------------------- report
    "report.title": ("网络体检报告", "網路體檢報告", "Connection health report"),
    "report.generated": ("生成时间", "產生時間", "Generated"),
    "report.window": ("统计范围", "統計範圍", "Window"),
    "report.watching": ("监测对象", "監測對象", "Watching"),
    "report.chart": ("延迟走势", "延遲走勢", "Latency over time"),
    "report.worst": ("最不稳定的时段", "最不穩定的時段", "The roughest hour"),
    "report.segments": ("分段诊断", "分段診斷", "Path segments"),
    "report.extras": ("其他监测目标", "其他監測目標", "Other watches"),
    "report.uptime": ("探测成功率", "偵測成功率", "Probes answered"),
    "report.samples": ("样本数", "樣本數", "Samples"),
    "report.stalls": ("卡顿", "卡頓", "Stalls"),
    "report.spikes": ("延迟突增", "延遲突增", "Spikes"),
    "report.hours": ("最近 {n} 小时", "最近 {n} 小時", "Last {n} h"),
    "report.all": ("全部记录", "全部紀錄", "Everything recorded"),
    "report.no_data": (
        "还没有足够的历史数据", "還沒有足夠的歷史資料", "Not enough history yet",
    ),
    "report.legend_avg": ("平均延迟", "平均延遲", "average"),
    "report.legend_range": ("每分钟最好～最差", "每分鐘最好～最差", "best to worst, per minute"),
    "report.legend_marks": ("卡顿／突增", "卡頓／突增", "stalls and spikes"),
    "report.worst_line": (
        "{time}　平均 {avg}，最高 {max}，{stalls} 次卡顿或突增",
        "{time}　平均 {avg}，最高 {max}，{stalls} 次卡頓或突增",
        "{time} — average {avg}, worst {max}, {stalls} stalls or spikes",
    ),
    "report.no_trouble": (
        "这段时间没有卡顿，也没有延迟突增。",
        "這段時間沒有卡頓，也沒有延遲突增。",
        "No stalls and no spikes in this window.",
    ),
    "report.privacy": (
        "这份报告只包含延迟数字、你家内网地址和被测服务器；不含公网 IP、账号、"
        "浏览记录或任何 Cookie。",
        "這份報告只包含延遲數字、你家內網位址和被測伺服器；不含公網 IP、帳號、"
        "瀏覽紀錄或任何 Cookie。",
        "This report contains latency figures, addresses inside your own home network and "
        "the server being measured. No public IP, no account, no browsing history, no cookies.",
    ),
    "report.saved": ("报告已保存到：", "報告已儲存到：", "Report saved to:"),
    "report.copied": ("摘要已复制到剪贴板", "摘要已複製到剪貼簿", "Summary copied to the clipboard"),
    "report.failed": ("无法写入报告文件", "無法寫入報告檔案", "Could not write the report file"),
    "report.findings": ("卡顿时发生了什么", "卡頓時發生了什麼", "What happened when it broke"),
    "report.switches": ("自动换过的线路", "自動換過的線路", "Faster edges it moved to"),
    "report.switches_hint": (
        "同一个直播间由多个 CDN 节点提供，播放器只会拿到第一个。监视器发现明显更快的节点时会自动换过去。",
        "同一個直播間由多個 CDN 節點提供，播放器只會拿到第一個。監視器發現明顯更快的節點時會自動換過去。",
        "The same room is served from several CDN edges and the player just takes the first "
        "one. When a clearly faster edge exists, the monitor moves to it.",
    ),
    "report.auto_check": ("自动检查", "自動檢查", "checked automatically"),

    # ------------------------------------------------------- before and after
    "menu.mark": ("标记此刻（我改了设置）…", "標記此刻（我改了設定）…", "Mark this moment…"),
    "compare.title": ("我改的设置有用吗", "我改的設定有用嗎", "Did the change help?"),
    "compare.hint": (
        "前后用的是一样长的时间窗口，取两边都有资料的较短那段，"
        "免得拿一整晚的「之前」去比五分钟的「之后」。",
        "前後用的是一樣長的時間視窗，取兩邊都有資料的較短那段，"
        "免得拿一整晚的「之前」去比五分鐘的「之後」。",
        "Both sides use the same length of time - the shorter of what is available "
        "either side - so a whole evening of \"before\" is never compared with five "
        "minutes of \"after\".",
    ),
    "compare.better": ("好转了，快了 {value}", "好轉了，快了 {value}", "Better by {value}"),
    "compare.worse": ("反而差了 {value}", "反而差了 {value}", "Worse by {value}"),
    "compare.same": ("没有明显差别", "沒有明顯差別", "No real difference"),
    "compare.unclear": ("资料不够，看不出来", "資料不夠，看不出來", "Not enough data to tell"),
    "compare.span_min": ("前后各 {n} 分钟", "前後各 {n} 分鐘", "{n} min either side"),
    "compare.span_hour": ("前后各 {n} 小时", "前後各 {n} 小時", "{n} h either side"),
    "compare.dialog": ("标记此刻", "標記此刻", "Mark this moment"),
    "compare.prompt": (
        "你刚才改了什么？（例如：换成 5GHz、DNS 改 8.8.8.8、换了网线）",
        "你剛才改了什麼？（例如：換成 5GHz、DNS 改 8.8.8.8、換了網線）",
        "What did you just change? (for example: moved to 5GHz, DNS to 8.8.8.8, "
        "plugged in a cable)",
    ),
    "compare.marked": (
        "已标记。让它再跑一阵子，报告里就会出现前后对照。",
        "已標記。讓它再跑一陣子，報告裡就會出現前後對照。",
        "Marked. Leave it running a while and the report will show the before and after.",
    ),
    "compare.waiting": (
        "还在收集「之后」的资料", "還在收集「之後」的資料", "still collecting the \"after\"",
    ),
    "history.markers": ("标记", "標記", "Markers"),

    # --------------------------------------------------------------- speed test
    "menu.speedtest": ("测一下网速…", "測一下網速…", "Test my speed…"),
    "cdn.op.bilibili": ("B 站自建节点", "B 站自建節點", "Bilibili's own edge"),
    "cdn.op.aliyun": ("阿里云 CDN", "阿里雲 CDN", "Alibaba Cloud CDN"),
    "cdn.op.tencent": ("腾讯云 CDN", "騰訊雲 CDN", "Tencent Cloud CDN"),
    "cdn.op.huawei": ("华为云 CDN", "華為雲 CDN", "Huawei Cloud CDN"),
    "cdn.op.baidu": ("百度云 CDN", "百度雲 CDN", "Baidu Cloud CDN"),
    "cdn.op.kingsoft": ("金山云 CDN", "金山雲 CDN", "Kingsoft Cloud CDN"),
    "cdn.op.wangsu": ("网宿 CDN", "網宿 CDN", "Wangsu CDN"),
    "cdn.op.akamai": ("Akamai", "Akamai", "Akamai"),
    "cdn.op.peer": ("PCDN 边缘节点（别人家的宽带）", "PCDN 邊緣節點（別人家的寬頻）", "Peer-assisted node (someone's home line)"),
    "cdn.peer.warn": (
        "这是 PCDN／P2P 节点，不是机房机器——它其实是别人家的宽带在卖闲置上行。线路测起来正常却一直卡，很常见的原因就是被分到这种节点。",
        "這是 PCDN／P2P 節點，不是機房機器——它其實是別人家的寬頻在賣閒置上行。線路測起來正常卻一直卡，很常見的原因就是被分到這種節點。",
        "A peer-assisted node, not a datacentre machine - a home connection reselling spare upstream. Being handed one is a common reason for stuttering on a line that tests fine.",
    ),
    "cdn.isp.telecom": ("中国电信", "中國電信", "China Telecom"),
    "cdn.isp.unicom": ("中国联通", "中國聯通", "China Unicom"),
    "cdn.isp.mobile": ("中国移动", "中國移動", "China Mobile"),
    "cdn.isp.bgp": ("BGP 多线", "BGP 多線", "BGP multi-carrier"),
    "cdn.isp.edu": ("教育网", "教育網", "CERNET"),
    "cdn.region.mainland": ("中国大陆", "中國大陸", "mainland China"),
    "cdn.region.hongkong": ("香港", "香港", "Hong Kong"),
    "cdn.region.taiwan": ("台湾", "台灣", "Taiwan"),
    "cdn.region.singapore": ("新加坡", "新加坡", "Singapore"),
    "cdn.region.japan": ("日本", "日本", "Japan"),
    "cdn.region.us": ("美国", "美國", "United States"),
    "cdn.region.overseas": ("海外节点", "海外節點", "overseas node"),
    "pingcmp.title": ("为什么跟 ping 不一样", "為什麼跟 ping 不一樣", "Why this does not match ping"),
    "pingcmp.host": ("主机名", "主機名", "Hostname"),
    "pingcmp.address": ("实际连到", "實際連到", "Connected to"),
    "pingcmp.server": ("这台是", "這台是", "That server is"),
    "pingcmp.failed": ("量不到", "量不到", "Could not measure"),
    "pingcmp.none": ("没有回应", "沒有回應", "no answer"),
    "pingcmp.best": ("最快", "最快", "best"),
    "pingcmp.median": ("中位数", "中位數", "median"),
    "pingcmp.row.tcp": ("TCP 握手（本程式用的）", "TCP 握手（本程式用的）", "TCP handshake (what this app uses)"),
    "pingcmp.row.icmp": ("ICMP ping（CMD 用的）", "ICMP ping（CMD 用的）", "ICMP ping (what CMD uses)"),
    "pingcmp.row.dns": ("DNS 解析", "DNS 解析", "DNS lookup"),
    "pingcmp.dns_note": ("（已经不算进上面的数字里）", "（已經不算進上面的數字裡）", "(no longer counted in the figures above)"),
    "pingcmp.gap": ("差距（TCP 减 ICMP）", "差距（TCP 減 ICMP）", "Gap (TCP minus ICMP)"),
    "pingcmp.verdict.agree": (
        "两边一致。你在 CMD 里如果量到差很多，那多半是 ping 的对象根本不是这台机器——比如 ping 的是 www.bilibili.com，而实际给你推流的是上面这台 CDN 边缘节点。",
        "兩邊一致。你在 CMD 裡如果量到差很多，那多半是 ping 的對象根本不是這台機器——比如 ping 的是 www.bilibili.com，而實際給你推流的是上面這台 CDN 邊緣節點。",
        "The two agree. A large gap against your own terminal almost certainly means ping was aimed at a different machine - the front door rather than the CDN edge above, which is what actually serves the stream.",
    ),
    "pingcmp.verdict.small": (
        "差一点点，属于正常。TCP 握手要走到真正终结连接的那台机器，ICMP 可能由更前面的设备代答。",
        "差一點點，屬於正常。TCP 握手要走到真正終結連線的那台機器，ICMP 可能由更前面的設備代答。",
        "A small gap, which is normal: the handshake has to reach the machine that terminates the connection, while ICMP may be answered by something in front of it.",
    ),
    "pingcmp.verdict.wide": (
        "差很多。这台机器对 ICMP 和 TCP 的处理明显不同——路由器和 CDN 常把 ICMP 丢到低优先级、限速，或干脆由前面的设备代答。这种情况下 ping 的数字不能拿来判断你看直播会不会卡，TCP 的才算数。",
        "差很多。這台機器對 ICMP 和 TCP 的處理明顯不同——路由器和 CDN 常把 ICMP 丟到低優先級、限速，或乾脆由前面的設備代答。這種情況下 ping 的數字不能拿來判斷你看直播會不會卡，TCP 的才算數。",
        "A wide gap: this machine treats ICMP and TCP visibly differently. Edges and routers commonly deprioritise or rate limit ICMP, or answer it from a box in front. Where that happens the ping figure cannot tell you whether the stream will stutter; the TCP one can.",
    ),
    "pingcmp.verdict.no_icmp": (
        "这台机器不回 ICMP，所以 ping 量不到它——但 TCP 通，直播照样看得成。很多 CDN 边缘节点就是这样设定的，不代表有问题。",
        "這台機器不回 ICMP，所以 ping 量不到它——但 TCP 通，直播照樣看得成。很多 CDN 邊緣節點就是這樣設定的，不代表有問題。",
        "This machine does not answer ICMP, so ping cannot measure it at all - while TCP connects fine and the stream plays. Many CDN edges are configured this way; it is not a fault.",
    ),
    "pingcmp.verdict.no_tcp": (
        "TCP 连不上这台机器，没办法比对。",
        "TCP 連不上這台機器，沒辦法比對。",
        "TCP could not reach this machine, so there is nothing to compare.",
    ),
    "pingcmp.footer": (
        "拿这个跟 CMD 的 ping 比之前，先确认你 ping 的是上面那个「实际连到」的位址。",
        "拿這個跟 CMD 的 ping 比之前，先確認你 ping 的是上面那個「實際連到」的位址。",
        "Before comparing this with ping in a terminal, check that you are pinging the address listed above as what it connected to.",
    ),
    "cdn.where": ("伺服器位置", "伺服器位置", "Server"),
    "cdn.unknown": ("主机名看不出位置", "主機名看不出位置", "location not stated in the name"),
    "cdn.pr.beijing": ("北京", "北京", "Beijing"),
    "cdn.pr.shanghai": ("上海", "上海", "Shanghai"),
    "cdn.pr.tianjin": ("天津", "天津", "Tianjin"),
    "cdn.pr.chongqing": ("重庆", "重慶", "Chongqing"),
    "cdn.pr.guangdong": ("广东", "廣東", "Guangdong"),
    "cdn.pr.jiangsu": ("江苏", "江蘇", "Jiangsu"),
    "cdn.pr.zhejiang": ("浙江", "浙江", "Zhejiang"),
    "cdn.pr.shandong": ("山东", "山東", "Shandong"),
    "cdn.pr.hubei": ("湖北", "湖北", "Hubei"),
    "cdn.pr.hunan": ("湖南", "湖南", "Hunan"),
    "cdn.pr.henan": ("河南", "河南", "Henan"),
    "cdn.pr.hebei": ("河北", "河北", "Hebei"),
    "cdn.pr.sichuan": ("四川", "四川", "Sichuan"),
    "cdn.pr.fujian": ("福建", "福建", "Fujian"),
    "cdn.pr.anhui": ("安徽", "安徽", "Anhui"),
    "cdn.pr.jiangxi": ("江西", "江西", "Jiangxi"),
    "cdn.pr.liaoning": ("辽宁", "遼寧", "Liaoning"),
    "cdn.pr.jilin": ("吉林", "吉林", "Jilin"),
    "cdn.pr.heilongjiang": ("黑龙江", "黑龍江", "Heilongjiang"),
    "cdn.pr.shaanxi": ("陕西", "陝西", "Shaanxi"),
    "cdn.pr.shanxi": ("山西", "山西", "Shanxi"),
    "cdn.pr.guangxi": ("广西", "廣西", "Guangxi"),
    "cdn.pr.guizhou": ("贵州", "貴州", "Guizhou"),
    "cdn.pr.yunnan": ("云南", "雲南", "Yunnan"),
    "cdn.pr.gansu": ("甘肃", "甘肅", "Gansu"),
    "cdn.pr.ningxia": ("宁夏", "寧夏", "Ningxia"),
    "cdn.pr.qinghai": ("青海", "青海", "Qinghai"),
    "cdn.pr.xinjiang": ("新疆", "新疆", "Xinjiang"),
    "cdn.pr.xizang": ("西藏", "西藏", "Tibet"),
    "cdn.pr.neimenggu": ("内蒙古", "內蒙古", "Inner Mongolia"),
    "cdn.pr.hainan": ("海南", "海南", "Hainan"),
    "cdn.city.yichang": ("宜昌", "宜昌", "Yichang"),
    "cdn.city.wuhan": ("武汉", "武漢", "Wuhan"),
    "cdn.city.nanjing": ("南京", "南京", "Nanjing"),
    "cdn.city.suzhou": ("苏州", "蘇州", "Suzhou"),
    "cdn.city.hangzhou": ("杭州", "杭州", "Hangzhou"),
    "cdn.city.ningbo": ("宁波", "寧波", "Ningbo"),
    "cdn.city.guangzhou": ("广州", "廣州", "Guangzhou"),
    "cdn.city.shenzhen": ("深圳", "深圳", "Shenzhen"),
    "cdn.city.dongguan": ("东莞", "東莞", "Dongguan"),
    "cdn.city.chengdu": ("成都", "成都", "Chengdu"),
    "cdn.city.qingdao": ("青岛", "青島", "Qingdao"),
    "cdn.city.jinan": ("济南", "濟南", "Jinan"),
    "cdn.city.fuzhou": ("福州", "福州", "Fuzhou"),
    "cdn.city.xiamen": ("厦门", "廈門", "Xiamen"),
    "cdn.city.zhengzhou": ("郑州", "鄭州", "Zhengzhou"),
    "cdn.city.changsha": ("长沙", "長沙", "Changsha"),
    "cdn.city.hefei": ("合肥", "合肥", "Hefei"),
    "cdn.city.shenyang": ("沈阳", "瀋陽", "Shenyang"),
    "cdn.city.xian": ("西安", "西安", "Xi'an"),
    "cdn.city.nanchang": ("南昌", "南昌", "Nanchang"),
    "edge.title": ("你被分到哪些节点", "你被分到哪些節點", "Which edges you were given"),
    "edge.col_host": ("节点", "節點", "Edge"),
    "edge.col_avg": ("平均延迟", "平均延遲", "Average"),
    "edge.col_share": ("占多少时间", "佔多少時間", "Share of time"),
    "edge.col_stalls": ("卡顿", "卡頓", "Stalls"),
    "edge.differs": (
        "差别很大：在 {worst} 上比在 {best} 上慢了 {diff} ms，而你有 {share}% 的时间在慢的那个上面。这就是「有时候卡有时候不卡」的原因——不是你的带宽，是你被分到哪台机器。",
        "差別很大：在 {worst} 上比在 {best} 上慢了 {diff} ms，而你有 {share}% 的時間在慢的那個上面。這就是「有時候卡有時候不卡」的原因——不是你的頻寬，是你被分到哪台機器。",
        "It matters: {worst} runs {diff} ms slower than {best}, and you spent {share}% of the time on the slower one. That is what \"sometimes it stutters\" usually is - not bandwidth, but which machine you were handed.",
    ),
    "edge.same": (
        "你用过的几个节点表现差不多，所以卡顿不是节点选择造成的。",
        "你用過的幾個節點表現差不多，所以卡頓不是節點選擇造成的。",
        "The edges you were given performed about the same, so the choice of edge is not what makes it stutter.",
    ),
    "edge.only_one": (
        "整段时间都在同一个节点上，没有别的可以比。",
        "整段時間都在同一個節點上，沒有別的可以比。",
        "You were on one edge the whole time, so there is nothing to compare it with.",
    ),
    "edge.not_enough": (
        "记录还不够久，看不出节点之间的差别（每个节点至少要 10 分钟）。",
        "紀錄還不夠久，看不出節點之間的差別（每個節點至少要 10 分鐘）。",
        "Not enough recorded yet to compare edges (each needs at least ten minutes).",
    ),
    "edge.none": ("没有节点资讯", "沒有節點資訊", "No edge recorded"),

    # -- which wireless network carried it -------------------------------
    "link.title": ("你用了哪些无线网路", "你用了哪些無線網路", "Which wireless links you used"),
    "link.col_host": ("无线网路", "無線網路", "Link"),
    "link.col_signal": ("讯号", "訊號", "Signal"),
    "link.col_roams": ("换 AP", "換 AP", "Roams"),
    "link.differs": (
        "差别很大：在 {worst} 上比在 {best} 上慢了 {diff} ms，而你有 {share}% 的时间在慢的那个上面。这个跟节点不一样——这个你自己就能换。",
        "差別很大：在 {worst} 上比在 {best} 上慢了 {diff} ms，而你有 {share}% 的時間在慢的那個上面。這個跟節點不一樣——這個你自己就能換。",
        "It matters: {worst} runs {diff} ms slower than {best}, and you spent {share}% of the time on the slower one. Unlike the CDN edge, this one is yours to change.",
    ),
    "link.same": (
        "你用过的几个无线网路表现差不多，所以卡顿不是选到哪个网路造成的。",
        "你用過的幾個無線網路表現差不多，所以卡頓不是選到哪個網路造成的。",
        "The wireless links you used performed about the same, so which one you were on is not what makes it stutter.",
    ),
    "link.only_one": (
        "整段时间都在同一个无线网路上，没有别的可以比。如果你的路由器同时有 2.4 GHz 和 5 GHz，可以两个都用一阵子再回来看。",
        "整段時間都在同一個無線網路上，沒有別的可以比。如果你的路由器同時有 2.4 GHz 和 5 GHz，可以兩個都用一陣子再回來看。",
        "You were on one wireless link the whole time, so there is nothing to compare it with. If your router offers both 2.4 GHz and 5 GHz, use each for a while and come back.",
    ),
    "link.not_enough": (
        "记录还不够久，看不出无线网路之间的差别（每个至少要 10 分钟）。",
        "紀錄還不夠久，看不出無線網路之間的差別（每個至少要 10 分鐘）。",
        "Not enough recorded yet to compare wireless links (each needs at least ten minutes).",
    ),
    "link.none": ("没有无线资讯（可能是有线连接）", "沒有無線資訊（可能是有線連接）", "No wireless recorded (probably a wired connection)"),
    "link.wired": ("这台机器是有线连接。", "這台機器是有線連接。", "This machine is on a wired connection."),

    "signal.title": ("讯号好的时候 vs 讯号差的时候", "訊號好的時候 vs 訊號差的時候", "Strong signal versus weak"),
    "signal.col_when": ("讯号", "訊號", "Signal"),
    "signal.strong": ("讯号好", "訊號好", "Strong"),
    "signal.weak": ("讯号弱", "訊號弱", "Weak"),
    "signal.differs": (
        "讯号弱的时候慢了 {diff} ms，而讯号弱的时间占了 {share}%。这是你家里的无线讯号，不是网路本身——"
        "靠近路由器、把它从柜子或角落里移出来，或者插网路线。",
        "訊號弱的時候慢了 {diff} ms，而訊號弱的時間佔了 {share}%。這是你家裡的無線訊號，不是網路本身——"
        "靠近路由器、把它從櫃子或角落裡移出來，或者插網路線。",
        "The weak-signal minutes ran {diff} ms slower, and they were {share}% of the time. "
        "That is the wireless in your home, not the internet - move closer to the router, get it "
        "out of the cupboard, or plug in a cable.",
    ),
    "signal.same": (
        "讯号强弱的时候表现差不多，所以卡顿不是讯号造成的。",
        "訊號強弱的時候表現差不多，所以卡頓不是訊號造成的。",
        "Strong and weak minutes performed about the same, so the signal is not what makes it stutter.",
    ),
    "signal.always_strong": (
        "整段时间讯号都很好，所以卡顿不是讯号造成的。",
        "整段時間訊號都很好，所以卡頓不是訊號造成的。",
        "The signal was strong throughout, so it is not what makes it stutter.",
    ),
    "signal.always_weak": (
        "整段时间讯号都偏弱（平均 {pct}%）。没有好讯号的时段可以对照，但这个强度本身就值得先处理——"
        "靠近路由器，或把它换个位置。",
        "整段時間訊號都偏弱（平均 {pct}%）。沒有好訊號的時段可以對照，但這個強度本身就值得先處理——"
        "靠近路由器，或把它換個位置。",
        "The signal was weak throughout (averaging {pct}%). There is no strong stretch to compare "
        "against, but that strength is worth dealing with on its own - move closer to the router, "
        "or move the router.",
    ),
    "signal.not_enough": (
        "记录还不够久，看不出讯号强弱的差别（每种至少要 10 分钟）。",
        "紀錄還不夠久，看不出訊號強弱的差別（每種至少要 10 分鐘）。",
        "Not enough recorded yet to compare strong and weak signal (each needs ten minutes).",
    ),
    "action.signal": (
        "靠近路由器，或把路由器从柜子／角落里移出来——讯号弱的时段明显比较慢",
        "靠近路由器，或把路由器從櫃子／角落裡移出來——訊號弱的時段明顯比較慢",
        "Move closer to the router, or get the router out of the cupboard - the weak-signal "
        "stretches were measurably slower",
    ),
    "action.because.signal": (
        "讯号弱的时候慢很多，而且那是你能改的",
        "訊號弱的時候慢很多，而且那是你能改的",
        "the weak-signal minutes were much slower, and that is yours to change",
    ),
    "action.switch_band": (
        "换到比较快的那个无线网路（通常是 5 GHz 那个）",
        "換到比較快的那個無線網路（通常是 5 GHz 那個）",
        "Move to the faster wireless network (usually the 5 GHz one)",
    ),
    "action.because.link": (
        "两个无线网路之间差很多，而且你能自己换",
        "兩個無線網路之間差很多，而且你能自己換",
        "the wireless links differ measurably, and that one is yours to change",
    ),
    "action.roaming": (
        "路由器／延伸器在把你转来转去。把装置固定在讯号最好的那台，或关掉延伸器试试",
        "路由器／延伸器在把你轉來轉去。把裝置固定在訊號最好的那台，或關掉延伸器試試",
        "Your router or repeater keeps handing you between access points. Pin the device to the strongest one, or try turning the repeater off",
    ),
    "action.because.roams": (
        "这段时间换了好几次 AP，每次换手都会断一到三秒",
        "這段時間換了好幾次 AP，每次換手都會斷一到三秒",
        "the access point changed several times, and each handover costs one to three seconds",
    ),
    "action.bt_interference": (
        "你的 Wi-Fi 在 2.4 GHz，蓝牙也在 2.4 GHz——换到 5 GHz 可以让它们不要抢",
        "你的 Wi-Fi 在 2.4 GHz，藍牙也在 2.4 GHz——換到 5 GHz 可以讓它們不要搶",
        "Your Wi-Fi is on 2.4 GHz and so is Bluetooth - moving to 5 GHz stops them competing",
    ),
    "action.because.bt_band": (
        "这不是量到的，是频段本身的事实：2.4 GHz Wi-Fi 和蓝牙共用同一段无线电",
        "這不是量到的，是頻段本身的事實：2.4 GHz Wi-Fi 和藍牙共用同一段無線電",
        "not measured - a fact about the band itself: 2.4 GHz Wi-Fi and Bluetooth share the same radio spectrum",
    ),
    "pattern.title": ("什么时候比较卡", "什麼時候比較卡", "When it is bad"),
    "pattern.found": (
        "有时段性：{when} 明显比平常差（{bad} ms，平常 {overall} ms）。会跟着时钟走的通常是壅塞——晚高峰、跨境线路挤，这一段不是你家设备能解决的。",
        "有時段性：{when} 明顯比平常差（{bad} ms，平常 {overall} ms）。會跟著時鐘走的通常是壅塞——晚尖峰、跨境線路擠，這一段不是你家設備能解決的。",
        "There is a pattern: {when} is clearly worse than usual ({bad} ms against {overall} ms). Something that follows the clock is congestion - peak hours, a busy cross-border link - and that is not something your own equipment can fix.",
    ),
    "pattern.none": (
        "没有时段性——每个时段都差不多。这反而排掉了「晚高峰壅塞」这一类原因，问题比较可能在固定的地方（线路、设备、或某个节点）。",
        "沒有時段性——每個時段都差不多。這反而排掉了「晚尖峰壅塞」這一類原因，問題比較可能在固定的地方（線路、設備、或某個節點）。",
        "No pattern - every hour looks about the same. That rules out the whole family of clock-shaped causes like peak-hour congestion, and points at something constant instead: the line, the equipment, or a particular edge.",
    ),
    "pattern.not_enough": (
        "记录还不够久，看不出时段性（大概要连续记两三天）。",
        "紀錄還不夠久，看不出時段性（大概要連續記兩三天）。",
        "Not enough recorded to see a pattern yet - it needs a couple of days.",
    ),
    "pattern.no_data": ("还没有记录", "還沒有紀錄", "Nothing recorded yet"),
    "pattern.covered": ("涵盖 {days} 天", "涵蓋 {days} 天", "covering {days} days"),
    "pattern.range": ("{start}:00–{end}:59", "{start}:00–{end}:59", "{start}:00-{end}:59"),
    "action.title": ("那我该怎么办", "那我該怎麼辦", "What to try"),
    "action.because": ("依据", "依據", "because"),
    "action.none": ("这段时间没量到值得处理的问题。", "這段時間沒量到值得處理的問題。", "Nothing worth acting on was measured in this period."),
    "action.not_yours": (
        "上面这些没有一项是你家里能修的。能做的是：降一档画质、错开尖峰时段，或换一个走不同线路的播放器／CDN。",
        "上面這些沒有一項是你家裡能修的。能做的是：降一檔畫質、錯開尖峰時段，或換一個走不同線路的播放器／CDN。",
        "None of the above is fixable from your side. What is left: drop one quality step, avoid the peak hours, or use a player or CDN that takes a different route.",
    ),
    "action.peer_node": (
        "重开播放器（或切一次画质）让服务器重新分配节点——你被分到的是 PCDN 节点",
        "重開播放器（或切一次畫質）讓伺服器重新分配節點——你被分到的是 PCDN 節點",
        "Reopen the player, or switch quality once, to be reassigned - you were given a peer-assisted node",
    ),
    "action.edge_reassign": (
        "重开播放器让服务器重新分配节点，并确认设定里的「自动选最快的 CDN」是开着的",
        "重開播放器讓伺服器重新分配節點，並確認設定裡的「自動選最快的 CDN」是開著的",
        "Reopen the player to be reassigned, and check that automatic CDN selection is on",
    ),
    "action.peak_hours": (
        "尖峰时段降一档画质，或错开那几个小时",
        "尖峰時段降一檔畫質，或錯開那幾個小時",
        "Drop one quality step during the busy hours, or watch outside them",
    ),
    "action.wifi": ("改用 5GHz，或直接插网路线", "改用 5GHz，或直接插網路線", "Move to 5GHz, or plug in a cable"),
    "action.home": (
        "先查你家里这一段：路由器、网路线、有没有别的装置在吃频宽",
        "先查你家裡這一段：路由器、網路線、有沒有別的裝置在吃頻寬",
        "Look inside your own home first: the router, the cable, anything else using the line",
    ),
    "action.dns": (
        "换一个 DNS（例如 1.1.1.1 或 8.8.8.8）再量一次",
        "換一個 DNS（例如 1.1.1.1 或 8.8.8.8）再量一次",
        "Try a different DNS resolver (1.1.1.1 or 8.8.8.8) and measure again",
    ),
    "action.isp": (
        "问题在电信商那一段——把这份报告寄给客服，上面的分段数字就是证据",
        "問題在電信商那一段——把這份報告寄給客服，上面的分段數字就是證據",
        "The problem is in your ISP's segment - send them this report; the per-hop numbers are the evidence",
    ),
    "action.server": (
        "问题在伺服器那一端，不在你这边——换个直播间或稍后再看",
        "問題在伺服器那一端，不在你這邊——換個直播間或稍後再看",
        "The far end is the problem, not your side - try another stream or come back later",
    ),
    "action.loss": (
        "先处理丢包：丢包对直播的伤害远大于延迟，1% 就会开始卡",
        "先處理丟包：丟包對直播的傷害遠大於延遲，1% 就會開始卡",
        "Deal with the packet loss first: a stream suffers far more from loss than from latency, and 1% is already enough to stutter",
    ),
    "action.target_down": (
        "对方根本没有回应——先确认直播还在播、房间号没打错",
        "對方根本沒有回應——先確認直播還在播、房間號沒打錯",
        "Nothing answered at all - check the stream is still live and the id is right",
    ),
    "action.lower_quality": (
        "降画质：你的实测下载速度撑不住高画质",
        "降畫質：你的實測下載速度撐不住高畫質",
        "Lower the quality: the measured download speed will not carry a high one",
    ),
    "action.flapping": (
        "节点换来换去，每次切换都会卡一下——固定一个节点会比较稳",
        "節點換來換去，每次切換都會卡一下——固定一個節點會比較穩",
        "It keeps moving between edges and each switch costs a stutter - staying on one would be steadier",
    ),
    "action.because.peer": ("量到 PCDN 节点", "量到 PCDN 節點", "a peer-assisted node was served"),
    "action.because.edge": ("节点之间差很多", "節點之間差很多", "the edges differ measurably"),
    "action.because.pattern": ("有时段性", "有時段性", "it follows the clock"),
    "action.because.verdict": ("分段诊断的结论", "分段診斷的結論", "the path check's verdict"),
    "action.because.loss": ("丢包 {detail}", "丟包 {detail}", "packet loss {detail}"),
    "action.because.speed": ("实测速度 {detail}", "實測速度 {detail}", "measured {detail}"),
    "action.because.switches": ("切换 {detail} 次", "切換 {detail} 次", "{detail} switches"),
    "menu.selftest": ("产生诊断报告…", "產生診斷報告…", "Run a self-test…"),
    "selftest.title": ("诊断报告", "診斷報告", "Self-test"),
    "selftest.running": (
        "正在对真实伺服器跑每一项检测，大约十几秒…",
        "正在對真實伺服器跑每一項檢測，大約十幾秒…",
        "Running every probe against the real thing; this takes a few seconds…",
    ),
    "selftest.done": (
        "报告已经复制到剪贴簿了，可以直接贴给别人看。",
        "報告已經複製到剪貼簿了，可以直接貼給別人看。",
        "The report has been copied to the clipboard, ready to paste.",
    ),
    "selftest.privacy": (
        "里面只有你家内网位址和被测伺服器，没有 Wi-Fi 名称、公网 IP 或帐号。",
        "裡面只有你家內網位址和被測伺服器，沒有 Wi-Fi 名稱、公網 IP 或帳號。",
        "It contains addresses inside your own network and the servers measured - no Wi-Fi name, no public IP, no account.",
    ),
    "selftest.ask_room": (
        "贴上一个正在直播的房间号或直播间网址。\n没有的话可以留空按确定——但和 B 站有关的四项检查就会跳过，而那几项正是最需要在真实环境验证的。",
        "貼上一個正在直播的房間號或直播間網址。\n沒有的話可以留空按確定——但和 B 站有關的四項檢查就會跳過，而那幾項正是最需要在真實環境驗證的。",
        "Paste a room id or the URL of a stream that is live right now.\nLeaving it empty is fine, but the four Bilibili checks will skip - and those are the ones that most need testing against the real thing.",
    ),
    "speed.title": ("网速测试", "網速測試", "Speed test"),
    "speed.host": ("测速对象", "測速對象", "Server measured"),
    "speed.confirm": (
        "这会用尽全部带宽下载 {seconds} 秒（最多 {megabytes} MB），期间延迟会飙高、"
        "直播可能会卡——这是它自己造成的，不是你的网络出问题。\n\n"
        "会从你正在看的那个 CDN 下载（没有在看东西时才用公开测速点）。要开始吗？",
        "這會用盡全部頻寬下載 {seconds} 秒（最多 {megabytes} MB），期間延遲會飆高、"
        "直播可能會卡——這是它自己造成的，不是你的網路出問題。\n\n"
        "會從你正在看的那個 CDN 下載（沒有在看東西時才用公開測速點）。要開始嗎？",
        "This downloads flat out for {seconds} seconds (at most {megabytes} MB). "
        "Latency will spike and the stream may stutter while it runs - that is this "
        "test doing it, not your connection failing.\n\n"
        "It downloads from the CDN you are already watching, or a public endpoint "
        "when there is nothing to watch. Start?",
    ),
    "speed.running": ("正在测速，先别管延迟数字…", "正在測速，先別管延遲數字…",
                      "Testing - ignore the latency figure for a moment…"),
    "speed.result": ("下载速度：{value}", "下載速度：{value}", "Download: {value}"),
    "speed.failed": ("测速失败", "測速失敗", "The speed test did not finish"),
    "speed.source_stream": (
        "测的是你正在看的那个 CDN——也就是真正影响你的那条路。",
        "測的是你正在看的那個 CDN——也就是真正影響你的那條路。",
        "Measured against the CDN you are watching - the path that actually matters.",
    ),
    "speed.source_public": (
        "没有在看东西，所以用了公开测速点（Cloudflare）。",
        "沒有在看東西，所以用了公開測速點（Cloudflare）。",
        "Nothing was being watched, so a public endpoint (Cloudflare) was used.",
    ),
    "speed.cost": ("用掉 {megabytes} MB，花了 {seconds} 秒。",
                   "用掉 {megabytes} MB，花了 {seconds} 秒。",
                   "It used {megabytes} MB over {seconds} seconds."),
    "speed.short": (
        "（还没跑到全速就结束了，这个数字可能偏低——TCP 慢启动还没完。）",
        "（還沒跑到全速就結束了，這個數字可能偏低——TCP 慢啟動還沒完。）",
        "(It finished before TCP reached full speed, so this may read low.)",
    ),
    "speed.marker": ("测速（延迟飙高是正常的）", "測速（延遲飆高是正常的）",
                     "speed test (the spike is this test)"),
    "speed.budget": ("测速时长（秒）", "測速時長（秒）", "Test for (seconds)"),
    "speed.max_mb": ("最多下载（MB）", "最多下載（MB）", "Download at most (MB)"),
    "speed.group": ("网速测试", "網速測試", "Speed test"),
    "speed.hint": (
        "两个上限哪个先到就停，所以千兆线路不会为了证明自己而拉掉一整 GB。",
        "兩個上限哪個先到就停，所以千兆線路不會為了證明自己而拉掉一整 GB。",
        "Whichever cap is reached first ends the test, so a gigabit line stops at the "
        "byte cap rather than pulling down a gigabyte to prove a point.",
    ),

    "speed.tier.4k": (
        "足够 4K（25 Mbps 以上）", "足夠 4K（25 Mbps 以上）", "Enough for 4K (25 Mbps+)",
    ),
    "speed.tier.1080p60": (
        "足够 1080p60 / 蓝光", "足夠 1080p60 / 藍光", "Enough for 1080p60 and Blu-ray tiers",
    ),
    "speed.tier.1080p": ("足够 1080p", "足夠 1080p", "Enough for 1080p"),
    "speed.tier.720p": ("足够 720p", "足夠 720p", "Enough for 720p"),
    "speed.tier.low": (
        "只够标清，看高画质会转圈", "只夠標清，看高畫質會轉圈",
        "Only enough for low quality; anything higher will buffer",
    ),

    # ------------------------------------------------------------- setup wizard
    "wizard.title": ("初次设置", "初次設定", "Setup"),
    "wizard.welcome": ("欢迎使用 {app}", "歡迎使用 {app}", "Welcome to {app}"),
    "wizard.blurb": (
        "回答三个问题就能开始，其它都有合理的默认值，之后随时可以在设置里改。",
        "回答三個問題就能開始，其它都有合理的預設值，之後隨時可以在設定裡改。",
        "Three questions and you are running. Everything else has a sensible default "
        "and can be changed later in Settings.",
    ),
    "wizard.watch": ("① 要监测什么？", "① 要監測什麼？", "1. What should it watch?"),
    "wizard.watch.auto": (
        "我在看的 B 站直播／视频（自动跟随）",
        "我在看的 B 站直播／影片（自動跟隨）",
        "The Bilibili live room or video I am watching (follows me)",
    ),
    "wizard.watch.app": (
        "某个程序（游戏、语音、浏览器…）", "某個程式（遊戲、語音、瀏覽器…）",
        "A program - a game, a voice app, a browser",
    ),
    "wizard.watch.target": (
        "某个服务器地址", "某個伺服器位址", "A server address",
    ),
    "wizard.watch.network": (
        "先只看整体网络就好", "先只看整體網路就好", "Just my connection in general, for now",
    ),
    "wizard.detail.app": ("程序名称", "程式名稱", "Program"),
    "wizard.detail.target": ("地址", "位址", "Address"),
    "wizard.hint.auto": (
        "浏览器和官方 PC 客户端都支持，换直播间会自己切过去。",
        "瀏覽器和官方 PC 用戶端都支援，換直播間會自己切過去。",
        "Works with the browser and the official desktop client, and follows you when "
        "you switch rooms.",
    ),
    "wizard.hint.app": (
        "留空＝自动跟随你当前使用的程序。之后在设置里可以从列表挑。",
        "留空＝自動跟隨你目前使用的程式。之後在設定裡可以從清單挑。",
        "Leave it empty to follow whichever program is in front. You can pick from a "
        "list later in Settings.",
    ),
    "wizard.hint.target": (
        "例如 8.8.8.8、游戏服务器、公司 VPN。",
        "例如 8.8.8.8、遊戲伺服器、公司 VPN。",
        "For example 8.8.8.8, a game server, or a VPN gateway.",
    ),
    "wizard.place": ("② 悬浮窗放哪里？", "② 懸浮視窗放哪裡？", "2. Where should the overlay sit?"),
    "wizard.place.free": (
        "自由拖动（我自己放）", "自由拖曳（我自己放）", "Wherever I drag it",
    ),
    "wizard.updates": ("③ 检查更新？", "③ 檢查更新？", "3. Check for updates?"),
    "wizard.footer": (
        "版本 {version}　·　不需要登录，不收集任何使用数据。",
        "版本 {version}　·　不需要登入，不收集任何使用資料。",
        "Version {version} · No login, and no usage data is collected.",
    ),
    "wizard.start": ("开始使用", "開始使用", "Start"),

    # ----------------------------------------------------------------- updates
    "update.enabled": (
        "有新版本时提醒我", "有新版本時提醒我", "Tell me when a new version is out",
    ),
    "update.hint": (
        "每天最多向 GitHub 查询一次「最新版本号是多少」，只读取一个公开页面："
        "不上传任何信息、不含标识符，也不会自动下载或安装。关掉也完全不影响使用。",
        "每天最多向 GitHub 查詢一次「最新版本號是多少」，只讀取一個公開頁面："
        "不上傳任何資訊、不含識別碼，也不會自動下載或安裝。關掉也完全不影響使用。",
        "At most once a day it asks GitHub what the newest version number is - one public "
        "page, no identifier, nothing uploaded, and nothing downloaded or installed "
        "automatically. Turning it off changes nothing else.",
    ),
    "update.available": (
        "有新版本 {version}（你在用 {current}）", "有新版本 {version}（你在用 {current}）",
        "Version {version} is out (you have {current})",
    ),
    "update.install": ("直接更新", "直接更新", "Update now"),
    "update.install_hint": (
        "会下载官方安装程序（约 {megabytes} MB）、核对校验码，然后自动装好。本程序会先关掉——Windows 不允许覆盖正在执行的程序——装完会自己开回来。",
        "會下載官方安裝程式（約 {megabytes} MB）、核對校驗碼，然後自動裝好。本程式會先關掉——Windows 不允許覆蓋正在執行的程式——裝完會自己開回來。",
        "Downloads the official installer (about {megabytes} MB), checks it against the published checksum and runs it. This app closes first - Windows will not replace a running program - and the installer starts it again afterwards.",
    ),
    "update.downloading": ("正在下载更新…", "正在下載更新…", "Downloading the update…"),
    "update.install_failed": (
        "更新没有装成：{reason}\n改成开下载页给你，手动装一样可以。",
        "更新沒有裝成：{reason}\n改成開下載頁給你，手動裝一樣可以。",
        "The update was not installed: {reason}\nOpening the download page instead.",
    ),
    "update.open": ("去下载", "去下載", "Open the page"),
    "update.skip": ("跳过这个版本", "跳過這個版本", "Skip this version"),
    "update.later": ("以后再说", "以後再說", "Later"),
    "update.none": ("已经是最新版本", "已經是最新版本", "You are on the newest version"),
    "update.failed": (
        "查不到版本信息（可能没联网）", "查不到版本資訊（可能沒連網）",
        "Could not reach the release page (offline?)",
    ),
    "menu.check_update": ("检查更新…", "檢查更新…", "Check for updates…"),
    "update.group": ("更新", "更新", "Updates"),

    # ------------------------------------------------------ automatic checking
    "history.auto_check": (
        "卡顿时自动查一次原因", "卡頓時自動查一次原因", "Find out why when it stalls",
    ),
    "history.auto_check_hint": (
        "探测失败或延迟突增时，在后台跑一次精简版分段诊断（3 个 ping，约 2 秒），"
        "把结论记在那一分钟上——事后就知道「昨晚 9 点是 Wi-Fi 的问题」而不只是「卡过」。",
        "偵測失敗或延遲突增時，在背景跑一次精簡版分段診斷（3 個 ping，約 2 秒），"
        "把結論記在那一分鐘上——事後就知道「昨晚 9 點是 Wi-Fi 的問題」而不只是「卡過」。",
        "When a probe fails or latency jumps, a cut-down path check (three pings, about two "
        "seconds) runs in the background and its verdict is filed against that minute - so "
        "afterwards you know last night was the Wi-Fi, not just that it was bad.",
    ),
}


def normalize(code: str) -> str:
    """``ja_JP.UTF-8`` -> ``ja``; anything unrecognised -> ``""``."""
    code = (code or "").replace("-", "_")
    if code in LANGUAGES:
        return code
    lowered = code.lower()
    if lowered.startswith("zh"):
        if any(tag in lowered for tag in ("tw", "hk", "mo", "hant")):
            return "zh_TW"
        return "zh_CN"
    if lowered.startswith("en"):
        return "en"
    if lowered.startswith("ja"):
        return "ja"
    if lowered.startswith("ko"):
        return "ko"
    return ""


def detect_system_language(candidates: Iterable[str] | None = None) -> str:
    if candidates is None:
        env = [os.environ.get(name, "") for name in ("BILI_LATENCY_LANG", "LC_ALL", "LC_MESSAGES", "LANG")]
        try:
            env.append(locale.getdefaultlocale()[0] or "")
        except (ValueError, TypeError):  # pragma: no cover - platform dependent
            pass
        candidates = env
    for candidate in candidates:
        resolved = normalize(candidate)
        if resolved:
            return resolved
    return "zh_CN"


def set_language(code: str) -> str:
    """Set the active language; ``auto`` resolves against the environment."""
    global _current
    if not code or code == "auto":
        _current = detect_system_language()
    else:
        _current = normalize(code) or "zh_CN"
    return _current


def current_language() -> str:
    return _current


def tr(key: str, **kwargs) -> str:
    entry = STRINGS.get(key)
    if entry is None:
        return key
    overlay = OVERLAYS.get(_current)
    if overlay is not None:
        # English is the fallback: a key nobody has translated yet still says
        # something, in a language more people read than a raw key.
        text = overlay.get(key) or entry[BASE_LANGUAGES.index("en")]
    else:
        text = entry[BASE_LANGUAGES.index(_current)]
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text
