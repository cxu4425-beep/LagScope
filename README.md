<div align="center">

<img src="assets/icon.png" width="96" alt="LagScope">

# LagScope · 延遲監視器

**任何程式的即時延遲都能看：遊戲、通話、瀏覽器、下載——常駐在狀態列或畫面角落。**
**對 B 站另外做了深度支援：自動跟著你正在看的直播間／影片，量到「伺服器 → 電腦 → 螢幕」。**

免費開源 · 免登入 · 免安裝 exe · 支援 Windows / macOS / Linux · 简体 / 繁體 / English / 日本語 / 한국어

**[▸ 介紹網站](https://cxu4425-beep.github.io/LagScope/)** · **[下載最新版](https://github.com/cxu4425-beep/LagScope/releases/latest)**

[介紹網站](https://cxu4425-beep.github.io/LagScope/) · [功能](#-功能) · [安裝](#-安裝) · [使用](#-使用) · [網路體檢](#-網路體檢告訴你是誰的錯) · [歷史與報告](#-歷史走勢與一鍵體檢報告) · [前後對照](#-我改的設定有用嗎) · [自我檢測](#-自我檢測---selftest) · [CDN 節點](#-自動選最快的-cdn-節點) · [測網速](#-測一下這條線到底多快) · [伺服器在哪](#-你到底連到哪台伺服器) · [跟 ping 不一樣](#-為什麼跟-cmd-的-ping-不一樣) · [為什麼總是卡](#-為什麼總是會卡) · [手機](#-用手機看不用裝-app) · [自動偵測](#-自動跟隨我正在看的頁面) · [設定](#️-設定說明) · [更新與隱私](#-更新與隱私) · [常見問題](#-常見問題-faq) · [English](#english)

<img src="docs/images/overlay-demo.gif" width="260" alt="懸浮窗即時變化">

<em>延遲上去時數字和折線一起變色；右邊掛著的路由器和 DNS 還是綠的，一眼就知道問題不在你家。</em>

<br>

<img src="docs/images/overlay-app.png" width="232" alt="任意應用模式懸浮窗">
<img src="docs/images/overlay-dark.png" width="232" alt="直播模式懸浮窗">
<img src="docs/images/overlay-video.png" width="232" alt="影片模式懸浮窗">
<img src="docs/images/overlay-compact.png" width="212" alt="緊湊模式">

<em>左起：任意應用（延遲＋連線數＋上下行）、B 站直播、B 站影片（起播＋頻寬）、緊湊模式</em>

</div>

---

## ✨ 功能

### 任何程式都能測（不限 B 站）

- **選一個程式**（遊戲、Discord、瀏覽器、下載器…），監視器會找出**它實際連的伺服器**並持續測延遲；
  UDP 的遊戲連不上 TCP 時自動改用 ping。順便顯示它開了幾條連線。
- **自動跟隨目前使用的程式**：切到哪個視窗就量哪個程式，不用每次設定。
- **自訂伺服器位址**：直接填 `8.8.8.8`、遊戲伺服器、公司 VPN，先試 TCP、不通就 ping。
- **全機上傳／下載速度**：每一筆樣本都附帶，一眼看出「是不是有別的東西在吃頻寬」。
- **同時盯多個目標**：主要對象之外再掛 4 個（路由器／DNS／語音／自訂），
  分辨「只有這個卡」還是「整條線都卡」。
- **網路體檢**：一鍵拆出「你→路由器→電信商→伺服器」各段延遲與丟包，直接告訴你該怪誰
  （見[網路體檢](#-網路體檢告訴你是誰的錯)）。
- **歷史走勢圖**：每分鐘存一行摘要，關掉程式也不會丟。回頭就看得出「昨晚九點特別卡」
  （見[歷史與報告](#-歷史走勢與一鍵體檢報告)）。
- **一鍵體檢報告**：走勢圖＋分段診斷輸出成一個自包含的 HTML 檔，可以直接寄給客服或貼到論壇。
- **測一下線有多快**：主動把線佔滿量真實下載速度，測的是**你正在看的那個 CDN**，有時間和流量雙上限，測速期間會自動在歷史上標記（見[測網速](#-測一下這條線到底多快)）。
- **改了設定有沒有用**：標記「我剛剛換了 5GHz」，之後報告會用前後**一樣長**的時間窗口告訴你
  到底有沒有變好（見[前後對照](#-我改的設定有用嗎)）。
- **卡頓時自動查原因**：探測失敗或延遲突增時，背景自動跑一次精簡診斷，把結論記在那一分鐘上——
  事後看得到「昨晚 9 點是 Wi-Fi 的問題」，而不只是「那時候卡過」。
- **卡頓與延遲突增偵測**：探測失敗或延遲跳到平常的兩倍以上就記一次事件，
  可選擇彈出提示（有冷卻時間，不會一直吵）。

### B 站深度支援

- **自動跟隨你在看的頁面**：不用每次手動貼房間號，換直播間、換影片、換分頁都會自己切過去
  （見[自動偵測](#-自動跟隨我正在看的頁面)），也可以隨時關掉改成手動指定。
- **網頁版和官方 PC 客戶端都支援**：客戶端也是全自動的（直接讀它自己的瀏覽紀錄），
  萬一版本不同讀不到，複製一次分享連結也能立刻切過去。
- **直播與一般影片都能測**：直播量的是離直播邊緣有多遠；一般影片量的是
  **起播延遲**與**頻寬餘量**（線路撐不撐得住這個畫質、會不會轉圈）。
- **即時延遲監測**：每 2 秒（可調）量一次，總延遲 + 網路 / 推流 / 顯示分項。
- **看得到伺服器在哪**：主機名稱說得出的時候直接解出來（`cn-hbyc-ct-01` 就是宜昌、中國電信）；
  租用公有雲的節點和 PCDN 什麼都不說，那就用**光速**——往返花了多久，就限制了它最遠能在多遠
  （4 ms 代表它必定在 400 公里內）。不查 GeoIP、不連任何第三方，只有一個乘法。
- **看是哪個 Wi-Fi 在拖你**：每分鐘記下你在哪個無線網路（SSID **加頻段** —— 很多路由器兩個頻段同名，
  只看名字會剛好把最該分開的兩個平均在一起），然後用跟 CDN 節點同一套比較告訴你
  「你在 2.4 GHz 的時候慢了 750 ms，而你有一半的時間在上面」。這個跟節點不一樣 —— 這個你自己就能換。
- **只有一個 Wi-Fi 也能比**：多數人家裡只有一個網路，沒有第二個可以對照。
  那就比**訊號好的分鐘和訊號弱的分鐘** ——「訊號弱的時候慢了 1100 ms，而那佔了四分之一的時間」
  一個網路就問得出來。
- **mesh 換手偵測**:有延伸器的話,換 AP 時 SSID 完全不變,斷那一到三秒本來看不出原因。現在記 BSSID,說得出來。
- **藍牙耳機延遲校正**：用藍牙聽的話，聲音會比畫面晚 100–250 毫秒，而**沒有作業系統會報這個數字**。
  程式放一聲、閃一下，你調到兩者重合，量出來的就補進總延遲——電腦和 Android App 都有
  （見[方法論第 5 節](docs/METHODOLOGY.md)）。
- **CDN 線路比較與自動切換**：B 站同一個直播間會發好幾個節點，監視器定期把每條線都測一遍，
  明顯更快的就自動換過去（見[CDN 節點](#-自動選最快的-cdn-節點)）。
- **直播間詳情**：人氣、分區、開播時長、畫質名稱、編碼、格式，全都看得到。
- **常駐兩種形態，可同時開**
  - **狀態列（系統匣）圖示**：圖示上直接畫出目前的毫秒數，滑鼠移上去看完整分項。
  - **懸浮窗**：永遠置頂、半透明，可**自由拖曳**、**吸附螢幕角落**，或**跟隨 B 站視窗**移動。
- **位置完全自訂**：四個角落 + 水平/垂直偏移、縮放、透明度、三種主題、緊湊模式、滑鼠穿透、鎖定位置。
- **適合長時間掛著**：資料窗口有上限、記憶體不長胖；探測失敗會指數退避；斷網恢復後自動接上；設定原子寫入不怕當機。
- **統計資訊**：均值、P95、抖動、迷你折線圖，可選擇把每一筆樣本寫成 CSV（自動輪替）。
- **手機也能看**：電腦開一個唯讀網頁，手機瀏覽器連進來就看得到同一份數字（見[用手機看](#-用手機看不用裝-app)）。
- **多人可用**：不需要帳號或 Cookie，設定存在各自的使用者目錄，同一台電腦不同使用者互不干擾。
- **免登入、無遙測**：只呼叫瀏覽器打開直播間時同樣的公開 API。
- **完整介面**：所有選項都在設定視窗裡，不用手改設定檔；打包好的 exe 雙擊即用。

> 延遲數字的精確定義、量測公式與誤差範圍，請看 **[docs/METHODOLOGY.md](docs/METHODOLOGY.md)**。

<div align="center">
<img src="docs/images/tray-icons.png" width="384" alt="狀態列圖示會依延遲變色">
<br><em>狀態列圖示：綠 / 黃 / 紅 依門檻自動變色</em>
</div>

---

## 📦 安裝

### 方式一：下載現成的執行檔（最簡單，Windows 推薦）

1. 打開 [Releases](https://github.com/cxu4425-beep/LagScope/releases) 頁面。
2. 下載對應系統的檔案：
   - **Windows（推薦）**：`LagScope-setup.exe` —— 安裝程式，雙擊下一步就好，
     會建立開始功能表捷徑、可選開機自動啟動，解除安裝也乾淨。
     **不需要系統管理員權限**（裝在你自己的使用者資料夾裡），所以公司或學校的電腦也能裝。
   - Windows（免安裝）：`LagScope-windows-x64.zip` —— 解壓縮就能跑，適合放隨身碟。
   - macOS：`LagScope-macos-arm64.zip`
   - Linux：`LagScope-linux-x64.tar.gz`
3. 壓縮檔版本解壓縮後直接執行 `LagScope`（Windows 是 `LagScope.exe`）。
   免安裝、不寫登錄檔（除非你自己勾選「開機自動啟動」）。

第一次開啟會有一個**三個問題的設定精靈**（要監測什麼／懸浮窗放哪／要不要檢查更新），
回答完就開始跑，其它設定都有合理預設值。

<div align="center"><img src="docs/images/wizard.png" width="460" alt="初次設定精靈"></div>

> Windows SmartScreen 可能提示「未知發行者」——這是沒有付費程式碼簽章憑證的開源程式的正常現象，
> 點「其他資訊 → 仍要執行」即可。不放心的話請用方式二／方式三自行打包。
>
> macOS 首次開啟若提示「無法驗證開發者」，在「系統設定 → 隱私權與安全性」按「仍要打開」，
> 或執行 `xattr -dr com.apple.quarantine LagScope.app`。

### 方式二：從原始碼執行（跨平台，需要 Python 3.9+）

```bash
git clone https://github.com/cxu4425-beep/LagScope.git
cd LagScope

python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate

pip install -r requirements.txt
python run.py                   # 直接跑，不用安裝
```

或安裝成系統指令：

```bash
pip install -e .
lagscope                    # 之後在任何目錄都能啟動
```

Linux 若缺少 Qt 依賴，先裝：

```bash
sudo apt-get install -y libegl1 libgl1 libxkbcommon0 libdbus-1-3 libfontconfig1
```

### 方式三：自己打包 exe

```bash
pip install -r requirements-dev.txt
python packaging/build.py       # 產物在 dist/
```

Windows 也可以直接雙擊 `packaging\build_windows.bat`（會自動建立虛擬環境、安裝依賴、打包）。
專案內附 GitHub Actions（`.github/workflows/build.yml`）：推一個 `v*` tag 就會自動幫三個平台打包並上傳到 Release。

---

## 🚀 使用

### 第一次啟動

1. 執行程式後，狀態列（Windows 右下角 / macOS 選單列）會出現圖示，畫面上出現懸浮窗。
2. **直接用瀏覽器打開任何 B 站直播間或影片**，監視器會自己認出來並開始量
   （預設就是「自動跟隨我正在看的頁面」）。
3. 想手動指定的話：在圖示或懸浮窗上按右鍵 → **設定…** → 把「監測對象」改成
   「手動指定直播間」或「手動指定視頻」，再填內容。

**監測對象**五種模式（設定 → 常規 → 監測對象）：

| 模式 | 說明 |
| --- | --- |
| **自動跟隨我正在看的頁面**（預設）| 自動偵測你在看哪個 B 站直播間／影片，換頁就跟著換 |
| **手動指定直播間** | 只量你填的那個直播間，不受瀏覽器影響 |
| **手動指定視頻** | 只量你填的那支影片（可指定分 P）|
| **任意應用程序** | 選一個程式（遊戲、通話、瀏覽器…），量它**實際連的伺服器** |
| **自定義服務器地址** | 直接填 IP／網域＋連接埠，例如遊戲伺服器、`8.8.8.8` |

填寫格式都很寬鬆：

- 直播間：`21452505`、`https://live.bilibili.com/21452505`，或整段網址貼上。
- 影片：`BV1GJ411x7h7`、`av170001`、`https://www.bilibili.com/video/BV1GJ411x7h7?p=2`（分 P 用 `?p=`）。
- 應用程式：從下拉選單挑（會列出正在連網的程式和它的連線數），或直接打 `game.exe`；
  也可以勾「自動跟隨當前使用的程序」，切到哪個視窗就量哪個。

全部留空、又關掉自動偵測時，進入**僅網路模式**，只量到 B 站伺服器的網路延遲。

### 量任何程式（遊戲／通話／下載…）

1. 設定 → 常規 → 監測對象 → **任意應用程序**
2. 從下拉選單選你的程式（例如 `ValorantGame.exe`、`Discord.exe`、`chrome.exe`），
   按「刷新列表」可以重新掃描；程式還沒開的話直接把名字打進去也行。
3. 確定。懸浮窗會變成：**延遲 / 連接數 / 顯示**，統計列顯示 **↓下載 ↑上傳**。

它是怎麼量的：從系統的連線表找出**這個程式現在連著哪些伺服器**，挑連線數最多的那個公網位址，
每輪對它計時一次 TCP 交握。很多遊戲走 UDP，TCP 連不上時會自動改用系統 `ping`（不需要管理員權限）。

| 你會看到 | 意思 |
| --- | --- |
| 延遲 | 到該程式伺服器的往返時間（TCP 或 ping）|
| 連接數 | 這個程式目前開著幾條連線 |
| ↓ / ↑ | 整台電腦的下載／上傳速度，用來判斷「是不是有別的東西在吃頻寬」|

> 讀的是自己電腦上、自己程式的連線表（Windows/Linux 直接可讀；macOS 對其他程式的連線可能需要權限，
> 讀不到時會顯示「該應用當前沒有網絡連接」）。不注入、不抓封包、不看內容。


### 同時盯好幾個目標

主要對象旁邊還能再掛最多 **4 個附加監測**，一眼分辨「只有這個卡」還是「整條線都卡」：

<div align="center"><img src="docs/images/overlay-app.png" width="260" alt="附加監測"></div>

上圖：遊戲本身 49ms 正常、路由器 2ms 正常、DNS 28ms 正常，但 **Discord 語音 180ms 紅字**——
問題出在語音服務，不是你的網路。這種判斷用單一數字是做不到的。

設定 → 常規 → **同時監測（附加）**：

- **＋路由器**：自動偵測你的閘道位址並加入（判斷「是不是家裡的問題」最快的一招）
- **＋DNS**：加入 `8.8.8.8:53`（判斷「是不是整條外網都慢」）
- **新增…**：自訂位址＋連接埠，或選一個程式

**成本控制**：附加目標是**輪流**量的（每輪測一個），所以不管加幾個都不會拖慢主要數字；
4 個目標在預設 2 秒間隔下，每個約 8 秒更新一次——足夠回答「現在整條線如何」。
手機儀表板上也會一起顯示。

### 支援哪些 App？

**沒有白名單——任何會連網的程式都能量。** 監視器讀的是系統的連線表，只要那個程式開著網路連線就抓得到，
不需要為它做任何適配。下面列的是常見例子和它們的進程名稱，方便你在選單裡對號入座：

| App | 進程名稱（Windows）| 測到的是 | 走 UDP？|
| --- | --- | --- | --- |
| **Roblox** | `RobloxPlayerBeta.exe` | 你所在的遊戲伺服器 | 是 → 自動用 ping |
| **Discord** | `Discord.exe` | 語音／訊息伺服器 | 語音是 → 自動用 ping |
| **Zoom** | `Zoom.exe` | 會議媒體伺服器 | 是 → 自動用 ping |
| **VALORANT** | `VALORANT-Win64-Shipping.exe` | 對戰伺服器 | 是 → 自動用 ping |
| **League of Legends** | `League of Legends.exe` | 對戰伺服器 | 是 → 自動用 ping |
| **Chrome / Edge** | `chrome.exe` / `msedge.exe` | 目前連線最多的那個網站 | 否（TCP）|
| **微信 WeChat** | `WeChat.exe` | 微信長連線伺服器 | 否（TCP）|
| **QQ** | `QQ.exe` | QQ 伺服器 | 部分是 |
| **原神 Genshin Impact** | `YuanShen.exe`（國服）／ `GenshinImpact.exe`（國際服）| 遊戲伺服器 | 是 → 自動用 ping |
| **網易雲音樂** | `cloudmusic.exe` | 音樂 CDN | 否（TCP）|
| **騰訊會議 Tencent Meeting** | `wemeetapp.exe` | 會議伺服器 | 是 → 自動用 ping |

遊戲和語音程式通常同時開著**一條 UDP 連線到遊戲／語音伺服器**和**好幾條 TCP 連線到網站與 CDN**。
監視器會**優先選 UDP 那條**——那才是決定你卡不卡的連線，網站那幾條再多也只是背景雜訊。

其他常見的也一樣可以：Steam（`steam.exe`）、Telegram、Spotify、迅雷、釘釘、CS2（`cs2.exe`）、
Minecraft（`javaw.exe`）、OBS 推流、任何下載工具……

**進程名稱會因版本、國服／國際服、安裝方式而不同**，所以不用死記：設定裡按「刷新列表」會列出
**目前正在連網的程式和它們的連線數**，直接挑就好；命令列則是 `LagScope.exe --list-apps`。

> **B 站客戶端**不用走這裡——用「自動跟隨」或直播間／影片模式，量到的是真正的**播放延遲**，
> 比單純的伺服器往返時間有用得多。

### 直播和影片量的東西不一樣

| | 直播 | 一般影片 |
| --- | --- | --- |
| 中間那一列 | **推流**：離直播邊緣有多遠 | **起播**：現在開播要等多久才有畫面 |
| 統計列 | 均值 / P95 / 抖動 | 均值 / P95 / **帶寬**（實測下載速度）|
| 典型數值 | 2–6 秒 | 0.3–1.5 秒 |
| 怎麼看 | 數字越小越接近「即時」 | 帶寬遠大於畫質碼率＝不會卡；接近或更低＝會轉圈 |

錄播沒有「直播邊緣」，所以延遲改用「起播延遲 + 頻寬餘量」表示——這才是看影片時真正有感的東西。
公式與誤差都寫在 [docs/METHODOLOGY.md](docs/METHODOLOGY.md)。

### 讓它待在你要的位置

在設定的「顯示」分頁選一種**位置模式**：

| 模式 | 行為 | 適合 |
| --- | --- | --- |
| **自由拖動**（預設） | 用滑鼠拖到哪就停在哪，關掉再開也記得 | 想放在直播畫面某個角落 |
| **吸附螢幕角落** | 固定在指定螢幕的某個角落 + 偏移量 | 多螢幕、想固定在副螢幕 |
| **跟隨B站視窗** | 自動貼著標題含「哔哩哔哩」的視窗移動 | 瀏覽器視窗會移動、切換的人 |

> 「跟隨B站視窗」目前只在 **Windows** 上有效（用 `user32` 尋找視窗）。
> macOS / Linux 會自動退回「吸附螢幕角落」。關鍵字可自己改，例如改成 `Chrome` 或直播間標題。

### 常用操作

| 操作 | 效果 |
| --- | --- |
| 左鍵拖曳懸浮窗 | 移動位置（勾了「鎖定位置」就不會被拖動） |
| 懸浮窗上按右鍵 | 打開選單（和狀態列圖示右鍵選單相同） |
| 雙擊懸浮窗 | 切換緊湊模式（只顯示總延遲的大數字） |
| 單擊狀態列圖示 | 顯示 / 隱藏懸浮窗 |
| 選單 → 鼠標穿透 | 讓懸浮窗不擋滑鼠，點擊會穿到下面的視窗 |
| 選單 → 暫停監測 | 暫時停止探測（例如你要跑測速） |
| 選單 → 複製診斷信息 | 複製一份 JSON 診斷資料，回報問題時貼上很有幫助 |

---

## 🩺 網路體檢：告訴你「是誰的錯」

看到「延遲 180ms」之後，真正的問題是**該怪誰**。體檢把整條路徑拆開來量：

```
你 → 路由器:      38 ms   丟包 0%   (192.168.1.1)
路由器 → 電信商:  44 ms   丟包 0%   (100.64.0.1)
→ 目標伺服器:     71 ms   丟包 0%   (8.8.8.8)
網域解析:         18 ms
Wi-Fi: 家裡的路由器  41%  802.11n

延遲主要卡在你和路由器之間，而且 Wi-Fi 訊號偏弱——靠近路由器或改用網線會明顯改善。
```

**怎麼用**：托盤選單 → **網路體檢…**（約 10 秒），或命令列 `LagScope.exe --diagnose`
（也可以指定目標：`--diagnose 8.8.8.8`）。不指定時就診斷你目前監測的那個對象。

它會判斷出這幾種結論：

| 結論 | 意思 | 你能做什麼 |
| --- | --- | --- |
| **Wi-Fi** | 延遲卡在你↔路由器，且訊號弱 | 靠近路由器、換 5GHz、改用網線 |
| **家裡網路** | 延遲卡在你↔路由器，但訊號正常 | 路由器過載？重開機？換網線？ |
| **電信商** | 你家正常，出門那一段開始變慢 | 你改不了——拿這份報告去問客服 |
| **伺服器** | 你的線路正常，是伺服器太遠 | 換伺服器／節點最有效 |
| **丟包** | 有封包遺失 | 比延遲更傷遊戲和通話，優先處理 |
| **DNS** | 線路正常，但網域解析很慢 | 換成 8.8.8.8 或 1.1.1.1 常常立刻見效 |

> **網域解析（DNS）也會量**：這是最常被漏掉的一段——每個 ping 都正常、網頁就是慢半拍，
> 通常就是它。位址型目標（像 `8.8.8.8`）不需要解析，會顯示 0。

**技術上**：全部用系統內建工具（`ping`、`tracert`/`traceroute`、`netsh`/`iw`），
不需要管理員權限、不用 raw socket。統計值是從**每一筆回應**自己算的，不解析會被翻譯的摘要行，
所以中文版 Windows、英文版、Linux、macOS 都一樣準（四種格式都有測試涵蓋）。

---

## 📈 歷史走勢與一鍵體檢報告

「我家網路很爛」不是一份報告。能讓客服動起來、能在論壇問出答案的，是一張**什麼時候爛、爛到什麼程度、
爛在哪一段**的圖。

<div align="center"><img src="docs/images/history.png" width="820" alt="延遲歷史走勢"></div>

**歷史走勢**（托盤選單 → **延遲歷史…**）

- 藍線是每分鐘的平均，淡色帶是那一分鐘的**最好～最差**，底部的紅／黃小豎線是**卡頓／延遲突增**。
- 電腦睡著、程式關掉的那段時間，線是**斷開的**——不會用一條直線把不存在的資料連起來。
- 可切 1 小時／6 小時／24 小時／全部，下面直接寫出「最不穩定的時段」。
- 儲存的是**每分鐘一行摘要**（均值／最好／最差／P95／抖動／丟失／事件數），不是每一筆樣本，
  所以一天約 130 KB、48 小時約 260 KB，預設保留 48 小時（可在設定→高級改，或整個關掉）。

**卡頓時自動查原因**（設定 → 高級可關）

底部的紅色小豎線告訴你「這時候卡過」，但不會告訴你為什麼——除非當時有人在電腦前按下體檢。
所以現在只要偵測到卡頓或延遲突增，就會在背景自動跑一次**精簡版分段診斷**（3 個 ping、約 2 秒、
不跑 traceroute，不會加重當下的網路負擔），把結論記在那一分鐘上。事後打開報告會多一段：

```
卡頓時發生了什麼
  08-28 21:14   延遲主要卡在你和路由器之間，而且 Wi-Fi 訊號偏弱……
  08-28 23:02   你家網路正常，延遲是從電信商那一段開始變大的……
```

同一個問題最多每 10 分鐘查一次，所以整晚不穩也不會變成幾百次 ping。

**體檢報告**（托盤選單 → **匯出體檢報告…**，或歷史視窗右下角）

按下去會產生一個 HTML 檔並自動用瀏覽器打開，裡面有：總覽數字、走勢圖、最不穩定的時段、
上面那份「卡頓時發生了什麼」、分段診斷結論、其他監測目標。

- **完全自包含**：圖是內嵌 SVG，樣式是內嵌 CSS，沒有任何外部檔案、沒有 JavaScript。
  可以直接當附件寄出去，離線三週後打開一樣正常。
- **可以貼的純文字版**：歷史視窗的「複製摘要」會把同一份結論複製成純文字，適合論壇回覆或聊天室。
- **裡面沒有什麼**：不含公網 IP、不含帳號、不含 Cookie、不含你看過的網址。
  出現的位址只有你家內網的（192.168.x.x）和被測的那台伺服器。

命令列也可以：

```bash
lagscope --report              # 產生報告（順便跑一次分段診斷），印出檔案路徑
lagscope --report ~/net.html   # 指定輸出位置
lagscope --history             # 把最近 24 小時的摘要印成文字
lagscope --history all         # 全部保留的紀錄
```

---

## ⚡ 自動選最快的 CDN 節點

B 站同一個直播間**同時由好幾個 CDN 節點提供**，播放器拿到哪一個基本是運氣。差別不小：
同一個房間，最快和最慢的節點差幾十毫秒是常事，偶爾差到上百毫秒。

打開之後（預設開啟），監視器每兩分鐘量一次所有節點，發現明顯更快的就自動換過去：

```
cn-hbyc-ct-01.bilivideo.com   210 ms   ← 播放器給的
cn-gotcha09.bilivideo.com      48 ms   ← 換到這個
```

**它什麼時候才會換**——刻意設得很保守，因為換節點要重新連線，不能為了幾毫秒亂跳：

| 條件 | 為什麼 |
| --- | --- |
| 快 **25 ms 以上**，**而且**快 **20% 以上** | 20ms 差 4ms 是雜訊；200ms 差 40ms 才值得 |
| 距離上次換至少 **3 分鐘** | 兩個速度接近的節點不會來回搶 |
| 目前這個**完全沒回應**時直接換 | 這種情況不用談條件 |
| 只在**格式相同**時比速度 | fmp4 才有伺服器時鐘（實測而非估算），不會為了快幾毫秒把精度換掉 |

換過的節點會列在體檢報告裡（時間、從哪換到哪、省了多少）。不想要就在
**設定 → 高級 → 自動選最快的 CDN 節點**關掉。

> **它改的是什麼**：只影響**這個程式自己**去量哪個節點，**不會**改變你瀏覽器或客戶端正在播的那一路。
> 也就是說它讓「量到的數字」更接近「這條線最好能到多少」，而不是幫你的播放器換節點。

---

## 🔬 我改的設定有用嗎

工具告訴你「Wi-Fi 訊號弱」，你去換了 5GHz、改了 DNS、插了網線——**然後呢？**
以前只能憑感覺，因為沒有任何東西告訴你有沒有變好。

現在按一下 **標記此刻（我改了設定）…**，輸入你改了什麼，之後報告就會多一段：

<div align="center"><img src="docs/images/history-marked.png" width="820" alt="標記前後的走勢"></div>

```
我改的設定有用嗎
  08-29 12:30   換到 5GHz
      218 ms → 87 ms    好轉了，快了 131 ms    (前後各 1.5 小時)
```

走勢圖上會畫一條虛線標出那個時刻，**體檢報告裡的圖也有**，所以寄出去的那份一看就懂。

**這裡最重要的一件事是它怎麼避免騙你**：前後用的是**一樣長**的時間窗口，
取兩邊都有資料的**較短**那段。拿一整晚的「之前」去比五分鐘的「之後」，
幾乎任何改動都會顯得有效——這種比較方式本身就是在說謊。

| 規則 | 為什麼 |
| --- | --- |
| 前後窗口**等長**，取較短的那邊 | 不然一整晚 vs 五分鐘，什麼改動都「有效」 |
| 最長各 **6 小時** | 「之前」不會跨到完全不同的另一個晚上 |
| 每邊至少 **5 分鐘**，否則不給結論 | 兩分鐘的資料只是雜訊 |
| 差距在 **10 ms 以內**算「沒有明顯差別」 | 不把測量誤差說成改善 |
| 平均、P95、丟包率都會比 | 只看平均會漏掉「偶爾爆一下」 |

資料不夠時它會直接說「資料不夠，看不出來」，不會硬給一個結論。

---

## 🩺 自我檢測（`--selftest`）

這個功能是給**回報問題**用的，也是給我自己用的。

坦白說：這個程式所有 B 站相關的程式碼——playurl 解析、HLS 伺服器時鐘、FLV 關鍵影格、
CDN 比較與自動切換——**都是對著測試資料寫出來的**，因為開發環境根本連不上 B 站。
單元測試能證明「給定這種格式，解析是對的」，不能證明「B 站現在還是這種格式」。

`--selftest` 就是把每個探測對著真實世界跑一次，然後把拿到什麼原封不動印出來：

```bash
lagscope --selftest              # 不含 B 站的部分
lagscope --selftest 21452505     # 帶一個正在直播的房間號，涵蓋全部
```

```
[ ok ] name resolution
        api.live.bilibili.com: 12 ms
[ ok ] Bilibili API reachable
        TCP handshake: 18 ms
        API answered, code=0
[ ok ] play URLs
        6 endpoint(s), 3 distinct edge(s)
          http_hls     fmp4  qn=10000  cn-gotcha09.bilivideo.com
          ...
        chosen: fmp4 on cn-gotcha09.bilivideo.com
[ ok ] live measurement
        method: hls-pdt   measured
        stream: 2310 ms   host: cn-gotcha09.bilivideo.com
[ ok ] CDN edges
        cn-gotcha09.bilivideo.com     48 ms
        cn-hbyc-ct-01.bilivideo.com   210 ms
        it moved: cn-hbyc-ct-01... -> cn-gotcha09... (saving 162 ms)
```

它**不做任何斷言**，只是把證據攤開來給人看。有問題的話把整段貼進 issue 就夠了。

**輸出裡沒有什麼**：沒有 Wi-Fi 名稱、沒有公網 IP、沒有帳號、沒有其他程式的資訊。
出現的位址只有你家內網的，和被測的伺服器。房間號是你自己給的。

---

## 🚀 測一下這條線到底多快

一直以來狀態列上的 `↓46.8M` 是**被動**的——你的機器現在正好在搬多少資料。
它能回答「是不是有別的東西在吃頻寬」，但回答不了「這條線最快能跑多少」，
因為那個當下根本沒有人在要求它跑快。

托盤選單的 **測一下網速…** 會真的去要求：

```
下載速度：94.2 Mbps

足夠 4K（25 Mbps 以上）

測的是你正在看的那個 CDN——也就是真正影響你的那條路。
用掉 80 MB，花了 9 秒。
```

有兩件事比那個數字本身更重要，所以按下去之前會先問你一次：

| | |
| --- | --- |
| **它會把線佔滿** | 測的時候延遲一定會飆高、直播可能會卡。**這是它自己造成的**，所以它會先在歷史紀錄上標一筆「測速（延遲飆高是正常的）」，免得你等一下看走勢圖，把自己造成的那根尖峰當成故障在查。 |
| **它會用掉流量** | 預設**時間和流量各有上限**（10 秒 / 80 MB），先到哪個就停哪個。所以千兆的線是停在 80 MB，不會因為「跑滿 10 秒」而拉掉一個 GB。兩個上限都可以在設定裡改。 |

**它去哪裡下載是刻意的**：優先用**你正在看的那個 CDN 節點**，因為會不會卡取決於你到那台機器的那條路，
而不是取決於你到某個測速網站的那條路——那兩條路常常根本不同家。真的沒有在看東西時，
才退回公開測速點（Cloudflare）。

結果會寫進體檢報告裡，所以寄給客服的那份會同時有「延遲多少」和「線多快」。
沒有 GUI 的話用 `lagscope --speedtest`。

**關於 TCP 慢啟動**：連線剛建立的頭一秒鐘一定慢，把那一秒算進去會讓快的線看起來很平庸。
所以開頭那段是**單獨算完丟掉**的，只有暖機後的那段算數。真的太快結束（檔案太小或線太慢）
連暖機都沒跑完時，它會直接跟你說「這個數字可能偏低」，而不是假裝那就是你的線速。

---

## 🌏 你到底連到哪台伺服器

B 站的邊緣節點主機名不是亂碼,它本身就寫了答案:

```
cn-hbyc-ct-01.bilivideo.com
│  │    │  └── 節點編號
│  │    └───── ct = 中國電信（cu 聯通、cm 移動）
│  └────────── hbyc = 湖北宜昌
└───────────── cn = 中國大陸
```

報告和 `--selftest` 會直接翻出來:

| 主機名 | 翻出來是 |
| --- | --- |
| `cn-hbyc-ct-01.bilivideo.com` | 宜昌 · 中國電信 |
| `upos-sz-mirrorhw.bilivideo.com` | 華為雲 CDN |
| `cn-gotcha09.bilivideo.com` | B 站自建節點 · 中國大陸 |
| `xy118x123x45x67xy.mcdn.bilivideo.cn` | **PCDN 邊緣節點（別人家的寬頻）** |

**為什麼要做這個**:「為什麼會卡」多半是「你被分到哪台機器」的問題,不是「你頻寬夠不夠」的問題。
以前你只看得到一串主機名,等於看不到答案。

**認不出來的就說認不出來。** 省市代碼是唯一能靠猜的部分,所以只查一張有把握的對照表,
查不到就把原始代碼原樣印出來(`湖北 (hbqq) · 中國聯通`)。編一個看起來很像的城市名
比說「不知道」糟得多,因為會有人照著它去做決定。

**PCDN 會特別警告。** 主機名把 IP 直接編進去的那種(`xy118x123x45x67xy...`),
不是機房機器,是別人家的寬頻在賣閒置上行。線路測起來正常卻一直卡,被分到這種節點是
很常見又完全看不見的原因。

---

## 🔍 為什麼跟 CMD 的 ping 不一樣

```bash
lagscope --why-ping                            # 目前在量的那台
lagscope --why-ping cn-gotcha09.bilivideo.com
```

對**同一個解析後的位址**各量五次 ICMP 和 TCP,並排印出來:

```
主機名: cn-hbyc-ct-01.bilivideo.com
實際連到: 203.0.113.45:443
這台是: 宜昌 · 中國電信

  TCP 握手（本程式用的）             最快   62.4 ms   中位數   64.1 ms
  ICMP ping（CMD 用的）              最快   21.0 ms   中位數   21.3 ms
  DNS 解析                                 18.7 ms   （已經不算進上面的數字裡）

差距（TCP 減 ICMP）: +41.4 ms
差很多。這台機器對 ICMP 和 TCP 的處理明顯不同——路由器和 CDN 常把 ICMP 丟到低優先級、
限速,或乾脆由前面的設備代答。
```

四個常見原因它會說中哪一個,其中最常見、也最容易被忽略的是:**你 ping 的根本不是同一台機器**
——ping `www.bilibili.com` 打到的是前門,而推流給你的是某台 CDN 邊緣節點,可能差好幾個省。

**另外修掉一個本程式自己的量測誤差**:以前 `create_connection(主機名)` 會先做 DNS 解析,
而那段時間一直被算進「伺服器延遲」裡。現在解析和握手分開計時、分開顯示。

---

## 🕘 為什麼「總是」會卡

「總是」是一個關於**模式**的說法。這個程式以前能答「現在如何」和「剛剛那次為什麼」,
答不了「總是」——因為它沒把足以回答的東西記下來。現在記了。

### 你被分到哪些節點

```
節點                                    平均延遲   佔多少時間   卡頓
upos-sz-mirrorhw.bilivideo.com           67 ms       33%        0
華為雲 CDN
cn-hbyc-ct-01.bilivideo.com             160 ms       58%      360
宜昌 · 中國電信
xy118x123x45x67xy.mcdn.bilivideo.cn     300 ms        8%        0
PCDN 邊緣節點（別人家的寬頻）
```

**它指的是「最花你時間的那個」,不是「最慢的那個」。** 上面那個 PCDN 最慢(300 ms),
但你只在上面待 8%;真正在拖你的是 160 ms 卻佔了 58% 時間的那個。
指最慢的會把人送去處理比較小的問題。

### 什麼時候比較卡

按「星期幾 × 幾點」分組。**「沒有時段性」也是一個真的答案**——它一口氣排掉「晚尖峰壅塞」
這一整類原因,把問題指向固定的東西:線路、設備、或某個節點。

歷史保留 **7 天**(約 0.9 MB),因為週的模式不可能在 48 小時裡出現。

### 那我該怎麼辦

報告最後會給一份照順序排的清單,**每一條都印出它的依據**:

```
1. 重開播放器（或切一次畫質）讓伺服器重新分配節點——你被分到的是 PCDN 節點
     (依據: 量到 PCDN 節點)
2. 重開播放器讓伺服器重新分配節點，並確認「自動選最快的 CDN」是開著的
     (依據: 節點之間差很多)
3. 尖峰時段降一檔畫質，或錯開那幾個小時
     (依據: 有時段性)
```

不會因為「這是普遍的好建議」就給你——**一份每次都叫你重開路由器的清單,只會教會你不要看它**。
如果整份清單沒有一項是你家能修的,它會直說。

### 產生診斷報告(不用開命令列)

托盤選單的 **「產生診斷報告…」** 會把每個探測對真實伺服器跑一次,結果直接進剪貼簿。
這個程式所有 B 站相關的程式碼都只對著假資料測過,從真實機器跑出來的報告是唯一的驗證。

---

## 📱 用手機看（不用裝 App）

<div align="center"><img src="docs/images/phone-dashboard.png" width="300" alt="手機儀表板"></div>

電腦跑 LagScope，手機開個網頁就能看到**同一份即時數字**——iPhone、Android 都可以，不用裝任何東西。
適合「電腦在客廳、人在沙發」，或打遊戲時把手機擱旁邊當儀表板。

1. 設定 → 常規 → **手機儀表板** → 勾「讓同一網路下的手機也能看」
2. 想要的話填一組**存取碼**（建議填，四位數就夠）
3. 下面會直接顯示網址，例如 `http://192.168.1.20:23125/?key=4321`
   （托盤選單的「手機網址…」也會顯示並自動複製）
4. 手機和電腦連同一個 Wi-Fi，瀏覽器輸入那個網址即可

畫面上有：總延遲大字（依門檻變色）、分項、折線圖、均值／P95／上下行、抖動與卡頓次數，每 2 秒自動更新。

**安全性：**

- 預設**關閉**，要自己打開才會開埠。
- **唯讀**——手機上改不了任何設定，也控制不了監視器，整個服務只有兩個 GET 端點。
- 只在你的**區域網路**內有效（沒有做任何對外轉發）；填了存取碼後，沒有碼就只會拿到 403。
- 網頁是**完全自包含**的，不載入任何外部資源，所以在沒有網際網路的區網裡也能開。

> 想在手機上跑完整的 LagScope（懸浮窗＋任意 App 延遲）目前做不到：Android 從 10 開始就不讓
> App 讀別的程式的連線表（要 root 或做成 VPN 服務），iOS 更是連懸浮窗都不允許。
> 所以手機這邊是「看電腦量到的數字」，而不是「在手機上量手機」。

---

## 🔎 自動跟隨我正在看的頁面

監視器用幾個**各自獨立、都可以單獨關掉**的來源判斷你在看什麼，優先順序由高到低：

| 來源 | 怎麼運作 | 適用 | 預設 |
| --- | --- | --- | --- |
| **油猴腳本** | 頁面自己把網址回報到 `http://127.0.0.1:23124` | 瀏覽器（最準，換分頁立刻反映）| 關（需裝腳本）|
| **視窗標題** | 記住「這個視窗標題 = 這個直播間」，之後看到同樣標題就自動認出 | 客戶端／瀏覽器（Windows）| 開 |
| **歷史紀錄 + 視窗標題** | 取最近造訪的 B 站網址，再用開著的視窗標題比對出「現在這個分頁」 | 瀏覽器（Windows）| 開 |
| **官方客戶端紀錄** | 直接讀客戶端自己的資料夾，看它最近在播什麼 | **官方 PC 客戶端（全自動）** | 開 |
| **複製連結** | 你按「分享 → 複製連結」，監視器認出剪貼簿裡的 B 站網址 | 客戶端備援、手機分享的連結、任何 App | 開 |
| **歷史紀錄** | 取時間窗口內最新一筆 B 站網址 | 瀏覽器 | 開 |

> 前兩者是**現在畫面上開著什麼**的證據，所以排在前面；
> 後三者比誰的時間比較新，新的贏。

### 用官方 PC 客戶端的話（不用瀏覽器也可以）

**測量本身完全不受影響**——延遲是直接問 B 站公開 API 的，跟你用網頁版、官方客戶端還是別的播放器無關。
自動偵測也有專門的路：官方客戶端是 Chromium 核心的程式，**它自己會在使用者資料夾裡留下瀏覽紀錄**，
監視器就直接讀那份（唯讀、只挑 B 站網址），所以**你什麼都不用做**——打開直播間就開始量了。

它會自動找這些位置：`%APPDATA%` 和 `%LOCALAPPDATA%` 底下的
`bilibili` / `BiliBili` / `哔哩哔哩` 等資料夾，以及 Microsoft Store 版的
`Packages\*Bilibili*`；找到 Chromium 格式的 `History` 就直接讀，沒有的話改掃客戶端自己的
`.log` 檔（只抓 `roomid` / `room_id` / `BV` 號，不留其他內容）。

**先跑一次這個確認你的客戶端讀不讀得到：**

```bash
lagscope --detect-report          # 打包版：LagScope.exe --detect-report
```

它會列出找到的客戶端資料夾、讀到的房間號、視窗標題等等。如果 `client.folders` 是空的，
代表你的客戶端裝在別的位置——用 `--client-dir "路徑"` 指定（可重複），
順便把路徑回報給我，我加進預設清單。

**萬一真的讀不到（客戶端版本不同），還有兩層備援：**

1. 在客戶端點 **分享 → 複製連結**（`b23.tv` 短連結會自動還原），監視器立刻切過去，
   同時把**當下客戶端視窗的標題**和這個房間配成一對記起來——之後再打開同一個直播間，
   光靠視窗標題就自動認出，不用再複製。
2. 把「監測對象」改成手動指定，貼一次房間號就固定量它。

補充：

- 客戶端視窗標題若只有「哔哩哔哩」這種看不出房間的字樣，就學不到標題對應；
  這時複製過的目標會一直保持到你複製下一個連結為止。
- 剪貼簿只處理**含 B 站網址**的文字，其他內容一律忽略，不記錄、不上傳。
- 學到的「標題 ↔ 房間」對應存在設定目錄的 `titles.json`（最多 200 筆），可以直接刪掉。
- 讀客戶端資料、讀剪貼簿、記標題這三項都能在「設定 → 常規 → 自動檢測」個別關掉。
- 懸浮窗的「跟隨B站視窗」也適用於客戶端：把關鍵字設成客戶端視窗標題裡有的字（預設「哔哩哔哩」）即可。

### 關於讀取瀏覽器歷史紀錄（用瀏覽器的人請先看這段）

這是**用瀏覽器**時，不裝任何外掛也能知道你在看哪個頁面的方法，做法刻意收得很窄：

- 歷史紀錄檔會先**複製**成暫存檔，再以**唯讀**方式開啟，瀏覽器開著也能讀，且**絕不寫回原檔**；
- SQL 只撈網址含 `bilibili.com` 的列，**其他網站的紀錄不會被讀出來**；
- 只看設定的時間窗口內（預設 30 分鐘）的紀錄；
- 結果只有房間號或 BV 號，**只留在記憶體裡，不上傳、不寫檔、不需要登入**；
- 支援 Chrome / Edge / Brave / Vivaldi / Chromium / Firefox 的各個設定檔。

不想用就在「設定 → 常規 → 自動檢測」把「讀取瀏覽器歷史記錄」取消勾選；
整個自動偵測也可以在托盤選單一鍵關閉（**自動跟隨觀看頁面**）。

### 想要最準：安裝油猴腳本（選用）

1. 瀏覽器安裝 [Tampermonkey](https://www.tampermonkey.net/)（或 Violentmonkey）。
2. 安裝本專案的
   [`extras/bililagscope-bridge.user.js`](extras/bililagscope-bridge.user.js)
   （在 GitHub 上點檔案 → Raw，油猴會自動跳出安裝視窗）。
3. 監視器裡：**設定 → 常規 → 自動檢測 → 勾選「接收油猴腳本上報」**，端口保持一致（預設 23124）。

腳本只做一件事：把目前頁面的網址 POST 到 `127.0.0.1`。不讀 Cookie、不讀頁面內容、
不連任何外部伺服器；監視器的接收埠只綁定本機、只接受 `*.bilibili.com` 來源的請求。

### 命令列參數

```bash
lagscope --room 21452505              # 啟動時直接指定直播間（並關閉自動偵測）
lagscope --video BV1GJ411x7h7         # 指定影片；也可貼整段網址（?p=2 指定分P）
lagscope --detect                     # 強制開啟自動跟隨
lagscope --no-detect                  # 強制關閉自動跟隨
lagscope --lang zh_TW                 # 介面語言 (auto / zh_CN / zh_TW / en / ja / ko)
lagscope --no-overlay                 # 只留狀態列圖示
lagscope --no-tray                    # 只留懸浮窗
lagscope --config-dir D:\bili-cfg     # 攜帶式：設定寫到指定資料夾
lagscope --reset-config               # 用預設值啟動（不刪除原本的設定檔）
lagscope --probe-once --room 21452505 # 不開視窗，量一次印出 JSON 後結束
lagscope --probe-once --detect        # 量「我現在正在看的那個頁面」一次
lagscope --detect-report              # 列出各偵測來源在你機器上讀到什麼（排查用）
lagscope --client-dir "D:\bili"       # 客戶端裝在別處時，指定它的資料夾（可重複）
lagscope --app ValorantGame.exe       # 量某個程式的延遲
lagscope --app-foreground             # 量目前最前面那個程式
lagscope --ping 8.8.8.8               # 量某個位址（用 --ping-port 指定連接埠）
lagscope --list-apps                  # 列出正在連網的程式（挑名字用）
lagscope --diagnose                   # 分段診斷（可加位址：--diagnose 8.8.8.8）
lagscope --report                     # 匯出體檢報告 HTML，印出檔案位置
lagscope --history                    # 把最近 24 小時的歷史摘要印成文字（all＝全部）
lagscope --selftest                   # 每個探測對真實世界跑一次，印出結果（可加房間號）
lagscope --speedtest                  # 測一次下載速度（會佔滿頻寬、用掉流量）
lagscope --why-ping [主機]             # ICMP 和 TCP 並排量,說明為什麼跟 ping 不一樣
```

`--probe-once` 很適合排查問題或寫成腳本定時記錄：

```json
{
  "total_ms": 2534.7,
  "stream_ms": 2534.7,
  "network_ms": 41.2,
  "ok": true,
  "estimated": false,
  "kind": "live",
  "method": "hls-pdt",
  "host": "cn-hbyc-ct-01.bilivideo.com",
  "target": { "kind": "live", "id": "21452505", "page": 1, "source": "history+title" }
}
```

影片模式下還會多出 `throughput_mbps`（實測下載速度）與 `required_mbps`（該畫質需要的碼率）。

---

## ⚙️ 設定說明

<div align="center"><img src="docs/images/settings.png" width="430" alt="設定視窗"></div>

### 常規

| 項目 | 說明 |
| --- | --- |
| 監測對象 | 自動跟隨 / 直播間 / 視頻 / 任意應用程序 / 自定義服務器地址 |
| 應用程序 | 「任意應用程序」模式要量哪個程式，可勾自動跟隨前景程式 |
| 服務器地址 / 端口 | 「自定義服務器地址」模式要量的目標 |
| 顯示全機上傳／下載速度 | 每筆樣本附帶網速（可關）|
| 卡頓／延遲突增時彈出提示 | 有冷卻時間，不會一直吵（可關）|
| 手機儀表板：開關／端口／存取碼 | 讓同一網路的手機用瀏覽器看（唯讀，預設關）|
| 同時監測（附加）| 最多 4 個附加目標，輪流量測，懸浮窗與手機頁面都會顯示 |
| 直播間號或連結 | 要監測的直播間；自動模式下當作找不到頁面時的備援 |
| 視頻號或連結 | 要監測的影片，支援 BV / av / 網址（`?p=` 指定分 P）|
| 自動檢測：讀取官方PC客戶端正在播放的內容 | 直接讀客戶端自己的紀錄，全自動（可關）|
| 自動檢測：識別復制的鏈接 | 客戶端備援：複製分享連結就自動切換（可關）|
| 自動檢測：記住窗口標題對應的房間 | 學會「這個視窗標題 = 這個直播間」，之後自動認出（可關）|
| 自動檢測：讀取瀏覽器歷史記錄 | 本機唯讀、只看 bilibili.com 網址（可關）|
| 自動檢測：用窗口標題識別當前標籤頁 | 讓它跟著你切分頁走（Windows）|
| 自動檢測：也跟隨普通視頻 | 關掉的話只跟隨直播間，看影片時維持原本目標 |
| 自動檢測：接收油猴腳本上報 | 最準的來源，需安裝 [`extras/`](extras/) 裡的腳本 |
| 自動檢測：時間窗口 / 檢測間隔 | 歷史紀錄要看多久以內、多久重新判斷一次 |
| 探測間隔 | 預設 2000 ms。長時間掛著建議 2000–5000 ms |
| 統計窗口 | 均值 / P95 / 抖動 使用的樣本數（預設 180） |
| 界面語言 | 跟隨系統 / 简体中文 / 繁體中文 / English / 日本語 / 한국어 |
| 開機自動啟動 | Windows 寫 `HKCU\...\Run`；Linux 寫 `~/.config/autostart`；macOS 寫 LaunchAgent |
| 狀態列圖示 | 是否顯示系統匣圖示、是否在圖示上畫出數值 |

### 顯示

位置模式、角落、偏移、螢幕、跟隨關鍵字、不透明度、縮放、主題（深色 / 淺色 / 粉色）、
總在最前、鼠標穿透、鎖定位置、緊湊模式，以及分項 / 折線圖 / 統計行的顯示開關。

### 高級

| 項目 | 說明 |
| --- | --- |
| 請求超時 | 單次 HTTP / TCP 探測的等待上限 |
| 播放地址刷新 | 播放 URL 會過期，預設每 240 秒重取一次 |
| RTT 探測主機 | 沒設定房間時，用來量網路延遲的主機 |
| 自動選最快的 CDN 節點 | 定期比較所有節點，明顯更快就換過去（預設開啟） |
| 優先使用 HLS | 開啟（預設）才能拿到帶伺服器時鐘的「實測」延遲 |
| 播放器緩衝分片數 | 估算播放器要墊多少緩衝，預設 1 個分片 |
| 合成器排隊幀數 | 顯示延遲模型的排隊層數，預設 2 |
| 顯示器輸入延遲補償 | 你的螢幕面板延遲（可查評測），預設 0 |
| 總延遲包含顯示延遲 | 關掉後總延遲只算到「客戶端拿到影格」為止 |
| 綠色 / 黃色門檻 | 顏色變化的門檻，預設 2000 / 5000 ms |
| 記錄到 CSV | 把每一筆樣本寫進 `logs/latency.csv`（自動輪替，保留 3 份） |
| 保存延遲歷史 | 每分鐘一行摘要，走勢圖和體檢報告的資料來源；可改保留時長（預設 48 小時） |
| 卡頓時自動查原因 | 偵測到卡頓／突增時背景跑一次精簡診斷，把結論記進歷史（最多 10 分鐘一次） |
| 有新版本時提醒我 | 每天最多一次向 GitHub 查最新版本號；不上傳任何資訊，也不會自動下載 |

歷史記錄可以在**高級**分頁關掉或改保留時長；關掉之後走勢圖和報告就沒有資料可畫，
但即時監測完全不受影響。

### 設定檔位置

| 系統 | 路徑 |
| --- | --- |
| Windows | `%APPDATA%\LagScope\config.json` |
| macOS | `~/Library/Application Support/LagScope/config.json` |
| Linux | `~/.config/lagscope/config.json` |

日誌與 CSV 在同目錄的 `logs/` 底下。選單的「打開配置目錄」會直接幫你開啟。
用 `--config-dir` 可以指定到 USB 隨身碟，做成攜帶式版本。

---

## 🔄 更新與隱私

**更新提醒**：預設每天最多一次，向 GitHub 查詢「最新的版本號是多少」——就是讀一個公開頁面。
**不會上傳任何資訊、不含任何識別碼**，也不會自己偷偷裝東西。

**「直接更新」**：發現新版時可以按這個，它會下載官方安裝程式、核對校驗碼、裝好，
中間本程式會先關掉（Windows 不允許覆蓋正在執行的程式），裝完自己開回來。
**這是這個程式裡唯一一個「下載檔案然後執行它」的功能，所以規矩訂得很死：**

| 規矩 | 為什麼 |
| --- | --- |
| 只收 https，主機必須在固定的 GitHub 清單裡，**重導向之後再檢查一次** | API 就算回了奇怪的東西也帶不到別的地方 |
| 位元組必須符合 API 公布的 **sha256**，不符直接刪掉 | 這是「下載」和「執行」之間唯一的關卡 |
| **沒公布校驗碼就不自動裝**，只給連結 | 為省一次點擊去跑沒驗證過的執行檔，不划算 |
| **只有安裝版會自我更新** | 免安裝版要覆蓋自己正在跑的檔案，做錯了你會連一個能用的程式都不剩 |

按「去下載」就跟以前一樣只開頁面，什麼都不下載。
可以在初次設定精靈或「設定 → 高級 → 更新」關掉，也可以對某個版本按「跳過這個版本」。
托盤選單的「檢查更新…」則是手動查一次。

**這個程式總共會連的地方**（除此之外沒有了）：

| 連到哪裡 | 什麼時候 | 為什麼 |
| --- | --- | --- |
| 你正在監測的對象 | 每次探測 | 就是要量它的延遲 |
| B 站公開 API | 只在監測 B 站直播／影片時 | 取播放位址和房間資訊（免登入、不帶 Cookie） |
| 你的路由器／第一跳／目標 | 按下體檢，或卡頓時自動查 | 分段診斷（系統內建 ping） |
| GitHub Releases | 每天最多一次，可關 | 查最新版本號 |
| GitHub 的檔案伺服器 | **只在你按下「直接更新」時** | 下載那一個安裝程式（會核對 sha256） |
| `speed.cloudflare.com` | **只在你按下測速、而且當下沒在看任何東西時** | 公開測速點；有在看東西時測的是那個 CDN，不會連這裡 |

沒有統計、沒有回報、沒有帳號、沒有 Cookie。

---

## 👥 多人使用

- **不需要 B 站帳號**，不讀取瀏覽器 Cookie，任何人下載就能用。
- 設定與紀錄都放在**目前使用者**的設定目錄，同一台電腦上不同 Windows 使用者各自獨立。
- 每個使用者同時只會有一份程式在跑（重複啟動會把已在執行的那份叫出來，而不是開第二份），
  不同使用者之間互不影響。
- 介面支援 **简体中文 / 繁體中文 / English / 日本語 / 한국어**，預設跟隨系統語言，隨時可以在設定裡改。
- 想在公司或宿舍分享？直接把 Release 的壓縮檔丟給對方就好，沒有安裝程序、沒有註冊表殘留。

---

## ❓ 常見問題 FAQ

**Q：我用的是官方 Windows 客戶端，不用網頁版，可以用嗎？要手動複製連結嗎？**
A：可以用，而且**正常情況下不用手動做任何事**。客戶端是 Chromium 核心，會在自己的
資料夾裡留下瀏覽紀錄，監視器直接讀那份就知道你在看哪個直播間。
先跑 `lagscope --detect-report` 確認讀不讀得到；讀不到再用「分享 → 複製連結」當備援，
或直接手動指定房間號。詳見[上面這一節](#用官方-pc-客戶端的話不用瀏覽器也可以)。

**Q：自動偵測沒反應／認錯頁面？**
A：依序檢查：
1. 托盤選單的「自動跟隨觀看頁面」有沒有勾；
2. 用**客戶端**的話，有沒有複製過一次分享連結（見上一題）；
3. 用**瀏覽器**的話：設定裡「讀取瀏覽器歷史記錄」是否被關掉、是不是無痕模式
   （無痕不寫歷史紀錄）、瀏覽器是否在支援清單內
   （Chrome / Edge / Brave / Vivaldi / Chromium / Firefox）。
最保險的做法是裝上油猴腳本（瀏覽器）或直接改成「手動指定」。

**Q：讀我的瀏覽器歷史紀錄？我不放心。**
A：可以理解，所以它是可以關的：設定 → 常規 → 自動檢測 → 取消「讀取瀏覽器歷史記錄」。
程式只會複製歷史檔後**唯讀**開啟、只撈網址含 `bilibili.com` 的列、只留房間號／BV 號在記憶體，
不寫回、不上傳、不需要登入。相關程式碼在
[`src/lagscope/detect/history.py`](src/lagscope/detect/history.py)，歡迎自己看過再決定。

**Q：一般影片的「延遲」是什麼意思？**
A：錄播沒有直播邊緣，所以量的是**起播延遲**（現在開播要等多久才有畫面）加上顯示延遲，
另外用實測下載速度和該畫質碼率算出**頻寬餘量**，直接告訴你會不會卡。

**Q：一直顯示「主播未开播」？**
A：該直播間目前沒有開播（輪播錄影也算沒開播）。換一個正在直播的房間號即可。

**Q：顯示「探测失败」怎麼辦？**
A：依序檢查：網路是否正常、公司/校園網是否擋了 B 站 CDN、有沒有設定系統代理
（本程式會沿用系統代理設定）。選單 →「複製診斷信息」可以看到最後一次的錯誤內容。

**Q：數字旁邊寫「估算」和「實測」差在哪？**
A：「實測」代表拿到了播放清單裡的伺服器時鐘（`hls-pdt`），最準；
「估算」代表只能從分片長度或首個關鍵影格推算。詳見
[docs/METHODOLOGY.md](docs/METHODOLOGY.md)。

**Q：為什麼監視器顯示 2.5 秒，但我覺得延遲有 8 秒？**
A：監視器量的是「現在開始播會落後多少」，你的播放器可能已經累積了很多緩衝。
重新整理直播頁面通常就會回到監視器顯示的水準——這正是這個工具最實用的地方。

**Q：找不到狀態列圖示？**
A：Windows 會把新圖示藏在「顯示隱藏的圖示」箭頭裡，拖出來釘住即可。
Linux 某些桌面環境需要安裝 AppIndicator 擴充套件；沒有系統匣時程式會只顯示懸浮窗。

**Q：懸浮窗在全螢幕遊戲/播放器上看不到？**
A：獨佔全螢幕模式下，任何置頂視窗都會被蓋掉，請把播放器改成「視窗化全螢幕 / 無邊框」。
Linux 的 Wayland 對「總在最前」支援有限，必要時改用 X11 工作階段。

**Q：懸浮窗擋到我點按鈕了。**
A：開啟選單裡的「鼠標穿透」，滑鼠就會直接點到下面的視窗；要再調整位置時把它關掉即可。

**Q：會不會很吃資源 / 會不會被風控？**
A：預設每 2 秒一次 TCP 交握 + 一份幾 KB 的播放清單，遠低於一個網頁播放器的流量；
探測失敗會自動退避。只用公開 API、不登入、不模擬觀看行為。

**Q：可以同時監測多個直播間嗎？**
A：一個使用者同時跑一份程式、監測一個對象。要同時記錄多個房間／影片，可以用不同的
`--config-dir` 搭配 `--probe-once` 寫成腳本定時執行。

---

## 🛠 開發

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q          # 單元測試，全部離線執行，不需要網路
python docs/make_screenshots.py    # 重新產生 README 的截圖
python assets/make_icon.py         # 重新產生圖示
```

專案結構：

```
src/lagscope/
├── cli.py            命令列進入點（run.py 只是免安裝的啟動器）
├── app.py            主程式：串起懸浮窗、狀態列、設定、監測執行緒
├── monitor.py        監測迴圈（獨立執行緒，含退避與時鐘校正）
├── config.py         每位使用者的設定檔（原子寫入、損毀自動隔離）
├── models.py         樣本與滾動統計
├── i18n.py           字串表（简体 / 繁體 / English）
├── translations.py   日本語 / 한국어（缺字自動回退英文）
├── recording.py      CSV 紀錄與輪替
├── autostart.py      三個平台的開機自動啟動
├── targets.py        決定「這一輪要量什麼」（GUI 與命令列共用）
├── events.py         卡頓／延遲突增事件與通知冷卻
├── probes/
│   ├── network.py    TCP RTT、TTFB、ICMP ping、時鐘偏移
│   ├── appnet.py     任意程式：連線表 → 伺服器 → 往返時間
│   ├── netspeed.py   全機上傳／下載速度
│   ├── stream.py     直播 playurl API、m3u8 解析、FLV tag 解析
│   ├── video.py      影片 view/playurl API、Range 測速與起播延遲
│   └── display.py    影格週期與顯示延遲估算
├── detect/           自動判斷你在看哪個頁面
│   ├── urls.py       B站網址 → 監測對象
│   ├── client.py     官方 PC 客戶端的資料夾（History / log，唯讀）
│   ├── history.py    瀏覽器歷史紀錄（複製後唯讀，只篩 bilibili.com）
│   ├── clipboard.py  剪貼簿裡的分享連結、b23.tv 短連結還原
│   ├── titles.py     視窗標題比對與「標題 ↔ 房間」記憶
│   ├── bridge.py     127.0.0.1 上的油猴腳本接收埠
│   └── manager.py    來源優先順序、節流與 --detect-report
└── ui/
    ├── overlay.py    懸浮窗（繪製、拖曳、跟隨視窗）
    ├── tray.py       狀態列圖示
    ├── settings.py   設定視窗
    ├── anchor.py     位置計算與 Windows 視窗搜尋
    ├── icons.py      程式內畫出來的圖示
    └── theme.py      配色與數字格式化

extras/
└── bililagscope-bridge.user.js   選用的油猴腳本（最準的自動偵測來源）
```

歡迎 issue 與 PR。送 PR 前請先跑過 `python -m pytest tests -q`。

---

## 📄 授權與聲明

MIT License，詳見 [LICENSE](LICENSE)。

本專案為**非官方**的第三方工具，與上海寬娛數碼科技有限公司（bilibili）無任何隸屬關係。
只使用公開的網頁 API 讀取直播間狀態與播放地址，不需要登入、不會蒐集或上傳任何個人資料。
「哔哩哔哩」「bilibili」為其各自權利人的商標。

---

# English

**Latency Monitor** shows, in real time, the latency of **any application** — a game, a
voice call, a browser, a download — in an always-on-top overlay and/or a status-bar
(tray) icon that draws the number right on itself. Bilibili gets extra depth on top:
it follows whatever you are watching (live rooms and ordinary videos alike) and
measures server → client → screen.

**[▸ Project site](https://cxu4425-beep.github.io/LagScope/)** ·
**[Download the latest release](https://github.com/cxu4425-beep/LagScope/releases/latest)**

### Highlights

**Any application**

- Pick a program and the monitor finds **the servers it is actually connected to**, then
  times them every round — falling back to `ping` for UDP games. It also shows how many
  sockets that program holds open.
- **Follow the foreground app**: whatever window you switch to is what gets measured.
- **A server address you type**: a game server, a VPN gateway, `8.8.8.8`.
- **Machine upload / download speed** on every sample, so you can see when something else
  is eating the line.
- **Stall and spike detection**: a failed probe, or latency jumping past twice its recent
  normal, is recorded as an event and can raise one (rate-limited) notification.
- **History and a report**: one summary row per minute is kept on disk, so the chart shows
  the evening that went wrong days later - and exports as a self-contained HTML report
  (see [History and report](#history-and-report)).
- **Finds out why, unattended**: when a probe fails or latency jumps, a cut-down path check
  runs in the background and its verdict is filed against that minute - so afterwards you
  know last night was the Wi-Fi, not just that it was bad.
- **An actual speed test**: saturates the line to measure real download speed, against
  **the CDN edge you are watching**, capped by both time and bytes, and marks the history
  so the self-inflicted spike is not mistaken for a fault
  (see [How fast is this line, really?](#how-fast-is-this-line-really)).

**Which apps are supported?** There is no whitelist - anything that opens a network
connection works, because the monitor reads the system connection table rather than
adapting to each program. Common examples and their Windows process names:

| App | Process | UDP? |
| --- | --- | --- |
| Roblox | `RobloxPlayerBeta.exe` | yes - ping |
| Discord | `Discord.exe` | voice is - falls back to ping |
| Zoom | `Zoom.exe` | yes - ping |
| VALORANT | `VALORANT-Win64-Shipping.exe` | yes - ping |
| League of Legends | `League of Legends.exe` | yes - ping |
| Chrome / Edge | `chrome.exe` / `msedge.exe` | no (TCP) |
| WeChat 微信 | `WeChat.exe` | no (TCP) |
| QQ | `QQ.exe` | partly |
| Genshin Impact 原神 | `YuanShen.exe` / `GenshinImpact.exe` | yes - ping |
| NetEase Cloud Music 网易云音乐 | `cloudmusic.exe` | no (TCP) |
| Tencent Meeting 腾讯会议 | `wemeetapp.exe` | yes - ping |

Games and voice apps hold one UDP socket to the game or voice server and several TCP ones to
web and CDN endpoints; the monitor picks the UDP peer, because that is the connection that
decides whether you lag.

Steam, Telegram, Spotify, CS2, Minecraft, OBS and any download client work the same way.
Process names differ between versions and regions, so don't memorise them: **Refresh** in the
settings lists the programs currently holding connections, and `LagScope.exe --list-apps`
does the same from the terminal.

**Bilibili**

- **Follows what you watch**: no pasting room ids — it detects the live room or video
  you have open and switches with you (see [Auto-detection](#auto-detection)).
- **Live rooms and videos**: live shows the distance from the live edge; a VOD shows
  **start-up delay** and **bandwidth headroom** (can this connection sustain that quality?).
- Total latency plus a **network / stream / display** breakdown, refreshed every 2 s (configurable).
- Overlay you can **drag freely**, **pin to a screen corner**, or **attach to the Bilibili window** (Windows).
- Tray icon with the live value, colour coded green / amber / red.
- Built for long sessions: bounded memory, exponential backoff, atomic config writes, auto recovery.
- Stats (avg / p95 / jitter or speed), a sparkline, and optional CSV logging with rotation.
- **No account, no cookies, no telemetry** — only the public endpoints a browser already calls.
- **Picks the fastest CDN edge**: the same room is served from several edges and the player
  just takes the first one. The monitor times them all periodically and moves to a clearly
  faster one - 25 ms *and* 20% better, at most once every three minutes, and never trading
  away the fmp4 format that makes the latency measured rather than estimated. It changes
  what this tool measures, not what your player is playing.
- **Room details**: popularity, category, uptime, quality name, codec and container.
- 简体中文 / 繁體中文 / English / 日本語 / 한국어, per-user settings, single instance per user.

### Watch several things at once

Beside the main target you can pin up to four more - the router, DNS, a voice app, any address -
and they appear under the main figure with their own colours. That is what separates "only this
game is laggy" from "the whole line is". They are measured in turn, one per round, so adding
them never slows the main figure down. Quick-add buttons fill in your router and DNS for you.

### Network check: which segment is to blame

`lagscope --diagnose` (or the tray menu) splits the path into **you → router → ISP → server**
(plus how long a name lookup takes, the segment most often missed when every ping looks fine),
measures each segment's latency and packet loss, reads the Wi-Fi signal, and names the culprit:
your Wi-Fi, your home network, your provider, the distance to the server, or packet loss. It uses
only the tools that ship with the OS - no admin rights, no raw sockets - and computes its
statistics from the individual replies, so it reads the same in any system language.

### Did the change help?

The tool can say the Wi-Fi is the problem. Whether moving the router actually helped was
never something it could answer - until now. **Mark this moment…** records what you changed,
and the report then compares the periods either side of it.

The honesty of that comparison is the whole feature: both sides use **the same length of
time**, the shorter of what is available either way, capped at six hours and refused below
five minutes. Six hours of "before" against five minutes of "after" would make almost any
change look like a triumph. A difference under 10 ms is reported as no real difference
rather than dressed up as an improvement, and average, p95 and packet loss are all compared,
because looking only at the average hides "it spikes occasionally".

The chart draws a dashed line at the marked moment, in the window and in the exported report.

### Self-test

Every Bilibili code path here - the playurl response, the HLS server clock, the FLV key
frame, the CDN comparison and the edge switch - was written against fixtures, because the
machine it was written on cannot reach Bilibili at all. The unit tests prove the parsing is
right *given that shape of input*; they cannot prove the input still has that shape.

`lagscope --selftest [room-id]` runs each probe once against the real thing and prints what
came back, asserting nothing. It is evidence for a person to read and paste into a bug
report. The output carries addresses inside your own network and the servers measured - no
Wi-Fi name, no public IP, no account.

### How fast is this line, really?

The `↓46.8M` in the status row is *passive* - what the machine happens to be moving right
now. That answers "is something else eating my bandwidth" and cannot answer "how fast could
this line go", because nothing was asking it to go fast.

**Speed test** in the tray menu does ask. Two things about it matter more than the number,
which is why it asks for confirmation first:

**It saturates the line while it runs.** Latency spikes and the stream may stutter. Because
that is self-inflicted, the app marks those minutes in the history first, so the spike is not
later investigated as a fault.

**It costs data.** Time *and* bytes are both capped - 10 seconds or 80 MB by default,
whichever comes first - so a gigabit line stops at the byte cap instead of pulling down a
gigabyte to fill its ten seconds. Both limits are settings.

Where it downloads from is deliberate: the CDN edge already serving what you are watching,
because whether you stutter depends on the path to *that* machine, not on the path to a speed
test site - they are frequently not even the same carrier. Only when nothing is being watched
does it fall back to a public endpoint (Cloudflare).

The result is included in the exported report, so the file you send to support carries both
the latency and the line speed. Headless: `lagscope --speedtest`.

The opening second of any connection is slow, and averaging TCP slow start in makes a fast
line look mediocre, so that stretch is measured separately and discarded. When a download
ends before the warm-up finishes it says the figure may read low rather than presenting it
as the line speed.

### Which server you were assigned

Bilibili's edge hostnames state who runs the node, often where it is, and which carrier it
sits behind - `cn-hbyc-ct-01` is Yichang on China Telecom, `upos-sz-mirrorhw` is Huawei Cloud,
`cn-gotcha09` is Bilibili's own edge. The report and `--selftest` decode them, because "why
does it stutter" is usually a question about *which machine you were assigned* rather than
about bandwidth, and a hostname a viewer cannot read is an answer they cannot act on.

The location is the guessable half, so it is looked up in a table of codes we are confident
about and otherwise handed back raw - `Hubei (hbqq) · China Unicom`, never an invented city.
A plausible wrong city is worse than an admitted unknown, because somebody would act on it.

Peer-assisted (PCDN/mCDN) nodes are flagged specifically. A name like
`xy118x123x45x67xy.mcdn.bilivideo.cn` spells an address out inside itself; those are consumer
connections reselling spare upstream, not datacentre machines, and being handed one is a
common and invisible reason for stuttering on a line that tests fine.

### Why this disagrees with ping

`lagscope --why-ping [host]` times ICMP and a TCP handshake against the *same resolved
address*, five rounds each, prints them side by side with the name lookup on its own line, and
says which of the four ordinary explanations the numbers support.

The most commonly missed one: `ping bilibili.com` reaches the front door while this measures
the edge actually serving the stream, and they can be in different provinces.

This also fixed a measurement error of its own. `create_connection(hostname)` resolves, so the
DNS lookup was quietly billed to the server's latency on every sample - a moving error, given
how short CDN name TTLs are. Resolution and handshake are now timed and reported separately.

### Why it is "always" laggy

"Always" is a claim about a pattern, and the app used to keep nothing that could answer it.

Every minute now records the CDN edge that served it, so the good minutes can be grouped
against the bad ones - and the comparison names the edge that **costs the most time overall**,
not the slowest one. An edge that is dreadful for four minutes matters less than a mediocre
one you sit on for half the evening.

Minutes are also grouped by hour of the week. "No pattern" is a real answer: it rules out
every clock-shaped cause and points at something constant instead. History is kept for a week
(about 0.9 MB) because a weekly pattern cannot exist inside two days.

The report then ends with an ordered list of things to try, each naming the observation behind
it. Nothing is suggested without evidence - a list that always says "restart your router"
teaches people to ignore the list - and where nothing on it is fixable from your side, it says
so rather than pretending every problem has a local fix.

**Run a self-test…** in the tray runs every probe against the real thing and copies the result
to the clipboard, without needing a terminal.

### Updates and what it connects to

Once a day at most, LagScope asks GitHub what the newest version number is - one public page,
no identifier, nothing uploaded. The setup wizard asks before it ever runs, and it can be
turned off in Settings.

When there is a new version you can let it install itself: it downloads the official
installer, verifies it against the sha256 the releases API publishes, runs it, and quits so
Windows can replace the executable. This is the only feature that downloads a file and then
executes it, so it is https-only from a fixed list of GitHub hosts (re-checked after
redirects), a digest mismatch deletes the file, an asset with no published digest is offered
as a link rather than installed, and a portable copy never rewrites itself - it opens the
download page, as before.

That is the entire list of things it talks to: whatever you are measuring, Bilibili's public
API (only in Bilibili mode, no login and no cookies), your own router and first hop during a
path check, and the releases page. A speed test started while nothing is being watched
also reaches speed.cloudflare.com; started while something is, it measures that CDN and
does not. No analytics, no accounts, no telemetry.

### History and report

The overlay answers "how is it right now"; nobody can answer "when did it break" from that.
One summary row per minute - average, best, worst, p95, jitter, loss, events - is kept on
disk, which is roughly 130 KB a day and survives a restart.

**Latency history** (tray menu) plots it: the average as a line, each minute's best-to-worst
as a band, stalls and spikes as ticks on the floor. Time the machine spent asleep is a real
gap in the line, never a straight segment across invented data. Ranges: 1 h / 6 h / 24 h /
everything, with the roughest hour named underneath.

**Export a health report** turns the same data into one HTML file and opens it: the chart,
the headline numbers, the roughest hour, the segment verdict and the side watches. The chart
is inline SVG and the styles are inline, so there is no JavaScript and nothing to fetch - it
can be attached to a ticket and opened offline weeks later. "Copy summary" produces the same
findings as plain text for a forum post.

It contains latency figures, addresses inside your own home network and the server being
measured. No public IP, no account, no cookies, no browsing history.

### Watch from your phone

Turn on **Settings → General → Phone dashboard** and open the shown address in a phone browser
on the same Wi-Fi - the same live numbers, on iPhone and Android, with nothing to install. It is
**read-only** (two GET endpoints, nothing can be changed from the phone), off by default, LAN
only, and can require an access code. The page is fully self-contained, so it works on a network
with no internet at all.

Running the full LagScope *on* a phone is not possible: since Android 10 an app cannot read
another app's connection table without root or a VPN service, and iOS allows no overlay over
other apps at all. The phone shows what the PC measures.

### Auto-detection

Independent, individually switchable local sources, highest priority first:

| Source | How | Works with | Default |
| --- | --- | --- | --- |
| **Userscript** | the page posts its URL to `http://127.0.0.1:23124` | browser (best, instant on tab changes) | off (install the script) |
| **Window title** | learns "this window title is that room", then recognises it | client / browser (Windows) | on |
| **History + window titles** | newest visited Bilibili URL, matched against open window titles | browser (Windows) | on |
| **Client records** | reads the desktop client's own data folder | **official desktop client (hands-free)** | on |
| **Copied link** | spots a Bilibili URL you copied to the clipboard | client fallback, shared links, any app | on |
| **History** | newest visited Bilibili URL in the time window | browser | on |

**Using the official desktop client?** Measuring works exactly the same — the numbers come
from the public API, not from your player — and detection needs nothing from you either:
the client is a Chromium-based app that keeps its own browsing records, and the monitor
reads those (read-only, Bilibili URLs only), falling back to the ids in the client's logs.
Run `lagscope --detect-report` to see exactly what was found on your machine; if the
client lives somewhere unusual, point at it with `--client-dir "PATH"`. Should a client
build store things differently, **share → copy link** still switches the target instantly
and teaches the monitor that window's title for next time.

Reading the browser history is deliberately narrow: the file is **copied** and opened
**read-only** (so a running browser is untouched and nothing is written back), only rows
whose URL contains `bilibili.com` are read, and the result — a room id or a BV id — stays
in memory. The clipboard source only ever acts on text containing a Bilibili URL and stores
nothing else. Turn any of them off in Settings → General → Auto-detection, or switch the
whole thing off from the tray menu. For the most accurate browser option, install
[`extras/bililagscope-bridge.user.js`](extras/bililagscope-bridge.user.js) in
Tampermonkey and tick "Accept userscript reports".

### Install

From [Releases](https://github.com/cxu4425-beep/LagScope/releases):

- **Windows**: `LagScope-setup.exe` is an installer that needs no administrator rights (it
  goes in your own profile, so a work or school machine is fine), adds a Start menu entry and
  an optional autostart, and uninstalls cleanly. `LagScope-windows-x64.zip` is the same
  program with nothing to install, for a USB stick.
- **macOS**: `LagScope-macos-arm64.zip` · **Linux**: `LagScope-linux-x64.tar.gz`

A first run asks three questions - what to watch, where the overlay goes, and whether it may
check for updates - and everything else has a default.

From source (Python 3.9+):

```bash
git clone https://github.com/cxu4425-beep/LagScope.git
cd LagScope
pip install -r requirements.txt
python run.py --room 21452505   # or: pip install -e . && lagscope
```

Build your own executable: `pip install -r requirements-dev.txt && python packaging/build.py`.

### Usage

Just open a Bilibili live room or video in your browser — the monitor picks it up on
its own. To pin it to one thing instead, right-click the tray icon (or the overlay) →
**Settings** → set "What to monitor" to a live room or a video and paste an id or URL.
With nothing selected and detection off it runs in network-only mode. Handy flags:

```bash
lagscope --lang en --room 21452505     # language + room (detection off)
lagscope --video BV1GJ411x7h7          # a video; URLs with ?p=2 work too
lagscope --no-detect                   # never auto-detect
lagscope --no-tray                     # overlay only
lagscope --config-dir /media/usb/cfg   # portable settings
lagscope --probe-once --detect         # one JSON measurement of what you are watching
lagscope --app ValorantGame.exe        # measure any application
lagscope --app-foreground              # measure whatever app is in front
lagscope --ping 8.8.8.8 --ping-port 53 # measure a server address
lagscope --list-apps                   # which programs are on the network right now
lagscope --diagnose                    # split the path up (add a host to pick the target)
lagscope --report                      # write the health report and print where it went
lagscope --history                     # print the last 24 h as text ("all" for everything)
lagscope --selftest [room]             # run every probe once for real and print the result
lagscope --speedtest                   # measure download speed once (saturates the line)
lagscope --why-ping [host]             # ICMP vs TCP side by side, and why they differ
```

### How the number is computed

For a **live room**, `total = stream + display`, where **stream** is measured from the
HLS playlist's `EXT-X-PROGRAM-DATE-TIME` server clock when available (shown as
*measured*) and estimated from the playlist window or the first FLV key frame otherwise
(*estimated*). For a **video**, the middle term is the start-up delay: a real 512 KB
ranged download gives a measured TTFB and throughput, and the figure shown is
`TTFB + bitrate ÷ throughput`, with the measured speed in the stats row.
**display** is a model of the client-to-photons delay you can calibrate or exclude.
The **network** RTT is reported for context and never added twice.
Full details, formulas and error bars: **[docs/METHODOLOGY.md](docs/METHODOLOGY.md)**.

### Licence

MIT. Unofficial third-party tool, not affiliated with bilibili.
