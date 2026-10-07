# -*- coding: utf-8 -*-
import os, json, datetime, requests, time, io, glob, base64, uuid, urllib3, re
from PIL import Image, ImageEnhance
urllib3.disable_warnings()

GROQ_KEY = os.environ.get("GROQ_KEY", "").strip()
GROQ_KEY2 = os.environ.get("GROQ_KEY2", "").strip()
OR_KEY = os.environ.get("OPENROUTER_KEY", "").strip()
OR_KEY2 = os.environ.get("OPENROUTER_KEY2", "").strip()
CEREBRAS_KEY = os.environ.get("CEREBRAS_KEY", "").strip()
MISTRAL_KEY = os.environ.get("MISTRAL_KEY", "").strip()
OPENAI_KEY = os.environ.get("OPENAI_KEY", "").strip()
GIGACHAT_CLIENT_ID = os.environ.get("GIGACHAT_CLIENT_ID1", "").strip()
GIGACHAT_CLIENT_SECRET = os.environ.get("GIGACHAT_CLIENT_SECRET1", "").strip()
VK_TOKEN = os.environ.get("VK_TOKEN", "").strip()
VK_USER_TOKEN = os.environ.get("VK_USER_TOKEN", "").strip()
VK_GROUP_ID = os.environ.get("VK_GROUP_ID", "").strip().lstrip("-")
TG_BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
MAX_TOKEN = os.environ.get("MAX_BOT_TOKEN", "").strip()
MAX_CHAT = os.environ.get("MAX_CHAT_ID", "").strip()
LINK_IN_TG = os.environ.get("LINK_IN_TG", "1").strip() != "0"
# v22: режимы и диагностика
SCHEDULE = os.environ.get("SCHEDULE", "").strip()
TEST_IMAGE = os.environ.get("TEST_IMAGE", "").strip()          # напр. covers/imperium.jpg
DOC_FALLBACK = os.environ.get("DOC_FALLBACK", "0").strip() == "1"
PUBLISH_CRON = "0 3 * * *"

VK_API = "https://api.vk.com/method/"
VK_V = "5.131"
ALBUM_CACHE = "vk_album.json"
ATT_CACHE = "vk_att.json"
PENDING = "pending_attach.json"     # v22: пост ждёт картинку
POLLINATIONS_API = "https://image.pollinations.ai/prompt/"
MAX_APIS = ["https://platform-api.max.ru", "https://platform-api2.max.ru", "https://botapi.max.ru"]
TAGS = "#ПавелГнесюк #книги #авторскийблог #писатель"
RU = "\n\nВАЖНО: Пиши ТОЛЬКО на русском языке."

GROQ_MODELS = ["meta-llama/llama-4-scout-17b-16e-instruct",
               "meta-llama/llama-4-maverick-17b-128e-instruct",
               "openai/gpt-oss-120b",
               "llama-3.1-8b-instant"]

HEAD_STYLES = [
    "сцена с середины: читатель уже внутри события",
    "обращение на «ты»: поставь читателя на место героя",
    "ставка-угроза: что будет потеряно навсегда",
    "контраст в одной фразе: нежность и жестокость рядом",
    "признание шёпотом: интонация тайны, рассказанной доверительно",
    "сенсорное погружение: запах, звук, свет, холод",
    "предупреждение или запрет: «не читай это ночью»",
    "шокирующий факт или число из мира книги",
    "предательство крупным планом: предал самый близкий",
    "любовь против долга: запретное чувство вопреки всему",
    "хуже измены: холодность, непризнание, отчуждение",
    "цена любви: чем пришлось заплатить за чувство",
    "слёзный контраст: сила в бою и слабость в одном взгляде",
    "КАПС-КРИК: одна строка ЗАГЛАВНЫМИ до 60 символов как удар",
]

LABEL_RE = re.compile(
    r'^(заголовок[-\s]?тизер|заголовок|тизер|статья|анонс|ти?тр|caption|title|headline)\s*[:\-–]?\s*',
    re.I
)

def head_style(day, shift=0):
    return HEAD_STYLES[(day + shift) % len(HEAD_STYLES)]

def log(msg):
    print(msg, flush=True)

log("Версия ℹ️ gnesyuk-vk-agent v22 (один выстрел загрузки; pending_attach + wall.edit докрепление на тиках; барометр флуда; TEST_IMAGE; DOC_FALLBACK)")

