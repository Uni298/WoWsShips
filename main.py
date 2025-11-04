#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_ships.py
- Wargaming WoWS encyclopedia/ships API を使い、
  * 全艦艇一覧をキャッシュ (ships_cache.json)
  * tier1..tier10 ごとに「購入可能/研究可能」な艦艇を抽出して JSON 化 -> tiers/tier_{n}.json
  * 画像は images/ フォルダへダウンロード。既存ファイルは再取得しない。
- 環境: Python 3.8+
- 使い方:
    1) API_KEY を設定
    2) python fetch_ships.py
"""

import requests, json, os, time, pathlib, sys
from typing import Dict, Any, Optional

# ====== 設定 ======
API_KEY = "352f3820d1e216d1896d0e3d430b829c"  # ← ここに Wargaming API key を入れてください
API_BASE = "https://api.worldofwarships.asia"
ENCYCLOPEDIA_SHIPS = API_BASE + "/wows/encyclopedia/ships/"
CACHE_FILE = "ships_cache.json"
IMAGES_DIR = "images"
TIERS_DIR = "tiers"
LANG = "ja"   # "en" 等に変更可能
REQUEST_DELAY = 0.2  # API の連続呼び出しでスロットリングを避けるための待ち時間

# ====== ユーティリティ ======
def ensure_dirs():
    os.makedirs(IMAGES_DIR, exist_ok=True)
    os.makedirs(TIERS_DIR, exist_ok=True)

def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(path: str):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# ====== API 呼び出し ======
def get_ships_page(page_no=1, fields=None):
    params = {
        "application_id": API_KEY,
        "language": LANG,
        "page_no": page_no,
    }
    if fields:
        params["fields"] = ",".join(fields)
    r = requests.get(ENCYCLOPEDIA_SHIPS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def update_cache_full():
    """
    全艦艇をページングで取得してキャッシュを生成。
    キャッシュは dict: { ship_id: ship_data }
    返り値: cache dict
    """
    print("全艦艇情報をAPIから取得しています...（ページング）")
    page = 1
    cache: Dict[str, Any] = {}
    while True:
        data = get_ships_page(page_no=page)  # fields を絞らずに全部取る
        if data.get("status") != "ok":
            raise RuntimeError("API error when fetching ships list: " + str(data))
        ships = data.get("data", {})
        for sid, sdata in ships.items():
            cache[sid] = sdata
        meta = data.get("meta", {})
        page_total = meta.get("page_total", 1)
        print(f"  fetched page {page}/{page_total}  (collected {len(cache)} ships so far)")
        if page >= page_total:
            break
        page += 1
        time.sleep(REQUEST_DELAY)
    save_json(CACHE_FILE, cache)
    print(f"キャッシュ保存: {CACHE_FILE} （{len(cache)} 隻）")
    return cache

def load_or_update_cache(force_update=False):
    if force_update or not os.path.exists(CACHE_FILE):
        return update_cache_full()
    cache = load_json(CACHE_FILE)
    if cache is None:
        return update_cache_full()
    return cache

# ====== 画像ダウンロード ======
def guess_image_url_from_shipdata(sdata: Dict[str, Any]) -> Optional[str]:
    """
    艦艇データから画像URLを推測する。API の返すフィールド名は場合により異なるため
    複数候補を試す。
    """
    # possible keys commonly seen in encyclopedia responses:
    # 'images': {'small': url, 'large': url, ...}
    # 'image': url
    # 'images': {'preview': url}
    # 'pictures' etc.
    if not sdata:
        return None
    # 1) images.small or images.large
    images = sdata.get("images")
    if isinstance(images, dict):
        for key in ("large", "big", "small", "preview", "contour_icon"):
            url = images.get(key)
            if url:
                return url
        # sometimes nested inside images -> small_icon etc
        for v in images.values():
            if isinstance(v, str) and v.startswith("http"):
                return v
    # 2) direct 'image' field
    image = sdata.get("image") or sdata.get("picture") or sdata.get("preview")
    if isinstance(image, str) and image.startswith("http"):
        return image
    # 3) try 'image/icon' style nested keys
    for candidate in ("image_small", "image_large", "icon", "contour_image"):
        url = sdata.get(candidate)
        if isinstance(url, str) and url.startswith("http"):
            return url
    return None

def download_image(url: str, out_path: str):
    if not url:
        return False
    if os.path.exists(out_path):
        return True
    try:
        r = requests.get(url, stream=True, timeout=30)
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(1024*8):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"画像取得失敗: {url} -> {e}")
        return False

# ====== 「購入可能 / 研究可能」判定ロジック ======
def is_buyable_or_researchable(sdata: Dict[str, Any]) -> bool:
    """
    API のフィールド差異を吸収するために複数条件で判定:
    - is_premium が True なら premium（通常研究ツリーで買えない） → 含めない
    - is_collectible / is_special など特殊なやつは除外
    - is_researchable が True なら研究可能（ツリー上で取得できる）
    - また price.credit や price_xxx のような購入情報があれば「購入可能」と判断
    - 最終的に tier が 1..10 の範囲にあり上記いずれかを満たすなら True
    """
    if not sdata:
        return False
    if sdata.get("is_premium") is True:
        return False
    if sdata.get("is_collectible") or sdata.get("is_special"):
        return False
    # researchable field common
    if sdata.get("is_researchable") is True:
        return True
    # price fields
    price = sdata.get("price") or sdata.get("prices")
    if isinstance(price, dict) and price:
        # price might be like {'credit': 150000, 'gold': 0} or nested
        for v in price.values():
            if isinstance(v, (int, float)) and v > 0:
                return True
    # some APIs include price_credit directly
    for k in ("price_credit", "price_gold"):
        if isinstance(sdata.get(k), (int, float)) and sdata.get(k) > 0:
            return True
    return False

# ====== メイン処理: tiers 作成 & 画像取得 ======
def build_tiers_and_images(cache: Dict[str, Any], download_images: bool = True):
    """
    cache: dict of ship_id -> ship_data
    出力:
      - tiers/tier_{n}.json : list of ship_data (簡易情報)
      - images/ : 画像ファイル（ファイル名 ship_{ship_id}.ext）
    """
    tiers = {i: [] for i in range(1, 11)}
    print("艦艇の分類を開始します...")
    for sid, s in cache.items():
        tier = s.get("tier")
        # some entries use 'level' or 'tier'
        if tier is None:
            tier = s.get("level")
        try:
            tier = int(tier) if tier is not None else None
        except:
            tier = None
        if not tier or not (1 <= tier <= 10):
            continue
        if not is_buyable_or_researchable(s):
            continue
        # collect minimal useful info per ship
        ship_entry = {
            "ship_id": s.get("ship_id") or sid,
            "name": s.get("name") or s.get("localized_name") or s.get("ship_name"),
            "tier": tier,
            "type": s.get("type") or s.get("ship_type"),
        }
        # try to find image URL
        img_url = guess_image_url_from_shipdata(s)
        if img_url:
            ship_entry["image_url"] = img_url
            # pick file extension
            ext = os.path.splitext(img_url.split("?")[0])[1] or ".jpg"
            fname = f"ship_{ship_entry['ship_id']}{ext}"
            ship_entry["image"] = fname
            if download_images:
                outpath = os.path.join(IMAGES_DIR, fname)
                if not os.path.exists(outpath):
                    ok = download_image(img_url, outpath)
                    if ok:
                        print("  downloaded:", fname)
                    else:
                        # don't fail hard; leave image out if download failed
                        ship_entry.pop("image", None)
                else:
                    # skip re-download
                    pass
        tiers[tier].append(ship_entry)
        # small delay to be polite (not strictly necessary here)
        time.sleep(REQUEST_DELAY)
    # save tiers files
    for t in range(1, 11):
        path = os.path.join(TIERS_DIR, f"tier_{t}.json")
        save_json(path, tiers[t])
        print(f"Saved {path} ({len(tiers[t])} ships)")
    return tiers

# ====== 実行 ======
def main():
    if not API_KEY or API_KEY == "YOUR_APPLICATION_ID":
        print("ERROR: API_KEY を設定してください（API_KEY = '...'）")
        sys.exit(1)
    ensure_dirs()
    cache = load_or_update_cache(force_update=False)
    # もし cache が ship_id -> data 形式でなく name->id のような古い構造なら、update する
    # ここでは cache の中身が ship_id keys であることを期待する
    # 簡単な検査:
    if not isinstance(cache, dict) or not any("ship_id" in v for v in cache.values()):
        print("キャッシュ形式異常または空のため、全取得でキャッシュを更新します。")
        cache = update_cache_full()
    print("キャッシュ読み込み完了。艦種分類と画像取得を開始します...")
    build_tiers_and_images(cache, download_images=True)
    print("完了。tiers/*.json と images/ にファイルが作成されています。")

if __name__ == "__main__":
    main()

