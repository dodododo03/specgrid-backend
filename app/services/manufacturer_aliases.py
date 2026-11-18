"""Korean/English spellings of the same manufacturer, for the 제조사 filter.

Sellers type the manufacturer freely ("삼성", "Samsung", "엔비디아", "NVIDIA"...), so filtering by one
spelling must also find the others. A query that equals any alias (case-insensitive) expands to the
whole group; anything else is searched as typed.
"""

ALIAS_GROUPS: list[tuple[str, ...]] = [
    ("삼성", "삼성전자", "Samsung"),
    ("LG", "엘지", "LG전자"),
    ("SK하이닉스", "하이닉스", "SK hynix", "Hynix"),
    ("한성컴퓨터", "한성", "Hansung"),
    ("앱코", "ABKO"),
    ("NVIDIA", "엔비디아"),
    ("AMD", "에이엠디"),
    ("Intel", "인텔"),
    ("Apple", "애플"),
    ("ASUS", "에이수스", "아수스"),
    ("Lenovo", "레노버"),
    ("Dell", "델"),
    ("Sony", "소니"),
    ("Corsair", "커세어"),
    ("Keychron", "키크론"),
    ("Logitech", "로지텍"),
]

_INDEX = {alias.casefold(): group for group in ALIAS_GROUPS for alias in group}


def search_terms(query: str) -> tuple[str, ...]:
    query = query.strip()
    return _INDEX.get(query.casefold(), (query,))