# ============================================================
# ИИ-ТЕКСТ
# ============================================================
def _extract(r):
    try: return r["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError): return None

def _err_snippet(r):
    e = r.get("error") or {}
    code = e.get("code") or e.get("type") or "?"
    msg = str(e.get("message") or e)
    return f"{code}: {msg[:100]}"

_GIGACHAT_TOKEN = None
_GIGACHAT_TOKEN_EXPIRY = 0

def get_gigachat_token():
    global _GIGACHAT_TOKEN, _GIGACHAT_TOKEN_EXPIRY
    if not GIGACHAT_CLIENT_ID or not GIGACHAT_CLIENT_SECRET:
        return None
    if _GIGACHAT_TOKEN and time.time() < _GIGACHAT_TOKEN_EXPIRY:
        return _GIGACHAT_TOKEN
    try:
        credentials = base64.b64encode(f"{GIGACHAT_CLIENT_ID}:{GIGACHAT_CLIENT_SECRET}".encode()).decode()
        r = requests.post("https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
            headers={"Authorization": f"Basic {credentials}",
                     "RqUID": str(uuid.uuid4()),
                     "Content-Type": "application/x-www-form-urlencoded"},
            data={"scope": "GIGACHAT_API_PERS"},
            timeout=30, verify=False)
        log(f"ℹ️ GigaChat OAuth: статус {r.status_code}")
        if r.status_code != 200:
            log(f"⚠️ GigaChat OAuth тело: {r.text[:300]}")
            return None
        j = r.json()
        if "access_token" in j:
            _GIGACHAT_TOKEN = j["access_token"]
            _GIGACHAT_TOKEN_EXPIRY = time.time() + 1700
            log("✅ GigaChat: токен получен (действует 30 мин)")
            return _GIGACHAT_TOKEN
    except Exception as e:
        log(f"⚠️ GigaChat auth error: {e}")
    return None

def ai_gigachat(prompt):
    token = get_gigachat_token()
    if not token:
        return None
    try:
        r = requests.post("https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"model": "GigaChat:latest", "temperature": 0.9, "max_tokens": 2000,
                  "messages": [{"role": "user", "content": prompt + RU}]},
            timeout=90, verify=False)
        if r.status_code != 200:
            log(f"⚠️ GigaChat chat: статус {r.status_code}: {r.text[:200]}")
            return None
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log(f"⚠️ GigaChat error: {e}")
        return None

def ai_cerebras(prompt):
    if not CEREBRAS_KEY: return None
    try:
        r = requests.post("https://api.cerebras.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {CEREBRAS_KEY}"},
            json={"model": "llama-3.3-70b", "temperature": 0.8,
                  "messages": [{"role": "user", "content": prompt + RU}]}, timeout=60).json()
        if "error" in r:
            log(f"   ⚠️ cerebras: {_err_snippet(r)}")
            return None
        return _extract(r)
    except Exception as e:
        log(f"   ⚠️ cerebras: сеть/ошибка {str(e)[:80]}")
        return None

def ai_mistral(prompt):
    if not MISTRAL_KEY: return None
    try:
        r = requests.post("https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {MISTRAL_KEY}"},
            json={"model": "mistral-small-latest", "temperature": 0.8,
                  "messages": [{"role": "user", "content": prompt + RU}]}, timeout=60).json()
        if "error" in r:
            log(f"   ⚠️ mistral: {_err_snippet(r)}")
            return None
        return _extract(r)
    except Exception as e:
        log(f"   ⚠️ mistral: сеть/ошибка {str(e)[:80]}")
        return None

def ai_groq(prompt, key, model):
    if not key: return None
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "temperature": 0.8,
                  "messages": [{"role": "user", "content": prompt + RU}]}, timeout=60).json()
        if "error" in r:
            log(f"   ⚠️ groq {model}: {_err_snippet(r)}")
            return None
        return _extract(r)
    except Exception as e:
        log(f"   ⚠️ groq {model}: сеть/ошибка {str(e)[:80]}")
        return None

def ai_openrouter_auto(prompt, key, max_tokens):
    if not key: return None
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "HTTP-Referer": "https://github.com"},
            json={"model": "auto", "temperature": 0.8, "max_tokens": max_tokens,
                  "messages": [{"role": "user", "content": prompt + RU}]}, timeout=60).json()
        if "error" in r:
            log(f"   ⚠️ openrouter auto (max={max_tokens}): {_err_snippet(r)}")
            return None
        return _extract(r)
    except Exception as e:
        log(f"   ⚠️ openrouter auto: сеть/ошибка {str(e)[:80]}")
        return None

def ai_pollinations_text(prompt):
    try:
        r = requests.post("https://text.pollinations.ai/openai",
            json={"model": "openai", "temperature": 0.8,
                  "messages": [{"role": "user", "content": prompt + RU}]}, timeout=90).json()
        res = _extract(r)
        if res:
            return res
    except Exception as e:
        log(f"   ⚠️ pollinations-text: {str(e)[:80]}")
    return None

