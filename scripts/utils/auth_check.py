"""
auth_check.py - 月次アクセストークン検証
scripts/utils/ に置いて、各メインスクリプトから呼び出す。
"""

import os
import re
from datetime import date
from pathlib import Path


def check_auth() -> tuple[bool, str]:
    """
    operation/auth/ の .key ファイルを検証する。
    Returns: (is_valid: bool, message: str)
    """
    # scripts/utils から operation/auth/ へのパスを解決
    script_dir = Path(__file__).resolve().parent.parent.parent
    auth_dir = script_dir / "operation" / "auth"

    if not auth_dir.exists():
        return False, "operation/auth/ フォルダが見つかりません。"

    key_files = sorted(auth_dir.glob("access_HOG-*.key"))
    if not key_files:
        return False, (
            "アクセストークンが見つかりません。\n"
            "コミュニティ管理者から access_HOG-YYYY-MM.key を受け取り、"
            "operation/auth/ に配置してください。"
        )

    key_file = key_files[-1]
    try:
        content = key_file.read_text(encoding="utf-8").strip()
    except Exception as e:
        return False, f"トークンファイルの読み込みに失敗しました: {e}"

    lines = content.splitlines()
    if not lines:
        return False, "トークンファイルが空です。"

    token_line = lines[0].strip()

    # トークン形式チェック: HOG-AUTH-YYYY-MM-XXXXXX
    if not re.match(r"^HOG-AUTH-\d{4}-\d{2}-[A-Z0-9]+$", token_line):
        return False, (
            f"トークン形式が不正です: {token_line}\n"
            "コミュニティ管理者から正しいトークンファイルを受け取ってください。"
        )

    # キー・バリューを解析
    kv = {}
    for line in lines[1:]:
        if ":" in line:
            k, _, v = line.partition(":")
            kv[k.strip()] = v.strip()

    # 有効期限チェック
    valid_until_str = kv.get("valid_until", "")
    if not valid_until_str:
        return False, "valid_until が見つかりません。トークンファイルが破損している可能性があります。"

    try:
        year, month, day = valid_until_str.split("-")
        valid_until = date(int(year), int(month), int(day))
    except (ValueError, AttributeError):
        return False, f"valid_until の日付形式が不正です: {valid_until_str}"

    today = date.today()
    if today > valid_until:
        return False, (
            f"アクセストークンの有効期限が切れています（期限: {valid_until_str}）。\n"
            "コミュニティ管理者から最新の月次トークンファイルを受け取り、"
            "operation/auth/ フォルダに入れてください。"
        )

    return True, f"認証OK（トークン有効期限: {valid_until_str}）"
