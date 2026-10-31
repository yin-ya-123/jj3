"""通用工具：股票代码规范化与市场判定"""


def normalize_code(symbol: str) -> str:
    """把 sh.600519 / 600519.SH / 600519 统一成 6 位数字代码"""

    text = str(symbol).strip().lower()

    if not text:
        raise ValueError("股票代码不能为空")

    if "." in text:
        digits = [part for part in text.split(".") if part.isdigit()]

        if not digits:
            raise ValueError(f"无效股票代码: {symbol}")

        text = digits[0]

    if not text.isdigit() or len(text) != 6:
        raise ValueError(f"无效股票代码: {symbol}")

    return text


def market_of(code: str) -> str:
    """根据证券代码判断所属交易市场（上交所、深交所、北交所）"""

    code = str(code).strip()

    # 兼容 sh.600519、sz.000001 等格式
    if "." in code:
        prefix, suffix = code.split(".", 1)
        if prefix.lower() in ("sh", "sz", "bj"):
            return prefix.upper()
        code = suffix

    code = code[-6:].zfill(6)

    # 上海证券交易所
    if code.startswith((
        "5",  # ETF、基金
        "6",  # 沪市股票
        "9",  # 部分其他证券
    )):
        return "SH"

    # 北京证券交易所
    if code.startswith(("4", "8")):
        return "BJ"

    # 深圳证券交易所
    if code.startswith((
        "0",  # 深市主板
        "1",  # 深市基金
        "2",  # 部分其他证券
        "3",  # 创业板
    )):
        return "SZ"

    raise ValueError(f"暂不支持的证券代码: {code}")