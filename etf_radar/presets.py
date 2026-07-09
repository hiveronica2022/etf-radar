from __future__ import annotations

from .normalization import compact_code


# 东财 spot 列表不含债券 ETF；这些代码的名称由交易所份额数据回填，
# 此处给出更可读的展示名，避免上交所简称过短（如“十年国债”）。
ETF_NAME_OVERRIDES = {
    "511010": "国债ETF(5年)",
    "511030": "公司债ETF",
    "511070": "沪公司债ETF",
    "511090": "30年国债ETF",
    "511130": "30年国债ETF博时",
    "511180": "上证可转债ETF",
    "511260": "十年国债ETF",
    "511360": "短融ETF",
    "511380": "可转债ETF",
    "511520": "政金债ETF",
    "511580": "国债政金ETF",
    "551520": "科创债ETF汇添富",
}


ETF_PRESETS = {
    "core": {
        "description": "主要宽基、创业板/科创和科技成长板块 ETF 观察池",
        "codes": [
            # 主要宽基
            "510050",  # 上证50ETF华夏
            "510300",  # 沪深300ETF华泰柏瑞
            "510500",  # 中证500ETF南方
            "512100",  # 中证1000ETF南方
            "159352",  # A500ETF南方
            "159901",  # 深100ETF易方达
            # 创业板、科创板、双创
            "159915",  # 创业板ETF易方达
            "159949",  # 创业板50ETF华安
            "159967",  # 创业板成长ETF华夏
            "588000",  # 科创50ETF华夏
            "588120",  # 科创100ETF国泰
            "588400",  # 科创创业ETF嘉实
            # 科技、成长和硬科技主题
            "512480",  # 半导体ETF国联安
            "159995",  # 芯片ETF华夏
            "159516",  # 半导体设备ETF国泰
            "588200",  # 科创芯片ETF嘉实
            "515880",  # 通信ETF国泰
            "515050",  # 通信ETF华夏
            "159819",  # 人工智能ETF易方达
            "516510",  # 云计算ETF易方达
            "515230",  # 软件ETF国泰
            "159939",  # 信息技术ETF广发
            "159997",  # 电子ETF天弘
            "159732",  # 消费电子ETF华夏
            # 港股科技互联网
            "159792",  # 港股通互联网ETF富国
            "513330",  # 恒生互联网ETF华夏
            "513180",  # 恒生科技ETF华夏
        ],
    },
    "bond": {
        "description": "利率债、信用债、科创债、可转债和短融 ETF 观察池",
        "codes": [
            # 利率债
            "511010",  # 国债ETF(5年) 国泰
            "511260",  # 十年国债ETF 国泰
            "511090",  # 30年国债ETF 鹏扬
            "511130",  # 30年国债ETF 博时
            "511520",  # 政金债ETF 富国
            "511580",  # 国债政金ETF
            "159650",  # 国开债ETF博时
            # 信用债、公司债
            "511030",  # 公司债ETF
            "511070",  # 沪公司债ETF
            # 科创债
            "159600",  # 科创债ETF嘉实
            "159111",  # 科创债ETF天弘
            "159112",  # 科创债ETF银华
            "551520",  # 科创债ETF汇添富
            # 可转债
            "511380",  # 可转债ETF 博时
            "511180",  # 上证可转债ETF
            # 短融
            "511360",  # 短融ETF 海富通
        ],
    },
    "dividend": {
        "description": "上证/中证红利、红利低波、国企/央企红利和港股红利 ETF 观察池",
        "codes": [
            # 宽口径红利
            "510880",  # 红利ETF华泰柏瑞（上证红利）
            "515180",  # 红利ETF易方达（中证红利）
            "515080",  # 中证红利ETF招商
            # 红利低波
            "512890",  # 红利低波ETF华泰柏瑞
            "515450",  # 红利低波50ETF南方
            "563020",  # 红利低波ETF易方达
            "159307",  # 红利低波100ETF博时
            # 国企、央企红利
            "510720",  # 红利国企ETF国泰
            "561580",  # 央企红利ETF华泰柏瑞
            # 港股红利
            "513530",  # 港股通红利ETF华泰柏瑞
        ],
    },
}


def resolve_codes(presets: list[str] | None, codes: list[str] | None) -> list[str] | None:
    resolved: list[str] = []
    for preset in presets or []:
        if preset not in ETF_PRESETS:
            known = ", ".join(sorted(ETF_PRESETS))
            raise ValueError(f"未知 preset: {preset}。可用 preset: {known}")
        resolved.extend(ETF_PRESETS[preset]["codes"])
    resolved.extend(codes or [])
    if not resolved:
        return None

    deduped: list[str] = []
    seen: set[str] = set()
    for code in resolved:
        normalized = compact_code(code)
        if normalized not in seen:
            deduped.append(normalized)
            seen.add(normalized)
    return deduped
