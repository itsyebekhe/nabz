import json
import os
import re
from datetime import datetime
import urllib.request
import requests
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager

# Ensure Tehran Timezone (UTC+3:30)
try:
    from zoneinfo import ZoneInfo
    TEHRAN_TZ = ZoneInfo("Asia/Tehran")
except Exception:
    from datetime import timezone, timedelta
    TEHRAN_TZ = timezone(timedelta(hours=3, minutes=30))


def get_tehran_now() -> datetime:
    return datetime.now(TEHRAN_TZ)


# Cloudscraper / requests session setup
try:
    import cloudscraper
    session = cloudscraper.create_scraper()
except ImportError:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    })


def to_persian_digits(num_str: str) -> str:
    persian_digits = {
        "0": "۰", "1": "۱", "2": "۲", "3": "۳", "4": "۴",
        "5": "۵", "6": "۶", "7": "۷", "8": "۸", "9": "۹", ",": "،"
    }
    return "".join(persian_digits.get(char, char) for char in str(num_str))


def ensure_vazirmatn_font():
    font_path = "Vazirmatn-Bold.ttf"
    if not os.path.exists(font_path):
        url = "https://raw.githubusercontent.com/rastikerdar/vazirmatn/master/fonts/ttf/Vazirmatn-Bold.ttf"
        try:
            print("Downloading Vazirmatn font...")
            urllib.request.urlretrieve(url, font_path)
        except Exception as e:
            print(f"Failed to download font: {e}")
            return None

    if os.path.exists(font_path):
        font_manager.fontManager.addfont(font_path)
        return font_manager.FontProperties(fname=font_path)
    return None


