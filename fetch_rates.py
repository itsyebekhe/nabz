import json
import os
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager

# Tehran Timezone (UTC+3:30)
try:
    from zoneinfo import ZoneInfo
    TEHRAN_TZ = ZoneInfo("Asia/Tehran")
except Exception:
    from datetime import timezone, timedelta
    TEHRAN_TZ = timezone(timedelta(hours=3, minutes=30))


def get_tehran_now() -> datetime:
    return datetime.now(TEHRAN_TZ)


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
    p = {"0": "۰", "1": "۱", "2": "۲", "3": "۳", "4": "۴", "5": "۵", "6": "۶", "7": "۷", "8": "۸", "9": "۹", ",": "،"}
    return "".join(p.get(c, c) for c in str(num_str))


def ensure_vazirmatn_font():
    font_path = "Vazirmatn-Bold.ttf"
    if not os.path.exists(font_path):
        url = "https://raw.githubusercontent.com/rastikerdar/vazirmatn/master/fonts/ttf/Vazirmatn-Bold.ttf"
        try:
            import urllib.request
            urllib.request.urlretrieve(url, font_path)
        except Exception:
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
        except Exception:
            pass
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


# Complete assets registry
ALL_ASSETS = {
    # Gold & Coins
    "gold_mesghal": {"title": "مثقال طلا (آبشده)", "symbol": "MESGHAL", "type": "gold", "url": "https://alanchand.com/en/gold-price/abshodeh", "category": "gold"},
    "gold_18k": {"title": "طلای ۱۸ عیار", "symbol": "GOLD_18K", "type": "gold", "url": "https://alanchand.com/en/gold-price/18ayar", "category": "gold"},
    "coin_emami": {"title": "سکه تمام امامی", "symbol": "COIN_EMAMI", "type": "gold", "url": "https://alanchand.com/en/gold-price/sekkeh", "category": "gold"},
    "coin_bahar": {"title": "سکه بهار آزادی", "symbol": "COIN_BAHAR", "type": "gold", "url": "https://alanchand.com/en/gold-price/bahar", "category": "gold"},
    "coin_half": {"title": "نیم سکه", "symbol": "COIN_HALF", "type": "gold", "url": "https://alanchand.com/en/gold-price/nim", "category": "gold"},
    "coin_quarter": {"title": "ربع سکه", "symbol": "COIN_QUARTER", "type": "gold", "url": "https://alanchand.com/en/gold-price/rob", "category": "gold"},
    "coin_gram": {"title": "سکه گرمی", "symbol": "COIN_GRAM", "type": "gold", "url": "https://alanchand.com/en/gold-price/sek", "category": "gold"},
    "gold_ounce": {"title": "انس جهانی طلا", "symbol": "XAU", "type": "ounce", "url": "https://alanchand.com/en/gold-price/usd_xau", "category": "gold", "unit": "دلار"},

    # Fiats
    "usd": {"title": "دلار آمریکا", "symbol": "USD", "type": "pegged_usd", "category": "major"},
    "eur": {"title": "یورو اروپا", "symbol": "EUR", "type": "currency", "url": "https://alanchand.com/en/currencies-price/eur", "category": "major"},
    "aed": {"title": "درهم امارات", "symbol": "AED", "type": "currency", "url": "https://alanchand.com/en/currencies-price/aed", "category": "major"},
    "try": {"title": "لیر ترکیه", "symbol": "TRY", "type": "currency", "url": "https://alanchand.com/en/currencies-price/try", "category": "major"},
    "gbp": {"title": "پوند انگلیس", "symbol": "GBP", "type": "currency", "url": "https://alanchand.com/en/currencies-price/gbp", "category": "major"},
    "cad": {"title": "دلار کانادا", "symbol": "CAD", "type": "currency", "url": "https://alanchand.com/en/currencies-price/cad", "category": "major"},
    "aud": {"title": "دلار استرالیا", "symbol": "AUD", "type": "currency", "url": "https://alanchand.com/en/currencies-price/aud", "category": "major"},
    "cny": {"title": "یوان چین", "symbol": "CNY", "type": "currency", "url": "https://alanchand.com/en/currencies-price/cny", "category": "major"},
    "rub": {"title": "روبل روسیه", "symbol": "RUB", "type": "currency", "url": "https://alanchand.com/en/currencies-price/rub", "category": "fiat"},
    "iqd": {"title": "۱۰۰ دینار عراق", "symbol": "IQD", "type": "currency", "url": "https://alanchand.com/en/currencies-price/iqd", "category": "fiat"},
    "myr": {"title": "رینگیت مالزی", "symbol": "MYR", "type": "currency", "url": "https://alanchand.com/en/currencies-price/myr", "category": "fiat"},
    "gel": {"title": "لاری گرجستان", "symbol": "GEL", "type": "currency", "url": "https://alanchand.com/en/currencies-price/gel", "category": "fiat"},
    "azn": {"title": "منات آذربایجان", "symbol": "AZN", "type": "currency", "url": "https://alanchand.com/en/currencies-price/azn", "category": "fiat"},
    "amd": {"title": "۱۰۰ درام ارمنستان", "symbol": "AMD", "type": "currency", "url": "https://alanchand.com/en/currencies-price/amd", "category": "fiat"},
    "thb": {"title": "بات تایلند", "symbol": "THB", "type": "currency", "url": "https://alanchand.com/en/currencies-price/thb", "category": "fiat"},
    "omr": {"title": "ریال عمان", "symbol": "OMR", "type": "currency", "url": "https://alanchand.com/en/currencies-price/omr", "category": "fiat"},
    "inr": {"title": "روپیه هند", "symbol": "INR", "type": "currency", "url": "https://alanchand.com/en/currencies-price/inr", "category": "fiat"},
    "pkr": {"title": "روپیه پاکستان", "symbol": "PKR", "type": "currency", "url": "https://alanchand.com/en/currencies-price/pkr", "category": "fiat"},
    "jpy": {"title": "۱۰۰ ین ژاپن", "symbol": "JPY", "type": "currency", "url": "https://alanchand.com/en/currencies-price/jpy", "category": "fiat"},
    "sar": {"title": "ریال عربستان", "symbol": "SAR", "type": "currency", "url": "https://alanchand.com/en/currencies-price/sar", "category": "fiat"},
    "afn": {"title": "افغانی افغانستان", "symbol": "AFN", "type": "currency", "url": "https://alanchand.com/en/currencies-price/afn", "category": "fiat"},
    "sek": {"title": "کرون سوئد", "symbol": "SEK", "type": "currency", "url": "https://alanchand.com/en/currencies-price/sek", "category": "fiat"},
    "chf": {"title": "فرانک سوئیس", "symbol": "CHF", "type": "currency", "url": "https://alanchand.com/en/currencies-price/chf", "category": "fiat"},
    "qar": {"title": "ریال قطر", "symbol": "QAR", "type": "currency", "url": "https://alanchand.com/en/currencies-price/qar", "category": "fiat"},
    "krw": {"title": "۱۰۰ وون کره جنوبی", "symbol": "KRW", "type": "currency", "url": "https://alanchand.com/en/currencies-price/krw", "category": "fiat"},
    "nok": {"title": "کرون نروژ", "symbol": "NOK", "type": "currency", "url": "https://alanchand.com/en/currencies-price/nok", "category": "fiat"},
    "nzd": {"title": "دلار نیوزیلند", "symbol": "NZD", "type": "currency", "url": "https://alanchand.com/en/currencies-price/nzd", "category": "fiat"},
    "sgd": {"title": "دلار سنگاپور", "symbol": "SGD", "type": "currency", "url": "https://alanchand.com/en/currencies-price/sgd", "category": "fiat"},
    "hkd": {"title": "دلار هنگ کنگ", "symbol": "HKD", "type": "currency", "url": "https://alanchand.com/en/currencies-price/hkd", "category": "fiat"},
    "kwd": {"title": "دینار کویت", "symbol": "KWD", "type": "currency", "url": "https://alanchand.com/en/currencies-price/kwd", "category": "fiat"},
    "dkk": {"title": "کرون دانمارک", "symbol": "DKK", "type": "currency", "url": "https://alanchand.com/en/currencies-price/dkk", "category": "fiat"},
    "bhd": {"title": "دینار بحرین", "symbol": "BHD", "type": "currency", "url": "https://alanchand.com/en/currencies-price/bhd", "category": "fiat"},
    "tjs": {"title": "سامانی تاجیکستان", "symbol": "TJS", "type": "currency", "url": "https://alanchand.com/en/currencies-price/tjs", "category": "fiat"},
    "tmt": {"title": "منات ترکمنستان", "symbol": "TMT", "type": "currency", "url": "https://alanchand.com/en/currencies-price/tmt", "category": "fiat"},
    "kgs": {"title": "سام قرقیزستان", "symbol": "KGS", "type": "currency", "url": "https://alanchand.com/en/currencies-price/kgs", "category": "fiat"},
    "syp": {"title": "۱۰۰ لیر سوریه", "symbol": "SYP", "type": "currency", "url": "https://alanchand.com/en/currencies-price/syp", "category": "fiat"},
    "brl": {"title": "رئال برزیل", "symbol": "BRL", "type": "currency", "url": "https://alanchand.com/en/currencies-price/brl", "category": "fiat"},
    "ars": {"title": "پزو آرژانتین", "symbol": "ARS", "type": "currency", "url": "https://alanchand.com/en/currencies-price/ars", "category": "fiat"},
}


