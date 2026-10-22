def to_title_case(value: str) -> str:
    def cap_word(word: str) -> str:
        return "-".join(part[:1].upper() + part[1:].lower() for part in word.split("-"))

    return " ".join(cap_word(w) for w in (value or "").split())