def extract_js_array(html_text: str, var_name: str):
    pattern = r"(?:const|let|var)\s+" + re.escape(var_name) + r"\s*=\s*(\[\s*\{.*?\}\]\s*);"
    match = re.search(pattern, html_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception as e:
            print(f"Error parsing JSON for {var_name}: {e}")
    return []


def gregorian_to_jalali(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    jy = 979 if gy > 1600 else 0
    gy -= 1600 if gy > 1600 else 621
    gy2 = gy if (gm > 2) else (gy - 1)
    days = (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) - 80 + gd + g_d_m[gm - 1]
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def format_price_display(val, unit="تومان"):
    if not val or val == "نامشخص":
        return "نامشخص"
    try:
        val_clean = str(val).replace(",", "").strip()
        if "." in val_clean:
            formatted = f"{float(val_clean):,.2f}"
        else:
            formatted = f"{int(val_clean):,}"
        return to_persian_digits(formatted) + f" {unit}"
    except Exception:
        return to_persian_digits(str(val))


# Assets Registry
ASSETS = {
    "usd": {
        "title": "دلار آمریکا",
        "symbol": "USD",
        "type": "pegged_usd",
        "unit": "تومان",
        "chart": True,
        "color": "#2563eb",
        "fill": "#3b82f6"
    },
    "eur": {
        "title": "یورو اروپا",
        "symbol": "EUR",
        "type": "currency",
        "url": "https://alanchand.com/en/currencies-price/eur",
        "unit": "تومان",
        "chart": False
    },
    "gbp": {
        "title": "پوند انگلیس",
        "symbol": "GBP",
        "type": "currency",
        "url": "https://alanchand.com/en/currencies-price/gbp",
        "unit": "تومان",
        "chart": False
    },
    "gold_mesghal": {
        "title": "مثقال طلا (آبشده)",
        "symbol": "GOLD_MESGHAL",
        "type": "gold",
        "url": "https://alanchand.com/en/gold-price/abshodeh",
        "unit": "تومان",
        "chart": False
    },
    "gold_18k": {
        "title": "طلای ۱۸ عیار (هر گرم)",
        "symbol": "GOLD_18K",
        "type": "gold",
        "url": "https://alanchand.com/en/gold-price/18ayar",
        "unit": "تومان",
        "chart": True,
        "color": "#eab308",
        "fill": "#fde047"
    },
    "coin_emami": {
        "title": "سکه تمام امامی",
        "symbol": "COIN_EMAMI",
        "type": "gold",
        "url": "https://alanchand.com/en/gold-price/sekkeh",
        "unit": "تومان",
        "chart": True,
        "color": "#f59e0b",
        "fill": "#fcd34d"
    },
    "coin_bahar": {
        "title": "سکه بهار آزادی",
        "symbol": "COIN_BAHAR",
        "type": "gold",
        "url": "https://alanchand.com/en/gold-price/bahar",
        "unit": "تومان",
        "chart": False
    },
    "coin_half": {
        "title": "نیم سکه بهار آزادی",
        "symbol": "COIN_HALF",
        "type": "gold",
        "url": "https://alanchand.com/en/gold-price/nim",
        "unit": "تومان",
        "chart": False
    },
    "coin_quarter": {
        "title": "ربع سکه بهار آزادی",
        "symbol": "COIN_QUARTER",
        "type": "gold",
        "url": "https://alanchand.com/en/gold-price/rob",
        "unit": "تومان",
        "chart": False
    },
    "coin_gram": {
        "title": "سکه گرمی",
        "symbol": "COIN_GRAM",
        "type": "gold",
        "url": "https://alanchand.com/en/gold-price/sek",
        "unit": "تومان",
        "chart": False
    },
    "gold_ounce": {
        "title": "انس جهانی طلا",
        "symbol": "XAU_USD",
        "type": "ounce",
        "url": "https://alanchand.com/en/gold-price/usd_xau",
        "unit": "دلار",
        "chart": False
    }
}


def fetch_alanchand_asset(url, asset_type):
    """
    Fetches the HTML, extracts live price and historical array (fullPriceData).
    Auto-normalizes gold/currency units to Toman (or USD for ounce).
    """
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code != 200:
            return None, []

        html = resp.text
        soup = BeautifulSoup(html, "lxml")
        raw_history = extract_js_array(html, "fullPriceData")

        live_price = None

        # 1. Product Schema offers
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                c = json.loads(s.get_text(strip=True) or "{}")
                if c.get("@type") == "Product":
                    raw_val = float(c.get("offers", {}).get("price", 0))
                    curr = c.get("offers", {}).get("priceCurrency", "")
                    if curr == "IRR":
                        live_price = int(round(raw_val / 10.0))
                    elif curr == "USD":
                        live_price = round(raw_val, 2)
                    break
            except Exception:
                continue

        # 2. Input fallback
        if live_price is None:
            input_el = soup.find("input", attrs={"data-curr": "tmn"}) or soup.find("input", id="inputCalcValue")
            if input_el:
                val = input_el.get("data-price") or input_el.get("value")
                if val:
                    live_price = int(round(float(str(val).replace(",", "").strip()) / 10.0))

        # 3. Clean history items
        normalized_history = []
        if raw_history:
            # Check if prices in fullPriceData are in IRR (10x Toman) or already Toman
            sample_price = raw_history[-1].get("price", 0)
            is_irr = False
            if asset_type in ["currency", "gold"] and live_price:
                # If sample history price is ~10x greater than live Toman, it's in IRR
                if sample_price > live_price * 4:
                    is_irr = True

            for item in raw_history:
                ts = item.get("timestamp")
                p = item.get("price", 0)
                if not ts or not p:
                    continue

                dt = datetime.fromtimestamp(ts, tz=TEHRAN_TZ)
                d_str = dt.strftime("%Y-%m-%d")

                if asset_type == "ounce":
                    final_price = round(float(p), 2)
                elif is_irr:
                    final_price = int(round(p / 10.0))
                else:
                    final_price = int(round(p))

                record = {
                    "timestamp": ts,
                    "date": d_str,
                    "price": final_price,
                }
                if asset_type != "ounce":
                    record["price_toman"] = final_price
                    record["price_irr"] = final_price * 10

                if "hobab" in item:
                    record["bubble"] = item["hobab"]
                if "hobab_percent" in item:
                    record["bubble_percent"] = item["hobab_percent"]

                normalized_history.append(record)

        return live_price, normalized_history
    except Exception as e:
        print(f"Error fetching asset at {url}: {e}")
        return None, []


def update_asset_history(symbol_key, live_price, history_items=None, api_dir="api"):
    """Saves and appends asset history to api/history_<key>.json."""
    os.makedirs(api_dir, exist_ok=True)
    cfg = ASSETS[symbol_key]
    filename = f"history_{symbol_key}.json"
    api_file = os.path.join(api_dir, filename)

    history_map = {}

    if os.path.exists(api_file):
        try:
            with open(api_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
                for item in existing.get("history", []):
                    history_map[item["date"]] = item
        except Exception as e:
            print(f"Warning reading {api_file}: {e}")

    # Bootstrap from website full history if local file is empty
    if not history_map and history_items:
        print(f"Bootstrapping {len(history_items)} historical records for {symbol_key}...")
        for item in history_items:
            history_map[item["date"]] = item

    # Update today's live rate
    now_tehran = get_tehran_now()
    today_str = now_tehran.strftime("%Y-%m-%d")
    current_ts = int(now_tehran.timestamp())

    if live_price is not None:
        today_record = {
            "timestamp": current_ts,
            "date": today_str,
            "price": live_price
        }
        if cfg["unit"] == "تومان":
            today_record["price_toman"] = live_price
            today_record["price_irr"] = live_price * 10
        history_map[today_str] = today_record

    sorted_history = [history_map[k] for k in sorted(history_map.keys())]

    payload = {
        "symbol": cfg["symbol"],
        "title": cfg["title"],
        "unit": cfg["unit"],
        "timezone": "Asia/Tehran",
        "updated_at": now_tehran.strftime("%Y-%m-%d %H:%M:%S"),
        "total_records": len(sorted_history),
        "latest": sorted_history[-1] if sorted_history else None,
        "history": sorted_history
    }

    with open(api_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # Mirror USD to history.json for backwards compatibility
    if symbol_key == "usd":
        with open(os.path.join(api_dir, "history.json"), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    return sorted_history


def generate_chart(history_records, title, output_file, line_color="#2563eb", fill_color="#3b82f6", days_limit=180, unit="تومان"):
    if not history_records:
        return

    vazir_prop = ensure_vazirmatn_font()
    records = history_records[-days_limit:] if days_limit else history_records

    chart_dates = [datetime.strptime(item["date"], "%Y-%m-%d") for item in records]
    prices = [item["price"] for item in records]

    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    fig, ax = plt.subplots(figsize=(11, 5), dpi=150)

    ax.plot(chart_dates, prices, color=line_color, linewidth=2.3)
    ax.fill_between(chart_dates, prices, color=fill_color, alpha=0.15)

    latest_date = chart_dates[-1]
    latest_price = prices[-1]
    formatted_price = to_persian_digits(f"{latest_price:,.0f}" if isinstance(latest_price, (int, float)) else str(latest_price))

    ax.plot(latest_date, latest_price, marker="o", markersize=6, color=line_color)
    ax.annotate(
        f"{formatted_price} {unit}",
        xy=(latest_date, latest_price),
        xytext=(-95, 15),
        textcoords="offset points",
        fontproperties=vazir_prop,
        fontsize=10,
        bbox=dict(boxstyle="round,pad=0.4", fc="#ffffff", ec=line_color, lw=1.2),
        arrowprops=dict(arrowstyle="->", color=line_color, lw=1.2)
    )

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y/%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: to_persian_digits(f"{int(x):,}")))

    if vazir_prop:
        for label in ax.get_xticklabels() + ax.get_yticklabels():
            label.set_fontproperties(vazir_prop)

    ax.set_title(f"نمودار روند ۶ ماهه {title}", fontproperties=vazir_prop, fontsize=13, pad=15)
    ax.set_xlabel("تاریخ", fontproperties=vazir_prop, fontsize=10, labelpad=10)
    ax.set_ylabel(f"قیمت ({unit})", fontproperties=vazir_prop, fontsize=10, labelpad=10)
    ax.grid(True, linestyle="--", alpha=0.5)

    plt.tight_layout()
    plt.savefig(output_file, dpi=150)
    plt.close()
    print(f"Chart saved to {output_file}")


def update_readme(market_data):
    shamsi_date_str = market_data.get("date_shamsi_full", market_data.get("date", "--"))
    gregorian_date_str = market_data.get("date", "--")
    time_str = to_persian_digits(market_data.get("time", "--:--"))

    repo_slug = os.environ.get("GITHUB_REPOSITORY", "username/repo")
    BT = chr(96) * 3

    readme_content = f"""<div dir="rtl" align="center">

# 📊 نبض بازار | قیمت لحظه‌ای ارز، مسکوکات، طلا و نفت

[![Auto Update](https://img.shields.io/badge/Auto--Update-Every_30_Minutes-10b981?style=for-the-badge&logo=githubactions&logoColor=white)](#)
[![API Status](https://img.shields.io/badge/API-Live_&_Historical-3b82f6?style=for-the-badge&logo=json&logoColor=white)](#-وب‌سرویس-و-دسترسی-api)
[![Timezone](https://img.shields.io/badge/Timezone-Tehran_(UTC%2B3:30)-f59e0b?style=for-the-badge)](#)

<br/>

> [!NOTE]
> 📅 **تاریخ:** {shamsi_date_str} ({gregorian_date_str}) &nbsp;|&nbsp; ⏱ **ساعت آخرین بروزرسانی:** **{time_str}** (به وقت تهران)

<br/>

</div>

<div dir="rtl">

### 📋 جدول زنده نرخ‌ها

<table width="100%">
<thead>
<tr>
<th width="8%" align="center">نماد</th>
<th width="52%" align="right">عنوان شاخص بازار</th>
<th width="40%" align="left">قیمت زنده (بازار آزاد)</th>
</tr>
</thead>
<tbody>

<!-- بخش ارزها -->
<tr>
<th colspan="3" align="right" bgcolor="#f1f5f9">💵 ارزهای شاخص</th>
</tr>
<tr>
<td align="center">🇺🇸</td>
<td><b>دلار آمریکا</b></td>
<td align="left"><b>{format_price_display(market_data.get('usd'))}</b></td>
</tr>
<tr>
<td align="center">🇪🇺</td>
<td><b>یورو اروپا</b></td>
<td align="left"><b>{format_price_display(market_data.get('eur'))}</b></td>
</tr>
<tr>
<td align="center">🇬🇧</td>
<td><b>پوند انگلیس</b></td>
<td align="left"><b>{format_price_display(market_data.get('gbp'))}</b></td>
</tr>

<!-- بخش طلا -->
<tr>
<th colspan="3" align="right" bgcolor="#f1f5f9">🥇 طلا و مظنه</th>
</tr>
<tr>
<td align="center">✨</td>
<td><b>طلای ۱۸ عیار (هر گرم)</b></td>
<td align="left"><b>{format_price_display(market_data.get('gold_18k'))}</b></td>
</tr>
<tr>
<td align="center">⚖️</td>
<td><b>مثقال طلا (آبشده)</b></td>
<td align="left"><b>{format_price_display(market_data.get('gold_mesghal'))}</b></td>
</tr>
<tr>
<td align="center">🌐</td>
<td><b>انس جهانی طلا</b></td>
<td align="left"><b>{format_price_display(market_data.get('gold_ounce'), 'دلار')}</b></td>
</tr>

<!-- بخش سکه -->
<tr>
<th colspan="3" align="right" bgcolor="#f1f5f9">🪙 مسکوکات بهار آزادی</th>
</tr>
<tr>
<td align="center">🟡</td>
<td><b>سکه تمام امامی (طرح جدید)</b></td>
<td align="left"><b>{format_price_display(market_data.get('coin_emami'))}</b></td>
</tr>
<tr>
<td align="center">🟡</td>
<td><b>سکه بهار آزادی (طرح قدیم)</b></td>
<td align="left"><b>{format_price_display(market_data.get('coin_bahar'))}</b></td>
</tr>
<tr>
<td align="center">🟡</td>
<td><b>نیم سکه بهار آزادی</b></td>
<td align="left"><b>{format_price_display(market_data.get('coin_half'))}</b></td>
</tr>
<tr>
<td align="center">🟡</td>
<td><b>ربع سکه بهار آزادی</b></td>
<td align="left"><b>{format_price_display(market_data.get('coin_quarter'))}</b></td>
</tr>
<tr>
<td align="center">🟡</td>
<td><b>سکه گرمی</b></td>
<td align="left"><b>{format_price_display(market_data.get('coin_gram'))}</b></td>
</tr>

<!-- بخش انرژی -->
<tr>
<th colspan="3" align="right" bgcolor="#f1f5f9">🛢️ کامودیتی و انرژی</th>
</tr>
<tr>
<td align="center">⛽</td>
<td><b>نفت خام برنت / اوپک</b></td>
<td align="left"><b>{to_persian_digits(market_data.get('oil', 'نامشخص'))} دلار</b></td>
</tr>

</tbody>
</table>

---

### 📈 نمودارهای روند بازار

#### دلار آمریکا
<div align="center">
  <img src="usd_chart.png?raw=true" alt="نمودار روند قیمت دلار" width="100%" style="border-radius: 12px;" />
</div>

#### سکه تمام امامی
<div align="center">
  <img src="coin_emami_chart.png?raw=true" alt="نمودار روند قیمت سکه امامی" width="100%" style="border-radius: 12px;" />
</div>

#### طلای ۱۸ عیار
<div align="center">
  <img src="gold_18k_chart.png?raw=true" alt="نمودار روند قیمت طلای ۱۸ عیار" width="100%" style="border-radius: 12px;" />
</div>

---

### 🚀 وب‌سرویس و دسترسی API

داده‌های تاریخی به همراه قیمت روز برای هر دارایی در قالب فایل‌های تمیز JSON نگهداری می‌شوند:

* **قیمت‌های زنده تمامی نمادها:**
  {BT}text
  https://raw.githubusercontent.com/{repo_slug}/main/market.json
  {BT}

* **آرشیو تاریخی هر دارایی:**
  | دارایی | آدرس فایل JSON |
  | :--- | :--- |
  | **دلار آمریکا** | `https://raw.githubusercontent.com/{repo_slug}/main/api/history_usd.json` |
  | **یورو اروپا** | `https://raw.githubusercontent.com/{repo_slug}/main/api/history_eur.json` |
  | **پوند انگلیس** | `https://raw.githubusercontent.com/{repo_slug}/main/api/history_gbp.json` |
  | **سکه امامی** | `https://raw.githubusercontent.com/{repo_slug}/main/api/history_coin_emami.json` |
  | **سکه بهار آزادی** | `https://raw.githubusercontent.com/{repo_slug}/main/api/history_coin_bahar.json` |
  | **نیم سکه** | `https://raw.githubusercontent.com/{repo_slug}/main/api/history_coin_half.json` |
  | **ربع سکه** | `https://raw.githubusercontent.com/{repo_slug}/main/api/history_coin_quarter.json` |
  | **سکه گرمی** | `https://raw.githubusercontent.com/{repo_slug}/main/api/history_coin_gram.json` |
  | **طلای ۱۸ عیار** | `https://raw.githubusercontent.com/{repo_slug}/main/api/history_gold_18k.json` |
  | **مثقال طلا** | `https://raw.githubusercontent.com/{repo_slug}/main/api/history_gold_mesghal.json` |
  | **انس جهانی طلا** | `https://raw.githubusercontent.com/{repo_slug}/main/api/history_gold_ounce.json` |

</div>
"""
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(readme_content)
    print("README.md updated.")


def main():
    market_data = {}
    print("Starting market extraction...")

    # 1. Fetch USD (via AED Peg calculation)
    resp_aed = session.get("https://alanchand.com/en/currencies-price/aed", timeout=15)
    resp_usd = session.get("https://alanchand.com/en/exchange-rates/aed-usd", timeout=15)
    aed_irr_hist = extract_js_array(resp_aed.text, "fullPriceData") if resp_aed.status_code == 200 else []
    aed_usd_hist = extract_js_array(resp_usd.text, "fullPriceData") if resp_usd.status_code == 200 else []

    live_usd_toman = None
    try:
        soup_usd = BeautifulSoup(resp_usd.text, "lxml")
        soup_aed = BeautifulSoup(resp_aed.text, "lxml")
        usd_input = soup_usd.find("input", id="inputCalcValue") or soup_usd.find("input", id="outputCalcValue")
        usd_rate = float(usd_input.get("data-rate")) if usd_input and usd_input.get("data-rate") else 0.2723
        aed_input = soup_aed.find("input", attrs={"data-curr": "tmn"})
        aed_raw = aed_input.get("data-price") or aed_input.get("value") if aed_input else None
        if aed_raw:
            live_usd_toman = int(round((float(str(aed_raw).replace(",", "").strip()) / 10.0) / usd_rate))
    except Exception as e:
        print(f"USD calc error: {e}")

    usd_bootstrap_history = []
    if aed_irr_hist and aed_usd_hist:
        usd_rates = {
            datetime.fromtimestamp(x["timestamp"], tz=TEHRAN_TZ).strftime("%Y-%m-%d"): x.get("price") or x.get("dolar_rate", 0.272257)
            for x in aed_usd_hist
        }
        for item in aed_irr_hist:
            d = datetime.fromtimestamp(item["timestamp"], tz=TEHRAN_TZ).strftime("%Y-%m-%d")
            r = usd_rates.get(d, 0.272257)
            if r > 0:
                p_toman = int(round((item.get("price", 0) / 10.0) / r))
                usd_bootstrap_history.append({
                    "timestamp": item["timestamp"],
                    "date": d,
                    "price": p_toman,
                    "price_toman": p_toman,
                    "price_irr": p_toman * 10
                })

    market_data["usd"] = live_usd_toman
    usd_records = update_asset_history("usd", live_usd_toman, history_items=usd_bootstrap_history)
    generate_chart(usd_records, "دلار آمریکا", "usd_chart.png", line_color="#2563eb", fill_color="#3b82f6")

    # 2. Fetch all other assets
    for key, cfg in ASSETS.items():
        if key == "usd":
            continue
        print(f"Processing {cfg['title']} ({key})...")
        live_p, hist = fetch_alanchand_asset(cfg["url"], cfg["type"])
        market_data[key] = live_p
        records = update_asset_history(key, live_p, history_items=hist)

        if cfg.get("chart", False):
            chart_file = f"{key}_chart.png"
            generate_chart(
                records,
                cfg["title"],
                chart_file,
                line_color=cfg.get("color", "#2563eb"),
                fill_color=cfg.get("fill", "#3b82f6"),
                unit=cfg.get("unit", "تومان")
            )

    # 3. Fetch Oil Price
    try:
        resp_oil = session.get("https://oilprice.com/oil-price-charts/46", timeout=15)
        if resp_oil.status_code == 200:
            soup_oil = BeautifulSoup(resp_oil.text, "lxml")
            oil_el = soup_oil.select_one(".last_price")
            if oil_el:
                market_data["oil"] = oil_el.get_text(strip=True)
    except Exception as e:
        print(f"Error fetching Oil: {e}")

    # 4. Dates & market.json
    now_tehran = get_tehran_now()
    jy, jm, jd = gregorian_to_jalali(now_tehran.year, now_tehran.month, now_tehran.day)
    persian_months = [
        "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
        "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
    ]
    market_data["updated_at"] = now_tehran.strftime("%Y-%m-%d %H:%M:%S")
    market_data["date"] = now_tehran.strftime("%Y-%m-%d")
    market_data["date_shamsi"] = f"{jy}/{jm:02d}/{jd:02d}"
    market_data["date_shamsi_full"] = f"{to_persian_digits(jd)} {persian_months[jm - 1]} {to_persian_digits(jy)}"
    market_data["time"] = now_tehran.strftime("%H:%M")

    with open("market.json", "w", encoding="utf-8") as f:
        json.dump(market_data, f, ensure_ascii=False, indent=2)
    print("market.json saved.")

    # 5. Update README
    update_readme(market_data)
    print("All tasks finished successfully.")


if __name__ == "__main__":
    main()