def ai_text(prompt, minlen=300, rescue_min=200):
    best_res = ""
    def take(res, label):
        nonlocal best_res
        if not res:
            return None
        if len(res) >= minlen:
            log(f"✅ Успех: {label}, {len(res)} симв.")
            return res
        log(f"   ⚠️ {label}: текст короче нужного ({len(res)}/{minlen}) — запомнен кандидатом")
        if len(res) > len(best_res):
            best_res = res
        return None
    if not GIGACHAT_CLIENT_ID:
        log("⚠️ gigachat: GIGACHAT_CLIENT_ID1 не передан в env!")
    else:
        log("🔄 Попытка: gigachat (GigaChat:latest)...")
        r = take(ai_gigachat(prompt), "gigachat")
        if r: return r
    if not CEREBRAS_KEY:
        log("⚠️ cerebras: CEREBRAS_KEY не передан в env!")
    else:
        log("🔄 Попытка: cerebras (llama-3.3-70b)...")
        r = take(ai_cerebras(prompt), "cerebras")
        if r: return r
    if not MISTRAL_KEY:
        log("⚠️ mistral: MISTRAL_KEY не передан в env!")
    else:
        log("🔄 Попытка: mistral (mistral-small)...")
        r = take(ai_mistral(prompt), "mistral")
        if r: return r
    for i, key in enumerate((GROQ_KEY, GROQ_KEY2)):
        if not key: continue
        for model in GROQ_MODELS:
            log(f"🔄 Попытка: groq ({model}, ключ {i+1})...")
            r = take(ai_groq(prompt, key, model), f"groq ({model}, ключ {i+1})")
            if r: return r
    for i, key in enumerate((OR_KEY, OR_KEY2)):
        if not key: continue
        for mt in (1000, 512):
            log(f"🔄 Попытка: openrouter auto (max_tokens={mt}, ключ {i+1})...")
            r = take(ai_openrouter_auto(prompt, key, mt), f"openrouter auto (max={mt}, ключ {i+1})")
            if r: return r
    log("🔄 Попытка: pollinations-text (без ключа)...")
    r = take(ai_pollinations_text(prompt), "pollinations-text")
    if r: return r
    if best_res and len(best_res) >= rescue_min:
        log(f"ℹ️ Никто не дал {minlen} симв. — беру лучший кандидат ({len(best_res)} симв.)")
        return best_res
    return None

def clean_txt(t):
    return t.replace("**", "").replace("##", "").replace("#", "").strip()

def fix_headline(txt):
    lines = [l for l in txt.split("\n") if l.strip() not in ("*", "-", "_", "**", "***")]
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines:
        first = lines[0].strip()
        m = LABEL_RE.match(first)
        if m:
            rest = first[m.end():].strip()
            label = first[:m.end()].strip()
            if rest:
                lines[0] = rest
                log(f"🩹 fix_headline: срезана метка «{label}» → крючок: {rest[:80]}")
            else:
                lines.pop(0)
                while lines and not lines[0].strip():
                    lines.pop(0)
                if lines:
                    log(f"🩹 fix_headline: метка «{label}» удалена, крючком стала строка: {lines[0].strip()[:80]}")
    return "\n".join(lines).strip()

