# -*- coding: utf-8 -*-
import os, json, datetime, requests, time, io, glob, base64, uuid, urllib3
from PIL import Image
urllib3.disable_warnings()

GROQ_KEY = os.environ.get("GROQ_KEY", "").strip()
GROQ_KEY2 = os.environ.get("GROQ_KEY2", "").strip()
OR_KEY = os.environ.get("OPENROUTER_KEY", "").strip()
OR_KEY2 = os.environ.get("OPENROUTER_KEY2", "").strip()
CEREBRAS_KEY = os.environ.get("CEREBRAS_KEY", "").strip()
MISTRAL_KEY = os.environ.get("MISTRAL_KEY", "").strip()
OPENAI_KEY = os.environ.get("OPENAI_KEY", "").strip()
HF_TOKEN = os.environ.get("HF_TOKEN", "").strip()
GIGACHAT_CLIENT_ID = os.environ.get("GIGACHAT_CLIENT_ID1", "").strip()
GIGACHAT_CLIENT_SECRET = os.environ.get("GIGACHAT_CLIENT_SECRET1", "").strip()
VK_TOKEN = os.environ.get("VK_TOKEN", "").strip()
VK_USER_TOKEN = os.environ.get("VK_USER_TOKEN", "").strip()
VK_GROUP_ID = os.environ.get("VK_GROUP_ID", "").strip().lstrip("-")

VK_API = "https://api.vk.com/method/"
VK_V = "5.131"
ALBUM_CACHE = "vk_album.json"
POLLINATIONS_API = "https://image.pollinations.ai/prompt/"
TEXT_POLLINATIONS = "https://text.pollinations.ai/openai"
TAGS = "#ПавелГнесюк #книги #авторскийблог #писатель"
RU = "\n\nВАЖНО: Пиши ТОЛЬКО на русском языке."
MIN_BRIGHTNESS = 90

GROQ_MODELS = ["meta-llama/llama-4-scout-17b-16e-instruct",
               "meta-llama/llama-4-maverick-17b-128e-instruct",
               "openai/gpt-oss-120b",
               "llama-3.1-8b-instant"]

def log(msg):
    print(msg, flush=True)

