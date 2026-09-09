#!/usr/bin/env python3
"""
YURA Chaldea - FGO JP latest pickup updater (Ver.0.03c)

Fix:
FGO公式のお知らせ一覧は、リンク文字列だけでは
「ピックアップ召喚」を判定できないことがあります。
そこで一覧から公式記事URLを集め、各記事そのものを開いて
タイトルと開催期間を確認します。

APIキー不要 / 情報源はFate/Grand Order日本版公式サイト。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "pickup.json"

INDEX_URLS = [
    "https://news.fate-go.jp/",
    "https://news.fate-go.jp/nasu_gacha/",
]
BASE = "https://news.fate-go.jp/"
JST = timezone(timedelta(hours=9))
UA = "YURA-Chaldea-Pickup-Updater/1.3 (+GitHub Actions)"

ARTICLE_PATH_RE = re.compile(r"^/20\d{2}/\d{2}/[^/]+/?$")
DATE_IN_PATH_RE = re.compile(r"/(?P<y>20\d{2})/(?P<m>\d{2})/")

PERIOD_RE = re.compile(
    r"(?P<sy>\d{4})年(?P<sm>\d{1,2})月(?P<sd>\d{1,2})日"
    r"(?:\([^)]+\))?\s*(?P<sh>\d{1,2}):(?P<smin>\d{2})\s*"
    r"[～〜~\-－—–]\s*"
    r"(?:(?P<ey>\d{4})年)?(?P<em>\d{1,2})月(?P<ed>\d{1,2})日"
    r"(?:\([^)]+\))?\s*(?P<eh>\d{1,2}):(?P<emin>\d{2})"
)

PUBLISHED_RE = re.compile(
    r"(?P<y>20\d{2})[./年](?P<m>\d{1,2})[./月](?P<d>\d{1,2})日?"
)

PICKUP_TARGET_RE = re.compile(
    r"〖ピックアップ対象〗(?P<body>.*?)(?:サーヴァントの詳細はこちら|概念礼装の詳細はこちら|期間限定イベント|ピックアップ期間中)",
    re.S
)
SERVANT_LINE_RE = re.compile(
    r"★(?P<rarity>[345])\((?:SSR|SR|R)\)(?P<name>[^★\n]{1,80})"
)


def get(url: str) -> requests.Response:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
    r.raise_for_status()
    if not r.encoding or r.encoding.lower() == "iso-8859-1":
        r.encoding = r.apparent_encoding or "utf-8"
    return r


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def clean_title(s: str) -> str:
    s = clean_text(s)
    s = re.sub(r"\s*\|\s*Fate/Grand Order.*$", "", s)
    s = s.replace("〖期間限定〗", "").replace("【期間限定】", "")
    return s.strip()


def collect_article_urls() -> list[str]:
    """
    Collect article URLs from both the general news index and gacha index.
    We do NOT depend on anchor text because FGO's markup can separate the
    visible title from the clickable element.
    """
    urls = []
    seen = set()

    for index_url in INDEX_URLS:
        soup = BeautifulSoup(get(index_url).text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = urljoin(BASE, a["href"])
            p = urlparse(href)

            if p.netloc != "news.fate-go.jp":
                continue
            if not ARTICLE_PATH_RE.match(p.path):
                continue

            normalized = f"https://news.fate-go.jp{p.path}"
            if not normalized.endswith("/"):
                normalized += "/"

            if normalized not in seen:
                seen.add(normalized)
                urls.append(normalized)

    if not urls:
        raise RuntimeError("公式お知らせ一覧から記事URLを取得できませんでした。")

    return urls


def parse_published_date(soup: BeautifulSoup, url: str) -> datetime:
    # First, try text shown on the article.
    text = " ".join(soup.stripped_strings)
    m = PUBLISHED_RE.search(text[:1200])
    if m:
        return datetime(int(m["y"]), int(m["m"]), int(m["d"]), tzinfo=JST)

    # Fallback to year/month in URL, day 1. This is only for sorting.
    m = DATE_IN_PATH_RE.search(urlparse(url).path)
    if m:
        return datetime(int(m["y"]), int(m["m"]), 1, tzinfo=JST)

    return datetime(1970, 1, 1, tzinfo=JST)


def parse_period(text: str) -> tuple[datetime, datetime, str]:
    m = PERIOD_RE.search(text)
    if not m:
        raise ValueError("開催期間を読み取れませんでした")

    sy = int(m["sy"])
    sm, sd, sh, smin = map(int, (m["sm"], m["sd"], m["sh"], m["smin"]))
    ey = int(m["ey"]) if m["ey"] else sy
    em, ed, eh, emin = map(int, (m["em"], m["ed"], m["eh"], m["emin"]))

    if not m["ey"] and em < sm:
        ey += 1

    start = datetime(sy, sm, sd, sh, smin, tzinfo=JST)
    end = datetime(ey, em, ed, eh, emin, tzinfo=JST)
    period = f"{sy}/{sm}/{sd} {sh:02d}:{smin:02d} ～ {em}/{ed} {eh:02d}:{emin:02d}"
    return start, end, period


def normalize_servant_name(name: str) -> str:
    name = clean_text(name)

    # Remove category labels or prose that can follow a name.
    stops = [
        "▼", "期間限定サーヴァント", "ストーリー召喚サーヴァント",
        "恒常サーヴァント", "期間限定概念礼装", "概念礼装",
        "サーヴァントの詳細はこちら", "概念礼装の詳細はこちら"
    ]
    for stop in stops:
        if stop in name:
            name = name.split(stop, 1)[0]

    name = re.split(r"(?:を含む|をピックアップ|がピックアップ|について|※)", name, maxsplit=1)[0]
    return name.strip(" ・。、！! ")


def extract_servants(text: str) -> list[str]:
    """
    Ver.0.03c:
    FGO公式本文には「★4以上確定」「聖晶石1個」などの召喚説明が大量に含まれるため、
    広い正規表現では誤検出しやすい。

    そこで、概念礼装セクションより前にある
      「★5(SSR)サーヴァント名」
      「★4(SR)サーヴァント名」
      「★3(R)サーヴァント名」
    のような、公式がカギ括弧付きで明示した表記だけを採用する。

    取りこぼしは許容し、誤情報を出さないことを優先する。
    """
    area = text

    # CE欄以降は絶対に見ない。
    if "期間限定概念礼装" in area:
        area = area.split("期間限定概念礼装", 1)[0]

    quoted = re.compile(
        r"「★(?P<rarity>[345])\((?P<label>SSR|SR|R)\)(?P<name>[^」]{1,60})」"
    )

    banned = (
        "以上", "確定", "召喚", "概念礼装", "サーヴァント",
        "聖晶石", "呼符", "回目", "枚", "個", "コイン",
        "霊基再臨", "イラスト", "セイントグラフ", "宝具"
    )

    result = []
    seen = set()

    for m in quoted.finditer(area):
        rarity = m["rarity"]
        name = clean_text(m["name"]).strip(" ・。、！! ")

        if not name or len(name) > 50:
            continue
        if any(word in name for word in banned):
            continue
        if re.match(r"^\d", name):
            continue

        key = (rarity, name)
        if key in seen:
            continue
        seen.add(key)
        result.append(f"★{rarity} {name}")

    return result


def find_latest_pickup():
    now = datetime.now(JST)
    article_urls = collect_article_urls()

    candidates = []

    # Limit network load. Official indexes are newest-first, so recent URLs
    # normally appear near the top.
    for url in article_urls[:40]:
        try:
            r = get(url)
            soup = BeautifulSoup(r.text, "html.parser")
            text = " ".join(soup.stripped_strings)

            # FGO公式では最初のh1が記事タイトルとは限らないため、
            # <title> → og:title → h1 → 本文の順で判定する。
            title_candidates = []

            title_tag = soup.find("title")
            if title_tag:
                title_candidates.append(clean_title(" ".join(title_tag.stripped_strings)))

            og = soup.find("meta", attrs={"property": "og:title"})
            if og and og.get("content"):
                title_candidates.append(clean_title(og["content"]))

            for h1 in soup.find_all("h1"):
                t = clean_title(" ".join(h1.stripped_strings))
                if t:
                    title_candidates.append(t)

            title = next(
                (t for t in title_candidates if "ピックアップ召喚" in t),
                ""
            )

            # 最終フォールバック：本文中にPU召喚表記がある記事も拾う。
            if not title and "ピックアップ召喚" in text:
                m_title = re.search(
                    r"(?:〖期間限定〗)?[『「].{1,140}?ピックアップ召喚.{0,10}?[』」！!]",
                    text
                )
                if m_title:
                    title = clean_title(m_title.group(0))

            if "ピックアップ召喚" not in title:
                continue

            try:
                start, end, period_text = parse_period(text)
            except ValueError:
                continue

            published = parse_published_date(soup, url)
            servants = extract_servants(text)

            candidates.append({
                "title": title,
                "url": url,
                "start": start,
                "end": end,
                "periodText": period_text,
                "published": published,
                "servants": servants,
            })
        except Exception as e:
            print(f"Skip {url}: {e}")

    if not candidates:
        raise RuntimeError("公式記事を確認しましたが、ピックアップ召喚の記事を見つけられませんでした。")

    # Prefer currently running/upcoming pickup with the newest start time.
    active_or_upcoming = [c for c in candidates if c["end"] >= now]
    pool = active_or_upcoming or candidates
    pool.sort(key=lambda c: (c["start"], c["published"]), reverse=True)
    return pool[0]


def semantic_payload(d: dict) -> dict:
    return {
        "title": d.get("title"),
        "start": d.get("start"),
        "end": d.get("end"),
        "periodText": d.get("periodText"),
        "servants": d.get("servants", []),
        "officialUrl": d.get("officialUrl"),
    }


def main() -> None:
    latest = find_latest_pickup()

    previous = {}
    if OUT.exists():
        try:
            previous = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            previous = {}

    servants = latest["servants"]

    # If extraction is conservative and gets nothing for the same article,
    # preserve the previously confirmed list instead of erasing it.
    if not servants and previous.get("officialUrl") == latest["url"]:
        servants = previous.get("servants", [])

    candidate = {
        "schemaVersion": 1,
        "updatedAt": datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
        "title": latest["title"],
        "start": latest["start"].isoformat(),
        "end": latest["end"].isoformat(),
        "periodText": latest["periodText"],
        "servants": servants,
        "officialUrl": latest["url"],
        "source": "Fate/Grand Order 公式サイト",
        "autoUpdated": True,
    }

    if previous and semantic_payload(previous) == semantic_payload(candidate):
        print("No new pickup information. pickup.json unchanged.")
        print(candidate["title"])
        print(candidate["officialUrl"])
        return

    OUT.write_text(
        json.dumps(candidate, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )

    print("Updated pickup.json")
    print(candidate["title"])
    print(candidate["officialUrl"])
    if servants:
        print("Servants:", " / ".join(servants))
    else:
        print("Servant list was not extracted; official link is still available.")


if __name__ == "__main__":
    main()