def trim_text(t, limit):
    if len(t) <= limit: return t
    c = t[:limit]
    i = max(c.rfind("."), c.rfind("!"), c.rfind("?"), c.rfind("\n"))
    return (c[:i+1] if i > limit//2 else c).rstrip()

# ============================================================
# ПОСТЫ
# ============================================================
def build_post(book, day):
    t, a, s = book["title"], book["about"], book["series"]
    style = head_style(day)
    prompt = (f"Напиши пост-анонс для ВКонтакте о романе Павла Гнесюка «{t}» (серия «{s}»). "
              f"Сюжет: {a}. Требования: 1. ТОЛЬКО русский язык. "
              f"2. Первая строка — ЭМОЦИОНАЛЬНЫЙ КРЮЧОК (до 90 символов), приём сегодня: {style}. "
              f"Если приём «КАПС-КРИК» — первая строка ЗАГЛАВНЫМИ до 60 символов, остальной текст обычным регистром. "
              f"Крючок обязан вызывать эмоцию (страх, любопытство, сопереживание, предвкушение) и быть "
              f"привязан к конкретике книги (имена героев, события, места); НЕ повторяет название «{t}». "
              f"3. ЗАПРЕЩЕНО начинать пост со слов: роман, книга, серия, автор, Павел Гнесюк, жанр, "
              f"представляет, рассказывает, анонс. "
              f"4. Второе предложение усиливает напряжение. Середина — 2-3 абзаца конкретики: "
              f"имена, места, сенсорные детали (запах, звук, свет). "
              f"5. Финал — обрыв на интриге (открытый контур), затем короткий призыв прочитать. "
              f"6. Текст СТРОГО 500-700 символов, живой, без ** и #.")
    txt = ai_text(prompt, minlen=300, rescue_min=200)
    if not txt:
        log("⚠️ Пост не создан — стандартный текст.")
        txt = f"РОМАН «{t.upper()}»: ИСТОРИЯ, КОТОРАЯ ЗАТЯГИВАЕТ\n\n{a}"
    return fix_headline(clean_txt(txt))

def build_quote_post(book, day):
    fr = book["fragments"][day % len(book["fragments"])]
    style = head_style(day, 5)
    prompt = (f"Напиши пост для ВКонтакте: разбор цитаты из романа Павла Гнесюка «{book['title']}». "
              f"Цитата: «{fr}». Требования: 1. ТОЛЬКО русский язык. "
              f"2. Первая строка — ЭМОЦИОНАЛЬНЫЙ КРЮЧОК (до 90 символов), приём: {style}; "
              f"привязан к смыслу цитаты; НЕ повторяет название книги; без слов-меток «Заголовок/ТИТР». "
              f"3. 600-900 символов: раскрой смысл цитаты, атмосферу и интригу романа. "
              f"4. Сама цитата должна войти в текст поста. 5. Финал — обрыв на интриге.")
    txt = ai_text(prompt, minlen=250, rescue_min=150)
    if not txt:
        log("⚠️ Разбор цитаты не создан — стандартный пост.")
        return build_post(book, day)
    return fix_headline(clean_txt(txt))

def build_scene(post):
    prompt = (f"Из текста ниже выбери ОДНУ самую интригующую сцену и опиши её в 1-2 предложениях: "
              f"драматичный момент с героем (допустимы эмоция, пол-оборота, лицо) ИЛИ загадочный "
              f"предмет/место, ощущение опасности или тайны. Без толп людей.\n\n"
              f"ТЕКСТ: {post[:1500]}")
    return ai_text(prompt, minlen=30, rescue_min=30)

# ============================================================
# КАРТИНКИ + валидация на этапе создания/сохранения (v22)
# ============================================================
def image_stats(img_bytes):
    try:
        im = Image.open(io.BytesIO(img_bytes))
        im.verify()
        im = Image.open(io.BytesIO(img_bytes)).convert("L")
        im.thumbnail((64, 64))
        px = list(im.tobytes())
        avg = sum(px) / len(px)
        bright_ratio = sum(1 for p in px if p > 160) / len(px)
        return True, avg, bright_ratio
    except Exception:
        return False, 0.0, 0.0

def image_ok(img_bytes):
    ok, avg, br = image_stats(img_bytes)
    if not ok:
        return False
    good = avg >= 65 or br >= 0.10
    log(f"🔆 Яркость: средняя {avg:.0f}, ярких пикселей {br:.0%} "
        f"(пропуск: средняя≥65 ИЛИ акцент≥10%) → {'ПРОПУСК' if good else 'ОТБРАКОВКА'}")
    return good

def validate_image(img_bytes, label=""):
    """v22: жёсткая валидация перед любым использованием: открывается, JPEG-совместима, ≥400px."""
    try:
        im = Image.open(io.BytesIO(img_bytes))
        im.verify()
        im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        w, h = im.size
        if min(w, h) < 400:
            log(f"⚠️ Валидация {label}: размер {w}x{h} < 400 — отклонена")
            return None
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=90)
        data = buf.getvalue()
        log(f"✅ Валидация {label}: {w}x{h}, {len(data)} байт — картинка здорова")
        return data
    except Exception as e:
        log(f"⚠️ Валидация {label}: файл битый ({e}) — отклонён")
        return None

def brighten(img_bytes, target=80):
    ok, avg, br = image_stats(img_bytes)
    if not ok or avg >= target:
        return img_bytes
    factor = min(2.2, target / max(avg, 1))
    try:
        im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        im = ImageEnhance.Brightness(im).enhance(factor)
        im = ImageEnhance.Contrast(im).enhance(1.05)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=90)
        log(f"🌤 Авто-осветление: коэффициент {factor:.2f} (было средняя {avg:.0f})")
        return buf.getvalue()
    except Exception as e:
        log(f"⚠️ brighten: {e}")
        return img_bytes

def strip_watermark(img_bytes):
    try:
        im = Image.open(io.BytesIO(img_bytes))
        w, h = im.size
        cut = int(h * 0.09)
        im = im.crop((0, 0, w, h - cut))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=90)
        log(f"✂️ Водяной знак: срезана нижняя полоса {cut}px (было {w}x{h}, стало {im.size[0]}x{im.size[1]})")
        return buf.getvalue()
    except Exception as e:
        log(f"⚠️ strip_watermark: {e}")
        return img_bytes

def openai_image(prompt):
    if not OPENAI_KEY:
        return None
    try:
        r = requests.post("https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
            json={"model": "gpt-image-1", "prompt": prompt, "n": 1,
                  "size": "1024x1024", "quality": "low"},
            timeout=180).json()
        if "error" not in r:
            b64 = (r.get("data") or [{}])[0].get("b64_json")
            if b64:
                data = base64.b64decode(b64)
                log(f"✅ OpenAI gpt-image-1 (1024x1024 low, $0.011): картинка {len(data)} байт")
                return data
        else:
            log(f"⚠️ OpenAI gpt-image-1: {str(r['error'])[:120]}")
    except Exception as e:
        log(f"⚠️ OpenAI gpt-image-1 ошибка: {e}")
    return None

def pollinations_image(scene, seed):
    url = (POLLINATIONS_API + requests.utils.quote(scene) +
           f"?nologo=true&seed={seed}&model=flux&width=1024&height=576")
    try:
        r = requests.get(url, timeout=240)
        r.raise_for_status()
        return r.content
    except Exception as e:
        log(f"⚠️ Ошибка скачивания картинки (seed={seed}): {e}")
        return None

