# -*- coding: utf-8 -*-
import os, json, random, requests, hashlib, io, urllib.parse
try:
    from PIL import Image
    PIL_OK = True
except Exception:
    PIL_OK = False

VK_TOKEN = os.getenv("VK_TOKEN", "")
VK_USER_TOKEN = os.getenv("VK_USER_TOKEN", "")
VK_GROUP = os.getenv("VK_GROUP_ID", "").strip().lstrip("-")
GROQ_KEY = os.getenv("GROQ_KEY", "")
OR_KEY = os.getenv("OPENROUTER_KEY", "")

MUSIC_FILE = "music.json"
HISTORY_FILE = "music_history.json"
POLLINATIONS_API = "https://image.pollinations.ai/prompt/"
COVERS_BASE = "https://raw.githubusercontent.com/pavrus-ai/gnesyuk-vk-agent/main/covers/"

# Соответствие альбомов файлам обложек в папке covers/
COVER_FILES = {
    "Оставим грусть. С Новым Годом!": "ostavim-grust.jpg",
    "Горячий песок Египта": "goryachiy-pesok-egipta.jpg",
    "Дар богов": "dar-bogov.jpg",
    "Imperium": "imperium.jpg",
    "Энергия для души": "energiya-dlya-dushi.jpg",
    "Бездна": "bezdna.jpg",
    "Тишина вместо слов": "tishina-vmesto-slov.jpg",
    "Управление чувствами": "upravlenie-chuvstvami.jpg",
    "Небесный страж": "nebesnyy-strazh.jpg",
    "Пленники Хроноса": "plenniki-khronosa.jpg",
    "Поколение ветра": "pokolenie-vetra.jpg",
    "Туманные зеркала": "tumannye-zerkala.jpg",
    "Раскаленный мир": "raskalennyy-mir.jpg",
    "Обжигающий": "obzhigayushchiy.jpg",
    "Лекарство от печали": "lekarstvo-ot-pechali.jpg",
    "Пока ты ждёшь": "poka-ty-zhdesh.jpg",
    "Весенние чувства": "vesennie-chuvstva.jpg",
    "Тени Великой Тартарии": "teni-velikoy-tartarii.jpg",
    "Spirit": "spirit.jpg",
    "Enjoyments": "enjoyments.jpg",
    "Турецкие мотивы": "turetskie-motivy.jpg",
    "Прикосновения": "prikosnoveniya.jpg",
    "Истоки славы": "istoki-slavy.jpg",
    "Цена тишины": "tsena-tishiny.jpg",
    "Под одним небом": "pod-odnim-nebom.jpg",
    "Дух свободы": "dukh-svobody.jpg",
    "Gloria Romae": "gloria-romae.jpg",
    "Gloria Romae II": "gloria-romae-2.jpg",
    "Сибирский ветер": "sibirskiy-veter.jpg",
    "Чувственный горизонт": "chuvstvennyy-gorizont.jpg",
    "Твой свет": "tvoy-svet.jpg",
    "Дух возвращается": "dukh-vozvrashchaetsya.jpg",
    "Энергия существует": "energiya-sushchestvuet.jpg",
    "Тёплый свет": "tyoplyy-svet.jpg",
    "Россия матушка зовет (folk garmonica)": "rossiya-matushka-zovet.jpg",
    "Шторм и штиль": "shtorm-i-shtil.jpg"
}

def log(msg):
    print(msg, flush=True)

log("Версия ℹ️ music-agent v5 (music.json + covers/ + генерация 1:1)")

def _extract(r):
    try: return r["choices"][0]["message"]["content"].strip()
    except Exception: return None

def ai_call(prompt):
    models = [
        ("groq", "llama-3.3-70b-versatile", GROQ_KEY),
        ("openrouter", "meta-llama/llama-3.3-70b-instruct:free", OR_KEY),
        ("openrouter", "google/gemma-3-27b-it:free", OR_KEY),
        ("openrouter", "auto", OR_KEY)
    ]
    for provider, model, key in models:
        if not key: continue
        try:
            url = "https://api.groq.com/openai/v1/chat/completions" if provider == "groq" else "https://openrouter.ai/api/v1/chat/completions"
            headers = {"Authorization": f"Bearer {key}"}
            if provider == "openrouter": headers["HTTP-Referer"] = "https://github.com"
            r = requests.post(url, headers=headers, json={
                "model": model, "temperature": 0.8, "max_tokens": 800,
                "messages": [{"role": "user", "content": prompt + "\n\nВАЖНО: Пиши ТОЛЬКО на русском языке."}]
            }, timeout=45).json()
            if "error" not in r and "choices" in r:
                text = _extract(r)
                if text and 300 <= len(text) <= 750:
                    log(f"✅ Текст: {provider} ({model}), {len(text)} симв.")
                    return text
        except Exception:
            continue
    return None

def generate_text(track, album):
    coauthors = album.get("coauthors", [])
    co_text = f"Учти коллаборацию с {', '.join(coauthors)}. " if coauthors else ""
    song_info = track.get("about", "") or f"название «{track['title']}»"
    prompt = (
        f"Напиши пост о песне Павла Гнесюка для группы ВКонтакте.\n\n"
        f"ПЕСНЯ: «{track['title']}»\n"
        f"О ПЕСНЕ: {song_info}\n"
        f"АЛЬБОМ: «{album['title']}» ({album.get('type', 'альбом')}, {album.get('genre', '')}, {album.get('year', '')})\n"
        f"ОБ АЛЬБОМЕ: {album.get('about', '')}\n"
        f"СОАВТОРЫ: {', '.join(coauthors) if coauthors else 'сольно'}\n\n"
        f"ТРЕБОВАНИЯ:\n"
        f"1. ТОЛЬКО русский язык.\n"
        f"2. Длина СТРОГО 350-650 символов.\n"
        f"3. Начни с описания песни: о чём она, настроение, атмосфера. {co_text}\n"
        f"4. Добавь 1-2 предложения про смысл и атмосферу альбома.\n"
        f"5. В конце обязательно: 🎧 Слушать: {album['url']}\n"
        f"6. Стиль живой, искренний, без пафоса.\n"
        f"7. Хэштеги только: #ПавелГнесюк #музыка"
    )
    text = ai_call(prompt)
    if not text:
        log("⚠️ ИИ недоступен — шаблонный текст")
        text = (f"🎵 «{track['title']}» — трек из альбома «{album['title']}».\n\n"
                f"{album.get('about', '')}\n\n"
                f"🎧 Слушать: {album['url']}\n\n#ПавелГнесюк #музыка")
    return text

def get_cover(album, track):
    # 1. Ссылка из music.json
