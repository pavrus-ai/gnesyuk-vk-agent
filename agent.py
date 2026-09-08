# -*- coding: utf-8 -*-
import os, re, json, html, random, sys, io, time, datetime, requests, urllib3
from PIL import Image
urllib3.disable_warnings()

VK_TOKEN = os.environ.get("VK_TOKEN", "").strip()
VK_USER_TOKEN = os.environ.get("VK_USER_TOKEN", "").strip()
VK_GROUP_ID = os.environ.get("VK_GROUP_ID", "").strip().lstrip("-")
TG_BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
GROQ_KEY = os.environ.get("GROQ_KEY", "").strip()
OR_KEY = os.environ.get("OPENROUTER_KEY", "").strip()

SITE = "https://pavrus.ru"
SITEMAP = SITE + "/sitemap.xml"
HISTORY = "history_vk.json"
CACHE = "sitemap_cache.json"
CACHE_TTL_DAYS = 7
API = "https://api.vk.com/method/"
VK_V = "5.131"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml",
      "Accept-Language": "ru-RU,ru;q=0.9"}
BRANDS = ["pavrus", "chartu", "restmoment", "htdz"]
BL = ["корзин", "кабинет", "избранн", "сравнени", "войти", "заказать звонок",
      "санкт-петербург", "москва", "новосибирск", "8 (800", "info@", "показать еще",
      "ваш город", "бесплатная доставка", "главная", "обратная связь"]

CATEGORY_SEEDS = [
    "https://pavrus.ru/catalog/pavrus-sistema-golosovaniya/",
    "https://pavrus.ru/catalog/pavrus-potolochnye-gromkogovoriteli/",
    "https://pavrus.ru/catalog/pavrus-nastennye-gromkogovoriteli/",
    "https://pavrus.ru/catalog/pavrus-mixer-amp/",
    "https://pavrus.ru/catalog/pavrus-konferents-sistema/",
    "https://pavrus.ru/catalog/pavrus-wireless-conferences/",
    "https://pavrus.ru/catalog/pavrus-videooborudovanie-dlya-konferents-zala/",
    "https://pavrus.ru/catalog/pavrus-sinkhronnyy-perevod/",
    "https://pavrus.ru/catalog/pavrus-acoustic-systems-line-array/",
    "https://pavrus.ru/catalog/zvukovye-protsessory/",
    "https://pavrus.ru/catalog/pavrus-mikshernye-pulty/",
    "https://pavrus.ru/catalog/pavrus-radiosistema/",
    "https://pavrus.ru/catalog/pavrus-usiliteli-moshchnosti/",
    "https://pavrus.ru/catalog/gotovye-videosteny/",
    "https://pavrus.ru/catalog/pavrus/",
    "https://pavrus.ru/catalog/pavrus-videowall-controller/",
    "https://pavrus.ru/catalog/svetodiodnyy-ekran-led-videostena/",
    "https://pavrus.ru/catalog/pavrus-proektor/",
    "https://pavrus.ru/catalog/ekran-Classic-Solution/",
    "https://pavrus.ru/catalog/pavrus-terminal-vks/",
    "https://pavrus.ru/catalog/besprovodnaya-sistema-kontenta/",
    "https://pavrus.ru/catalog/pavrus-kommutator-hdmi/",
    "https://pavrus.ru/catalog/matrichnyy-kommutator-pavrus/",
    "https://pavrus.ru/catalog/pavrus-udlinitel-po-ip-i-vitoy-pare/",
    "https://pavrus.ru/catalog/usilitel-raspredelitel-kramer/",
]

def log(msg):
    print(msg, flush=True)

log("Версия ℹ️ pavrus-vk-agent v11 (фото ТОЛЬКО через community token → пост на стене, без предложенных)")

# ============================================================
# ИИ
# ============================================================

def _extract(r):
    try: return r["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError): return None

def ai_groq(prompt):
    if not GROQ_KEY: return None
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            json={"model": "llama-3.3-70b-versatile", "temperature": 0.8,
                  "messages": [{"role": "user", "content": prompt + "\n\nВАЖНО: Пиши ТОЛЬКО на русском языке."}]},
            timeout=60).json()
        if "error" in r: return None
        return _extract(r)
    except Exception: return None

