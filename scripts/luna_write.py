"""
luna_write.py
ルーナ担当: ハーマイオニーのブリーフィングをもとに投稿案3案を作成するスクリプト
ステップ③: ブリーフィング取得 → 投稿案3案生成 → GitHub Issues記録
"""

import os
import re
import sys
import requests
from datetime import datetime, timezone, timedelta
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
    for pattern in [r'\*{0,2}キャラ名\*{0,2}[：:]\s*(.+)', r'\*{0,2}名前\*{0,2}[：:]\s*(.+)']:
        m = re.search(pattern, voice_def)
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

    JST = timezone(timedelta(hours=9))
    now_jst = datetime.now(JST)
    weekday = now_jst.weekday()  # 0=月, 5=土, 6=日
    weekday_name = ["月", "火", "水", "木", "金", "土", "日"][weekday]
    is_weekend = weekday >= 5

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
めい（仙台在住・5歳の息子を持つワーキングママ・SNS運用代行×AI活用・法人化3期目）の実体験として語ること。
- SNS運用代行×AI活用（在宅10〜15時・育児との両立）が軸
- 「AIを使い始めてから作業時間が2時間→30分になった」体験として語ること
- 単なるAIツール紹介やニュース要約はNG。必ずめいの「気づき」か「体験」に乗せること

## 【最重要】絶対NGワード・NGテーマ（1つでも含まれたら即差し戻し）
- 禁止ワード：「副業」（→「ﾌｸ業」と書く）・「稼ぐ」・「稼げる」・「稼いだ」・「定時」・「社長」・「経営者」・「オーナー」・「上司」・「部長」
- 禁止テーマ：稟議書・議事録・会議資料・ビジネス文書作成・社内業務効率化・DX推進・プログラミング・エンタープライズ向けAI
- 禁止フレーズ：「続きはツリーで」「全部ツリーで話す」「詳細はツリーへ」などの誘導文言

## 【最重要】めいの実体験バンク（必ずここからネタを選ぶこと）
以下の実体験・気づきをベースに投稿を書くこと。
参考投稿の内容をそのまま使うことは厳禁。角度と構造だけを借りること。
**3スロットで同じツール・同じネタは絶対に使わない。毎回違うツールを選ぶこと。**

### 📱 SNS運用代行×AI活用の実体験
- 毎朝投稿文を考えるのに2時間かかってた。今は30分。変えたのはAIへの「相談する順番」だけだった
- ChatGPTで構成を作って、Claudeで文体を整えて、Canvaで画像を作る。この3分割で30分以内に完成する
- クライアント10社のSNS運用を、同じAIの仕組みで回してる。累計30社やってきた
- Threadsの投稿案、「タメ語で体験談ベースで3案作って」と入れるだけでClaudeが出してくれる
- 全部1つのAIに投げてる人、損してるよ。AIには得意不得意があるから

### 🤖 最新AIツール紹介（「こんなことできるみたい！試してみて！」スタイルでOK）
実際に使ったことがなくても、「〜らしい」「〜みたい」「気になってる」「試してみてね」のトーンで紹介する投稿はOK。
- **Manus**：AIが自分でブラウザを開いて、調べて、資料にまとめてくれるエージェント型AI。「指示するだけで全部やってくれるらしい」という角度で紹介できる
- **NoimosAI**：SNS運用に特化したAIツール。投稿の反応予測や最適な投稿時間まで提案してくれるらしい。試してみたい
- **Claude Code**：ターミナルで動くClaude。コードを書けない人でも、日本語で指示するだけで自動化ツールが作れるらしい
- **Cursor**：AIが入ったコードエディタ。SNS管理の簡単なツールを作ってもらったという話をよく聞く。プログラマーじゃなくても使えるらしい
- **Perplexity AI**：AIがリアルタイムで検索してまとめてくれる。無料で使えてトレンドリサーチが速い
- **Grok**：X（旧Twitter）のリアルタイムトレンドに強いAI。今何が話題かを把握するのに使ってみたい
- **Google Gemini**：YouTubeの動画を要約させてトレンドキャッチ。「この動画のSNS投稿案を3つ出して」と続けて使ってる
- **Descript**：音声・動画の文字起こしと編集をAIがやってくれる。リール用の音声作業が30分→5分になるらしい
- **Adobe Firefly**：Adobeの無料AI画像生成。Canvaと使い分けてる人が多い
- **Claude（無料版）**：文章のトーンを細かく指定できる。ChatGPTより人っぽい文体が出やすいと感じてる

