import os
import json
import requests
from time import sleep

API_KEY = "352f3820d1e216d1896d0e3d430b829c"
API_URL = "https://api.worldofwarships.asia/wows/encyclopedia/ships/"
TIERS_DIR = "tiers"
OUTPUT_DIR = "ships_data"

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

def get_all_tier_files():
    """tiers/ フォルダ内の tier_*.json ファイルを取得"""
    files = []
    for i in range(1, 11):
        f = os.path.join(TIERS_DIR, f"tier_{i}.json")
        if os.path.exists(f):
            files.append(f)
        else:
            print(f"⚠️ {f} が見つかりません。スキップ。")
    return files

def load_ships_from_tier_file(filepath):
    """tier_X.json から艦艇の name と ship_id を抽出"""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    ships = {}
    # tierファイルのフォーマットに応じて変更
    # 例: {"data": {"123456": {"name": "大和", "ship_id": 123456}}}
    if isinstance(data, dict):
        for ship_id, info in data.get("data", {}).items():
            name = info.get("name")
            if name and "ship_id" in info:
                ships[name] = info["ship_id"]
    elif isinstance(data, list):
        for info in data:
            if isinstance(info, dict):
                name = info.get("name")
                sid = info.get("ship_id")
                if name and sid:
                    ships[name] = sid
    return ships

def fetch_and_save_ship(ship_name, ship_id):
    """艦艇の詳細情報を取得して保存"""
    ensure_dir(OUTPUT_DIR)
    filepath = os.path.join(OUTPUT_DIR, f"{ship_name}.json")

    if os.path.exists(filepath):
        print(f"✅ {ship_name} は既に存在します。スキップ。")
        return

    params = {
        "application_id": API_KEY,
        "ship_id": ship_id,
        "language": "ja"
    }

    try:
        r = requests.get(API_URL, params=params)
        data = r.json()

        if data.get("status") != "ok":
            print(f"⚠️ {ship_name} ({ship_id}) の取得に失敗: {data}")
            return

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        print(f"💾 {ship_name}.json を保存しました。")
        sleep(0.3)  # API制限対策

    except Exception as e:
        print(f"❌ {ship_name} の取得中にエラー: {e}")

def main():
    if not API_KEY or API_KEY == "YOUR_APPLICATION_ID":
        print("❌ APIキーを設定してください。")
        return

    tier_files = get_all_tier_files()
    total_ships = {}

    print("📡 Tierデータから艦艇リストを読み込み中...")

    for file in tier_files:
        ships = load_ships_from_tier_file(file)
        total_ships.update(ships)

    print(f"🔎 合計 {len(total_ships)} 隻の艦艇を検出しました。")

    for name, sid in total_ships.items():
        fetch_and_save_ship(name, sid)

    print("✅ すべての艦艇詳細情報を保存しました。")

if __name__ == "__main__":
    main()

