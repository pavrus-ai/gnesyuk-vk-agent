#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Музыкальный агент для публикации альбомов в ВКонтакте
Версия 3.2 — для GitHub Actions:
  - без input() (режим через аргументы командной строки)
  - устойчив к "склеенному" JSON в music.json
  - безопасное чтение секретов (не падает на пустых значениях)
  - нормализация ID группы (любой формат записи -> с минусом)
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List

import requests

# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def _parse_int(raw):
    """Безопасно превращает строку из env в число. Пусто/мусор -> 0."""
    raw = (raw or "").strip()
    return int(raw) if raw.lstrip("-").isdigit() else 0


def _normalize_owner(raw_id: int) -> int:
    """Приводит ID группы к виду с минусом, убирая смещение 2000000000.
    Примеры: 1389112 -> -1389112 | -1389112 -> -1389112 | 2001389112 -> -1389112"""
    if raw_id == 0:
        return 0
    aid = abs(raw_id)
    if aid >= 2000000000:   # сохранено со смещением: 2001389112
        aid -= 2000000000   # -> 1389112
    return -aid             # публикация от имени группы = с минусом


# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================

CONFIG = {
    # Секреты из GitHub: Settings → Secrets and variables → Actions
    # (в music.yml они проброшены через env из secrets.VK_TOKEN и secrets.VK_GROUP_ID)
    "vk_access_token": (os.environ.get("VK_ACCESS_TOKEN") or "").strip(),
    "owner_id": _parse_int(os.environ.get("VK_OWNER_ID")),

    # Файлы
    "data_file": "music.json",
    "published_file": "published_albums.json",

    # Минимальный интервал между публикациями (часов). 0 = без ограничения
    "publish_interval_hours": 0,

    # Шаблон поста
    "post_template": (
        "🎵 {artist} представляет: {release_type} «{album_title}»!\n\n"
        "🎼 Жанр: {genre}\n"
        "📀 Треков: {track_count}\n\n"
        "{track_list}\n\n"
        "🎧 Слушайте прямо сейчас!\n\n"
        "#музыка #альбом #новинка #{artist_tag}"
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
    """Агент публикации музыки в ВКонтакте"""

    def __init__(self, config: Dict):
        self.config = config
        self.access_token = config["vk_access_token"]
        self.owner_id = _normalize_owner(config["owner_id"])
        self.api_version = "5.131"
        self.base_url = "https://api.vk.com/method"

        self.data = self._load_data()
        self.published = self._load_published()

        logger.info("🚀 Музыкальный агент инициализирован")
        logger.info(f"📊 Альбомов: {len(self.data.get('albums', []))}")
        logger.info(f"📊 EP: {len(self.data.get('eps', []))}")
        logger.info(f"📊 Синглов: {len(self.data.get('singles', []))}")
        logger.info(f"📌 Owner ID (стена): {self.owner_id}")

    # ========================================================
    # ЧТЕНИЕ ФАЙЛОВ (устойчивое к "склеенному" JSON)
    # ========================================================

    def _load_data(self) -> Dict:
        """Читает music.json. Если в файле несколько JSON-документов,
        выбирает самый полный (с наибольшим числом релизов)."""
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

    def _load_published(self) -> Dict:
        """Список уже опубликованных релизов"""
        try:
            if os.path.exists(self.config["published_file"]):
                with open(self.config["published_file"], "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"❌ Ошибка чтения published_albums.json: {e}")
        return {"published_albums": [], "last_publish_time": None}

    def _save_published(self):
        """Сохранение списка опубликованных релизов"""
        try:
            with open(self.config["published_file"], "w", encoding="utf-8") as f:
                json.dump(self.published, f, ensure_ascii=False, indent=2)
            logger.info("✅ published_albums.json сохранён")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения published_albums.json: {e}")

    # ========================================================
    # VK API
    # ========================================================

    def _make_request(self, method: str, params: Dict) -> Dict:
        """Запрос к VK API"""
        if not self.access_token:
            logger.error("❌ Не задан VK_ACCESS_TOKEN!")
            return {"success": False, "error": "no token"}

        params = dict(params)
        params["access_token"] = self.access_token
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

    def _post_text(self, release: Dict) -> str:
        """Текст поста для релиза"""
        artist = self.data.get("metadata", {}).get("artist", "Павел Гнесюк")
        type_names = {"album": "альбом", "ep": "EP", "single": "сингл"}
        tracks = release.get("tracks", [])
        track_list = "\n".join(f"{i}. {t['title']}" for i, t in enumerate(tracks, 1))
        return self.config["post_template"].format(
            artist=artist,
            release_type=type_names.get(release.get("type", "album"), "релиз"),
            album_title=release.get("title", ""),
            genre=release.get("genre", "разные жанры"),
            track_count=len(tracks),
            track_list=track_list,
            artist_tag=artist.replace(" ", "").lower(),
        )

    def publish_release(self, release: Dict) -> bool:
        """Публикация одного релиза на стене"""
        title = release.get("title", "")
        logger.info(f"📤 Публикую: {title}")

        tracks = release.get("tracks", [])
        attachments = ",".join(t["audio_id"] for t in tracks if t.get("audio_id"))

        result = self._make_request("wall.post", {
            "owner_id": self.owner_id,
            "message": self._post_text(release),
            "attachments": attachments,
            "from_group": 1 if self.owner_id < 0 else 0,
        })

        if result["success"]:
            post_id = result["response"].get("post_id")
            logger.info(f"✅ «{title}» опубликован! Пост: {post_id}")
            self.published["published_albums"].append({
                "title": title,
                "type": release.get("type"),
                "post_id": post_id,
                "publish_time": datetime.now().isoformat(),
            })
            self.published["last_publish_time"] = datetime.now().isoformat()
            self._save_published()
            return True

        return False

    # ========================================================
    # ЛОГИКА ПУБЛИКАЦИИ
    # ========================================================

    def get_unpublished(self) -> List[Dict]:
        """Релизы, которые ещё не публиковались"""
        done = {p["title"] for p in self.published["published_albums"]}
        out = []
        for key, rtype in (("albums", "album"), ("eps", "ep"), ("singles", "single")):
            for item in self.data.get(key, []):
                if item.get("title") not in done:
                    item = dict(item)
                    item["type"] = rtype
                    out.append(item)
        return out

    def can_publish_now(self) -> bool:
        """Проверка минимального интервала между публикациями"""
        hours = self.config["publish_interval_hours"]
        if hours <= 0 or not self.published["last_publish_time"]:
            return True
        last = datetime.fromisoformat(self.published["last_publish_time"])
        return datetime.now() - last >= timedelta(hours=hours)

    def run_once(self) -> Dict:
        """Однократный запуск: публикует один релиз"""
        logger.info("=" * 50)
        if not self.can_publish_now():
            logger.info("⏳ Интервал не выдержан — пропуск.")
            return {"success": False, "reason": "interval"}

        unpublished = self.get_unpublished()
        if not unpublished:
            logger.info("🎉 Все релизы уже опубликованы!")
            return {"success": True, "reason": "all_published"}

        release = unpublished[0]
        if self.publish_release(release):
            return {"success": True, "published": release["title"]}
        return {"success": False, "reason": "publish_failed"}

    def run_continuous(self):
        """Непрерывный режим (для локального запуска)"""
        logger.info("🔄 Непрерывный режим (Ctrl+C для остановки)")
        while True:
            try:
                self.run_once()
                time.sleep(3600)
            except KeyboardInterrupt:
                logger.info("👋 Остановлено")
                break

    def print_stats(self):
        """Статистика публикаций"""
        total = sum(len(self.data.get(k, [])) for k in ("albums", "eps", "singles"))
        done = len(self.published["published_albums"])
        pct = round(done / total * 100, 1) if total else 0
        print(f"\n📊 Всего: {total} | Опубликовано: {done} | "
              f"Осталось: {total - done} | Прогресс: {pct}%\n")


# ============================================================
# ТОЧКА ВХОДА (БЕЗ input()!)
# ============================================================

def main():
    print("\n🎵 МУЗЫКАЛЬНЫЙ АГЕНТ ВКОНТАКТЕ 🎵\n")
    agent = MusicAgent(CONFIG)

    # Проверка секретов до любой работы
    if not agent.access_token or not agent.owner_id:
        logger.error("❌ Не заданы секреты VK_ACCESS_TOKEN и/или VK_OWNER_ID! "
                     "Проверьте блок env: в music.yml: должны быть "
                     "secrets.VK_TOKEN и secrets.VK_GROUP_ID")
        sys.exit(1)

    # Режим из аргумента командной строки: publish | stats | continuous
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "publish"

    if mode == "stats":
        agent.print_stats()
    elif mode == "continuous":
        agent.run_continuous()
    else:  # по умолчанию — публикация одного релиза (для GitHub Actions)
        result = agent.run_once()
        if result.get("success"):
            print(f"\n✅ Готово: {result.get('published', 'все релизы опубликованы')}")
        else:
            print(f"\nℹ️ Пропущено: {result.get('reason')}")
            sys.exit(1)


if __name__ == "__main__":
    main()
