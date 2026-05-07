import sys, os, urllib.request, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

token = os.getenv('GITHUB_TOKEN')
repo  = os.getenv('GITHUB_REPO')

slot1 = """\
「社長の朝7時LINE、手動で対応してた頃が懐かしい」💼
===THREAD===
「例の件、今日中によろしく」

朝7時のLINEにこれが来た瞬間、
以前の自分は固まってた。

今は違う。
LINEをコピーして10分で対応案が出てくる。
（承知いたしました、とだけ返して走らせてる）
===THREAD===
プロンプトはこれ：

「あなたは10年経験の秘書。
上司からの依頼を解釈して、
①実行ステップ3つ
②確認すべき点2つ
③30分以内にできる最初の行動
を出して」

これを一度作っておくだけ。
===THREAD===
返ってくる回答に「リスク」と
「確認事項」も含めると、
社長の詰めが来ても崩れない。

「え、もうできてるの？」が
毎回もらえるようになってる。

職場でのAI活用プロンプト、
続きはフォローして待ってて💼"""

slot2 = """\
「AIの回答が浅い」と感じてる人へ。💻
それ、プロンプトの問題だよ。
===THREAD===
社長から「競合と比較した資料を
今日中に」と言われた時。

❌ 初級：「競合を比較して」
→ 使えない表が来る

✅ 中級：ペルソナ＋制約＋視点指定
→ 経営判断に使える資料が来る

この差は指示の精度だけ。
===THREAD===
使ってるプロンプトはこれ：

「あなたは業界10年のマーケ責任者。
競合3社を①価格 ②強み ③弱みで比較。
当社の打ち手を3つ提案して。
各提案に根拠とリスクを添えること」

これだけで別次元になる。
===THREAD===
回答が出たら続けてこう投げてる：

「その提案の最大の弱点を教えて」
「反対意見を持つ役員の立場から反論して」

これで穴を先に潰してる。
社長の詰めが来ても崩れない資料になる。

「AIをもっと深く使いたい」人、
コメントで教えて💻"""

slot3 = """\
「AIで突発対応できる人」になるのは
難しいって思ってた。🤫正直に話す。
===THREAD===
半年前、社長のLINEに毎回テンパってた。

「AIに投げればいい」ってわかってたけど、
何を指示すればいいかわからなくて、
結局手動でやってた。

（これ、わかる人いるはず）
===THREAD===
変わったのは「役割を与える」を
覚えてから。

「ChatGPTを秘書として使う」じゃなくて、
「ChatGPTに社長役をやらせる」

この発想で返ってくる回答が別物になった。
===THREAD===
具体的にはこう使ってる：

「あなたは私の社長の立場。
この提案のどこが気になるか教えて」

「あなたは反対意見を持つ役員。
この案に反論して」

社長の頭の中をAIでシミュレート
してから会議に臨んでる。

秘書目線のプロンプト、
続きはフォローして待ってて🤫"""

body = (
    "## 🎩 神尾楓珠より：承認申請（2026-04-23分・事前作成）\n\n"
    "**審査日時:** 2026-04-22（翌日分・オーナー承認済み）\n\n"
    "全スロット合格。チカキャラ・中級者・突発対応テーマ・〜してる語尾 確認済み。\n\n"
    "---\n"
    "### 📋 推奨投稿案（3時間帯・オーナー一括承認用）\n\n"
    "**🌅 SLOT_1【7時・即時投稿】**\n"
    "```\n" + slot1 + "\n```\n\n"
    "**🌆 SLOT_2【18時・夕方投稿】**\n"
    "```\n" + slot2 + "\n```\n\n"
    "**🌙 SLOT_3【21時・夜投稿】**\n"
    "```\n" + slot3 + "\n```\n\n"
    "**オーナーへ:** このIssueに「承認」とコメントしてください。\n"
    "- SLOT_1（7時）→ 承認後すぐに投稿されます\n"
    "- SLOT_2（18時）→ GitHub Actionsが自動投稿します\n"
    "- SLOT_3（21時）→ GitHub Actionsが自動投稿します\n"
)

data = json.dumps({'body': body}).encode('utf-8')
req = urllib.request.Request(
    f'https://api.github.com/repos/{repo}/issues/4/comments',
    data=data,
    headers={
        'Authorization': f'token {token}',
        'Content-Type': 'application/json',
        'Accept': 'application/vnd.github.v3+json'
    },
    method='POST'
)
with urllib.request.urlopen(req) as res:
    result = json.loads(res.read())
    print('投稿完了 ID:', result['id'])
