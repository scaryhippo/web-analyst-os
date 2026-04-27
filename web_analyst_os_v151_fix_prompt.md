# Web Analyst OS v1.5.1 — DEDUP精度向上パッチ
作成日: 2026-04-27  
対象ディレクトリ: `~/Projects/web-analyst-os`

## 背景・目的

v1.5競合比較テストで以下の2点が残課題として確認された：

1. **P2でCase Studiesへの指摘が2件重複**：
   [conversion_architect]と[ux_auditor]が「Case Studiesが匿名・数値なし」を
   それぞれ独立して出力し、DEDUP_TOPIC_GROUPSで捕捉されていない。

2. **Strengthsセクション内でページ速度が重複**：
   P3から自動移動された称賛アイテムと、もともとStrengthsに存在する類似項目との
   重複チェックが行われていない。

---

## Fix 1：DEDUP_TOPIC_GROUPSへのグループ追加

### 対象ファイル：`core/report.py`（または DEDUP_TOPIC_GROUPS 定義箇所）

v1.5で追加したグループリストに、以下をさらに追記する：

```python
DEDUP_TOPIC_GROUPS = [
    # --- v1.5までの既存グループはそのまま維持 ---

    # v1.5.1 追加グループ
    {
        "name": "事例・実績の具体性",
        "keywords": [
            "Case Stud", "ケーススタディ", "事例", "匿名",
            "規模感", "数値成果", "定量成果", "実績の具体",
        ],
    },
    {
        "name": "ページ速度・パフォーマンス",
        "keywords": [
            "ページロード", "TTFB", "ロード時間", "表示速度",
            "高速", "軽量", "KBと", "msと",
        ],
    },
    {
        "name": "社会的証明・実績数値",
        "keywords": [
            "社会的証明", "導入実績", "顧客名", "顧客ロゴ",
            "実績件数", "導入企業数", "導入自治体数", "推薦",
        ],
    },
    {
        "name": "プロフィール・経歴の検証可能性",
        "keywords": [
            "LinkedIn", "在任期間", "MBBファーム", "経歴の検証",
            "公的記録", "プロフィール詳細", "キャリア詳細",
        ],
    },
    {
        "name": "サービス3分類・ターゲット設計",
        "keywords": [
            "3サービス", "Gov向け", "GovTech向け", "Market Strategy",
            "ターゲット別", "サービス分類", "3本柱",
        ],
    },
]
```

---

## Fix 2：Strengthsセクション内のDEDUP適用

### 対象ファイル：`core/report.py`

#### 問題の詳細

現状、DEDUP（`build_prioritized_items()` または `dedup_recommendations()`）は
P1・P2・P3を対象としているが、Strengthsセクションに対しては適用されていない。
その結果、以下の2つの経路で重複が発生する：

- 複数エージェントが同一強みを独立出力 → Strengths内重複
- Fix B（P3称賛アイテムの自動移動）で移動された項目と既存強み項目が重複

#### 修正内容

`generate_report()` 内の強みセクション組み立て処理に、
既存の `dedup_recommendations()` を適用する。

```python
# 強みセクションの重複排除
# （P3から自動移動された称賛アイテムを追加した後に実行すること）

strengths_items = dedup_recommendations(strengths_items)
```

`dedup_recommendations()` の呼び出しタイミングは、
`strengths_items.extend(auto_strengths)` の直後とする：

```python
# P3から分離された称賛アイテムを追加
strengths_items.extend(auto_strengths)  # p2_praise + p3_praise

# 追加後にDEDUPを実行（追加分と既存分の重複を除去）
strengths_items = dedup_recommendations(strengths_items)
```

#### 補足：dedup_recommendations() の挙動確認

既存の `dedup_recommendations()` は DEDUP_TOPIC_GROUPS の各グループに対して
キーワードマッチングを行い、同一グループ内で最初に出現した項目のみを残す。
Strengthsに適用しても同じロジックで動作するため、コードの追加変更は不要。

---

## 確認用テストコマンド

```bash
cd ~/Projects/web-analyst-os

# Fix 1 + Fix 2 の確認
python main.py https://www.scaryhippo.jp \
  --site-type consulting \
  --competitor-url https://qoollc.co.jp/ \
  > /tmp/scaryhippo_v151.md

# 確認ポイント1: P2でCase Studiesへの言及が1件のみであること
grep -n "Case Stud\|ケーススタディ\|匿名.*規模感\|規模感.*匿名" /tmp/scaryhippo_v151.md
# 出力が1行のみであることを確認

# 確認ポイント2: Strengthsセクションにページ速度の重複がないこと
# "強みと継承すべき点" 以降を抽出してページ速度言及数をカウント
awk '/強みと継承すべき点/,/Skeptical/' /tmp/scaryhippo_v151.md \
  | grep -c "ページロード\|TTFB\|ロード時間"
# 出力が1であることを確認（2以上なら重複あり）

# 回帰テスト：既存サイトでの品質維持
python main.py https://sunphototakahashi.com/ --crawl-subpages > /tmp/sunphoto_v151.md
python main.py https://atelier-a3.jp --site-type portfolio --crawl-subpages > /tmp/a3_v151.md
```

---

## 確認の判定基準

| 確認項目 | 合格基準 |
|---|---|
| Case Studies重複排除 | P2内でCase Studies/事例への言及が1件のみ |
| Strengths内速度重複 | ページ速度関連の強み項目が1件のみ |
| Strengths内三軸経歴 | 三軸資格情報への言及が1件のみ |
| 回帰：sunphoto | v1.5と同等のスコア・指摘内容が維持されている |

---

## バージョン管理

```bash
git add -A
git commit -m "v1.5.1: expand DEDUP groups for case-studies/performance, apply dedup to strengths section"
git push origin main
```
