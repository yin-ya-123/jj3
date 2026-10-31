from data.utils import market_of

test_codes = {
    "600519": "SH",
    "601318": "SH",
    "688001": "SH",
    "510010": "SH",
    "510300": "SH",
    "159915": "SZ",
    "159919": "SZ",
    "000001": "SZ",
    "300750": "SZ",
    "430047": "BJ",
    "830799": "BJ",
}

for code, expected in test_codes.items():
    actual = market_of(code)
    status = "PASS" if actual == expected else "FAIL"
    print(f"{status}: {code} -> {actual} (预期 {expected})")