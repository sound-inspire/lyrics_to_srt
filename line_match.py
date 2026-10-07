"""間奏明けの聞き取り文が、歌詞の何行目から始まるかを決める。"""
import difflib
import re

norm = lambda s: re.sub(r"[\s、。，．,.!?！？]", "", s)
TIE_MARGIN = 0.1  # 最高点からこの差以内の候補は同点とみなし、手前の行を選ぶ


def pick_line(lines, head, last_line):
    """head（正規化済みの聞き取り文）が始まる行番号と類似度を返す。
    探すのは last_line より後ろの行だけ。2行ぶんで照合する（くり返しサビの取り違え防止）。

    同じ文言がくり返し出てくると、2行目の違いで後ろの候補がわずかに勝つことがある。
    歌詞は順に進むので、最高点から TIE_MARGIN 以内の候補があれば一番手前を選ぶ
    （後ろへ何行も飛ばすと、飛ばした行が前の区間に押し込まれて長さ0に潰れるため）。
    同点の中には、手前の行の2行窓の後半に正解の文言が入っているだけの候補も混ざる。
    そこで同点の候補を、その行1行だけで聞き取りの頭と比べた点でも絞る。"""
    ratio = lambda a: difflib.SequenceMatcher(None, a, head[:len(a)]).ratio()
    scores = [(i, ratio(norm("".join(lines[i:i + 2]))), ratio(norm(lines[i])))
              for i in range(last_line + 1, len(lines))]
    if not scores:
        return None, 0.0
    best2 = max(s2 for _, s2, _ in scores)
    if best2 <= 0.0:
        return None, 0.0
    tied = [c for c in scores if c[1] >= best2 - TIE_MARGIN]
    best1 = max(s1 for _, _, s1 in tied)
    for i, s2, s1 in tied:
        if s1 >= best1 - TIE_MARGIN:
            return i, s2


def head_offset(line, head):
    """聞き取り文 head が、歌詞の行 line の何文字目から始まっているかを返す（不明なら None）。
    2文字以上一致する最初の箇所で、行側と聞き取り側の位置の差をとる。
    行の途中の息継ぎで聞き取りが切れると、次の区間は行の後半から始まり、ここが大きくなる。"""
    L = norm(line)
    sm = difflib.SequenceMatcher(None, L, head[:len(L)], autojunk=False)
    for m in sm.get_matching_blocks():
        if m.size >= 2:
            return m.a - m.b
    return None


def starts_mid_line(line, head):
    """聞き取り文が行頭ではなく行の途中から始まっていれば True。
    数文字のずれ（行頭の聞き漏らし、かなと漢字の表記差）は許す。"""
    off = head_offset(line, head)
    return off is not None and off >= max(3, len(norm(line)) // 3)
