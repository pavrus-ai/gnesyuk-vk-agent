# -*- coding: utf-8 -*-
import os, json, time, requests

COOKIES = os.getenv("VK_COOKIES", "")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Cookie": COOKIES,
    "Accept-Language": "ru-RU,ru;q=0.9",
}

ALBUMS = [
    ("Оставим грусть. С Новым Годом!", "-2000882358", "26882358"),
    ("Горячий песок Египта", "-2000087584", "26087584"),
    ("Дар богов", "-2000276266", "26276266"),
    ("Imperium", "-2000903105", "26903105"),
    ("Энергия для души", "-2000921965", "26921965"),
    ("Бездна", "-2000905527", "26905527"),
    ("Тишина вместо слов", "-2000915616", "26915616"),
    ("Управление чувствами", "-2000687207", "26687207"),
    ("Небесный страж", "-2000688683", "26688683"),
    ("Пленники Хроноса", "-2000688667", "26688667"),
    ("Поколение ветра", "-2000812994", "26812994"),
    ("Туманные зеркала", "-2000822740", "26822740"),
    ("Раскаленный мир", "-2000866265", "26866265"),
    ("Обжигающий", "-2000889455", "26889455"),
    ("Лекарство от печали", "-2000896190", "26896190"),
    ("Пока ты ждёшь", "-2000019250", "27019250"),
    ("Весенние чувства", "-2000142707", "27142707"),
    ("Тени Великой Тартарии", "-2000592309", "27592309"),
    ("Spirit", "-2000673297", "27673297"),
    ("Enjoyments", "-2000459373", "28459373"),
    ("Турецкие мотивы", "-2000457759", "28457759"),
    ("Прикосновения", "-2000457449", "28457449"),
    ("Истоки славы", "-2000517591", "28517591"),
    ("Цена тишины", "-2000694677", "28694677"),
    ("Под одним небом", "-2000817997", "28817997"),
    ("Дух свободы", "-2000819321", "28819321"),
    ("Gloria Romae", "-2000908768", "28908768"),
    ("Gloria Romae II", "-2000910959", "28910959"),
    ("Сибирский ветер", "-2000007672", "29007672"),
    ("Чувственный горизонт", "-2000295679", "27295679"),
    ("Твой свет", "-2000258699", "27258699"),
    ("Дух возвращается", "-2000688528", "28688528"),
    ("Энергия существует", "-2000690046", "28690046"),
    ("Тёплый свет", "-2000021745", "27021745"),
    ("Россия матушка зовет (folk garmonica)", "-2000267152", "26267152"),
    ("Шторм и штиль", "-2000266456", "26266456"),
]

def walk(obj, out):
    if isinstance(obj, dict):
        if "id" in obj and "owner_id" in obj and "title" in obj and ("duration" in obj or "artist" in obj):
            out[obj["title"]] = f"{obj['owner_id']}_{obj['id']}"
        for v in obj.values():
            walk(v, out)
    elif isinstance(obj, list):
        for v in obj:
            walk(v, out)

def parse_payload(text, out):
    idx = text.find("<!>")
    if idx == -1:
        return
    try:
        data = json.loads(text[idx+3:])
    except Exception:
        return
    payload = data.get("payload", []) if isinstance(data, dict) else data
    for item in (payload if isinstance(payload, list) else []):
        if isinstance(item, str) and item.strip().startswith(("{", "[")):
            try:
                walk(json.loads(item), out)
            except Exception:
                pass
        else:
            walk(item, out)

def main():
    if not COOKIES:
        print("❌ Нет VK_COOKIES")
        return
    result = {}
    total = 0
    first = True
    for title, owner, pl in ALBUMS:
        out = {}
        try:
            url = f"https://vk.ru/al_audio.php?act=section&al=1&claim=0&owner_id={owner}&playlist_id={pl}&type=playlist"
            h = dict(HEADERS)
            h["X-Requested-With"] = "XMLHttpRequest"
            h["Referer"] = f"https://vk.ru/music/album/{owner.lstrip('-')}_{pl}"
            r = requests.get(url, headers=h, timeout=30)
            if first:
                print(f"🔍 Диагностика: статус {r.status_code}, начало ответа: {r.text[:200]}")
                first = False
            parse_payload(r.text, out)
        except Exception as e:
            print(f"⚠️ {title}: {e}")
        result[title] = out
        total += len(out)
        print(f"🎵 {title}: {len(out)} треков")
        if out:
            ex = list(out.items())[0]
            print(f"   пример: {ex[0]} → {ex[1]}")
        time.sleep(1)
    with open("audio_ids.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n✅ ИТОГО: {total} треков с кодами плеера")

if __name__ == "__main__":
    main()