### 💰 LP制作・収益導線のヒント（クライアントの売上に繋がる運用代行の視点）
- SNS運用はフォロワーを増やすだけじゃなく、SNS→LP→LINE→購買の流れを設計することが大事
- Framer AIやSTUDIOなど、AIが自動でLPを作ってくれるツールが出てきてる。制作コストが大幅に下がった
- クライアントのSNSに収益導線を引くことで、フォロワー数より売上が変わる。これを提案できるかが単価の差になる
- 「投稿してるのに売れない」クライアントは、大抵SNSとLPが繋がってない。ここを直すだけで変わることがある
- SNS→LINEに誘導する文言をAIに考えてもらう。「LINE登録で〇〇プレゼント」の〇〇部分はAIと相談して決めてる

### 👶 在宅×育児×仕事を回す実体験
- 在宅で10時〜15時の間に仕事してる。仕事が少ない日は1日2時間で全部終わる
- 息子の「ねえねえ」に3回「うん」と返しながら、AIに作業を投げてた。これが今の働き方
- 「働く時間を減らしたい」じゃなくて、「成果を出す時間に集中したい」と思ってAIを使い始めた
- クライアント対応もAIで下書きして、自分で微調整する。送る前に「角が立つ表現ある？」と確認させてる

### 💡 AI活用で変わったこと・気づき
- 無料のClaude・ChatGPT・Gemini・Perplexityだけで仕事の8割は回る。お金かけなくていい
- AIを使い分けると、1時間かかってた作業が10分で終わることがある
- スキルがあっても単価が上がらない人は、作業スピードを見せられてないことが多い
- 新しいAIツールが出るたびに気になって調べてる。全部試す必要はない。自分の仕事に合うかどうかが基準

---
## バズ構造の型（「型」だけ参考にする。内容は実体験バンクのものを使うこと）
{ref_posts}

---
## ハーマイオニーのブリーフィング（ネタのヒントとして使う）
{briefing}
{feedback_section}

---
## ★今日は{weekday_name}曜日（コンテンツミックスを必ず守ること）
{"SLOT_1=共感系、SLOT_2=有益情報系、SLOT_3=有益情報系" if is_weekend else "SLOT_1=有益情報系、SLOT_2=共感系、SLOT_3=感情フック系"}
- 共感系：「わかるー」「私もそう」と読者が思える投稿。育児・在宅・生き方のリアルな体験。数字より感情を優先する
- 有益情報系：具体的なAIツール・使い方・実体験ベースのノウハウ。読んで実際に試せる内容にする
- 感情フック系：「え、そうなの？」「知らなかった」と思わせる発見・驚き・気づきの投稿

## ★日本語ライティングルール★（必ず守ること）
- 主語と述語が噛み合った、自然な日本語で書く
- 一文を短く。意味が伝わる順番で並べる（修飾語が遠すぎる文は禁止）
- 話し言葉のリズムで書く。「〜だよ」「〜してた」「〜なんだよね」を自然に混ぜる
- 読んで「あれ？」と止まるような不自然な表現は使わない
- AI定型表現は全て禁止：「〜することが重要です」「〜を心がけましょう」「まとめると」「結論として」
- 断定しすぎず余白を残す：「たぶん〜」「〜かもしれない」「〜気がしてる」

## ★AIネタのルール★（毎回必ず守ること）
1. **ツールの多様性**：SLOT_1/2/3で同じAIツールを使い回さない。Manus・NoimosAI・Claude Code・Cursor・Perplexityなど新しいツールを積極的に使う
2. **AIのかけ合わせ**：毎回必ず複数のAIを組み合わせた使い方を1つ入れる
   例：「Perplexityでトレンドリサーチ→ChatGPTで構成→Claudeで文体調整」
   例：「GeminiでYouTube要約→Claudeで投稿案化→Canvaで画像」
