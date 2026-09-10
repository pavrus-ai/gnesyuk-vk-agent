#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Музыкальный агент для публикации музыки в ВКонтакте
Версия 3.13:
- НОВОЕ: обложка принудительно конвертируется в чистый JPEG RGB через PIL
  (ВК отклоняет WebP/PNG/альфу, переименованные в .jpg, — поле photo пустое)
- НОВОЕ: контроль минимального размера 400x400 (увеличение, если меньше)
- НОВОЕ: повторная попытка загрузки обложки
- НОВОЕ: если обложка всё же не принята — пост публикуется с треком БЕЗ обложки
- пост = ОБЛОЖКА АЛЬБОМА из папки covers/ + ОДИН случайный трек с плеером
- загрузка обложек пользовательским токеном (VK_PHOTOS_TOKEN),
  пост — групповым от имени группы
- обложка загружается один раз на альбом, ID кэшируется в covers_cache.json
- вечная случайная ротация, 1 пост в день
"""
import json
import logging
import os
import random
import sys
import time
import io
from typing import Dict, List, Optional, Tuple

import requests

try:
    from PIL import Image
    HAS_PIL = True
except Exception:
    HAS_PIL = False

# ============================================================
# ТАБЛИЦА: НАЗВАНИЕ АЛЬБОМА -> ФАЙЛ ОБЛОЖКИ В covers/
# ============================================================
COVER_MAP = {
    # Альбомы
    "Дар богов": "dar-bogov.jpg",
    "Тишина вместо слов": "tishina-vmesto-slov.jpg",
    "Imperium": "imperium.jpg",
    "Цена тишины": "tsena-tishiny.jpg",
    "Spirit": "spirit.jpg",
    "Под одним небом": "pod-odnim-nebom.jpg",
    "Дух свободы": "dukh-svobody.jpg",
    "Небесный страж": "nebesnyy-strazh.jpg",
    "Истоки славы": "istoki-slavy.jpg",
    "Весенние чувства": "vesennie-chuvstva.jpg",
    "Раскаленный мир": "raskalennyy-mir.jpg",
    "Обжигающий": "obzhigayushchiy.jpg",
    "Поколение ветра": "pokolenie-vetra.jpg",
    "Тени Великой Тартарии": "teni-velikoy-tartarii.jpg",
    "Пока ты ждёшь": "poka-ty-zhdesh.jpg",
    "Сибирский ветер": "sibirskiy-veter.jpg",
    "Бездна": "bezdna.jpg",
    "Управление чувствами": "upravlenie-chuvstvami.jpg",
    "Прикосновения": "prikosnoveniya.jpg",
    "Энергия для души": "energiya-dlya-dushi.jpg",
    "Оставим грусть. С Новым Годом!": "ostavim-grust.jpg",
    "Турецкие мотивы": "turetskie-motivy.jpg",
    "Enjoyments": "enjoyments.jpg",
    "Горячий песок Египта": "goryachiy-pesok-egipta.jpg",
    "Лекарство от печали": "lekarstvo-ot-pechali.jpg",
    "Gloria Romae II": "gloria-romae-2.jpg",
    "Gloria Romae": "gloria-romae.jpg",
    # EP
    "Твой свет": "tvoy-svet.jpg",
    # Синглы
    "Дух возвращается": "dukh-vozvrashchaetsya.jpg",
    "Энергия существует": "energiya-sushchestvuet.jpg",
    "Тёплый свет": "tyoplyy-svet.jpg",
    "Чувственный горизонт": "chuvstvennyy-gorizont.jpg",
    # Задел на будущее
    "Пленники Хроноса": "plenniki-khronosa.jpg",
    "Россия матушка зовет": "rossiya-matushka-zovet.jpg",
    "Шторм и штиль": "shtorm-i-shtil.jpg",
    "Туманные зеркала": "tumannye-zerkala.jpg",
}

# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================
def _parse_int(raw):
    raw = (raw or "").strip()
    return int(raw) if raw.lstrip("-").isdigit() else 0

def _normalize_owner(raw_id: int) -> int:
    if raw_id == 0:
        return 0
    aid = abs(raw_id)
    if aid >= 2000000000:
        aid -= 2000000000
    return -aid

# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================
CONFIG = {
    # Групповой токен — публикация постов от имени группы
    "vk_access_token": (os.environ.get("VK_ACCESS_TOKEN") or "").strip(),
    # Пользовательский токен — загрузка обложек (групповым нельзя, ошибка 27)
    "vk_photos_token": (os.environ.get("VK_PHOTOS_TOKEN") or "").strip(),
    "owner_id": _parse_int(os.environ.get("VK_OWNER_ID")),
    "data_file": "music.json",
    "covers_dir": "covers",
    "covers_cache_file": "covers_cache.json",
    # Сколько случайных треков публиковать за один запуск (1 раз в день -> 1)
    "posts_per_run": 1,
    # Пауза между постами внутри одного запуска (секунды, если posts_per_run > 1)
    "pause_between_posts": 20,
    # Шаблон поста: название альбома СВЕРХУ, трек с плеером прикрепляется
    "post_template": (
        "💿 Альбом: «{album_title}»\n"
        "🎵 {artist} — «{track_title}»\n"
        "🎼 Жанр: {genre}\n"
        "🎧 Слушайте прямо сейчас!\n\n"
        "#музыка #новинка #{artist_tag}"
    ),
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("music_agent")

# ============================================================
# КЛАСС АГЕНТА
# ============================================================
class MusicAgent:
    """Пост = обложка альбома (из covers/) + один случайный трек с плеером"""

    def __init__(self, config: Dict):
        self.config = config
        self.access_token = config["vk_access_token"]
        self.photos_token = config["vk_photos_token"] or config["vk_access_token"]
        self.owner_id = _normalize_owner(config["owner_id"])
        self.api_version = "5.131"
        self.base_url = "https://api.vk.com/method"
        self.data = self._load_data()
        self.covers_cache = self._load_covers_cache()
        logger.info("🚀 Музыкальный агент инициализирован")
        logger.info(f"📊 Альбомов: {len(self.data.get('albums', []))}")
        logger.info(f"📊 EP: {len(self.data.get('eps', []))}")
        logger.info(f"📊 Синглов: {len(self.data.get('singles', []))}")
        logger.info(f"📌 Owner ID (стена): {self.owner_id}")

    # ========================================================
    # ЧТЕНИЕ ФАЙЛОВ
    # ========================================================
    def _load_data(self) -> Dict:
        path = self.config["data_file"]
        if not os.path.exists(path):
            logger.error(f"❌ Файл {path} не найден!")
            return {"albums": [], "eps": [], "singles": []}
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        docs = []
        decoder = json.JSONDecoder()
        idx, n = 0, len(content)
        while idx < n:
            while idx < n and content[idx].isspace():
                idx += 1
            if idx >= n:
                break
            try:
                obj, end = decoder.raw_decode(content, idx)
                docs.append(obj)
                idx = end
            except json.JSONDecodeError as e:
                logger.error(f"❌ Обрыв JSON на символе {idx}: {e}")
                break
        if not docs:
            logger.error("❌ Не удалось прочитать ни одного JSON-документа!")
            return {"albums": [], "eps": [], "singles": []}
        if len(docs) > 1:
            logger.warning(f"⚠️ В файле {len(docs)} JSON-документа(ов). Выбираю самый полный.")
            def size(d):
                if not isinstance(d, dict):
                    return 0
                return sum(len(d.get(k, [])) for k in ("albums", "eps", "singles"))
            return max(docs, key=size)
        return docs[0]

    def _load_covers_cache(self) -> Dict:
        try:
            if os.path.exists(self.config["covers_cache_file"]):
                with open(self.config["covers_cache_file"], "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"❌ Ошибка чтения кэша обложек: {e}")
        return {}

    def _save_covers_cache(self):
        try:
            with open(self.config["covers_cache_file"], "w", encoding="utf-8") as f:
                json.dump(self.covers_cache, f, ensure_ascii=False, indent=2)
            logger.info("✅ covers_cache.json сохранён")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения кэша обложек: {e}")

    # ========================================================
    # VK API
    # ========================================================
    def _make_request(self, method: str, params: Dict, token: Optional[str] = None) -> Dict:
        token = token or self.access_token
        if not token:
            logger.error("❌ Не задан токен ВК!")
            return {"success": False, "error": "no token"}
        params = dict(params)
        params["access_token"] = token
        params["v"] = self.api_version
        try:
            r = requests.post(f"{self.base_url}/{method}", data=params, timeout=30)
            r.raise_for_status()
            res = r.json()
            if "error" in res:
                logger.error(f"❌ VK API: {res['error']}")
                return {"success": False, "error": res["error"]}
            return {"success": True, "response": res.get("response")}
        except requests.RequestException as e:
            logger.error(f"❌ Ошибка запроса: {e}")
            return {"success": False, "error": str(e)}

    # ========================================================
    # ОБЛОЖКИ АЛЬБОМОВ
    # ========================================================
    def _find_cover_file(self, album_title: str) -> Optional[str]:
        fname = COVER_MAP.get(album_title)
        if not fname:
            logger.error(f"❌ Для альбома «{album_title}» нет записи в COVER_MAP!")
            return None
        path = os.path.join(self.config["covers_dir"], fname)
        if not os.path.exists(path):
            logger.error(f"❌ Файл обложки не найден: {path}")
            return None
        return path

    def _prepare_jpeg(self, path: str) -> Optional[bytes]:
        """v3.13: конвертация обложки в чистый JPEG RGB.
        ВК отклоняет WebP/PNG/альфу и экзотические профили, переименованные в .jpg."""
        try:
            with open(path, "rb") as f:
                raw = f.read()
            if not HAS_PIL:
                logger.warning("⚠️ PIL недоступен — отправляю файл как есть")
                return raw
            im = Image.open(io.BytesIO(raw))
            fmt = im.format or "?"
            if im.mode != "RGB":
                im = im.convert("RGB")
            w, h = im.size
            if min(w, h) < 400:
                k = 400 / min(w, h)
                im = im.resize((int(w * k), int(h * k)), Image.LANCZOS)
                w, h = im.size
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=92)
            data = buf.getvalue()
            logger.info(f"🔧 Обложка подготовлена: {fmt} {len(raw)} байт → JPEG {w}x{h} {len(data)} байт")
            return data
        except Exception as e:
            logger.error(f"❌ Ошибка конвертации обложки: {e}")
            return None

    def _upload_cover(self, path: str) -> Optional[str]:
        """Загрузка обложки на стену группы пользовательским токеном.
        v3.13: сначала конвертация в JPEG, затем до 2 попыток загрузки."""
        img = self._prepare_jpeg(path)
        if not img:
            return None
        data = None
        for attempt in (1, 2):
            srv = self._make_request(
                "photos.getWallUploadServer",
                {"owner_id": self.owner_id},
                token=self.photos_token,
            )
            if not srv["success"]:
                return None
            try:
                resp = requests.post(
                    srv["response"]["upload_url"],
                    files={"photo": ("cover.jpg", img, "image/jpeg")},
                    timeout=60,
                )
                data = resp.json()
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки файла обложки: {e}")
                return None
            if data.get("photo"):
                break
            logger.error(f"❌ ВК не принял файл обложки (поле photo пустое), попытка {attempt}: {data}")
            time.sleep(2)
        else:
            return None
        save = self._make_request(
            "photos.saveWallPhoto",
            {
                "owner_id": self.owner_id,
                "photo": data["photo"],
                "hash": data.get("hash", ""),
                "server": data.get("server", ""),
            },
            token=self.photos_token,
        )
        if not save["success"]:
            return None
        item = save["response"][0]
        att = f"photo{item['owner_id']}_{item['id']}"
        if item.get("access_key"):
            att += f"_{item['access_key']}"
        return att

    def _get_album_photo(self, album_title: str) -> Optional[str]:
        """Вложение photo... для альбома: из кэша или загрузка из covers/."""
        if album_title in self.covers_cache:
            return self.covers_cache[album_title]
        path = self._find_cover_file(album_title)
        if not path:
            return None
        logger.info(f"🖼 Загружаю обложку альбома «{album_title}» в ВК...")
        att = self._upload_cover(path)
        if att:
            self.covers_cache[album_title] = att
            self._save_covers_cache()
            logger.info(f"✅ Обложка загружена: {att}")
        return att

    # ========================================================
    # СЛУЧАЙНЫЙ ВЫБОР ТРЕКА
    # ========================================================
    def _all_playable_tracks(self) -> List[Tuple[Dict, Dict]]:
        out = []
        for key, rtype in (("albums", "album"), ("eps", "ep"), ("singles", "single")):
            for item in self.data.get(key, []):
                release = dict(item)
                release["type"] = rtype
                for track in release.get("tracks", []):
                    if track.get("audio_id"):
                        out.append((release, track))
        return out

    def pick_random_tracks(self, limit: int) -> List[Tuple[Dict, Dict]]:
        pool = self._all_playable_tracks()
        if not pool:
            return []
        return random.choices(pool, k=min(limit, len(pool)))

    # ========================================================
    # ПУБЛИКАЦИЯ
    # ========================================================
    def _post_text(self, release: Dict, track: Dict) -> str:
        artist = self.data.get("metadata", {}).get("artist", "Павел Гнесюк")
        return self.config["post_template"].format(
            album_title=release.get("title", ""),
            artist=artist,
            track_title=track.get("title", ""),
            genre=release.get("genre", "разные жанры"),
            artist_tag=artist.replace(" ", "").lower(),
        )

    def publish_track(self, release: Dict, track: Dict) -> bool:
        album_title = release.get("title", "")
        track_title = track.get("title", "")
        logger.info(f"🎲 Выбран случайный трек: {album_title} → {track_title}")
        photo = self._get_album_photo(album_title)
        attachments = track["audio_id"]
        if photo:
            attachments = f"{track['audio_id']},{photo}"
            logger.info("📎 Вложения: обложка альбома + трек с плеером")
        else:
            logger.warning("⚠️ Обложки нет — публикую трек БЕЗ обложки (v3.13 страховка)")
        result = self._make_request("wall.post", {
            "owner_id": self.owner_id,
            "message": self._post_text(release, track),
            "attachments": attachments,
            "from_group": 1 if self.owner_id < 0 else 0,
        })
        if result["success"]:
            post_id = result["response"].get("post_id")
            logger.info(f"✅ Пост опубликован: {post_id}")
            return True
        return False

    # ========================================================
    # ЗАПУСК
    # ========================================================
    def run_once(self) -> Dict:
        logger.info("=" * 50)
        picks = self.pick_random_tracks(self.config["posts_per_run"])
        if not picks:
            logger.error("❌ Нет ни одного трека с плеером в music.json!")
            return {"success": False, "reason": "no_tracks"}
        published_now = []
        for i, (release, track) in enumerate(picks):
            if i > 0:
                pause = self.config["pause_between_posts"]
                logger.info(f"⏳ Пауза {pause} сек...")
                time.sleep(pause)
            if self.publish_track(release, track):
                published_now.append(track["title"])
        if published_now:
            return {"success": True, "published": ", ".join(published_now)}
        return {"success": False, "reason": "publish_failed"}

    def print_stats(self):
        total = len(self._all_playable_tracks())
        print(f"\n📊 Треков с плеером в каталоге: {total} "
              f"(публикуется случайно, по 1 в день)\n")

# ============================================================
# ТОЧКА ВХОДА (БЕЗ input()!)
# ============================================================
def main():
    print("\n🎵 МУЗЫКАЛЬНЫЙ АГЕНТ ВКОНТАКТЕ 🎵\n")
    agent = MusicAgent(CONFIG)
    if not agent.access_token or not agent.owner_id:
        logger.error("❌ Не заданы секреты VK_ACCESS_TOKEN и/или VK_OWNER_ID! "
                     "Проверьте блок env: в music.yml")
        sys.exit(1)
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "publish"
    if mode == "stats":
        agent.print_stats()
    else:
        result = agent.run_once()
        if result.get("success"):
            print(f"\n✅ Готово: {result.get('published')}")
        else:
            print(f"\nℹ️ Не опубликовано: {result.get('reason')}")
            sys.exit(1)

if __name__ == "__main__":
    main()
