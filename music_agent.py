#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Музыкальный агент для публикации музыки в ВКонтакте
Версия 3.8:
  - пост = ФОТО + ОДИН случайный трек с плеером (требование ВК)
  - НОВОЕ: photos.get вызывается ПОЛЬЗОВАТЕЛЬСКИМ токеном (VK_PHOTOS_TOKEN),
    т.к. групповым токеном метод недоступен (ошибка 27);
    пост при этом публикуется групповым токеном от имени группы
  - если фото достать не удалось — можно задать фиксированную обложку cover_photo
  - без учёта прогресса: вечная случайная ротация, 1 пост в день
"""

import json
import logging
import os
import random
import sys
import time
from typing import Dict, List, Optional, Tuple

import requests

# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def _parse_int(raw):
    """Безопасно превращает строку из env в число. Пусто/мусор -> 0."""
    raw = (raw or "").strip()
    return int(raw) if raw.lstrip("-").isdigit() else 0


def _normalize_owner(raw_id: int) -> int:
    """Приводит ID группы к виду с минусом, убирая смещение 2000000000."""
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
    # Групповой токен — для публикации постов от имени группы
    "vk_access_token": (os.environ.get("VK_ACCESS_TOKEN") or "").strip(),
    # Пользовательский токен — для чтения фото (photos.get групповым недоступен)
    "vk_photos_token": (os.environ.get("VK_PHOTOS_TOKEN") or "").strip(),
    "owner_id": _parse_int(os.environ.get("VK_OWNER_ID")),

    "data_file": "music.json",

    # Фиксированная обложка (необязательно). Формат: photo-1389112_457234567
    # Если пусто — агент возьмёт случайное фото из группы через photos.get
    "cover_photo": "",

    # Сколько случайных треков публиковать за один запуск (1 раз в день -> 1)
    "posts_per_run": 1,

    # Пауза между постами внутри одного запуска (секунды, если posts_per_run > 1)
    "pause_between_posts": 20,

    # Шаблон поста: название альбома СВЕРХУ, трек с плеером прикрепляется
    "post_template": (
        "💿 Альбом: «{album_title}»\n\n"
        "🎵 {artist} — «{track_title}»\n"
        "🎼 Жанр: {genre}\n\n"
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
    """Агент публикации: пост = фото + один случайный трек с плеером"""

    def __init__(self, config: Dict):
        self.config = config
        self.access_token = config["vk_access_token"]
        self.photos_token = config["vk_photos_token"] or config["vk_access_token"]
        self.owner_id = _normalize_owner(config["owner_id"])
        self.api_version = "5.131"
        self.base_url = "https://api.vk.com/method"
        self._photo_cache: Optional[List[str]] = None

        self.data = self._load_data()

        logger.info("🚀 Музыкальный агент инициализирован")
        logger.info(f"📊 Альбомов: {len(self.data.get('albums', []))}")
        logger.info(f"📊 EP: {len(self.data.get('eps', []))}")
        logger.info(f"📊 Синглов: {len(self.data.get('singles', []))}")
        logger.info(f"📌 Owner ID (стена): {self.owner_id}")

    # ========================================================
    # ЧТЕНИЕ ФАЙЛА music.json
    # ========================================================

    def _load_data(self) -> Dict:
        """Читает music.json, устойчив к нескольким JSON-документам в файле."""
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
    # ФОТО ДЛЯ ПОСТА (требование ВК: музыка только вместе с фото)
    # ========================================================

    def _get_photo_attachment(self) -> Optional[str]:
        """Фиксированная обложка из конфига или случайное фото группы
        (читается ПОЛЬЗОВАТЕЛЬСКИМ токеном — групповым photos.get недоступен)."""
        fixed = (self.config.get("cover_photo") or "").strip()
        if fixed:
            return fixed

        if self._photo_cache is None:
            self._photo_cache = []
            for album in ("", "wall", "profile", "saved"):
                params = {"owner_id": self.owner_id, "count": 100}
                if album:
                    params["album_id"] = album
                result = self._make_request("photos.get", params, token=self.photos_token)
                if result["success"]:
                    items = result["response"].get("items", [])
                    if items:
                        for it in items:
                            att = f"photo{it['owner_id']}_{it['id']}"
                            if it.get("access_key"):
                                att += f"_{it['access_key']}"
                            self._photo_cache.append(att)
                        break
            logger.info(f"🖼 Фото группы доступно: {len(self._photo_cache)}")

        if not self._photo_cache:
            return None
        return random.choice(self._photo_cache)

    # ========================================================
    # СЛУЧАЙНЫЙ ВЫБОР ТРЕКА
    # ========================================================

    def _all_playable_tracks(self) -> List[Tuple[Dict, Dict]]:
        """Все треки с плеером из всех альбомов, EP и синглов."""
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
        """Случайный выбор N треков из всего каталога."""
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
        """Пост: ФОТО + ОДИН трек (плеер) + название альбома в тексте."""
        album_title = release.get("title", "")
        track_title = track.get("title", "")
        logger.info(f"🎲 Выбран случайный трек: {album_title} → {track_title}")

        photo = self._get_photo_attachment()
        if not photo:
            logger.error("❌ Не удалось достать фото группы. Загрузите фото в группу "
                         "или задайте CONFIG['cover_photo'] (формат photo-XXXX_YYYY)")
            return False

        attachments = f"{photo},{track['audio_id']}"
        logger.info(f"📎 Вложения: {attachments}")

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
