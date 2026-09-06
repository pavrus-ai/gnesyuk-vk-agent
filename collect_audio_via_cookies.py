# -*- coding: utf-8 -*-
import os, re, json, time, requests

COOKIES = os.getenv("VK_COOKIES", "")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Cookie": COOKIES,
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Accept": "text/html,application/xhtml+xml"
}

ALBUMS = [
    ("Оставим грусть. С Новым Годом!", "https://vk.ru/music/album/-2000882358_26882358_6ff3d07bfeac35f0ef"),
    ("Горячий песок Египта", "https://vk.ru/music/album/-2000087584_26087584_b013e84246c4dff381"),
    ("Дар богов", "https://vk.ru/music/album/-2000276266_26276266_99f1a9a82c0a73e68d"),
    ("Imperium", "https://vk.ru/music/album/-2000903105_26903105_411f47d2f816f741a4"),
    ("Энергия для души", "https://vk.ru/music/album/-2000921965_26921965_4dc493b1a5c92784be"),
    ("Бездна", "https://vk.ru/music/album/-2000905527_26905527_29a2dcbf8f8fbadea7"),
    ("Тишина вместо слов", "https://vk.ru/music/album/-2000915616_26915616_e457d43dc3ecf5ddb2"),
    ("Управление чувствами", "https://vk.ru/music/album/-2000687207_26687207_192f68240fd39f800c"),
    ("Небесный страж", "https://vk.ru/music/album/-2000688683_26688683_cb4c08dbcc33e8bd17"),
    ("Пленники Хроноса", "https://vk.ru/music/album/-2000688667_26688667_7227af46e6be2984e2"),
    ("Поколение ветра", "https://vk.ru/music/album/-2000812994_26812994_10e8e464e9f9e78603"),
    ("Туманные зеркала", "https://vk.ru/music/album/-2000822740_26822740_9fa8d6a321ee479617"),
    ("Раскаленный мир", "https://vk.ru/music/album/-2000866265_26866265_2d61f972a5b333be6d"),
    ("Обжигающий", "https://vk.ru/music/album/-2000889455_26889455_4faf6b714220265137"),
    ("Лекарство от печали", "https://vk.ru/music/album/-2000896190_26896190_b25d0459e63c8a1241"),
    ("Пока ты ждёшь", "https://vk.ru/music/album/-2000019250_27019250_a775e3121140fc05d6"),
    ("Весенние чувства", "https://vk.ru/music/album/-2000142707_27142707_c33699f31b611c1e0b"),
    ("Тени Великой Тартарии", "https://vk.ru/music/album/-2000592309_27592309_364f948d47334c622a"),
    ("Spirit", "https://vk.ru/music/album/-2000673297_27673297_1d787d08340076517b"),
    ("Enjoyments", "https://vk.ru/music/album/-2000459373_28459373_508e61520a6be43ed1"),
    ("Турецкие мотивы", "https://vk.ru/music/album/-2000457759_28457759_26697c925f76faa8b7"),
    ("Прикосновения", "https://vk.ru/music/album/-2000457449_28457449_aad8ecc96daa565f56"),
    ("Истоки славы", "https://vk.ru/music/album/-2000517591_28517591_75f40d4a60b3c70c74"),
    ("Цена тишины", "https://vk.ru/music/album/-2000694677_28694677_e8e1fd73ffb3285903"),
    ("Под одним небом", "https://vk.ru/music/album/-2000817997_28817997_4960097dc141b073c3"),
    ("Дух свободы", "https://vk.ru/music/album/-2000819321_28819321_6c669c9eb1aa645332"),
    ("Gloria Romae", "https://vk.ru/music/album/-2000908768_28908768_8e1f341f53ad31f353"),
    ("Gloria Romae II", "https://vk.ru/music/album/-2000910959_28910959_1a4eb3bd96fb0a9fe8"),
    ("Сибирский ветер", "https://vk.ru/music/album/-2000007672_29007672_e78d3545bf20d3a5db"),
    ("Чувственный горизонт", "https://vk.ru/music/album/-2000295679_27295679_c3208af894a41e2720"),
    ("Твой свет", "https://vk.ru/music/album/-2000258699_27258699_4dc606e03c0c365026"),
    ("Дух возвращается", "https://vk.ru/music/album/-2000688528_28688528_262a1fa12afef13358"),
    ("Энергия существует", "https://vk.ru/music/album/-2000690046_28690046_3826b3d599b705d96e"),
    ("Тёплый свет", "https://vk.ru/music/album/-2000021745_27021745_ea8b61798e26abbbdc"),
    ("Россия матушка зовет (folk garmonica)", "https://vk.ru/music/album/-2000267152_26267152_29098b7d7630fb679b"),
    ("Шторм и штиль", "https://vk.ru/music/album/-2000266456_26266456_3a8825f17f8307339f"),
]

def extract(html):
    res = {}
    for m in re.finditer(r'\{"id":(\d+),"owner_id":(-?\d+),"artist":"((?:[^"\\]|\\.)*)","title":"((?:[^"\\]|\\.)*)"', html):
        res[m.group(4)] = f"{m.group(2)}_{m.group(1)}"
    for m in re.finditer(r'\{"id":(\d+),"owner_id":(-?\d+),[^{}]*?"title":"((?:[^"\\]|\\.)*)","duration":\d+', html):
        res.setdefault(m.group(3), f"{m.group(2)}_{m.group(1)}")
    return res

def main():
    if not COOKIES:
        print("❌ Нет VK_COOKIES")
        return
    result = {}
    total = 0
    for title, url in ALBUMS:
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            tracks = extract(r.text)
            result[title] = tracks
            total += len(tracks)
            print(f"🎵 {title}: найдено {len(tracks)} треков")
            if tracks:
                first = list(tracks.items())[0]
                print(f"   пример: {first[0]} → {first[1]}")
        except Exception as e:
            print(f"⚠️ {title}: {e}")
            result[title] = {}
        time.sleep(1)
    with open("audio_ids.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n✅ ИТОГО: {total} треков с кодами плеера")

if __name__ == "__main__":
    main()
