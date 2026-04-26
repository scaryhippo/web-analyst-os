"""
Skeptical First-Timer — Red Team エージェント（3攻撃ベクター固定）
"""
from core.llm_router import call_llm
from agents._base import build_page_context

CLARITY_SYSTEM = """あなたは「Skeptical First-Timer / Clarity Attacker」です。
ゼロ文脈で初めてサイトを訪れた懐疑的な訪問者として攻撃を仕掛けます。

攻撃ベクター: **Clarity Attacker**
「このサイトを10秒見て、何の会社か・誰のためか・なぜ信頼できるか、説明できない」

メッセージの明確さ、ヒーローセクション、ナビゲーションのラベリングに対して
具体的で辛辣な批判を300文字以内で行ってください。"""

TRUST_SYSTEM = """あなたは「Skeptical First-Timer / Trust Destroyer」です。
ゼロ文脈で初めてサイトを訪れた懐疑的な訪問者として攻撃を仕掛けます。

攻撃ベクター: **Trust Destroyer**
「このサイトに個人情報・クレジットカード・時間を投資する理由が見当たらない」

トラストシグナルの欠如、社会的証明の弱さ、セキュリティ表示に対して
具体的で辛辣な批判を300文字以内で行ってください。"""

ACTION_SYSTEM = """あなたは「Skeptical First-Timer / Action Blocker」です。
ゼロ文脈で初めてサイトを訪れた懐疑的な訪問者として攻撃を仕掛けます。

攻撃ベクター: **Action Blocker**
「次に何をすべきかがわからない、あるいはやりたくない」

CTA の曖昧さ、摩擦の多いコンバージョンフロー、フォームの障壁に対して
具体的で辛辣な批判を300文字以内で行ってください。"""

REBUTTAL_SYSTEM = """あなたは専門家チームのリードです。
Skeptical First-Timer から受けた攻撃に対して、サイトの現状データに基づき
「RESOLVED（解決済み）」「PARTIALLY_RESOLVED（部分的に解決）」「UNRESOLVED（未解決）」
のいずれかを判定し、その根拠を述べてください。

【判定の確定性】
- 評価・判定は一度だけ出力すること。
- 「再判定」「訂正」「上記を修正して」などの自己修正プロセスを出力に含めないこと。
- 迷いがある場合は最初から慎重に判断し、確定した判定のみを出力する。
- 判定フォーマット: 「判定: RESOLVED / PARTIALLY_RESOLVED / UNRESOLVED のいずれか1つ」

回答形式（200文字以内）:
判定: RESOLVED|PARTIALLY_RESOLVED|UNRESOLVED
根拠: （簡潔な説明）"""


def red_team_attack_node(state: dict) -> dict:
    """3つの攻撃ベクターを実行する"""
    page_context = build_page_context(state)
    user_prompt = f"""以下のWebサイトを攻撃してください。\n\n{page_context}"""

    attacks = []
    default_attacks = {
        "clarity_attacker": "10秒では何の会社か判断できない。ヒーローコピーが不明瞭。（LLM 未実行）",
        "trust_destroyer": "信頼シグナルが確認できなかった。（LLM 未実行）",
        "action_blocker": "次のアクションが不明確。（LLM 未実行）",
    }
    for vector, system in [
        ("clarity_attacker", CLARITY_SYSTEM),
        ("trust_destroyer", TRUST_SYSTEM),
        ("action_blocker", ACTION_SYSTEM),
    ]:
        try:
            raw = call_llm("red_team", system, user_prompt, max_tokens=500)
            attacks.append({"vector": vector, "attack": raw.strip()})
        except Exception as e:
            attacks.append({"vector": vector, "attack": default_attacks[vector]})

    return {
        "red_team_attacks": attacks,
        "current_phase": "phase2_red_team",
    }


def specialist_rebuttal_node(state: dict) -> dict:
    """各攻撃への専門家の応答を生成する"""
    page_context = build_page_context(state)
    attacks = state.get("red_team_attacks", [])
    responses = []

    vector_labels = {
        "clarity_attacker": "Clarity Attacker（明確さへの攻撃）",
        "trust_destroyer": "Trust Destroyer（信頼への攻撃）",
        "action_blocker": "Action Blocker（行動障壁への攻撃）",
    }

    for attack_item in attacks:
        vector = attack_item.get("vector", "")
        attack_text = attack_item.get("attack", "")
        label = vector_labels.get(vector, vector)

        user_prompt = (
            f"攻撃ベクター: {label}\n\n"
            f"攻撃内容:\n{attack_text}\n\n"
            f"=== サイトデータ ===\n{page_context}\n\n"
            f"この攻撃に対する判定を行ってください。"
        )
        try:
            raw = call_llm("synthesis", REBUTTAL_SYSTEM, user_prompt, max_tokens=400)
            responses.append({"vector": vector, "rebuttal": raw.strip()})
        except Exception:
            responses.append({"vector": vector, "rebuttal": "判定: PARTIALLY_RESOLVED\n根拠: （LLM 未実行）"})

    return {
        "specialist_responses": responses,
        "current_phase": "phase2_rebuttal",
    }