def download_image(scene_text, seed):
    clean_img = "".join(c for c in scene_text if c.isalnum() or c.isspace() or c in ".,-")[:220].strip()
    base = ("Eye-catching cinematic book-promo artwork, BRIGHT and LUMINOUS: golden-hour sunlight or "
            "glowing practical light filling the whole scene, vivid saturated colors, high contrast "
            "accents, one striking focal point, strong sense of danger and mystery, sharp focus, "
            "composition draws the eye to the center. Scene: " + clean_img + ". ")
    p_openai = base + ("People and FACES allowed: expressive half-turns and close-ups welcome, "
                       "anatomically perfect faces, coherent eyes and hands, natural skin texture, "
                       "cinematic portrait lighting. No text, no logos, no watermark")
    p_poll = base + ("People ONLY as distant silhouettes seen from behind, no faces, no close-ups. "
                     "No text, no logos, no watermark")
    g = openai_image(p_openai)
    if g:
        g = brighten(g)
        if image_ok(g):
            return g
        log("⚠️ OpenAI картинка не прошла фильтр даже после осветления — пробую дальше")
    g = pollinations_image(p_poll, seed)
    if g:
        ok, avg, br = image_stats(g)
        if not ok:
            log(f"⚠️ Pollinations вернул не картинку (seed={seed})")
            return None
        g = brighten(g)
        if image_ok(g):
            log(f"✅ Картинка-замануха: {len(g)} байт (seed={seed})")
            return strip_watermark(g)
        log(f"⚠️ Картинка не прошла фильтр даже после осветления (seed={seed})")
    return None

def convert_to_jpeg(img_bytes):
    try:
        im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        im.thumbnail((1024, 1024))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85, optimize=True)
        data = buf.getvalue()
        log(f"🖼 Финал: {im.size[0]}x{im.size[1]}, {len(data)} байт")
        return data
    except Exception:
        return img_bytes

# ============================================================
# ВК v22: один выстрел, барометр, wall.edit, doc-обход
# ============================================================
def vk_call(method, params=None, token=None, retries=4):
    p = dict(params or {})
    p["access_token"] = token or VK_TOKEN
    p["v"] = VK_V
    for attempt in range(retries):
        try:
            r = requests.post(VK_API + method, data=p, timeout=30).json()
        except Exception as e:
            log(f"⚠️ VK {method}: сеть {e}")
            time.sleep(5 * (attempt + 1))
            continue
        if "error" in r:
            err = r["error"]
            if err.get("error_code") == 9:
                delay = 15 * (attempt + 1)
                log(f"⏳ VK Flood control на {method}: жду {delay} сек (попытка {attempt+1}/{retries})...")
                time.sleep(delay)
                continue
            log(f"⚠️ VK {method}: {str(err)[:150]}")
            return None
        return r.get("response")
    log(f"❌ VK {method}: флуд-контроль не отпустил за {retries} попыток")
    return None

def flood_probe():
    """v22: ОДИН вызов = барометр флуда. Возвращает (зелёный?, srv)."""
    srv = vk_call("photos.getWallUploadServer", {"owner_id": "-" + VK_GROUP_ID},
                  token=VK_USER_TOKEN, retries=1)
    ok = bool(srv and "upload_url" in srv)
    log(f"🌡 Барометр флуда: {'ЗЁЛЕНЫЙ — загрузка доступна' if ok else 'КРАСНЫЙ — флуд/кулдаун'}")
    return ok, srv

def finish_upload(srv, img_bytes):
    """v22: шаги 2-3 по уже полученному upload_url (без повторных вызовов шага 1)."""
    r = {}
    try:
        r = requests.post(srv["upload_url"],
                          files={"photo": ("cover.jpg", img_bytes, "image/jpeg")},
                          timeout=120).json()
    except Exception as e:
        log(f"⚠️ ВК upload: ошибка POST: {e}")
    if not (r.get("photo") and r.get("hash")):
        log(f"⚠️ ВК upload: пустое photo: {str(r)[:120]}")
        return None
    saved = vk_call("photos.saveWallPhoto",
                    {"owner_id": "-" + VK_GROUP_ID, "photo": r["photo"],
                     "server": r.get("server", ""), "hash": r.get("hash", "")},
                    token=VK_USER_TOKEN, retries=2)
    if not saved:
        return None
    p = saved[0]
    att = f"photo{p['owner_id']}_{p['id']}"
    if p.get("access_key"):
        att += f"_{p['access_key']}"
    log(f"✅ ВК: картинка загружена (один выстрел) → {att}")
    return att

def vk_upload_doc(img_bytes):
    """v22 (DOC_FALLBACK=1): обход флуда photos.* через docs.*"""
    for tok in (VK_USER_TOKEN, VK_TOKEN):
        if not tok:
            continue
        srv = vk_call("docs.getUploadServer", {"group_id": VK_GROUP_ID}, token=tok, retries=1)
        if not srv or "upload_url" not in srv:
            continue
        try:
            r = requests.post(srv["upload_url"],
                              files={"file": ("book.jpg", img_bytes, "image/jpeg")},
                              timeout=120).json()
        except Exception:
            continue
        if not r.get("file"):
            continue
        saved = vk_call("docs.save", {"file": r["file"], "title": "book.jpg"}, token=tok, retries=2)
        if saved:
            d = saved[0] if isinstance(saved, list) else saved
            att = f"doc{d['owner_id']}_{d['id']}"
            log(f"✅ ВК: картинка загружена через DOC-обход → {att}")
            return att
    return None