3. **無料AI情報**：Claude無料版・ChatGPT無料版・Gemini無料版・Perplexity無料版など、無料でできる情報を積極的に入れる
4. **AIの書き方順序**：AIを出すときは ①なぜそのAIか（他との違い・特徴を一言）→②使い方ステップ（具体的なプロンプトや操作）→③体験談 の順で書く
5. **「試してみて」スタイルOK**：実際に使ったことがなくても、「〜らしい」「〜みたい」「気になってる」「試してみてね！」のトーンで新しいAIを紹介する投稿はOK
6. **情報正確性**：使ったことがあるツールは正確に書く。使ったことがないツールは「〜らしい」「試してみてね」と添える

## ★文字数ルール★（厳守）
- **1投稿目（フック）：100〜150字** — 読者の指を止めるフック。「続きはツリーで」などの誘導文言なし。自然にツリーへ続く流れ
- **ツリー各投稿：100〜200字** — AIの特徴・使い方・体験談を展開。短く区切ってテンポよく
- **最終ツリー：100字程度** — 読者への問いかけで締める（「みんなはどうしてる？教えてほしいな🤍」）

## ★改行ルール★（必ず守ること）
- 1行は23文字以内に収める
- 23文字付近に「、」がある場合は、その「、」の直後で改行する
- 「。」で文が終わったら改行する
- 意味のまとまりごとに1行空ける

## ★絶対禁止★
- * （アスタリスク）は絶対に使用禁止。強調は「」を使うこと
- 箇条書き・番号リスト形式は禁止（SNS投稿は文章で流れるように）
- 「！」は1投稿2個まで。「？」は1投稿1個まで

## 時間帯別トーン
🌅 SLOT_1【15時】情報系・発見系。「今日から使える知識」。仕事の区切りに読まれる時間帯
🌆 SLOT_2【18時】共感系。「わかるー」「大事だな」と思わせる。仕事終わりの共感ゾーン
🌙 SLOT_3【21時】感情フック強め。「え、そうなの？」「これ面白い」と思わせる夜の投稿

## ★超重要★ 3スロットは必ず別テーマ・別角度にすること
- SLOT_1/2/3 でテーマが被らないこと
- ブリーフィングのネタは1スロットにのみ使い、残り2スロットは実体験バンクから別の切り口で書く

---
## 出力フォーマット
※ 各SLOTは1投稿目＋ツリー2〜3つで構成する。===THREAD=== で区切る
※ 全SLOTで別テーマ・別角度にすること
※ 1投稿目に誘導文言（「続きはツリーで」等）は絶対に入れないこと

🌅 SLOT_1【15時・昼投稿】（{"共感系：育児・在宅・生き方のリアル" if is_weekend else "有益情報系：今日から使えるAI活用ノウハウ"}）
━━━━━━━━━━━━━━━━━━━━
[1投稿目：100〜150字のフック。自然にツリーへ続く流れ]
===THREAD===
{"[ツリー①：育児か在宅ワークの共感エピソード]" if is_weekend else "[ツリー①：AIを選んだ理由・特徴を一言 + 使い方ステップ]"}
===THREAD===
[ツリー②：体験談 + 「みんなはどうしてる？教えてほしいな🤍」などの問いかけで締め]
━━━━━━━━━━━━━━━━━━━━

🌆 SLOT_2【18時・夕方投稿】（{"有益情報系：具体的なAIツール・ノウハウ" if is_weekend else "共感系：育児・在宅・生き方のリアル"}）
━━━━━━━━━━━━━━━━━━━━
[1投稿目：100〜150字のフック]
===THREAD===
{"[ツリー①：AIを選んだ理由・特徴を一言 + 使い方ステップ]" if is_weekend else "[ツリー①：体験談・共感エピソード]"}
===THREAD===
{"[ツリー②：体験談 + 読者への問いかけで締め]" if is_weekend else "[ツリー②：気づき・転換点 + 読者への問いかけで締め]"}
━━━━━━━━━━━━━━━━━━━━

🌙 SLOT_3【21時・夜投稿】（{"有益情報系：LP・収益導線・クライアント運用のヒント" if is_weekend else "感情フック系：発見・驚き・気づき"}）
━━━━━━━━━━━━━━━━━━━━
[1投稿目：100〜150字のフック]
===THREAD===
[ツリー①：本文①]
===THREAD===
[ツリー②：本文②]
===THREAD===
[ツリー③：読者への問いかけで締め]
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