def fetch_single_asset(key, cfg):
    url = cfg.get("url")
    if not url:
        return key, None, []

    try:
        resp = session.get(url, timeout=12)
        if resp.status_code != 200:
            return key, None, []

        html = resp.text
        soup = BeautifulSoup(html, "lxml")
        raw_history = extract_js_array(html, "fullPriceData")
        live_price = None

        # Schema Product offer
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

        # Fallback to input
        if live_price is None:
            input_el = soup.find("input", attrs={"data-curr": "tmn"}) or soup.find("input", id="inputCalcValue")
            if input_el:
                val = input_el.get("data-price") or input_el.get("value")
                if val:
                    live_price = int(round(float(str(val).replace(",", "").strip()) / 10.0))

        clean_history = []
        if raw_history:
            sample_p = raw_history[-1].get("price", 0)
            is_irr = (cfg.get("type") != "ounce" and live_price and sample_p > live_price * 4)

            for item in raw_history:
                ts = item.get("timestamp")
                p = item.get("price", 0)
                if not ts or not p:
                    continue

                d_str = datetime.fromtimestamp(ts, tz=TEHRAN_TZ).strftime("%Y-%m-%d")
                final_p = round(float(p), 2) if cfg.get("type") == "ounce" else int(round(p / 10.0 if is_irr else p))

                rec = {"timestamp": ts, "date": d_str, "price": final_p}
                if cfg.get("type") != "ounce":
                    rec["price_toman"] = final_p
                    rec["price_irr"] = final_p * 10
                if "hobab" in item:
                    rec["bubble"] = item["hobab"]
                if "hobab_percent" in item:
                    rec["bubble_percent"] = item["hobab_percent"]
                clean_history.append(rec)

        return key, live_price, clean_history
    except Exception as e:
        print(f"Error fetching {key}: {e}")
        return key, None, []


