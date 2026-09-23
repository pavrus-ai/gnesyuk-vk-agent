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

VK_API = "https://api.vk.com/method/"
VK_V = "5.131"
ALBUM_CACHE = "vk_album.json"
ATT_CACHE = "vk_att.json"
POLLINATIONS_API = "https://image.pollinations.ai/prompt/"
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

log("Версия ℹ️ gnesyuk-vk-agent v19 (OpenAI 1024x1024 low $0.011 + ЛИЦА разрешены; pollinations — силуэты со спины; остальное как v18: крючки, кэш вложения, антифлуд)")

# ============================================================
# ИИ-ТЕКСТ: ступени с диагностикой
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
# ПОСТЫ: крючок → эскалация → конкретика → обрыв
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
    """v19: сцена может включать героя с эмоцией/лицом — OpenAI это умеет;
    pollinations-страховка всё равно уйдёт в силуэт со спины (см. download_image)."""
    prompt = (f"Из текста ниже выбери ОДНУ самую интригующую сцену и опиши её в 1-2 предложениях: "
              f"драматичный момент с героем (допустимы эмоция, пол-оборота, лицо) ИЛИ загадочный "
              f"предмет/место, ощущение опасности или тайны. Без толп людей.\n\n"
              f"ТЕКСТ: {post[:1500]}")
    return ai_text(prompt, minlen=30, rescue_min=30)

# ============================================================
# КАРТИНКИ v19: OpenAI 1024x1024 low + лица; pollinations — силуэты
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
    """v19: два промпта. OpenAI — люди и лица разрешены (анатомия под защитой);
    pollinations — только силуэты со спины (страховка от несуразностей)."""
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
# ВК v19: кэш вложения на день + антифлуд-пауза 30 сек
# ============================================================

def vk_call(method, params=None, token=None):
    p = dict(params or {})
    p["access_token"] = token or VK_TOKEN
    p["v"] = VK_V
    try:
        r = requests.post(VK_API + method, data=p, timeout=30).json()
    except Exception as e:
        log(f"⚠️ VK {method}: {e}")
        return None
    if "error" in r:
        log(f"⚠️ VK {method}: {str(r.get('error'))[:150]}")
        return None
    return r.get("response")

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
        log(f"💾 ВК: вложение закэшировано в {ATT_CACHE} (повторные запуски сегодня не будут грузить фото)")
    except Exception as e:
        log(f"⚠️ vk_att cache: {e}")

def vk_get_album_id():
    env_id = os.environ.get("VK_ALBUM_ID", "").strip()
    if env_id.isdigit():
        return int(env_id)
    try:
        d = json.load(open(ALBUM_CACHE, encoding="utf-8"))
        if d.get("album_id"):
            return d["album_id"]
    except Exception:
        pass
    return None

def vk_upload_via_album(img_bytes):
    album = vk_get_album_id()
    if not album:
        log("ℹ️ ВК: путь 2 пропущен (нет VK_ALBUM_ID / vk_album.json)")
        return None
    for tok in (VK_USER_TOKEN, VK_TOKEN):
        if not tok:
            continue
        srv = vk_call("photos.getUploadServer",
                      {"group_id": VK_GROUP_ID, "album_id": album}, token=tok)
        if not srv or "upload_url" not in srv:
            continue
        try:
            r = requests.post(srv["upload_url"],
                              files={"file1": ("cover.jpg", img_bytes, "image/jpeg")},
                              timeout=120).json()
        except Exception:
            continue
        if not r.get("hash") or not r.get("photos_list"):
            log(f"⚠️ ВК upload в альбом: пустой ответ: {str(r)[:120]}")
            continue
        saved = vk_call("photos.save",
                        {"group_id": VK_GROUP_ID, "album_id": album,
                         "server": r.get("server", ""), "photos_list": r.get("photos_list", ""),
                         "hash": r.get("hash", "")}, token=tok)
        if saved:
            p = saved[0]
            att = f"photo{p['owner_id']}_{p['id']}"
            if p.get("access_key"):
                att += f"_{p['access_key']}"
            return att
    return None