def vk_edit_post(post_id, message, att):
    res = vk_call("wall.edit", {"owner_id": "-" + VK_GROUP_ID, "post_id": post_id,
                                "message": message, "attachments": att}, retries=2)
    if res:
        log(f"✅ ВК: картинка докреплена к посту {post_id} через wall.edit")
        return True
    return False

def vk_load_att_cache(day):
    try:
        d = json.load(open(ATT_CACHE, encoding="utf-8"))
        if d.get("day") == day and d.get("att"):
            log(f"ℹ️ ВК: беру вложение из кэша за сегодня: {d['att']}")
            return d["att"]
    except Exception:
        pass
    return None

def vk_save_att_cache(day, att):
    try:
        json.dump({"day": day, "att": att}, open(ATT_CACHE, "w", encoding="utf-8"))
        log(f"💾 ВК: вложение закэшировано в {ATT_CACHE}")
    except Exception as e:
        log(f"⚠️ vk_att cache: {e}")

def load_pending():
    try:
        if os.path.exists(PENDING):
            return json.load(open(PENDING, encoding="utf-8"))
    except Exception:
        pass
    return None

def save_pending(day, post_id, caption, img_file):
    try:
        json.dump({"day": day, "post_id": post_id, "caption": caption, "img_file": img_file},
                  open(PENDING, "w", encoding="utf-8"), ensure_ascii=False)
        log(f"💾 pending_attach.json создан: пост {post_id} ждёт картинку {img_file}")
    except Exception as e:
        log(f"⚠️ pending: {e}")

def clear_pending():
    try:
        if os.path.exists(PENDING):
            os.remove(PENDING)
            log("🧹 pending_attach.json удалён")
    except Exception:
        pass

def vk_post_wall(text, attachment=None):
    params = {"owner_id": "-" + VK_GROUP_ID, "message": text, "from_group": 1}
    if attachment:
        params["attachments"] = attachment
    res = vk_call("wall.post", params)
    if not res and VK_USER_TOKEN:
        log("⚠️ ВК: групповой токен не смог опубликовать — пробую юзер-токеном")
        res = vk_call("wall.post", params, token=VK_USER_TOKEN)
    if res:
        log(f"✅ ВК: пост опубликован: https://vk.com/wall-{VK_GROUP_ID}_{res.get('post_id')}")
        return res
    return None

# ============================================================
# TELEGRAM
# ============================================================
def tg_post(img_bytes, caption):
    if not TG_BOT or not TG_CHAT:
        log("ℹ️ TG не настроен (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID) — пропуск")
        return False
    cap = caption
    if len(cap) > 1000:
        cut = cap.rfind(".", 0, 1000)
        cap = cap[:cut+1] if cut > 800 else cap[:1000]
        log(f"✂️ TG: подписка обрезана до {len(cap)} симв. (лимит 1024)")
    try:
        if img_bytes:
            r = requests.post(f"https://api.telegram.org/bot{TG_BOT}/sendPhoto",
                data={"chat_id": TG_CHAT, "caption": cap},
                files={"photo": ("cover.jpg", img_bytes, "image/jpeg")}, timeout=120).json()
        else:
            r = requests.post(f"https://api.telegram.org/bot{TG_BOT}/sendMessage",
                data={"chat_id": TG_CHAT, "text": cap}, timeout=60).json()
        if r.get("ok"):
            log(f"✅ TG: пост о книге отправлен в {TG_CHAT}")
            return True
        log(f"⚠️ TG: {str(r)[:200]}")
    except Exception as e:
        log(f"⚠️ TG ошибка: {e}")
    return False

# ============================================================
# MAX
# ============================================================
def _max_headers():
    return ({"Authorization": f"Bearer {MAX_TOKEN}"}, {"Authorization": MAX_TOKEN})

def _max_call(method, params=None, payload=None):
    for base in MAX_APIS:
        for hdr in _max_headers():
            try:
                r = requests.post(f"{base}/{method}", headers=hdr, params=params,
                                  json=payload, timeout=60, verify=False)
                try:
                    j = r.json()
                except Exception:
                    continue
                if isinstance(j, dict) and j.get("code") == "verify.token":
                    continue
                log(f"ℹ️ MAX {method} → {base}")
                return j
            except Exception:
                continue
    return None

def _max_get(method, params=None):
    for base in MAX_APIS:
        for hdr in _max_headers():
            try:
                r = requests.get(f"{base}/{method}", headers=hdr, params=params,
                                 timeout=30, verify=False)
                try:
                    j = r.json()
                except Exception:
                    continue
                if isinstance(j, dict) and j.get("code") == "verify.token":
                    continue
                return j
            except Exception:
                continue
    return None