log("Версия ℹ️ gnesyuk-vk-agent v13 (компактный пост 500-700 симв.; один запрос GigaChat; картинки: pollinations + HF router; альбом: photos.save)")

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
            json={"model": "GigaChat:latest", "temperature": 0.8, "max_tokens": 2000,
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
        r = requests.post(TEXT_POLLINATIONS,
            json={"model": "openai", "temperature": 0.8,
                  "messages": [{"role": "user", "content": prompt + RU}]}, timeout=90).json()
        res = _extract(r)
        if res:
            return res
    except Exception as e:
        log(f"   ⚠️ pollinations-text: {str(e)[:80]}")
    return None

def ai_text(prompt, minlen=200, rescue_min=150):
    """v13: снижен minlen до 200 для компактного поста."""
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

def trim_text(t, limit):
    if len(t) <= limit: return t
    c = t[:limit]
    i = max(c.rfind("."), c.rfind("!"), c.rfind("?"), c.rfind("\n"))
    return (c[:i+1] if i > limit//2 else c).rstrip()

# ============================================================
# ТЕКСТЫ ПОСТОВ (v13: компактные 500-700 симв.)
# ============================================================

def build_vk_post(book):
    t, a, s = book["title"], book["about"], book["series"]
    prompt = (f"Напиши пост для сообщества ВКонтакте о романе Павла Гнесюка «{t}» (серия «{s}»). "
              f"Сюжет: {a}. Требования: 1. ТОЛЬКО русский язык. 2. Первая строка — заголовок ЗАГЛАВНЫМИ "
              f"буквами, без ** и ##. 3. Текст 500-700 символов, интригующий, живой, как анонс. "
              f"4. Закончи вопросом или крючком.")
    txt = ai_text(prompt, minlen=200, rescue_min=150)
    if not txt:
        log("⚠️ Пост не создан — стандартный текст.")
        txt = f"РОМАН «{t.upper()}»: ИСТОРИЯ, КОТОРАЯ ЗАТЯГИВАЕТ\n\n{a}"
    return clean_txt(txt)

def build_quote_post(book, day):
    fr = book["fragments"][day % len(book["fragments"])]
    prompt = (f"Напиши пост для ВКонтакте: разбор цитаты из романа Павла Гнесюка «{book['title']}». "
              f"Цитата: «{fr}». Требования: 1. ТОЛЬКО русский язык. 2. Первая строка — заголовок ЗАГЛАВНЫМИ, "
              f"без ** и ##. 3. 400-600 символов: раскрой смысл цитаты, атмосферу и интригу романа. "
              f"4. Сама цитата должна войти в текст поста.")
    txt = ai_text(prompt, minlen=180, rescue_min=150)
    if not txt:
        log("⚠️ Разбор цитаты не создан — стандартный пост.")
        return build_vk_post(book)
    return clean_txt(txt)

def build_scene(post):
    prompt = (f"Из текста ниже выбери ОДНУ атмосферную сцену и опиши её в 1-2 предложениях "
              f"БЕЗ ЛЮДЕЙ и без лиц: только место, предметы, природа, погода, свет, детали интерьера.\n\n"
              f"ТЕКСТ: {post[:1500]}")
    return ai_text(prompt, minlen=30, rescue_min=30)

# ============================================================
# КАРТИНКИ v13: gpt-image-1 → dall-e-3 (без response_format) → HF router (пропуск при 410) → pollinations
# ============================================================

def image_stats(img_bytes):
    try:
        im = Image.open(io.BytesIO(img_bytes))
        im.verify()
        im = Image.open(io.BytesIO(img_bytes)).convert("L")
        im.thumbnail((64, 64))
        px = im.tobytes()
        return True, sum(px) / len(px)
    except Exception:
        return False, 0.0

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
    full = prompt + ", photorealistic, high resolution, no text, no logos, no watermark"
    try:
        r = requests.post("https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
            json={"model": "gpt-image-1", "prompt": full, "n": 1, "size": "1024x1024"},
            timeout=180).json()
        if "error" not in r:
            b64 = (r.get("data") or [{}])[0].get("b64_json")
            if b64:
                data = base64.b64decode(b64)
                log(f"✅ OpenAI gpt-image-1: картинка {len(data)} байт (без водяного знака)")
                return data
        else:
            log(f"⚠️ OpenAI gpt-image-1: {str(r['error'])[:120]}")
    except Exception as e:
        log(f"⚠️ OpenAI gpt-image-1 ошибка: {e}")
    try:
        r = requests.post("https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
            json={"model": "dall-e-3", "prompt": full, "n": 1,
                  "size": "1024x1024", "quality": "standard"}, timeout=120).json()
        if "error" in r:
            log(f"⚠️ OpenAI DALL-E 3: {str(r['error'])[:120]}")
            return None
        item = (r.get("data") or [{}])[0]
        if item.get("b64_json"):
            data = base64.b64decode(item["b64_json"])
            log(f"✅ OpenAI DALL-E 3: картинка {len(data)} байт (без водяного знака)")
            return data
        if item.get("url"):
            img = requests.get(item["url"], timeout=120).content
            log(f"✅ OpenAI DALL-E 3 (url): картинка {len(img)} байт")
            return img
    except Exception as e:
        log(f"⚠️ OpenAI DALL-E 3 ошибка: {e}")
    return None

def hf_image(prompt):
    if not HF_TOKEN:
        return None
    full = prompt + ", photorealistic, high resolution, no text, no logos, no watermark"
    bases = ["https://router.huggingface.co/hf-inference/models/"]
    for base in bases:
        for mdl in ("black-forest-labs/FLUX.1-schnell", "black-forest-labs/FLUX.1-dev"):
            try:
                r = requests.post(base + mdl,
                    headers={"Authorization": f"Bearer {HF_TOKEN}"},
                    json={"inputs": full}, timeout=60)
                if r.status_code == 410:
                    log(f"⚠️ HF {mdl}: 410 модель устарела — HF пропускаем")
                    return None
                if r.status_code == 200 and r.headers.get("Content-Type", "").startswith("image/"):
                    log(f"✅ HF {mdl}: картинка {len(r.content)} байт (без водяного знака)")
                    return r.content
                log(f"⚠️ HF {mdl}: ответ {r.status_code}: {r.text[:80]}")
            except Exception as e:
                log(f"⚠️ HF {mdl} ошибка: {str(e)[:80]}")
    return None

def pollinations_image(scene, seed):
    url = (POLLINATIONS_API + requests.utils.quote(scene) +
           f"?nologo=true&seed={seed}&model=flux&width=1280&height=960")
    try:
        r = requests.get(url, timeout=240)
        r.raise_for_status()
        return r.content
    except Exception as e:
        log(f"⚠️ Ошибка скачивания картинки (seed={seed}): {e}")
        return None

def download_image(scene_text, seed):
    clean_img = "".join(c for c in scene_text if c.isalnum() or c.isspace() or c in ".,-")[:220].strip()
    p = ("Wide-angle cinematic landscape photograph, absolutely NO people, NO faces, NO portraits, "
         "bright vivid saturated colors, high contrast, warm golden daylight, crisp sharp details. "
         "Scene: " + clean_img + ". "
         "Empty space without humans, only environment and objects, eye-level wide shot, "
         "no text, no watermark")
    g = openai_image(p)
    if g:
        ok, bright = image_stats(g)
        if ok and bright >= MIN_BRIGHTNESS:
            return g
        log(f"⚠️ OpenAI картинка слишком тёмная ({bright:.0f}) — пробую дальше")
    g = hf_image(p)
    if g:
        ok, bright = image_stats(g)
        if ok and bright >= MIN_BRIGHTNESS:
            return g
        log(f"⚠️ HF FLUX картинка слишком тёмная ({bright:.0f}) — пробую дальше")
    g = pollinations_image(p, seed)
    if g:
        ok, bright = image_stats(g)
        if not ok:
            log(f"⚠️ Pollinations вернул не картинку (seed={seed})")
            return None
        log(f"🔆 Яркость картинки: {bright:.0f} (порог {MIN_BRIGHTNESS})")
        if bright < MIN_BRIGHTNESS:
            log(f"⚠️ Слишком тёмная картинка (seed={seed}) — отбракована")
            return None
        log(f"✅ Картинка: {len(g)} байт (seed={seed})")
        return strip_watermark(g)
    return None

def convert_to_jpeg(img_bytes):
    try:
        im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=92)
        return buf.getvalue()
    except Exception:
        return img_bytes

# ============================================================
# ВК: путь 1 (wall server) → путь 2 (альбом, photos.save)
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
                files={"file1": ("cover.jpg", img_bytes, "image/jpeg")}, timeout=120).json()
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
        log("⚠️ ВК: нет VK_USER_TOKEN — пост без фото")
        return None
    img_bytes = convert_to_jpeg(img_bytes)
    os.makedirs("img", exist_ok=True)
    day = datetime.date.today().toordinal()
    with open(f"img/vk_{day}.jpg", "wb") as f:
        f.write(img_bytes)
    for rnd in range(2):
        for params in ({"group_id": VK_GROUP_ID}, {"owner_id": "-" + VK_GROUP_ID}):
            srv = vk_call("photos.getWallUploadServer", params, token=tok)
            if not srv or "upload_url" not in srv:
                continue
            try:
                r = requests.post(srv["upload_url"],
                    files={"photo": ("cover.jpg", img_bytes, "image/jpeg")}, timeout=120).json()
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
                log(f"✅ ВК: картинка загружена (wall server) → {att}")
                return att
        if rnd == 0:
            log("⏳ ВК: пауза 15 сек перед повтором (раунд 1/2)")
            time.sleep(15)
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
    if res:
        log(f"✅ ВК: пост опубликован: https://vk.com/wall-{VK_GROUP_ID}_{res.get('post_id')}")
        return res

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

    if day % 3 == 0 and book.get("fragments"):
        post = build_quote_post(book, day)
    else:
        post = build_vk_post(book)
    log(f"✂️ Заголовок поста: {post.split(chr(10))[0][:150]}")
    link_part = f"\n\n📖 Читайте на ЛитРес: {book['url']}"
    caption = trim_text(post, 2000 - len(link_part) - len(TAGS) - 2) + link_part + "\n\n" + TAGS

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

    if not img_bytes:
        candidates = []
        for f in glob.glob("img/vk_*.jpg"):
            with open(f, "rb") as fh:
                ok, bright = image_stats(fh.read())
            if ok and bright >= MIN_BRIGHTNESS:
                candidates.append((bright, f))
        if candidates:
            candidates.sort(reverse=True)
            pick = candidates[0][1]
            log(f"⚠️ Генерация не удалась — беру прежнюю картинку {pick}")
            with open(pick, "rb") as f:
                img_bytes = f.read()
        else:
            log("⚠️ Нет ни свежей, ни подходящей старой картинки")

    att = vk_upload_photo(img_bytes) if img_bytes else None
    if not att:
        log("⚠️ Картинку загрузить не удалось — пост выйдет без картинки")
    vk_post_wall(caption, att)

    log("=" * 50)
    log("✅ FINISH: пост о книге → ВК!" + (" (с картинкой)" if att else " (БЕЗ картинки!)"))
    log("=" * 50)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        raise
