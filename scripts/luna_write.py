"""
luna_write.py
ルーナ担当: ハーマイオニーのブリーフィングをもとに投稿案3案を作成するスクリプト
ステップ③: ブリーフィング取得 → 投稿案3案生成 → GitHub Issues記録
"""

import os
import re
import sys
import requests
from datetime import datetime
from utils.github_issues import GitHubIssues
from utils.agent_config import name as _n
from utils.gemini_client import call_gemini
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY")
GITHUB_TOKEN        = os.getenv("GITHUB_TOKEN")
GITHUB_REPO         = os.getenv("GITHUB_REPO")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BUZZ_POSTS_PATH = os.path.join(SCRIPT_DIR, "..", "operation", "knowledge", "kb_sys_ref_v001.md")


def get_briefing_from_issue(issue_number: int, gh: GitHubIssues) -> str:
    """GitHub Issueのコメントからハーマイオニーのブリーフィングを抽出する"""
    comments = gh.get_comments(issue_number)
    for comment in reversed(comments):
        if f"{_n('hermione')}より" in comment.body and "ブリーフィング" in comment.body:
            return comment.body
    return ""


def get_malfoy_feedback(issue_number: int, gh: GitHubIssues) -> str:
    """マルフォイの差し戻し or オーナーの修正指示を取得する（あれば）"""
    comments = gh.get_comments(issue_number)
    for comment in reversed(comments):
        if comment.body.strip().startswith("修正:") and comment.user.type != "Bot":
            return f"【オーナーからの修正指示】\n{comment.body.strip()}"
        if f"{_n('malfoy')}より：差し戻し" in comment.body:
            return comment.body
    return ""


