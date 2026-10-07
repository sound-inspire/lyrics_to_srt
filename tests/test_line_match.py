"""間奏明けの行の選び方（line_match.pick_line）の回帰テスト。
実行: python tests/test_line_match.py （pytest 不要）"""
import os, re, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from line_match import pick_line, starts_mid_line

norm = lambda s: re.sub(r"[\s、。，．,.!?！？]", "", s)

# 「琥珀に落とす影の幅」の歌詞の一部。18行目と32行目が同じ文言。
KOHAKU = [
    "画面のなかで　踊る歌", "何度も戻す　小さな指", "奥歯を強く　噛みしめると", "古い鉄の　味が残る",
    "調光卓の　古びた灯り", "台本に引く　黒い線", "見落とされた　影の重さを", "指のさきで　探している",
    "青い光を　強く絞る", "温もりなんて　作れない", "歪んでいるのは　私なのか", "眩しさに目が　眩むのか",
    "靴底にのこる　静止の重さ", "動かせない足の　すれる音", "同じ画面を　見つめていても", "ふたりの呼吸は　重ならない",
    "消えない擦過痕を　抱えたまま",
    "冷えたシャツを　皮膚にあてる",      # 18行目（index 17）
    "ガシャンと響く　吊り物の音", "消えていた靴の　あの玄関", "閉まるジッパーの　低い余韻",
    "不格好な灯りが　足元を照らす", "夜風が抜ける　台所で", "背中をゆらす　笑顔を見る",
    "私の痛みは　私だけのもの", "誰の光も　奪えない", "靴底にのこる　静止の重さ", "動かせない足の　すれる音",
    "同じ画面を　見つめていても", "ふたりの呼吸は　重ならない", "消えない擦過痕を　抱えたまま",
    "冷えたシャツを　皮膚にあてる",      # 32行目（index 31）
    "琥珀の舞台に　影をまぜる", "畳の上に伸ばす　一線の光", "障子の隙間を　静かに閉じて", "明日もまた　あの歌を聞く",
]

FAIL = []

def check(ok, label, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"  {detail}" if detail else ""))
    if not ok:
        FAIL.append(label)

# 1. 聞き取りが1行ぶんしか無く、同じ文言が先に2回ある → 手前（18行目）を選ぶ
i, sc = pick_line(KOHAKU, norm("冷えたシャツを皮膚にあてる"), 0)
check(i == 17, "repeated line after interlude -> earliest occurrence", f"got line {None if i is None else i + 1} score {sc:.2f}")

# 2. 手前に一致が無い行は、飛ばしてでも正しく選ぶ
i, sc = pick_line(KOHAKU, norm("琥珀の舞台に影をまぜる畳の上に伸ばす"), 17)
check(i == 32, "unique later line is still found", f"got line {None if i is None else i + 1}")

# 3. 探索は last_line より後ろだけ（18行目を使った後は32行目）
i, sc = pick_line(KOHAKU, norm("冷えたシャツを皮膚にあてる"), 17)
check(i == 31, "search starts after last_line", f"got line {None if i is None else i + 1}")

# 4. 似た行が無ければ類似度は低い（呼び出し側が 0.5 未満を捨てる）
i, sc = pick_line(KOHAKU, norm("まったく関係のない言葉ばかり"), 0)
check(sc < 0.5, "unrelated text scores low", f"{sc:.2f}")

# 5. 行の途中の息継ぎで切れた聞き取り（「冷えた鉄と甘い脂」の実例）は行の途中と判定する
for line, head in [("残された匂い ズレた位置を", "連れた位置を自分の手の中計り直すの"),
                   ("ポケットの鍵を 強く握って", "を強く握って枝の先っぽ光を吸ってた")]:
    check(starts_mid_line(line, norm(head)), "mid-line head is detected", head)

# 6. 行頭から始まる聞き取りは、末尾が次の行にはみ出していても、表記差があっても行頭とみなす
for line, head in [("指先がなぞる 削れた重み", "指先がなぞる削れた重み残された匂い"),
                   ("去っていく背中 一人の頷き", "去っていく背中一人のうなずき"),
                   ("ユビサキがなぞる ケズレタオモミ", "指先がなぞる"),
                   ("ポケットの底で 金属が冷える", "ケットの底で金属が冷える")]:
    check(not starts_mid_line(line, norm(head)), "line-start head is not mid-line", head)

print("failures", len(FAIL))
sys.exit(1 if FAIL else 0)
