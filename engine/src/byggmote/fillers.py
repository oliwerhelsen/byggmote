"""Filler words out of dictated text (#843). Only sounds that are never a word: "er" is a Swedish word ("ger er"), so
it is a filler only in English; "mm" means yes in Swedish and stays. Words that are fillers only sometimes ("liksom",
"like") stay. Meetings keep their fillers."""

COMMON = set("öh öhm äh ähm eh ehm um uh uhm hm hmm".split())
FILLERS = {"sv": COMMON, "en": COMMON | {"er", "erm"}}
END = ".!?"


def clean(words: list[dict], lang: str) -> list[dict]:
    """`words` without fillers. A filler's sentence end moves to the word before it, and the word after a filler that
    started a sentence gets a capital letter."""
    fillers = FILLERS.get(lang, COMMON)
    out, cap = [], False
    for w in words:
        core = w["w"].strip(".,!?:;…-\"'")
        if core.lower() not in fillers:
            if cap and w["w"].islower():
                w = w | {"w": w["w"].capitalize()}
            out.append(w)
            cap = False
            continue
        end = next((c for c in reversed(w["w"]) if c in END), "")
        if not out or out[-1]["w"][-1:] in END:
            cap = True
        elif end:
            out[-1] = out[-1] | {"w": out[-1]["w"].rstrip(",;:") + end}
    if out and len(out) < len(words) and out[-1]["w"][-1:] in ",;:":
        out[-1] = out[-1] | {"w": out[-1]["w"].rstrip(",;:")}
    return out