def load_voice_definition() -> str:
    """kb_sys_ref_v001.mdから「自分のアカウントの声」定義セクションを抽出する"""
    try:
        with open(BUZZ_POSTS_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        marker = "## 🎤 自分のアカウントの声"
        if marker in content:
            start = content.index(marker)
            end = content.find("\n## ", start + len(marker))
            return content[start:end].strip() if end != -1 else content[start:].strip()
        return content[2000:4000]
    except FileNotFoundError:
        return "（声定義なし）"


def extract_persona_name(voice_def: str) -> str:
    """声定義からキャラ名を動的に抽出する"""
    m = re.search(r'\*{0,2}キャラ名\*{0,2}[：:]\s*(.+)', voice_def)
    if m:
        return m.group(1).strip().strip('*')
    return "キャラクター"


def extract_opening_line(voice_def: str) -> str:
    """声定義から定番のつかみフレーズを動的に抽出する"""
    m = re.search(r'「(.+?)」は定番のつかみ', voice_def)
    if m:
        return m.group(1)
    return ""


def load_reference_posts() -> str:
    """kb_sys_ref_v001.mdからバズ要因分析（構造の教訓）だけを抽出する。実際の投稿文は含めない"""
    try:
        with open(BUZZ_POSTS_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        marker = "## 🎤 自分のアカウントの声"
        if marker in content:
            ref_section = content[:content.index(marker)]
        else:
            ref_section = content[:3000]
        # ```コードブロック（実際の投稿文）を除去し、構造分析だけ残す
        ref_section = re.sub(r'```[\s\S]*?```', '[投稿文は省略・構造分析のみ参照]', ref_section)
        return ref_section[:3000]
    except FileNotFoundError:
        return "（参考投稿なし）"


def generate_posts(briefing: str, voice_def: str, ref_posts: str, malfoy_feedback: str = "") -> str:
    """Gemini Flash で投稿案3案を生成する（タイムアウト・フォールバック付き）"""

    persona_name = extract_persona_name(voice_def)
    opening_line = extract_opening_line(voice_def)

    # 声定義をsystem_instructionとして渡す（Geminiがシステムレベルで強制的に従う）
    opening_rule = f"""
■ 最重要ルール: 全SLOTの1投稿目は必ず「{opening_line}」で始めること。
この後に本題のフックを続ける。例外なし。この行がない投稿は全て差し戻しになる。
""" if opening_line else ""

    system_instruction = f"""あなたは「{persona_name}」というSNSキャラクターです。
以下の声定義に100%従ってください。これはシステムレベルの絶対ルールです。

{voice_def}
{opening_rule}
■ 絶対遵守ルール:
- 語尾は「〜してる」「〜だよ」「〜んだ」「〜よね」「〜てる」を中心に使うこと
- 「〜のさ」は使用禁止
- 「〜です」「〜ます」「〜ですよ」「〜ませんか」「〜しましょう」は使用禁止
- 「皆さん」は使用禁止。「みんな」を使うこと
- 「〜してください」「〜しませんか」等の丁寧語は使用禁止
- *（アスタリスク）は使用禁止。強調は「」を使うこと
"""

    feedback_section = f"""
## ⚠️ マルフォイからの前回差し戻し指摘（必ず反映すること）
{malfoy_feedback}
""" if malfoy_feedback else ""

    prompt = f"""
## 発信テーマ（必須・厳守）
チカ（30代前半・社長秘書）の実体験として語ること。
- 秘書業務×AI活用（稟議・上申・議事録・根回し・社長対応）が軸
- 「AI音痴な社長の無茶振りをAIで秒殺した」体験として語ること
- 単なるAIツール紹介・ニュース要約はNG。必ずチカの「やらかし」か「気づき」に乗せること

## 【最重要】自分の実体験バンク（必ずここからネタを選ぶこと）
以下の実体験・気づきをベースに投稿を書くこと。
参考投稿の内容をそのまま使うことは厳禁。角度と構造だけを借りること。

### 💼 稟議・上申での実体験
- 差し戻しが3連発→冒頭8文字を変えたら通るようになった。社長は本文をほぼ読んでない
- 通る稟議の冒頭は「削減額か効果 ② 着手タイミング ③ リスクの有無」を1〜2行に凝縮してる
- ChatGPTに「意思決定者が3秒で判断できる冒頭に書き直して」と投げるだけで別物になる
- 通過率が上がってから「チカって仕事早いね」と言われるようになった（中身は同じなのに）

### 📋 議事録での実体験
- 「文字起こしを議事録にして」の一発投げは初級。綺麗な文が出るだけでToDoが見えない
- プロンプトを3つに分ける：①サマリー用 ②アクション抽出用（誰が・何を・いつまで） ③社長報告用
- 議事録作成：2時間→15分、社長への報告準備：30分→即日、差し戻し：月5件→ほぼゼロ
- 社長に「で、ToDoは？」と言われたことが3回ある。今はもう言われない

### 🤫 社長対応・根回しでの実体験
- 「もっと詳しく調べて」に初級者はざっくり回答を出す。中級者はペルソナ＋制約で質を上げてる
- ペルソナ指定プロンプト：「あなたは〇〇業界10年のマーケ責任者。競合3社を比較し打ち手を3つ提案して」
- 回答が出たら「その提案の最大の弱点を指摘して」と続ける。社長の詰めが来ても崩れない資料になる
- 根回しメールもAIで下書き→自分で微調整。送る前に「この文章で角が立つ表現はあるか」とチェックさせてる

### ⚡ 秘書×AI活用で変わったこと
- 「承知いたしました」の裏で「ChatGPT、10分で頼む」と走らせてる。これが自分のルーティン
- 社長の思いつき指示（朝7時のLINE）も、AIに投げて8時には対応案が出てる
- 手動でやってた頃は毎日定時に帰れなかった。今は定時に帰って副業してる
- AIが出したドラフトを自分で修正する時間の方が短い。修正前提で使う方が速い

---
## バズ構造の型（「型」だけ参考にする。内容は実体験バンクのものを使うこと）
{ref_posts}

---
## ハーマイオニーのブリーフィング（ネタのヒントとして使う）
{briefing}
{feedback_section}

---
## ★有益さと密度の基準★

### 4種類のエンゲージメントトリガー（各スロット最低1つ必ず入れる）

**【いいね】共感・発見トリガー**
- 「あるある」「わかるー」と思わせる瞬間
- 例：「手動で毎日投稿してた頃、正直しんどかった」

**【再投稿・保存】シェアしたくなるトリガー**
- 番号付きリスト形式 or 対比・比較形式
- ★3スロットのうち必ず1つはリスト形式か対比形式にすること

**【フォロー】価値提示トリガー（最重要・必ず入れる）**
- ❌ NG：「フォローしてくれると嬉しいよ」← 理由がない
- ✅ OK：「何を届けるか」を具体的に書く
- **CTAには必ず「何を届けるか」を具体的に書く。「嬉しいよ」だけは禁止**

**【ツリーへの引き】続きを読ませるトリガー**
- 「ただし落とし穴が1つある」「具体的な手順は次のツリーで」

## ★超重要★ 3スロットそれぞれ異なるネタ・切り口にすること
- SLOT_1/2/3 は必ず別テーマ・別角度
- ブリーフィングのネタは1スロットにのみ使い、残り2スロットは実体験バンクから別の切り口で

## ★改行ルール★
- 1行あたり約40文字で改行すること（文の途中で改行しない。句点・文末語尾の後のみ）
- ❌ NG：「稟議の文章が問題なのかと\\n思ってた。」
- ✅ OK：「稟議の文章が問題なのかと思ってた。\\n違った。冒頭8文字の問題だった。」

## ★絶対禁止文字★
- * （アスタリスク）は絶対に使用禁止。1つでも含まれていたら即差し戻し
- 強調したい場合は「」（カギ括弧）を使うこと

## 時間帯別トーン
🌅 SLOT_1【7時】情報系・発見系。「今日から使える知識」
🌆 SLOT_2【18時】共感系。仕事終わりに「わかるー」「大事だな」
🌙 SLOT_3【21時】感情フック強め。「え、知らなかった」「これ面白い」

## ツリー投稿形式（内容の密度に応じて3〜5投稿を使い分ける）

### ⛔ 各投稿の文字数制限（厳守）
- **1投稿目（フック）：80文字以内** — 興味を引く一文だけ。続きを読みたくなる引き
- **2投稿目以降（本文）：各150〜300文字** — 具体例・ノウハウ・体験談を展開
- **最終投稿（CTA）：100文字以内** — まとめ＋「何を届けるか」を明示

### ツリー数の目安
- **3投稿（最低）**: シンプルなメッセージ。フック→本文→CTA
- **4投稿（標準）**: 体験談や具体例を1つ深掘り。フック→本文①→本文②→CTA
- **5投稿（リスト・ノウハウ系）**: 複数のポイントを列挙。フック→ポイント①→ポイント②→ポイント③→CTA
- 内容が薄くなるくらいなら少なく、密度を保てるなら多く。質が最優先

### CTAのルール（最終投稿に必ず入れる）
- ❌ 禁止：「フォローしてくれると嬉しいよ」「フォローしてね」だけ
- ✅ 必須：「何を届けるか」を具体的に書く

---
## 出力フォーマット
※ 各SLOTは3〜5投稿で構成する。===THREAD=== で区切る
※ 全SLOTの1投稿目は必ず「{opening_line}」で始めること！
※ 投稿の順序が正しいことを確認（フック→本文→…→CTA）

🌅 SLOT_1【7時・朝投稿】（情報・発見系）
━━━━━━━━━━━━━━━━━━━━
{opening_line}
[この後に本題のフックを続ける。合計80文字以内]
===THREAD===
[2投稿目：本文・導入]
===THREAD===
[3投稿目：本文・具体例や深掘り]
===THREAD===
[4投稿目：まとめ＋価値提示型CTA]
━━━━━━━━━━━━━━━━━━━━

🌆 SLOT_2【18時・夕方投稿】（共感・体験系）
━━━━━━━━━━━━━━━━━━━━
{opening_line}
[この後に本題のフックを続ける。合計80文字以内]
===THREAD===
[2投稿目：本文・体験や共感]
===THREAD===
[3投稿目：本文・気づきや転換]
===THREAD===
[4投稿目：まとめ＋価値提示型CTA]
━━━━━━━━━━━━━━━━━━━━

🌙 SLOT_3【21時・夜投稿】（感情フック・リスト系）
━━━━━━━━━━━━━━━━━━━━
{opening_line}
[この後に本題のフックを続ける。合計80文字以内]
===THREAD===
[2投稿目：本文①]
===THREAD===
[3投稿目：本文②]
===THREAD===
[4投稿目：本文③（リスト系なら追加ポイント）]
===THREAD===
[5投稿目：まとめ＋価値提示型CTA]
━━━━━━━━━━━━━━━━━━━━
"""

    result = call_gemini(prompt, GEMINI_API_KEY, system_instruction=system_instruction)

    # 定番つかみが1投稿目に含まれていない場合、強制的に挿入する
    if opening_line:
        result = force_opening_line(result, opening_line)

    return result


def force_opening_line(text: str, opening: str) -> str:
    """各SLOTの1投稿目冒頭に定番つかみを強制挿入する"""
    lines = text.split("\n")
    result_lines = []
    in_slot = False
    slot_first_line_done = False

    for line in lines:
        stripped = line.strip()
        # SLOT開始を検知（━━━の罫線の後）
        if "━━━" in stripped:
            if not in_slot:
                in_slot = True
                slot_first_line_done = False
            else:
                # 2つ目の罫線 = SLOT終了
                in_slot = False
            result_lines.append(line)
            continue

        # SLOT内の最初の非空行にopening_lineを挿入
        if in_slot and not slot_first_line_done and stripped:
            slot_first_line_done = True
            if opening not in stripped:
                result_lines.append(opening)
            result_lines.append(line)
            continue

        result_lines.append(line)

    return "\n".join(result_lines)


def main():
    logger.info("=== ルーナ 投稿案作成開始 ===")

    gh    = GitHubIssues(GITHUB_TOKEN, GITHUB_REPO)
    issue = gh.get_or_create_today_issue()
    gh.update_pipeline_status(issue.number, "luna", "running")

    try:
        briefing = get_briefing_from_issue(issue.number, gh)
        if not briefing:
            logger.error("ハーマイオニーのブリーフィングが見つかりません。先にhermione_research.pyを実行してください。")
            gh.update_pipeline_status(issue.number, "luna", "error")
            sys.exit(1)

        voice_def = load_voice_definition()
        logger.info(f"声定義ロード: {len(voice_def)}文字, persona={extract_persona_name(voice_def)}, opening={extract_opening_line(voice_def)}")
        ref_posts = load_reference_posts()
        malfoy_feedback = get_malfoy_feedback(issue.number, gh)
        if malfoy_feedback:
            logger.info("マルフォイの差し戻しコメントを取得しました。フィードバックを反映して再生成します。")

        posts = generate_posts(briefing, voice_def, ref_posts, malfoy_feedback)
        logger.info("投稿案3案生成完了")

        comment_body = f"""## ✍️ {_n('luna')}より：3時間帯投稿案 完成

**作成日時:** {datetime.now().strftime('%Y-%m-%d %H:%M')}

{posts}

---
*{_n('malfoy')}、3スロット分の校閲をお願いします。*
"""
        done_ts = datetime.now().strftime("%H:%M")
        gh.add_comment(issue.number, comment_body)
        gh.update_pipeline_status(issue.number, "luna", "done", done_ts)
        logger.info(f"GitHub Issue #{issue.number} に投稿案を追加しました")
        logger.info("=== ルーナ 投稿案作成完了 ===")

    except Exception as e:
        logger.error(f"ルーナ実行失敗: {type(e).__name__}: {e}")
        gh.update_pipeline_status(issue.number, "luna", "error")
        gh.add_comment(issue.number, f"## ❌ {_n('luna')}: エラー発生\n\n```\n{type(e).__name__}: {str(e)[:500]}\n```")
        url = os.getenv("DISCORD_WEBHOOK_URL", "")
        if url:
            try:
                requests.post(url, json={"content": f"❌ {_n('luna')}実行エラー: {type(e).__name__}: {str(e)[:200]}"}, timeout=10)
            except Exception:
                pass
        sys.exit(1)


if __name__ == "__main__":
    main()