def update_asset_history(symbol_key, live_price, history_items=None, api_dir="api"):
    os.makedirs(api_dir, exist_ok=True)
    cfg = ALL_ASSETS[symbol_key]
    api_file = os.path.join(api_dir, f"history_{symbol_key}.json")

    history_map = {}
    if os.path.exists(api_file):
        try:
            with open(api_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
                for item in existing.get("history", []):
                    history_map[item["date"]] = item
        except Exception:
            pass

    if not history_map and history_items:
        for item in history_items:
            history_map[item["date"]] = item

    now_tehran = get_tehran_now()
    today_str = now_tehran.strftime("%Y-%m-%d")

    if live_price is not None:
        rec = {"timestamp": int(now_tehran.timestamp()), "date": today_str, "price": live_price}
        if cfg.get("unit", "تومان") == "تومان":
            rec["price_toman"] = live_price
            rec["price_irr"] = live_price * 10
        history_map[today_str] = rec

    sorted_history = [history_map[k] for k in sorted(history_map.keys())]

    payload = {
        "symbol": cfg["symbol"],
        "title": cfg["title"],
        "unit": cfg.get("unit", "تومان"),
        "timezone": "Asia/Tehran",
        "updated_at": now_tehran.strftime("%Y-%m-%d %H:%M:%S"),
        "total_records": len(sorted_history),
        "latest": sorted_history[-1] if sorted_history else None,
        "history": sorted_history
    }

    with open(api_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

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

    latest_date, latest_price = chart_dates[-1], prices[-1]
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


def main():
    print("Starting multithreaded extraction for all fiats & coins...")
    market_data = {}

    # 1. Fetch USD Calculation via AED
    resp_aed = session.get("https://alanchand.com/en/currencies-price/aed", timeout=12)
    resp_usd = session.get("https://alanchand.com/en/exchange-rates/aed-usd", timeout=12)
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
        print(f"USD calculation error: {e}")

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
                usd_bootstrap_history.append({"timestamp": item["timestamp"], "date": d, "price": p_toman, "price_toman": p_toman, "price_irr": p_toman * 10})

    market_data["usd"] = live_usd_toman
    usd_records = update_asset_history("usd", live_usd_toman, history_items=usd_bootstrap_history)
    generate_chart(usd_records, "دلار آمریکا", "usd_chart.png", line_color="#2563eb", fill_color="#3b82f6")

    # 2. Parallel scraping of all other currencies & coins
    tasks = {k: v for k, v in ALL_ASSETS.items() if k != "usd"}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_single_asset, k, v) for k, v in tasks.items()]
        for future in as_completed(futures):
            key, live_p, hist = future.result()
            market_data[key] = live_p
            records = update_asset_history(key, live_p, history_items=hist)

            # Generate primary charts
            if key in ["coin_emami", "gold_18k", "eur"]:
                cfg = ALL_ASSETS[key]
                color = "#f59e0b" if "coin" in key else ("#eab308" if "gold" in key else "#10b981")
                generate_chart(records, cfg["title"], f"{key}_chart.png", line_color=color, fill_color=color)

    # 3. Live Oil Price
    try:
        resp_oil = session.get("https://oilprice.com/oil-price-charts/46", timeout=10)
        if resp_oil.status_code == 200:
            oil_el = BeautifulSoup(resp_oil.text, "lxml").select_one(".last_price")
            if oil_el:
                market_data["oil"] = oil_el.get_text(strip=True)
    except Exception:
        pass

    # 4. Dates & market.json
    now_tehran = get_tehran_now()
    jy, jm, jd = gregorian_to_jalali(now_tehran.year, now_tehran.month, now_tehran.day)
    persian_months = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
    market_data["updated_at"] = now_tehran.strftime("%Y-%m-%d %H:%M:%S")
    market_data["date"] = now_tehran.strftime("%Y-%m-%d")
    market_data["date_shamsi"] = f"{jy}/{jm:02d}/{jd:02d}"
    market_data["date_shamsi_full"] = f"{to_persian_digits(jd)} {persian_months[jm - 1]} {to_persian_digits(jy)}"
    market_data["time"] = now_tehran.strftime("%H:%M")

    with open("market.json", "w", encoding="utf-8") as f:
        json.dump(market_data, f, ensure_ascii=False, indent=2)

    print(f"Successfully processed {len(ALL_ASSETS)} assets and updated market.json.")


if __name__ == "__main__":
    main()