def max_collect_ids():
    ids, user_ids = [], []
    u = _max_get("updates")
    if isinstance(u, dict):
        ups = u.get("updates") or []
        log(f"ℹ️ MAX /updates: событий = {len(ups)}")
        for up in ups:
            t = up.get("update_type") or ""
            if t in ("bot_added", "bot_started", "chat_added", "bot_added_to_chat"):
                chat = up.get("chat") or ((up.get("message") or {}).get("recipient")) or {}
                cid = chat.get("chat_id") or chat.get("id") or up.get("chat_id")
                if cid and cid not in ids:
                    ids.insert(0, cid)
            rec = ((up.get("message") or {}).get("recipient")) or {}
            cid = rec.get("chat_id")
            if cid and cid not in ids:
                ids.append(cid)
            cid2 = up.get("chat_id")
            if cid2 and cid2 not in ids:
                ids.append(cid2)
    return ids, user_ids

def max_upload(img_bytes, chat_val):
    u = _max_call("uploads", params={"type": "image", "chat_id": chat_val})
    up_url = (u or {}).get("url") if isinstance(u, dict) else None
    if not up_url:
        log(f"⚠️ MAX uploads: нет url: {str(u)[:150]}")
        return None
    try:
        ru = requests.post(up_url, files={"data": ("cover.jpg", img_bytes, "image/jpeg")},
                           timeout=120, verify=False)
        rj = {}
        try:
            rj = ru.json()
        except Exception:
            pass
        tok = None
        if isinstance(rj, dict):
            ph = rj.get("photos") or {}
            if isinstance(ph, dict):
                for v in ph.values():
                    if isinstance(v, dict) and v.get("token"):
                        tok = v["token"]
                        break
            tok = tok or rj.get("token") or rj.get("file")
        if tok:
            log("✅ MAX: фото загружено, токен вложения получен")
            return [{"type": "image", "payload": {"token": tok}}]
        log(f"⚠️ MAX upload: токен не найден в ответе: {str(rj)[:150]}")
    except Exception as e:
        log(f"⚠️ MAX upload: {str(e)[:100]}")
    return None

def max_post(img_bytes, text):
    if not MAX_TOKEN:
        log("ℹ️ MAX_BOT_TOKEN не задан — MAX пропущен")
        return False
    ids, user_ids = max_collect_ids()
    variants = list(ids)
    if MAX_CHAT:
        sec = int(MAX_CHAT) if MAX_CHAT.lstrip("-").isdigit() else MAX_CHAT
        if sec not in variants:
            variants.append(sec)
        if str(MAX_CHAT) not in variants:
            variants.append(str(MAX_CHAT))
    if not variants:
        log("⚠️ MAX: ни одного chat_id из событий и секрета")
        return False
    log(f"ℹ️ MAX: кандидаты chat_id: {variants}")
    att = max_upload(img_bytes, variants[0]) if img_bytes else None
    for chat_val in variants:
        payload = {"text": text[:4000]}
        if att:
            payload["attachments"] = att
        r = _max_call("messages", params={"chat_id": chat_val}, payload=payload)
        ok = isinstance(r, dict) and (r.get("success") is True or isinstance(r.get("message"), dict))
        if ok:
            m = r.get("message") or {}
            log(f"✅ MAX: пост о книге отправлен (chat_id={chat_val}, id={m.get('id')})")
            return True
        log(f"⚠️ MAX: chat_id={chat_val} → {str(r)[:150]}")
    return False

# ============================================================
# v22: РЕЖИМ ТИКА (каждые 6 часов) — докрепление картинки
# ============================================================
def run_tick(day):
    log("🕐 Режим: ТИК (только барометр + докрепление картинки)")
    green, srv = flood_probe()
    pend = load_pending()
    if not pend:
        log("ℹ️ pending_attach.json нет — постов без картинки не ожидается")
        return True
    if pend.get("day", 0) < day - 1:
        log(f"⚠️ pending от {pend.get('day')} устарел (>1 сут) — сбрасываю")
        clear_pending()
        return True
    if not green:
        log("⏳ Флуд красный — картинка подождёт до следующего тика (вызовов больше не делаю)")
        return True
    img_file = pend.get("img_file", "")
    img_bytes = None
    if os.path.exists(img_file):
        with open(img_file, "rb") as f:
            img_bytes = validate_image(f.read(), label=img_file)
    if not img_bytes:
        log(f"⚠️ Файл картинки {img_file} недоступен/бит — сбрасываю pending")
        clear_pending()
        return True
    att = finish_upload(srv, img_bytes)
    if not att:
        log("⚠️ Загрузка на зелёном барометре не удалась — жду следующий тик")
        return True
    if vk_edit_post(pend["post_id"], pend["caption"], att):
        vk_save_att_cache(day, att)
        clear_pending()
        return True
    log("⚠️ wall.edit не смог докрепить — попробуем в следующем тике")
    return True

