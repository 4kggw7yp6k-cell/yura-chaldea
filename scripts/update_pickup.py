#!/usr/bin/env python3
"""
YURA Chaldea - Fate/Grand Order JP latest pickup updater

Official source:
  https://news.fate-go.jp/nasu_gacha/

The script:
1. Reads the official FGO news index.
2. Finds the newest article whose title includes "ピックアップ召喚".
3. Reads its official period.
4. Extracts pickup servants only when official page text gives enough evidence.
5. Rewrites pickup.json only when the actual pickup changed.

No API key is required.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "pickup.json"
INDEX_URL = "https://news.fate-go.jp/nasu_gacha/"
BASE_URL = "https://news.fate-go.jp/"
JST = timezone(timedelta(hours=9))
UA = "YURA-Chaldea-Pickup-Updater/1.0 (+GitHub Actions; official FGO news checker)"

PERIOD_RE = re.compile(
    r"(?P<sy>\d{4})年(?P<sm>\d{1,2})月(?P<sd>\d{1,2})日"
    r"(?:\([^)]+\))?\s*(?P<sh>\d{1,2}):(?P<smin>\d{2})\s*[～〜~\-]\s*"
    r"(?:(?P<ey>\d{4})年)?(?P<em>\d{1,2})月(?P<ed>\d{1,2})日"
    r"(?:\([^)]+\))?\s*(?P<eh>\d{1,2}):(?P<emin>\d{2})"
)

RARITY_RE = re.compile(r"★(?P<rarity>[345])\((?:SSR|SR|R)\)(?P<name>[^「」\n]{1,60})")


def get(url: str) -> requests.Response:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r


def clean_title(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*\|\s*Fate/Grand Order.*$", "", text)
    text = text.replace("【期間限定】", "").replace("〖期間限定〗", "")
    return text.strip(" !！")


def find_latest_pickup() -> tuple[str, str]:
    soup = BeautifulSoup(get(INDEX_URL).text, "html.parser")

    candidates: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        title = " ".join(a.stripped_strings)
        if "ピックアップ召喚" not in title:
            continue
        href = urljoin(BASE_URL, a["href"])
        if "news.fate-go.jp" not in href:
            continue
        candidates.append((clean_title(title), href))

    # De-duplicate while preserving official news order (newest first).
    seen = set()
    unique = []
    for title, href in candidates:
        if href in seen:
            continue
        seen.add(href)
        unique.append((title, href))

    if not unique:
        raise RuntimeError("公式お知らせ一覧からピックアップ召喚を見つけられませんでした。")

    return unique[0]


def parse_period(text: str) -> tuple[datetime, datetime, str]:
    m = PERIOD_RE.search(text)
    if not m:
        raise RuntimeError("公式ページから開催期間を読み取れませんでした。")

    sy = int(m["sy"])
    sm, sd, sh, smin = map(int, (m["sm"], m["sd"], m["sh"], m["smin"]))
    ey = int(m["ey"]) if m["ey"] else sy
    em, ed, eh, emin = map(int, (m["em"], m["ed"], m["eh"], m["emin"]))

    # Handles a Dec -> Jan notice where the end year is omitted.
    if not m["ey"] and em < sm:
        ey += 1

    start = datetime(sy, sm, sd, sh, smin, tzinfo=JST)
    end = datetime(ey, em, ed, eh, emin, tzinfo=JST)
    period = f"{sy}/{sm}/{sd} {sh:02d}:{smin:02d} ～ {em}/{ed} {eh:02d}:{emin:02d}"
    return start, end, period


def normalize_servant_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip()
    # Stop at phrases that commonly follow a servant name in prose.
    name = re.split(
        r"(?:を含む|をピックアップ|がピックアップ|のセイントグラフ|の霊基|について|は、|は |が |を )",
        name,
        maxsplit=1
    )[0].strip("。、！!※ ")
    return name


def extract_servants(soup: BeautifulSoup, text: str) -> list[str]:
    """
    Conservative extraction:
    Keep ★5/★4/★3 names when the nearby official wording indicates
    a servant/saint graph/servant lineup. This intentionally prefers
    an incomplete list over incorrectly labeling Craft Essences.
    """
    found: list[tuple[int, str]] = []

    for m in RARITY_RE.finditer(text):
        rarity = int(m["rarity"])
        name = normalize_servant_name(m["name"])
        if not name or len(name) > 45:
            continue

        lo = max(0, m.start() - 150)
        hi = min(len(text), m.end() + 150)
        context = text[lo:hi]

        servant_signal = any(word in context for word in (
            "サーヴァント", "セイントグラフ", "霊基再臨", "9騎", "騎をピックアップ", "騎と"
        ))
        ce_signal = "概念礼装" in context and not servant_signal

        if ce_signal or not servant_signal:
            continue

        found.append((rarity, name))

    # Pickup headings are strong evidence for featured ★5s. If a heading name
    # can be matched to a rarity occurrence elsewhere, include it.
    heading_texts = []
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "strong"]):
        t = " ".join(tag.stripped_strings)
        if "ピックアップ召喚" in t:
            heading_texts.append(t)

    rarity_occurrences = []
    for m in RARITY_RE.finditer(text):
        rarity_occurrences.append((int(m["rarity"]), normalize_servant_name(m["name"])))

    for heading in heading_texts:
        before = heading.split("ピックアップ召喚", 1)[0]
        # Remove campaign/common prefixes and retain the most likely target label.
        pieces = re.split(r"[』」\n]", before)
        target = pieces[-1].strip(" 『「")
        target = re.sub(r"^.*開幕直前\s*", "", target)
        if len(target) < 2:
            continue
        for rarity, name in rarity_occurrences:
            if target in name or name in target:
                found.append((rarity, name))
                break

    # Stable rarity-first output and de-dupe exact names.
    result = []
    seen = set()
    for rarity, name in sorted(found, key=lambda x: (-x[0], x[1])):
        key = (rarity, name)
        if key in seen:
            continue
        seen.add(key)
        result.append(f"★{rarity} {name}")

    return result


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
    list_title, url = find_latest_pickup()
    response = get(url)
    soup = BeautifulSoup(response.text, "html.parser")
    page_text = " ".join(soup.stripped_strings)

    h1 = soup.find("h1")
    page_title = clean_title(" ".join(h1.stripped_strings)) if h1 else list_title
    title = page_title if "ピックアップ召喚" in page_title else list_title

    start, end, period_text = parse_period(page_text)
    servants = extract_servants(soup, page_text)

    previous = {}
    if OUT.exists():
        try:
            previous = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            previous = {}

    # If conservative extraction finds nothing, preserve no guessed names.
    # If it is the same official article, preserve the already-confirmed list.
    if not servants and previous.get("officialUrl") == url:
        servants = previous.get("servants", [])

    candidate = {
        "schemaVersion": 1,
        "updatedAt": datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
        "title": title,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "periodText": period_text,
        "servants": servants,
        "officialUrl": url,
        "source": "Fate/Grand Order 公式サイト",
        "autoUpdated": True,
    }

    if previous and semantic_payload(previous) == semantic_payload(candidate):
        print("No new pickup information. pickup.json unchanged.")
        return

    OUT.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Updated pickup.json: {title}")
    print(url)
    if servants:
        print("Servants:", " / ".join(servants))
    else:
        print("Servant list could not be extracted conservatively; official link remains available.")


if __name__ == "__main__":
    main()
