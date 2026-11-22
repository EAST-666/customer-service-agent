# -*- coding: utf-8 -*-
"""FAQ 检索：中文 bigram + TF-IDF 余弦，够用不引依赖"""
import json
import math
import re
from collections import Counter

from .config import FAQ_PATH, TOP_K

_TOKEN_RE = re.compile(r"[\u4e00-\u9fa5a-zA-Z0-9]+")


def tokenize(text: str):
    """中文按二字组合切，英文数字整词"""
    out = []
    for seg in _TOKEN_RE.findall(text.lower()):
        if seg.isascii():
            out.append(seg)
        else:
            if len(seg) == 1:
                out.append(seg)
            for i in range(len(seg) - 1):
                out.append(seg[i:i + 2])
    return out


class FAQIndex:
    def __init__(self, path=FAQ_PATH):
        items = json.loads(path.read_text(encoding="utf-8-sig"))
        self.items = items
        docs = [tokenize(i["q"] + " " + i["a"] + " " + " ".join(i.get("tags", []))) for i in items]
        self.df = Counter()
        for d in docs:
            for t in set(d):
                self.df[t] += 1
        n = len(docs)
        self.idf = {t: math.log((n + 1) / (c + 1)) + 1 for t, c in self.df.items()}
        self.vecs = [self._vec(d) for d in docs]

    def _vec(self, tokens):
        tf = Counter(tokens)
        v = {t: (1 + math.log(c)) * self.idf.get(t, 1.0) for t, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}

    def search(self, query: str, k: int = TOP_K):
        qv = self._vec(tokenize(query))
        scored = []
        for item, dv in zip(self.items, self.vecs):
            s = sum(w * dv.get(t, 0.0) for t, w in qv.items())
            if s > 0.05:
                scored.append({"id": item["id"], "q": item["q"], "a": item["a"], "score": round(s, 3)})
        scored.sort(key=lambda x: -x["score"])
        return scored[:k]