# ============================================================
# v22: РЕЖИМ ПУБЛИКАЦИИ (03:00 UTC / ручной запуск)
# ============================================================
def run_publish(day):
    log("Publish Режим: ПУБЛИКАЦИЯ (пост + одна попытка картинки)")
    if not VK_TOKEN or not VK_GROUP_ID:
        log("⚠️ Нет VK_TOKEN/VK_GROUP_ID — пропуск ВК")
        return
    books = json.load(open("books.json", encoding="utf-8"))["books"]
    book = books[day % len(books)]
    log(f"📚 Книга дня: «{book['title']}» ({book['series']})")
    log(f"🎣 Эмоциональный крючок сегодня: {head_style(day)}")
    if day % 3 == 0 and book.get("fragments"):
        post = build_quote_post(book, day)
    else:
        post = build_post(book, day)
    if len(post) > 750:
        post = trim_text(post, 700)
        log(f"✂️ Пост доведён до 700: {len(post)} симв.")
    log(f"✂️ Крючок поста: {post.split(chr(10))[0][:150]}")
    log(f"📝 Длина поста: {len(post)} симв.")

    link = book.get("url", "")
    link_part = f"\n\n📖 Читайте на ЛитРес: {link}" if (link and LINK_IN_TG) else ""
    caption = trim_text(post, 4000 - len(link_part) - len(TAGS) - 2) + link_part + "\n\n" + TAGS

    # Картинка: TEST_IMAGE → генерация → старая из img/
    img_bytes = None
    img_file = ""
    if TEST_IMAGE and os.path.exists(TEST_IMAGE):
        log(f"🧪 TEST_IMAGE: беру файл {TEST_IMAGE} вместо генерации")
        with open(TEST_IMAGE, "rb") as f:
            img_bytes = validate_image(f.read(), label=TEST_IMAGE)
        img_file = TEST_IMAGE
    if not img_bytes:
        scene = build_scene(post)
        base_img = scene if scene else book.get("about", "")[:120]
        run_no = int(os.environ.get("GITHUB_RUN_NUMBER", "0"))
        for attempt in range(4):
            seed = day + 3000000 + (run_no % 100) + attempt * 7919
            raw = download_image(base_img, seed)
            if raw:
                img_bytes = validate_image(convert_to_jpeg(raw), label="генерация")
                if img_bytes:
                    break
            log(f"⏳ Попытка {attempt + 1} не удалась, пробуем снова...")
    if img_bytes and not img_file:
        os.makedirs("img", exist_ok=True)
        img_file = f"img/vk_{day}.jpg"
        with open(img_file, "wb") as f:
            f.write(img_bytes)
        log(f"💾 Картинка сохранена: {img_file}")
    if not img_bytes:
        candidates = []
        for f in glob.glob("img/vk_*.jpg"):
            with open(f, "rb") as fh:
                if image_ok(fh.read()):
                    candidates.append(f)
        if candidates:
            img_file = candidates[-1]
            log(f"⚠️ Генерация не удалась — беру прежнюю картинку {img_file}")
            with open(img_file, "rb") as f:
                img_bytes = validate_image(f.read(), label=img_file)
        else:
            log("⚠️ Нет ни свежей, ни подходящей старой картинки")

    # Один выстрел загрузки
    att = vk_load_att_cache(day) if img_bytes else None
    if img_bytes and not att:
        green, srv = flood_probe()
        if green:
            att = finish_upload(srv, img_bytes)
            if att:
                vk_save_att_cache(day, att)
        elif DOC_FALLBACK:
            log("🧯 DOC_FALLBACK=1: пробую обход через docs.*")
            att = vk_upload_doc(img_bytes)
            if att:
                vk_save_att_cache(day, att)
        else:
            log("⚠️ Флуд красный: лишних вызовов не делаю, картинка уйдёт в pending")

    res = vk_post_wall(caption, att)
    ok_vk = bool(res)
    if ok_vk and att:
        log("✅ ВК: пост с картинкой")
    elif ok_vk and img_bytes:
        save_pending(day, res["post_id"], caption, img_file)
    ok_tg = tg_post(img_bytes, caption)
    ok_max = max_post(img_bytes, caption)

    log("=" * 50)
    log(f"✅ FINISH книги: ВК={'ДА' if ok_vk else 'НЕТ'}, TG={'ДА' if ok_tg else 'НЕТ'}, "
        f"MAX={'ДА' if ok_max else 'НЕТ'}" + ("" if att else " (картинка докрепится тиком)"))
    log("=" * 50)
    if not (ok_vk or ok_tg or ok_max):
        raise SystemExit(1)

# ============================================================
# ТОЧКА ВХОДА
# ============================================================
def main():
    day = datetime.date.today().toordinal()
    mode = "publish" if (not SCHEDULE or SCHEDULE == PUBLISH_CRON) else "tick"
    log(f"🗓 Расписание запуска: «{SCHEDULE or 'ручной'}» → режим: {mode}")
    if mode == "tick":
        run_tick(day)
    else:
        run_publish(day)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        raise