def ai_openrouter(prompt, model):
    if not OR_KEY: return None
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OR_KEY}", "HTTP-Referer": "https://github.com"},
            json={"model": model, "temperature": 0.8, "max_tokens": 2000,
                  "messages": [{"role": "user", "content": prompt + "\n\nВАЖНО: Пиши ТОЛЬКО на русском языке."}]},
            timeout=60).json()
        if "error" in r: return None
        return _extract(r)
    except Exception: return None

def ai_call(prompt, minlen=400):
    models = [
        ("groq", "llama-3.3-70b-versatile"),
        ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
        ("openrouter", "google/gemma-3-27b-it:free"),
        ("openrouter", "deepseek/deepseek-chat-v3-0324:free"),
        ("openrouter", "auto")
    ]
    for provider, model in models:
        try:
            log(f"🔄 Попытка: {provider} ({model})...")
            res = ai_groq(prompt) if provider == "groq" else ai_openrouter(prompt, model)
            if res and len(res) >= minlen:
                log(f"✅ Успех: {provider} ({model}), {len(res)} симв.")
                return res
        except Exception:
            pass
    return None

# ============================================================
# ХЕЛПЕРЫ
# ============================================================

def clean(s):
    for _ in range(3):
        s = html.unescape(s)
        s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def abs_url(u):
    u = (u or "").strip()
    if not u or u.startswith("data:"): return ""
    if u.startswith("//"): return "https:" + u
    if u.startswith("/"): return SITE + u
    if u.startswith("http"): return u
    return ""

def get_h1(r):
    m = re.search(r"<h1[^>]*>(.*?)</h1>", r, re.S | re.I)
    return clean(m.group(1)) if m else ""

def get_title_fallback(r):
    t = ""
    m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']', r, re.S | re.I)
    if m:
        t = clean(m.group(1))
    if not t:
        m = re.search(r"<title[^>]*>(.*?)</title>", r, re.S | re.I)
        t = clean(m.group(1)) if m else ""
    return re.split(r"\s*[—|]\s*", t)[0].strip()

def get_meta(r, name):
    for pat in (
        r'<meta[^>]+name=["\']' + name + r'["\'][^>]+content=["\'](.*?)["\']',
        r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']' + name + r'["\']',
    ):
        m = re.search(pat, r, re.S | re.I)
        if m:
            v = clean(m.group(1))
            if v: return v
    return ""

# ============================================================
# КЭШ КАРТЫ САЙТА
# ============================================================

def load_cache():
    try:
        d = json.load(open(CACHE, encoding="utf-8"))
        urls, ts = d.get("urls", []), d.get("ts", 0)
        age = (time.time() - ts) / 86400
        if urls and age < CACHE_TTL_DAYS:
            log(f"ℹ️ Этап 1: сохранённая карта сайта: {len(urls)} ссылок (возраст {age:.1f} дн.)")
            return urls, False
        log(f"ℹ️ Карта устарела ({age:.1f} дн.) — обновим")
    except Exception:
        log("ℹ️ Кэша карты нет — создадим")
    return [], True

