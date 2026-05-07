"""
get_threads_user_id.py

Threads公式APIの /me エンドポイントから THREADS_USER_ID を取得して表示する補助スクリプト。

前提:
  - .env に THREADS_ACCESS_TOKEN を設定済み
"""

import os
import sys
import requests
from dotenv import load_dotenv


def main() -> int:
    load_dotenv()

    token = os.getenv("THREADS_ACCESS_TOKEN", "").strip()
    if not token or token.startswith("your_"):
        print("THREADS_ACCESS_TOKEN が未設定です。.env に設定してから再実行してください。", file=sys.stderr)
        return 1

    url = "https://graph.threads.net/v1.0/me"
    params = {
        "fields": "id,username,name",
        "access_token": token,
    }

    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"/me の取得に失敗しました: {e}", file=sys.stderr)
        return 2

    data = r.json()
    user_id = data.get("id", "")
    username = data.get("username", "")
    name = data.get("name", "")

    if not user_id:
        print(f"レスポンスに id がありません: {data}", file=sys.stderr)
        return 3

    print(f"THREADS_USER_ID={user_id}")
    if username:
        print(f"username={username}")
    if name:
        print(f"name={name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

