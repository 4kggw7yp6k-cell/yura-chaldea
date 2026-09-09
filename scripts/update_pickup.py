#!/usr/bin/env python3
"""
YURA Chaldea - FGO JP latest pickup updater
Final safe version / Ver.0.03e

方針:
- FGO公式サイトから最新の「ピックアップ召喚」記事を自動検出
- タイトル / 開催期間 / 公式URL は自動更新
- サーヴァント一覧は誤検出防止を最優先
- 確認済みページは安全なリストを表示
- 未確認の新PUは、無理に本文解析せず空欄にしてアプリ側で「公式で確認」と表示

APIキー不要。
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
UA = "YURA-Chaldea-Pickup-Updater/2.0 (+GitHub Actions)"

ARTICLE_PATH_RE = re.compile(r"^/20\d{2}/\d{2}/[^/]+/?$")

PERIOD_RE = re.compile(
    r"(?P<sy>\d{4})年(?P<sm>\d{1,2})月(?P<sd>\d{1,2})日"
    r"(?:\([^)]+\))?\s*(?P<sh>\d{1,2}):(?P<smin>\d{2})\s*"
    r"[～〜~\-－—–]\s*"
    r"(?:(?P<ey>\d{4})年)?(?P<em>\d{1,2})月(?P<ed>\d{1,2})日"
    r"(?:\([^)]+\))?\s*(?P<eh>\d{1,2}):(?P<emin>\d{2})"
)

# 公式で確認済みの安全なPU一覧。
# URLの「path」で照合するので、末尾スラッシュやクエリ差異で壊れない。
KNOWN_SERVANT_LISTS = {
    "/2026/09/halloween2026_cp_pu/": [
        "★5 エリザベート･バートリー",
        "★5 クレオパトラ",
        "★5 呼延灼(アサシン)",
        "★5 ジャック･ド･モレー(フォーリナー)",
        "★5 シトナイ",
        "★4 ゼノビア",
        "★4 ヴラド三世〔EXTRA〕",
        "★4 エリザベート･バートリー",
        "★4 黄飛虎",
    ]
}


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
    return s.strip(" !！")


def normalize_article_url(url: str) -> str:
    p = urlparse(url)
    path = p.path
    if not path.endswith("/"):
        path += "/"
    return f"https://news.fate-go.jp{path}"


def article_path(url: str) -> str:
    p = urlparse(url)
    path = p.path
    if not path.endswith("/"):
        path += "/"
    return path


def collect_article_urls() -> list[str]:
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

            normalized = normalize_article_url(href)
            if normalized not in seen:
                seen.add(normalized)
                urls.append(normalized)

    if not urls:
        raise RuntimeError("公式お知らせ一覧から記事URLを取得できませんでした。")

    return urls


def parse_period(text: str):
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


def extract_article_title(soup: BeautifulSoup, text: str) -> str:
    candidates = []

    title_tag = soup.find("title")
    if title_tag:
        candidates.append(clean_title(" ".join(title_tag.stripped_strings)))

    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        candidates.append(clean_title(og["content"]))

    for h1 in soup.find_all("h1"):
        t = clean_title(" ".join(h1.stripped_strings))
        if t:
            candidates.append(t)

    for title in candidates:
        if "ピックアップ召喚" in title:
            return title

    if "ピックアップ召喚" in text:
        m = re.search(
            r"(?:〖期間限定〗)?[『「].{1,160}?ピックアップ召喚.{0,15}?[』」！!]",
            text
        )
        if m:
            return clean_title(m.group(0))

    return ""


def find_latest_pickup():
    now = datetime.now(JST)
    candidates = []

    # 公式一覧は新しい記事が先に出るため、上位40件だけ確認。
    for url in collect_article_urls()[:40]:
        try:
            r = get(url)
            soup = BeautifulSoup(r.text, "html.parser")
            text = " ".join(soup.stripped_strings)
            title = extract_article_title(soup, text)

            if "ピックアップ召喚" not in title:
                continue

            try:
                start, end, period_text = parse_period(text)
            except ValueError:
                continue

            candidates.append({
                "title": title,
                "url": normalize_article_url(url),
                "start": start,
                "end": end,
                "periodText": period_text,
            })

        except Exception as e:
            print(f"Skip {url}: {e}")

    if not candidates:
        raise RuntimeError(
            "公式記事を確認しましたが、ピックアップ召喚の記事を見つけられませんでした。"
        )

    active_or_upcoming = [c for c in candidates if c["end"] >= now]
    pool = active_or_upcoming or candidates
    pool.sort(key=lambda c: c["start"], reverse=True)

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


def main():
    latest = find_latest_pickup()

    previous = {}
    if OUT.exists():
        try:
            previous = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            previous = {}

    path = article_path(latest["url"])

    # 安全な既知リストがある記事だけ自動でサーヴァント一覧を表示。
    if path in KNOWN_SERVANT_LISTS:
        servants = KNOWN_SERVANT_LISTS[path]

    # 同じ記事なら、すでに保存済みの正しい一覧を維持。
    elif previous.get("officialUrl") == latest["url"]:
        servants = previous.get("servants", [])

    # 新しい未知のPUは誤情報を出さず、アプリ側の「公式で確認」に退避。
    else:
        servants = []

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
    print("Servants:", " / ".join(servants) if servants else "official page only")


if __name__ == "__main__":
    main()