def fetch_sitemap():
    urls = []
    xml = requests.get(SITEMAP, timeout=30, headers=UA).text
    locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", xml)
    smps = [l for l in locs if "sitemap" in l.lower()] or [SITEMAP]
    for sm in smps:
        try:
            x = requests.get(sm, timeout=30, headers=UA).text
        except Exception:
            continue
        urls += [u for u in re.findall(r"<loc>\s*(.*?)\s*</loc>", x) if "/catalog/" in u]
    urls = sorted(set(urls))
    if len(urls) < 10:
        for s in CATEGORY_SEEDS:
            try:
                h = requests.get(s, timeout=20, headers=UA).text
            except Exception:
                continue
            for href in re.findall(r'href=["\'](/catalog/[^"\']+)["\']', h):
                u = abs_url(href)
                if u and u not in urls:
                    urls.append(u)
        urls = sorted(set(urls))
    if not urls:
        raise RuntimeError("пустая карта сайта")
    json.dump({"ts": time.time(), "urls": urls}, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    log(f"✅ Этап 1: карта обновлена: {len(urls)} ссылок")
    return urls

def brand_rank(u):
    return 0 if any(b in u.lower() for b in BRANDS) else 1

# ============================================================
# ПАРСИНГ СТРАНИЦЫ (v9: галерея по классу — источник №1)
# ============================================================

def parse_page(r, h1):
    desc = get_meta(r, "description") or get_meta(r, "og:description")
    tail = re.sub(r"<script[^>]*>.*?</script>", " ", r, flags=re.S | re.I)
    tail = re.sub(r"<style[^>]*>.*?</style>", " ", tail, flags=re.S | re.I)
    for mk in ["Назад к списку", "Нужна консультация", "Подробная информация"]:
        i = tail.find(mk)
        if i != -1:
            tail = tail[:i]
    chunks = re.findall(r"<p[^>]*>(.*?)</p>", tail, re.S | re.I)
    chunks += re.findall(r'<div[^>]+class=["\'][^"\']*(?:descr|text|content|detail|char)[^"\']*["\'][^>]*>(.*?)</div>', tail, re.S | re.I)
    raw = " ".join(clean(c) for c in chunks)
    keep = [s.strip() for s in raw.split(". ")
            if len(s.strip()) > 30 and "{" not in s
            and not any(b in s.lower() for b in BL)]
    body = " ".join(keep)[:1500]

    imgs, seen = [], set()
    def add(u):
        if u and u.startswith("http") and u not in seen:
            seen.add(u)
            imgs.append(u)

    gallery_count = 0
    for tag in re.finditer(r'<(?:a|div|img)[^>]+class="[^"]*catalog-element-gallery-picture[^"]*"[^>]*>', r, re.I):
        t = tag.group(0)
        for attr in ("href", "data-src", "src"):
            am = re.search(attr + r'\s*=\s*["\']([^"\']+)["\']', t, re.I)
            if am and am.group(1).strip():
                u = abs_url(am.group(1).split(",")[0].strip().split(" ")[0])
                if u:
                    add(u)
                    gallery_count += 1
                break
    log(f"ℹ️ Фото из галереи товара (catalog-element-gallery-picture): {gallery_count}")

    for m in re.finditer(r'["\'](/upload/iblock/[^"\']+\.(?:jpg|jpeg|png|webp))["\']', r, re.I):
        add(abs_url(m.group(1)))
    for m in re.finditer(r'["\'](/upload/[^"\']+\.(?:jpg|jpeg|png|webp))["\']', r, re.I):
        add(abs_url(m.group(1)))
    og = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](.*?)["\']', r, re.S | re.I)
    if og:
        add(abs_url(og.group(1)))
    ls = re.search(r'<link[^>]+rel=["\']image_src["\'][^>]+href=["\'](.*?)["\']', r, re.S | re.I)
    if ls:
        add(abs_url(ls.group(1)))
    for tag in re.findall(r"<img[^>]+>", tail):
        for attr in ("data-src", "data-lazy-src", "data-original", "data-lazy", "src"):
            am = re.search(attr + r'\s*=\s*["\']([^"\']+)["\']', tag, re.I)
            if am and am.group(1).strip():
                add(abs_url(am.group(1).split(",")[0].strip().split(" ")[0]))
                break
        am = re.search(r'srcset\s*=\s*["\']([^"\']+)["\']', tag, re.I)
        if am:
            add(abs_url(am.group(1).split(",")[0].strip().split(" ")[0]))
    for m in re.finditer(r'background(?:-image)?\s*:\s*url\(["\']?([^"\')\s]+)["\']?\)', tail, re.I):
        add(abs_url(m.group(1)))

    log(f"ℹ️ Всего кандидатов картинок: {len(imgs)} (первая: {imgs[0][:70] if imgs else '—'})")
    return desc, body, imgs

def choose_image(imgs, referer):
    hdr = dict(UA)
    hdr["Referer"] = referer
    hdr["Accept"] = "image/avif,image/webp,image/png,image/*,*/*;q=0.8"
    best, best_px, checked, err_log = None, 0, 0, 0
    for u in imgs[:20]:
        try:
            rs = requests.get(u, timeout=20, headers=hdr)
            if rs.status_code != 200:
                if err_log < 4:
                    log(f"   ⚠️ img HTTP {rs.status_code}: {u[:90]}")