def vk_upload_photo(img_bytes):
    tok = VK_USER_TOKEN or VK_TOKEN
    if not tok:
        log("⚠️ ВК: нет ни VK_USER_TOKEN, ни VK_TOKEN — пост без фото")
        return None
    if not VK_USER_TOKEN:
        log("⚠️ ВК: нет VK_USER_TOKEN — групповым токеном стену грузить нельзя (ошибка 27); "
            "пробую альбом-фолбэк")
    else:
        for rnd in range(2):
            for params in ({"group_id": VK_GROUP_ID}, {"owner_id": "-" + VK_GROUP_ID}):
                srv = vk_call("photos.getWallUploadServer", params, token=tok)
                if not srv or "upload_url" not in srv:
                    continue
                try:
                    r = requests.post(srv["upload_url"],
                                      files={"photo": ("cover.jpg", img_bytes, "image/jpeg")},
                                      timeout=120).json()
                except Exception:
                    continue
                if not r.get("photo"):
                    log(f"⚠️ VK upload вернул пустое photo (раунд {rnd+1}) — флуд")
                    continue
                if "server" not in r or "hash" not in r:
                    continue
                sp = dict(params)
                sp.update({"photo": r["photo"], "server": r["server"], "hash": r["hash"]})
                saved = vk_call("photos.saveWallPhoto", sp, token=tok)
                if saved:
                    p = saved[0]
                    att = f"photo{p['owner_id']}_{p['id']}"
                    if p.get("access_key"):
                        att += f"_{p['access_key']}"
                    log(f"✅ ВК: картинка загружена (wall server, юзер-токен) → {att}")
                    return att
            if rnd == 0:
                log("⏳ ВК: пауза 30 сек перед повтором (антифлуд, раунд 1/2)")
                time.sleep(30)
    att = vk_upload_via_album(img_bytes)
    if att:
        log(f"✅ ВК: картинка загружена (через альбом группы) → {att}")
        return att
    return None

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
# ГЛАВНАЯ ЛОГИКА
# ============================================================

def main():
    if not VK_TOKEN or not VK_GROUP_ID:
        log("⚠️ Нет VK_TOKEN/VK_GROUP_ID — пропуск ВК")
        return
    books = json.load(open("books.json", encoding="utf-8"))["books"]
    day = datetime.date.today().toordinal()
    book = books[day % len(books)]
    log(f"📚 Книга дня: «{book['title']}» ({book['series']})")
    log(f"🎣 Эмоциональный крючок сегодня: {head_style(day)}")

    if day % 3 == 0 and book.get("fragments"):
        post = build_quote_post(book, day)
    else:
        post = build_post(book, day)
    if len(post) > 750:
        post = trim_text(post, 700)
        log(f"✂️ Пост довёден до 700: {len(post)} симв.")
    log(f"✂️ Крючок поста: {post.split(chr(10))[0][:150]}")
    log(f"📝 Длина поста: {len(post)} симв.")
    link = book.get("url", "")
    link_part = f"\n\n📖 Читайте на ЛитРес: {link}" if link else ""
    caption = trim_text(post, 4000 - len(link_part) - len(TAGS) - 2) + link_part + "\n\n" + TAGS

    scene = build_scene(post)
    base_img = scene if scene else book.get("about", "")[:120]
    run_no = int(os.environ.get("GITHUB_RUN_NUMBER", "0"))
    img_bytes = None
    for attempt in range(4):
        seed = day + 3000000 + (run_no % 100) + attempt * 7919
        img_bytes = download_image(base_img, seed)
        if img_bytes:
            break
        log(f"⏳ Попытка {attempt + 1} не удалась, пробуем снова...")

    if img_bytes:
        img_bytes = convert_to_jpeg(img_bytes)
        os.makedirs("img", exist_ok=True)
        path = f"img/vk_{day}.jpg"
        with open(path, "wb") as f:
            f.write(img_bytes)
        log(f"💾 Картинка сохранена: {path}")
    else:
        candidates = []
        for f in glob.glob("img/vk_*.jpg"):
            with open(f, "rb") as fh:
                if image_ok(fh.read()):
                    candidates.append(f)
        if candidates:
            pick = candidates[-1]
            log(f"⚠️ Генерация не удалась — беру прежнюю картинку {pick}")
            with open(pick, "rb") as f:
                img_bytes = f.read()
        else:
            log("⚠️ Нет ни свежей, ни подходящей старой картинки")

    att = None
    if img_bytes:
        att = vk_load_att_cache(day)
        if not att:
            att = vk_upload_photo(img_bytes)
            if att:
                vk_save_att_cache(day, att)
    if not att:
        log("⚠️ Картинку загрузить не удалось — пост выйдет без картинки")
    res = vk_post_wall(caption, att)

    log("=" * 50)
    if res:
        log("✅ FINISH: пост о книге → ВК!" + (" (с картинкой)" if att else " (БЕЗ картинки!)"))
    else:
        log("❌ FINISH: пост не опубликован")
    log("=" * 50)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        raise
