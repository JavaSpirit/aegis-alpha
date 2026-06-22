from __future__ import annotations

import pytest

from aegis_alpha.adapters.jvquant_market_data import (
    JvQuantMarketDataAdapter,
    _inferred_change_pct_for_limit_up,
    normalize_symbol,
)


def _multi_board_payload(query: str) -> dict:
    if "概念" in query or "题材" in query:
        fields = ["代码", "名称", "涨跌幅", "连板(天)", "成交额", "是否ST", "涨停", "概念", "个股题材", "行业", "最新价"]
        rows = [
            ["001366", "播恩集团", "9.99", "2", "2.66亿", "否", "涨停", "饲料、乡村振兴", "农业涨价", "饲料", "18.61"],
            ["002001", "新和成", "10.00", "3", "4.12亿", "否", "涨停", "合成生物、维生素", "医药上游", "合成生物", "32.10"],
        ]
    elif "炸板次数" in query or "回封次数" in query or "最后封板" in query:
        fields = ["代码", "名称", "涨跌幅", "连板(天)", "行业", "是否ST", "涨停", "涨停最终封板时间", "炸板次数(次)", "涨停回封次数(次)", "最新价", "成交额"]
        rows = [
            ["001366", "播恩集团", "9.99", "2", "饲料", "否", "涨停", "09:42:18", "0", "0", "18.61", "2.66亿"],
            ["002001", "新和成", "10.00", "3", "合成生物", "否", "涨停", "10:42:08", "1", "1", "32.10", "4.12亿"],
        ]
    elif "1分钟涨幅" in query:
        fields = ["代码", "名称", "涨跌幅", "连板(天)", "行业", "是否ST", "涨停", "区间涨跌幅(1分钟)@2026-05-26 09:39:00-2026-05-26 09:40:00", "最新价", "成交额"]
        rows = [
            ["001366", "播恩集团", "9.99", "2", "饲料", "否", "涨停", "0.90", "18.61", "2.66亿"],
            ["002001", "新和成", "10.00", "3", "合成生物", "否", "涨停", "-0.20", "32.10", "4.12亿"],
        ]
    elif "3分钟涨幅" in query:
        fields = ["代码", "名称", "涨跌幅", "连板(天)", "行业", "是否ST", "涨停", "区间涨跌幅(1分钟)@2026-05-26 09:37:00-2026-05-26 09:40:00", "最新价", "成交额"]
        rows = [
            ["001366", "播恩集团", "9.99", "2", "饲料", "否", "涨停", "2.30", "18.61", "2.66亿"],
            ["002001", "新和成", "10.00", "3", "合成生物", "否", "涨停", "0.80", "32.10", "4.12亿"],
        ]
    elif "10分钟涨幅" in query:
        fields = ["代码", "名称", "涨跌幅", "连板(天)", "行业", "是否ST", "涨停", "区间涨跌幅(1分钟)@2026-05-26 09:30:00-2026-05-26 09:40:00", "最新价", "成交额"]
        rows = [
            ["001366", "播恩集团", "9.99", "2", "饲料", "否", "涨停", "5.20", "18.61", "2.66亿"],
            ["002001", "新和成", "10.00", "3", "合成生物", "否", "涨停", "2.90", "32.10", "4.12亿"],
        ]
    elif "最大封单" in query:
        fields = ["代码", "名称", "涨跌幅", "连板(天)", "行业", "是否ST", "涨停", "最大封单金额", "最大封单量", "最新价", "成交额"]
        rows = [
            ["001366", "播恩集团", "9.99", "2", "饲料", "否", "涨停", "1.28亿", "688.00万", "18.61", "2.66亿"],
            ["002001", "新和成", "10.00", "3", "合成生物", "否", "涨停", "4200.00万", "230.00万", "32.10", "4.12亿"],
        ]
    elif "封单" in query or "首次涨停" in query:
        fields = ["代码", "名称", "涨跌幅", "连板(天)", "行业", "是否ST", "涨停", "涨停首次封板时间", "涨停封单额", "涨停封单量(股)", "涨停封成比", "最新价", "成交额"]
        rows = [
            ["001366", "播恩集团", "9.99", "2", "饲料", "否", "涨停", "09:42:18", "1.28亿", "688.00万", "1.65", "18.61", "2.66亿"],
            ["002001", "新和成", "10.00", "3", "合成生物", "否", "涨停", "10:22:31", "4200.00万", "230.00万", "0.82", "32.10", "4.12亿"],
        ]
    elif "资金" in query or "5分钟" in query:
        fields = ["代码", "名称", "涨跌幅", "连板(天)", "行业", "是否ST", "涨停", "区间涨跌幅(1分钟)@2026-05-26 09:35:00-2026-05-26 09:40:00", "主力净额", "最新价", "成交额"]
        rows = [
            ["001366", "播恩集团", "9.99", "2", "饲料", "否", "涨停", "2.10", "3000.00万", "18.61", "2.66亿"],
            ["002001", "新和成", "10.00", "3", "合成生物", "否", "涨停", "0.80", "-500.00万", "32.10", "4.12亿"],
        ]
    else:
        fields = ["代码", "名称", "涨跌幅", "连板(天)", "行业", "是否ST", "涨停", "最新价", "成交额"]
        rows = [
            ["001366", "播恩集团", "9.99", "2", "饲料", "否", "涨停", "18.61", "2.66亿"],
            ["002001", "新和成", "10.00", "3", "合成生物", "否", "涨停", "32.10", "4.12亿"],
        ]
    return {"code": 0, "message": "", "data": {"count": len(rows), "fields": fields, "list": rows}}


class FakeJvQuantClient:
    def query(self, query: str, page: int, sort_type: int, sort_key: str) -> dict:
        if "是否涨停@2026-05-23" in query and "行业" in query:
            fields = ["代码", "名称", "行业", "涨跌幅@2026-05-23", "涨停封单额@2026-05-23"]
            rows = [
                ["001366", "播恩集团", "饲料", "10.0", "8000.00万"],
                ["600001", "农业甲", "饲料", "10.0", "5000.00万"],
                ["603000", "人民网", "传媒", "9.99", "3000.00万"],
            ]
            return {"code": 0, "message": "", "data": {"count": len(rows), "fields": fields, "list": rows}}
        if "成交额@2026-05-25大于30亿" in query:
            fields = [
                "代码",
                "名称",
                "涨跌幅@2026-05-25",
                "收盘价@2026-05-25",
                "最高价@2026-05-25",
                "成交额@2026-05-25",
                "行业",
            ]
            rows = [
                ["300475", "香农芯创", "0.60", "38.40", "39.20", "42.00亿", "半导体"],
                ["002491", "通鼎互联", "-1.20", "6.40", "6.55", "32.00亿", "通信设备"],
            ]
            return {"code": 0, "message": "", "data": {"count": len(rows), "fields": fields, "list": rows}}
        if "是否涨停@2026-05-25" in query and "行业" in query and "涨跌幅@2026-05-25" in query:
            fields = [
                "代码",
                "名称",
                "涨跌幅@2026-05-25",
                "涨停首次封板时间@2026-05-25",
                "涨停封单额@2026-05-25",
                "涨停封单量@2026-05-25",
                "涨停封成比@2026-05-25",
                "收盘价@2026-05-25",
                "成交额@2026-05-25",
                "行业",
            ]
            rows = [
                ["001366", "播恩集团", "10.01", "09:42:18", "1.28亿", "688.00万", "1.65", "16.92", "2.66亿", "饲料"],
                ["002001", "新和成", "10.00", "10:22:31", "4200.00万", "230.00万", "0.82", "30.00", "4.12亿", "合成生物"],
                ["603000", "人民网", "9.98", "13:14:20", "3000.00万", "120.00万", "0.50", "24.00", "6.00亿", "传媒"],
            ]
            return {"code": 0, "message": "", "data": {"count": len(rows), "fields": fields, "list": rows}}
        if "是否涨停@2026-05-23" in query:
            fields = ["代码", "名称"]
            rows = [["002001", "新和成"]]
            return {"code": 0, "message": "", "data": {"count": len(rows), "fields": fields, "list": rows}}
        if "是否涨停@2026-05-25" in query and "涨跌幅@2026-05-26" in query:
            fields = [
                "代码",
                "名称",
                "涨跌幅@2026-05-26",
                "涨停首次封板时间@2026-05-26",
                "涨停封单额@2026-05-26",
                "涨停封单量@2026-05-26",
                "涨停封成比@2026-05-26",
                "收盘价@2026-05-26",
                "成交额@2026-05-26",
                "行业",
            ]
            rows = [
                ["001366", "播恩集团", "9.99", "09:42:18", "1.28亿", "688.00万", "1.65", "18.61", "2.66亿", "饲料"],
                ["002001", "新和成", "7.10", "10:22:31", "4200.00万", "230.00万", "0.82", "32.10", "4.12亿", "合成生物"],
            ]
            return {"code": 0, "message": "", "data": {"count": len(rows), "fields": fields, "list": rows}}
        elif "连板数大于1" in query:
            return _multi_board_payload(query)
        if "昨日涨停" in query:
            if "竞价" in query:
                fields = ["代码", "名称", "行业", "是否ST", "涨停", "集合竞价涨跌幅", "集合竞价成交额", "集合竞价换手率", "开盘价", "最新价", "成交额"]
                rows = [
                    ["001366", "播恩集团", "饲料", "否", "涨停", "3.20", "9200.00万", "1.80", "17.90", "18.61", "2.66亿"],
                    ["002001", "新和成", "合成生物", "否", "涨停", "1.10", "3100.00万", "0.70", "31.50", "32.10", "4.12亿"],
                ]
            elif "概念" in query or "题材" in query:
                fields = ["代码", "名称", "涨跌幅", "成交额", "是否ST", "涨停", "概念", "个股题材", "行业", "最新价"]
                rows = [
                    ["001366", "播恩集团", "9.99", "2.66亿", "否", "涨停", "饲料、乡村振兴", "农业涨价", "饲料", "18.61"],
                    ["002001", "新和成", "7.10", "4.12亿", "否", "涨停", "合成生物、维生素", "医药上游", "合成生物", "32.10"],
                ]
            elif "炸板次数" in query or "回封次数" in query or "最后封板" in query:
                fields = ["代码", "名称", "涨跌幅", "行业", "是否ST", "涨停", "涨停最终封板时间", "炸板次数(次)", "涨停回封次数(次)", "最新价", "成交额"]
                rows = [
                    ["001366", "播恩集团", "9.99", "饲料", "否", "涨停", "09:42:18", "0", "0", "18.61", "2.66亿"],
                    ["002001", "新和成", "7.10", "合成生物", "否", "涨停", "10:42:08", "1", "1", "32.10", "4.12亿"],
                ]
            elif "1分钟涨幅" in query:
                fields = ["代码", "名称", "涨跌幅", "行业", "是否ST", "涨停", "区间涨跌幅(1分钟)@2026-05-26 09:39:00-2026-05-26 09:40:00", "最新价", "成交额"]
                rows = [
                    ["001366", "播恩集团", "9.99", "饲料", "否", "涨停", "0.90", "18.61", "2.66亿"],
                    ["002001", "新和成", "7.10", "合成生物", "否", "涨停", "-0.20", "32.10", "4.12亿"],
                ]
            elif "3分钟涨幅" in query:
                fields = ["代码", "名称", "涨跌幅", "行业", "是否ST", "涨停", "区间涨跌幅(1分钟)@2026-05-26 09:37:00-2026-05-26 09:40:00", "最新价", "成交额"]
                rows = [
                    ["001366", "播恩集团", "9.99", "饲料", "否", "涨停", "2.30", "18.61", "2.66亿"],
                    ["002001", "新和成", "7.10", "合成生物", "否", "涨停", "0.80", "32.10", "4.12亿"],
                ]
            elif "10分钟涨幅" in query:
                fields = ["代码", "名称", "涨跌幅", "行业", "是否ST", "涨停", "区间涨跌幅(1分钟)@2026-05-26 09:30:00-2026-05-26 09:40:00", "最新价", "成交额"]
                rows = [
                    ["001366", "播恩集团", "9.99", "饲料", "否", "涨停", "5.20", "18.61", "2.66亿"],
                    ["002001", "新和成", "7.10", "合成生物", "否", "涨停", "2.90", "32.10", "4.12亿"],
                ]
            elif "封单" in query or "首次涨停" in query:
                fields = [
                    "代码",
                    "名称",
                    "涨跌幅",
                    "行业",
                    "是否ST",
                    "涨停",
                    "涨停首次封板时间",
                    "涨停封单额",
                    "涨停封单量(股)",
                    "涨停封成比",
                    "最新价",
                    "成交额",
                ]
                rows = [
                    ["001366", "播恩集团", "9.99", "饲料", "否", "涨停", "09:42:18", "1.28亿", "688.00万", "1.65", "18.61", "2.66亿"],
                    ["002001", "新和成", "7.10", "合成生物", "否", "涨停", "10:22:31", "4200.00万", "230.00万", "0.82", "32.10", "4.12亿"],
                ]
            elif "资金" in query or "5分钟" in query:
                fields = [
                    "代码",
                    "名称",
                    "涨跌幅",
                    "行业",
                    "是否ST",
                    "涨停",
                    "区间涨跌幅(1分钟)@2026-05-26 09:35:00-2026-05-26 09:40:00",
                    "主力净额",
                    "最新价",
                    "成交额",
                ]
                rows = [
                    ["001366", "播恩集团", "9.99", "饲料", "否", "涨停", "2.10", "3000.00万", "18.61", "2.66亿"],
                    ["002001", "新和成", "7.10", "合成生物", "否", "涨停", "0.80", "-500.00万", "32.10", "4.12亿"],
                ]
            else:
                fields = ["代码", "名称", "涨跌幅", "行业", "是否ST", "涨停", "最新价", "成交额"]
                rows = [
                    ["001366", "播恩集团", "9.99", "饲料", "否", "涨停", "18.61", "2.66亿"],
                    ["002001", "新和成", "7.10", "合成生物", "否", "涨停", "32.10", "4.12亿"],
                ]
        elif "今日涨停" in query:
            fields = [
                "代码",
                "名称",
                "涨跌幅",
                "行业",
                "是否ST",
                "涨停",
                "涨停首次封板时间",
                "涨停封单额",
                "涨停封单量(股)",
                "涨停封成比",
                "最新价",
                "成交额",
            ]
            rows = [
                ["001366", "播恩集团", "9.99", "饲料", "否", "涨停", "09:42:18", "1.28亿", "688.00万", "1.65", "18.61", "2.66亿"],
                ["002001", "新和成", "10.00", "合成生物", "否", "涨停", "10:22:31", "4200.00万", "230.00万", "0.82", "32.10", "4.12亿"],
            ]
        elif "炸板" in query:
            fields = ["代码", "名称", "涨跌幅", "行业", "是否ST", "炸板次数", "最新价", "成交额"]
            rows = [
                ["603278", "大业股份", "6.00", "通用设备", "否", "1", "14.14", "8.37亿"],
            ]
        else:
            fields = ["代码", "名称", "涨跌幅", "行业", "是否ST", "涨停", "最新价", "成交额"]
            rows = [["600839", "四川长虹", "-2.57", "黑色家电", "上交所主板", "否", "7.95", "6.47亿"]]

        return {
            "code": 0,
            "message": "",
            "data": {
                "count": len(rows),
                "fields": fields,
                "list": rows,
            },
        }

    def kline(self, code: str, cate: str, fq: str, type: str, limit: int) -> dict:
        if code == "000001" and type == "day":
            rows = [
                ["2026-05-23", "10.00", "10.10", "10.20", "9.90", "100", "100000", "3.0", "1.0", "0.10", "1.0"],
                ["2026-05-25", "10.10", "10.20", "10.30", "10.00", "100", "100000", "3.0", "1.0", "0.10", "1.0"],
                ["2026-05-26", "10.20", "10.30", "10.40", "10.10", "100", "100000", "3.0", "1.0", "0.10", "1.0"],
                ["2026-05-27", "10.30", "10.40", "10.50", "10.20", "100", "100000", "3.0", "1.0", "0.10", "1.0"],
            ]
        elif code == "001366" and type == "day":
            rows = [
                ["2026-05-18", "9.80", "10.00", "10.20", "9.70", "100", "6000000000", "5.0", "1.00", "0.10", "2.0"],
                ["2026-05-19", "10.00", "10.20", "10.30", "9.90", "100", "5800000000", "4.0", "2.00", "0.20", "2.1"],
                ["2026-05-20", "10.20", "10.40", "10.50", "10.10", "100", "6100000000", "4.0", "1.96", "0.20", "2.2"],
                ["2026-05-21", "10.40", "10.60", "10.70", "10.30", "100", "5900000000", "4.0", "1.92", "0.20", "2.3"],
                ["2026-05-22", "10.60", "10.80", "10.90", "10.50", "100", "6000000000", "4.0", "1.89", "0.20", "2.4"],
                ["2026-05-23", "10.80", "10.70", "10.90", "10.60", "100", "3000000000", "3.0", "-0.93", "-0.10", "1.8"],
                ["2026-05-25", "15.30", "16.92", "17.20", "15.20", "100", "266000000", "12.0", "10.01", "1.54", "3.0"],
                ["2026-05-26", "16.92", "18.61", "18.61", "16.80", "100", "266000000", "10.0", "9.99", "1.69", "2.0"],
                ["2026-05-27", "19.00", "20.47", "20.47", "18.80", "100", "300000000", "9.0", "9.99", "1.86", "2.2"],
            ]
        elif code == "002001" and type == "day":
            rows = [
                ["2026-05-26", "30.00", "32.10", "32.10", "29.90", "100", "412000000", "8.0", "7.10", "2.10", "1.8"],
                ["2026-05-27", "31.00", "31.80", "33.00", "30.50", "100", "280000000", "7.8", "-0.93", "-0.30", "1.5"],
            ]
        elif code == "603000" and type == "day":
            rows = [
                ["2026-05-18", "20.00", "20.10", "20.20", "19.90", "100", "800000000", "2.0", "0.50", "0.10", "1.0"],
                ["2026-05-19", "20.10", "20.20", "20.30", "20.00", "100", "850000000", "2.0", "0.50", "0.10", "1.0"],
                ["2026-05-20", "20.20", "20.30", "20.40", "20.10", "100", "820000000", "2.0", "0.50", "0.10", "1.0"],
                ["2026-05-21", "20.30", "20.40", "20.50", "20.20", "100", "810000000", "2.0", "0.49", "0.10", "1.0"],
                ["2026-05-22", "20.40", "20.50", "20.60", "20.30", "100", "830000000", "2.0", "0.49", "0.10", "1.0"],
                ["2026-05-23", "20.50", "20.40", "20.60", "20.30", "100", "900000000", "2.0", "-0.49", "-0.10", "1.0"],
                ["2026-05-25", "21.82", "24.00", "24.10", "21.80", "100", "600000000", "10.0", "9.98", "2.18", "1.2"],
            ]
        elif code == "300475" and type == "day":
            rows = [
                ["2026-05-11", "30.00", "30.50", "30.80", "29.80", "100", "6200000000", "3.0", "1.0", "0.30", "2.0"],
                ["2026-05-12", "30.50", "31.20", "31.40", "30.40", "100", "6400000000", "3.1", "2.3", "0.70", "2.1"],
                ["2026-05-13", "31.20", "32.00", "32.20", "31.00", "100", "6600000000", "3.2", "2.6", "0.80", "2.2"],
                ["2026-05-14", "32.00", "33.10", "33.30", "31.90", "100", "6900000000", "3.3", "3.4", "1.10", "2.3"],
                ["2026-05-15", "33.10", "34.00", "34.30", "32.80", "100", "7100000000", "3.4", "2.7", "0.90", "2.4"],
                ["2026-05-18", "34.00", "35.10", "35.30", "33.80", "100", "7300000000", "3.5", "3.2", "1.10", "2.5"],
                ["2026-05-19", "35.10", "36.20", "36.50", "35.00", "100", "7200000000", "3.6", "3.1", "1.10", "2.6"],
                ["2026-05-20", "36.20", "37.10", "37.40", "36.00", "100", "7000000000", "3.7", "2.5", "0.90", "2.7"],
                ["2026-05-21", "37.10", "38.00", "38.50", "36.90", "100", "6800000000", "3.8", "2.4", "0.90", "2.8"],
                ["2026-05-22", "38.00", "38.20", "38.40", "37.50", "100", "6500000000", "3.9", "0.5", "0.20", "2.9"],
                ["2026-05-25", "38.20", "38.40", "39.20", "37.80", "100", "4200000000", "4.0", "0.6", "0.20", "3.0"],
            ]
        elif code == "002491" and type == "day":
            rows = [
                ["2026-05-11", "5.50", "5.60", "5.70", "5.40", "100", "5200000000", "3.0", "1.0", "0.10", "2.0"],
                ["2026-05-12", "5.60", "5.70", "5.80", "5.50", "100", "5300000000", "3.1", "1.8", "0.10", "2.1"],
                ["2026-05-13", "5.70", "5.85", "5.90", "5.65", "100", "5400000000", "3.2", "2.6", "0.15", "2.2"],
                ["2026-05-14", "5.85", "6.00", "6.10", "5.80", "100", "5600000000", "3.3", "2.6", "0.15", "2.3"],
                ["2026-05-15", "6.00", "6.15", "6.20", "5.95", "100", "5800000000", "3.4", "2.5", "0.15", "2.4"],
                ["2026-05-18", "6.15", "6.30", "6.35", "6.05", "100", "5900000000", "3.5", "2.4", "0.15", "2.5"],
                ["2026-05-19", "6.30", "6.45", "6.50", "6.25", "100", "5700000000", "3.6", "2.4", "0.15", "2.6"],
                ["2026-05-20", "6.45", "6.60", "6.70", "6.40", "100", "5500000000", "3.7", "2.3", "0.15", "2.7"],
                ["2026-05-21", "6.60", "6.70", "6.80", "6.55", "100", "5300000000", "3.8", "1.5", "0.10", "2.8"],
                ["2026-05-22", "6.70", "6.50", "6.90", "6.45", "100", "5100000000", "3.9", "-3.0", "-0.20", "2.9"],
                ["2026-05-25", "6.50", "6.40", "6.55", "6.30", "100", "3200000000", "4.0", "-1.2", "-0.10", "3.0"],
            ]
        else:
            rows = [
                [
                    "2026-05-26",
                    "1285.35",
                    "1273.38",
                    "1289.89",
                    "1270.01",
                    "45932",
                    "5867830633",
                    "1.55",
                    "-0.97",
                    "-12.5",
                    "0.37",
                ]
            ]
        return {
            "code": code,
            "message": "",
            "data": {
                "code": code,
                "name": "贵州茅台",
                "type": type,
                "fq": fq,
                "fields": ["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额", "振幅", "涨跌幅", "涨跌额", "换手率"],
                "list": rows,
            },
        }

    def level_queue(self, code: str) -> dict:
        return {
            "code": code,
            "message": "",
            "data": {
                "code": code,
                "count": 4,
                "fields": ["S2", "S1", "B1", "B2"],
                "list": [
                    {
                        "type": "S2",
                        "price": 1306.5,
                        "volume_count": 1200,
                        "queue_count": 3,
                        "queue_slice": "100,200,900",
                    },
                    {
                        "type": "S1",
                        "price": 1306.0,
                        "volume_count": 3300,
                        "queue_count": 23,
                        "queue_slice": "100,100,100",
                    },
                    {
                        "type": "B1",
                        "price": 1305.5,
                        "volume_count": 2500,
                        "queue_count": 18,
                        "queue_slice": "100,300,500",
                    },
                    {
                        "type": "B2",
                        "price": 1305.0,
                        "volume_count": 900,
                        "queue_count": 6,
                        "queue_slice": "100,200,600",
                    },
                ],
            },
        }

    def minute(self, code: str, end_day: str, limit: int) -> dict:
        return {
            "code": 0,
            "cnt": 1,
            "msg": "",
            "data": {
                "code": code,
                "start": "2026-05-26",
                "end": "2026-05-26",
                "count": 1,
                "days": ["2026-05-26"],
                "fields": ["时间", "最新价", "均价", "成交量"],
                "list": [
                    {
                        "date": "2026-05-26",
                        "last_price": 16.92,
                        "list": [
                            ["09:30", 17.30, 17.30, 100000],
                            ["09:31", 17.70, 17.50, 150000],
                            ["09:32", 17.82, 17.62, 160000],
                            ["09:33", 18.00, 17.75, 170000],
                            ["09:34", 18.18, 17.91, 190000],
                            ["09:35", 18.61, 18.05, 230000],
                        ],
                    }
                ],
            },
        }


def test_normalize_symbol_for_jvquant() -> None:
    assert normalize_symbol("600519.SH") == "600519"
    assert normalize_symbol("000001.sz") == "000001"


def test_jvquant_realtime_snapshot_from_fake_client() -> None:
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    snapshot = adapter.get_stock_realtime_snapshot("600519.SH")

    assert snapshot.data_mode == "live_provider"
    assert snapshot.provider == "jvQuant"
    assert snapshot.name == "贵州茅台"
    assert snapshot.last_price == 1273.38
    assert snapshot.change_pct == -0.97
    assert snapshot.turnover_cny == 5867830633
    assert snapshot.bid_quality_score > 0


def test_jvquant_orderbook_snapshot_from_fake_client() -> None:
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    snapshot = adapter.get_stock_orderbook_snapshot("600519.SH")

    assert snapshot.data_mode == "live_provider"
    assert snapshot.provider == "jvQuant"
    assert snapshot.level_count == 4
    assert snapshot.best_bid_price == 1305.5
    assert snapshot.best_ask_price == 1306.0
    assert len(snapshot.bid_levels) == 2
    assert len(snapshot.ask_levels) == 2


def test_jvquant_minute_replay_snapshot_from_fake_client() -> None:
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    snapshot = adapter.get_stock_minute_replay_snapshot("001366.SZ", end_day="2026-05-26", limit_days=1)

    assert snapshot.data_mode == "minute_replay"
    assert snapshot.provider == "jvQuant"
    assert snapshot.trading_day == "2026-05-26"
    assert snapshot.timestamp == "2026-05-26T09:35:00+08:00"
    assert snapshot.minute_count == 6
    assert snapshot.speed_pct_by_window["1m"] == 2.3652
    assert snapshot.speed_pct_by_window["5m"] == 7.5723
    assert snapshot.speed_window_by_window["5m"] == (
        "minute_replay_exact_window:2026-05-26 09:30:00-2026-05-26 09:35:00"
    )


def test_jvquant_market_gate_from_semantic_query() -> None:
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    snapshot = adapter.get_market_snapshot()
    gate = adapter.get_market_sentiment_gate()
    limitup_pool = adapter.get_limitup_pool()
    break_pool = adapter.get_break_board_pool()

    assert snapshot.data_mode == "live_provider"
    assert snapshot.provider == "jvQuant"
    assert snapshot.limit_up_count == 2
    assert snapshot.break_board_count == 1
    assert snapshot.break_board_rate == 0.3333
    assert snapshot.leading_themes
    assert gate.data_mode == "live_provider"
    assert 0.0 <= gate.break_board_rate <= 1.0
    assert isinstance(gate.risk_flags, list) and gate.risk_flags
    assert limitup_pool[0].data_mode == "live_provider"
    assert limitup_pool[0].status == "sealed"
    assert limitup_pool[0].first_limit_up_time == "09:42:18"
    assert limitup_pool[0].seal_amount_cny == 128_000_000
    assert break_pool[0].current_change_pct == 6.0


def test_jvquant_second_board_candidates_use_minute_replay_when_available() -> None:
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    candidates = adapter.get_second_board_candidates()
    explanation = adapter.explain_second_board_candidate(candidates[0].symbol)

    assert candidates
    assert candidates[0].symbol == "001366"
    assert candidates[0].data_mode == "live_provider"
    assert candidates[0].provider == "jvQuant"
    assert candidates[0].current_change_pct == 9.99
    assert candidates[0].auction_change_pct == 3.20
    assert candidates[0].auction_turnover_cny == 92_000_000
    assert candidates[0].auction_turnover_rate == 1.80
    assert candidates[0].five_min_speed_pct == 7.5723
    assert candidates[0].five_min_speed_window == "minute_replay_exact_window:2026-05-26 09:30:00-2026-05-26 09:35:00"
    assert candidates[0].five_min_speed_timestamp == "2026-05-26T09:35:00+08:00"
    assert candidates[0].minute_replay_trading_day == "2026-05-26"
    assert candidates[0].minute_replay_bar_count == 6
    assert candidates[0].one_min_speed_pct == 2.3652
    assert candidates[0].three_min_speed_pct == 4.4332
    assert candidates[0].ten_min_speed_pct == 7.5723
    assert candidates[0].big_order_net_inflow_ratio > 0
    assert candidates[0].concept_tags == ["饲料", "乡村振兴"]
    assert candidates[0].topic_tags == ["农业涨价"]
    assert candidates[0].break_board_count == 0
    assert candidates[0].reseal_count == 0
    assert candidates[0].final_seal_time == "09:42:18"
    assert candidates[0].max_seal_amount_cny == 128_000_000
    assert candidates[0].data_quality["five_min_speed"].source == "jvquant.minute_replay"
    assert candidates[0].data_quality["five_min_speed"].confidence == "high"
    assert candidates[0].data_quality["auction_metrics"].usable_for_grading is True
    assert candidates[0].data_quality["theme_tags"].usable_for_grading is True
    assert candidates[0].data_quality["break_reseal_metrics"].usable_for_grading is True
    assert candidates[0].data_quality["multi_speed"].usable_for_grading is True
    assert {item.authority for item in candidates[0].data_quality["five_min_speed"].evidence} == {
        "official_doc",
        "internal_inference",
    }
    assert any(
        item.authority == "internal_inference"
        for item in candidates[0].data_quality["seal_metrics"].evidence
    )
    assert candidates[0].data_quality["history_stats"].usable_for_grading is False
    assert candidates[0].first_limit_up_time == "09:42:18"
    assert candidates[0].seal_amount_cny == 128_000_000
    assert candidates[0].seal_volume_shares == 6_880_000
    assert candidates[0].seal_to_turnover_ratio == 1.65
    assert "Own-order queue position unavailable" in candidates[0].queue_position_note
    assert candidates[0].same_theme_rising_count >= 1
    assert any("Five-minute speed window" in observation for observation in explanation.observations)
    assert "not investment advice" in explanation.disclaimer.lower()


def test_jvquant_second_board_candidates_can_fallback_to_semantic_speed(monkeypatch) -> None:
    monkeypatch.setenv("AEGIS_ALPHA_ENABLE_MINUTE_REPLAY", "false")
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    candidates = adapter.get_second_board_candidates()

    assert candidates[0].five_min_speed_pct == 2.10
    assert candidates[0].five_min_speed_window == "provider_exact_window:2026-05-26 09:35:00-2026-05-26 09:40:00"
    assert candidates[0].five_min_speed_timestamp == "2026-05-26T09:40:00+08:00"
    assert candidates[0].data_quality["five_min_speed"].source == "jvquant.semantic_query"
    assert {item.authority for item in candidates[0].data_quality["five_min_speed"].evidence} == {
        "official_doc",
        "observed_probe",
        "internal_inference",
    }


def test_jvquant_historical_second_board_candidates_from_fake_client() -> None:
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    rows = adapter.get_historical_second_board_candidates("2026-05-26", limit=5)

    assert len(rows) == 2
    assert rows[0]["symbol"] == "001366"
    assert rows[0]["prev_day"] == "2026-05-25"
    assert rows[0]["next_day"] == "2026-05-27"
    assert rows[0]["data_mode"] == "historical_provider"
    assert rows[0]["seal_amount_cny"] == 128_000_000
    assert rows[0]["seal_volume_shares"] == 6_880_000
    assert rows[0]["turnover_cny"] == 266_000_000
    assert "promotion_grade" not in rows[0]
    assert "promotion_likelihood" not in rows[0]


def test_jvquant_historical_first_board_watchlist_from_fake_client() -> None:
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    rows = adapter.get_historical_first_board_watchlist("2026-05-25", limit=5)

    assert len(rows) == 2
    assert rows[0]["symbol"] == "001366"
    assert rows[0]["as_of_day"] == "2026-05-25"
    assert rows[0]["prev_day"] == "2026-05-23"
    assert rows[0]["target_second_board_day"] == "2026-05-26"
    assert rows[0]["previous_day_limit_up"] is False
    assert rows[0]["first_board_confirmed"] is True
    assert rows[0]["seal_amount_cny"] == 128_000_000
    assert "涨跌幅@2026-05-26" not in rows[0]["query"]
    assert "promotion_grade" not in rows[0]
    assert "promotion_likelihood" not in rows[0]


def test_jvquant_strategy_watchlist_from_fake_client() -> None:
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    rows = adapter.get_strategy_watchlist("2026-05-25", limit=5)

    assert len(rows) == 3
    by_symbol = {row["symbol"]: row for row in rows}
    assert set(by_symbol) == {"001366", "300475", "002491"}
    first = rows[0]
    assert first["symbol"] == "001366"
    assert first["target_second_board_day"] == "2026-05-26"
    assert first["candidate_sources"] == ["first_board_watchlist"]
    assert first["strategy_data_mode"] == "historical_provider"
    assert first["avg_turnover_10d_cny"] > 5_000_000_000
    assert first["avg_turnover_10d_pass"] is True
    assert first["prev_day_shrink"] is True
    assert first["as_of_high_broke_previous_high"] is True
    assert first["strategy_filter_pass"] is True
    assert "ma5_slope_degrees" not in first
    assert "ma5_slope" not in first["strategy_coverage"]
    assert "涨跌幅@2026-05-26" not in first["query"]
    assert first["strategy_coverage"]["theme_two_week_continuity"] is True
    assert first["theme_continuity"]["theme"] == "饲料"
    assert first["theme_continuity"]["active_days"] >= 1
    assert first["theme_continuity"]["off_platform_news_checked"] is False
    assert by_symbol["300475"]["candidate_sources"] == ["large_turnover_trend_seed"]
    assert by_symbol["300475"]["avg_turnover_10d_pass"] is True
    assert by_symbol["300475"]["prev_day_shrink"] is True
    assert by_symbol["300475"]["as_of_high_broke_previous_high"] is True
    assert by_symbol["002491"]["candidate_sources"] == ["large_turnover_trend_seed"]
    assert by_symbol["002491"]["avg_turnover_10d_pass"] is True
    assert by_symbol["002491"]["prev_day_shrink"] is True
    assert "promotion_grade" not in first
    assert "promotion_likelihood" not in first


def test_jvquant_strategy_watchlist_allows_missing_next_day_for_current_prepare() -> None:
    class NoNextClient(FakeJvQuantClient):
        def query(self, query: str, page: int, sort_type: int, sort_key: str) -> dict:
            if "成交额大于30亿" in query and "@" not in query:
                fields = [
                    "代码",
                    "名称",
                    "涨跌幅2026-05-27",
                    "收盘价(日线不复权)2026-05-27",
                    "成交额2026-05-27",
                    "行业分类二级",
                ]
                rows = [["300475", "香农芯创", "2.1", "42.00", "45.00亿", "半导体"]]
                return {"code": 0, "message": "", "data": {"count": len(rows), "fields": fields, "list": rows}}
            return super().query(query, page, sort_type, sort_key)

        def kline(self, code: str, cate: str, fq: str, type: str, limit: int) -> dict:
            payload = super().kline(code, cate, fq, type, limit)
            if code == "000001" and type == "day":
                payload["data"]["list"] = [
                    row for row in payload["data"]["list"] if row[0] <= "2026-05-27"
                ]
            if code == "300475" and type == "day":
                payload["data"]["list"] = [
                    *payload["data"]["list"],
                    ["2026-05-26", "38.40", "41.00", "41.50", "38.00", "100", "4400000000", "4.0", "6.8", "2.60", "3.0"],
                    ["2026-05-27", "41.00", "42.00", "42.50", "40.50", "100", "4500000000", "4.0", "2.1", "1.00", "3.0"],
                ]
            return payload

    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = NoNextClient()

    rows = adapter.get_strategy_watchlist("2026-05-27", limit=5)

    assert rows
    assert rows[0]["symbol"] == "300475"
    assert rows[0]["target_second_board_day"] == ""
    assert rows[0]["data_mode"] == "current_provider_as_of"
    assert rows[0]["strategy_filter_pass"] is True


def test_jvquant_theme_continuity_from_fake_client() -> None:
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    result = adapter.get_theme_continuity("饲料", "2026-05-25", lookback_days=14)

    assert result["theme"] == "饲料"
    assert result["data_mode"] == "historical_provider"
    assert result["active_days"] >= 2
    assert result["burst_days"] >= 1
    assert result["off_platform_news_checked"] is False
    assert result["cls_news_checked"] is False
    assert "continuity_label" in result


def test_jvquant_historical_strategy_replay_from_fake_client() -> None:
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    result = adapter.run_historical_strategy_replay(
        "2026-05-25",
        "2026-05-26",
        symbols=["001366"],
        limit=5,
    )

    assert result["as_of_day"] == "2026-05-25"
    assert result["target_day"] == "2026-05-26"
    assert result["data_mode"] == "historical_replay"
    assert result["result_count"] == 1
    item = result["results"][0]
    assert item["symbol"] == "001366"
    assert item["previous_high_price"] > 0
    assert item["minute_count_replayed"] >= 1
    assert "signals" in item
    assert item["pattern_diagnostics"]["crossed_previous_high"] in {True, False}
    assert "no_signal_reason" in item["pattern_diagnostics"]
    assert "sealed_next_day" not in item
    assert any("Level-2" in gap for gap in item["data_gaps"])


def test_jvquant_intraday_orderflow_confirmation_returns_daily_proxy() -> None:
    adapter = JvQuantMarketDataAdapter(token="fake")

    class FakeCapitalFlowClient:
        def query(self, query: str, page: int, sort_type: int, sort_key: str) -> dict:  # noqa: ARG002
            fields = [
                "代码", "名称", "涨跌幅2026-06-18", "成交额2026-06-18",
                "主力净额2026-06-18", "超大单净额2026-06-18",
                "大单净额2026-06-18", "中单净额2026-06-18",
                "小单净额2026-06-18",
            ]
            rows = [[
                "002281", "光迅科技", "5.31", "100.00亿",
                "3.00亿", "1.20亿", "0.80亿", "-0.50亿", "-2.50亿",
            ]]
            return {"code": 0, "message": "", "data": {"count": len(rows), "fields": fields, "list": rows}}

    adapter._client = FakeCapitalFlowClient()
    result = adapter.get_intraday_orderflow_confirmation(
        "002281",
        trading_day="2026-06-18",
        trigger_time="09:41",
        window_start="09:31",
        window_end="10:00",
    )

    assert result["data_mode"] == "historical_orderflow_proxy"
    assert result["historical_big_order_buy_ratio_available"] is False
    assert result["big_order_buy_ratio"] is None
    assert result["realtime_orderflow_capability"]["lv2_large_trade_proxy_available"] is True
    assert result["realtime_orderflow_capability"]["active_trade_side_available"] is False
    assert result["realtime_orderflow_capability"]["can_compute_big_order_buy_ratio"] is False
    assert result["daily_capital_flow_available"] is True
    assert result["daily_capital_flow"]["big_order_net_inflow_cny"] == 200_000_000.0
    assert result["daily_capital_flow"]["big_order_net_inflow_ratio"] == 0.02
    assert result["daily_capital_flow"]["main_capital_net_inflow_ratio"] == 0.03
    assert result["daily_capital_flow"]["direction"] == "positive"
    assert any("daily net inflow" in note for note in result["notes"])


def test_jvquant_intraday_orderflow_confirmation_falls_back_to_dated_fields() -> None:
    adapter = JvQuantMarketDataAdapter(token="fake")

    class FakeDatedCapitalFlowClient:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def query(self, query: str, page: int, sort_type: int, sort_key: str) -> dict:  # noqa: ARG002
            self.queries.append(query)
            if "主力净额2026-06-18" not in query:
                return {"code": 0, "message": "", "data": {"count": 0, "fields": [], "list": []}}
            fields = [
                "代码", "名称", "涨跌幅2026-06-18", "成交额2026-06-18",
                "主力净额2026-06-18", "超大单净额2026-06-18",
                "大单净额2026-06-18", "中单净额2026-06-18",
                "小单净额2026-06-18",
            ]
            rows = [[
                "002281", "光迅科技", "10.00", "104.78亿",
                "14.22亿", "15.03亿", "-8158.70万", "-7.46亿", "-6.75亿",
            ]]
            return {"code": 0, "message": "", "data": {"count": len(rows), "fields": fields, "list": rows}}

    fake_client = FakeDatedCapitalFlowClient()
    adapter._client = fake_client
    result = adapter.get_intraday_orderflow_confirmation("002281", trading_day="2026-06-18")

    assert len(fake_client.queries) == 2
    assert result["daily_capital_flow_available"] is True
    assert result["daily_capital_flow"]["big_order_net_inflow_ratio"] == 0.1357
    assert result["daily_capital_flow"]["direction"] == "positive"


def test_intraday_theme_copump_counts_same_theme_peers_by_trigger_time() -> None:
    from aegis_alpha.adapters.jvquant.adapter import _intraday_theme_copump

    day_results = [
        {
            "symbol": "000001",
            "theme": "通信设备",
            "first_triggered_at": "09:40",
            "pattern_diagnostics": {
                "first_cross_time": "09:33",
                "opening_window_cross_time": "09:32",
            },
        },
        {
            "symbol": "000002",
            "theme": "通信设备",
            "first_triggered_at": "09:38",
            "pattern_diagnostics": {
                "first_cross_time": "09:34",
                "opening_window_cross_time": "",
            },
        },
        {
            "symbol": "000003",
            "theme": "通信设备",
            "first_triggered_at": "09:50",
            "pattern_diagnostics": {
                "first_cross_time": "09:35",
                "opening_window_cross_time": "",
            },
        },
        {
            "symbol": "000004",
            "theme": "半导体",
            "first_triggered_at": "09:35",
            "pattern_diagnostics": {
                "first_cross_time": "09:32",
                "opening_window_cross_time": "09:31",
            },
        },
    ]

    result = _intraday_theme_copump(day_results[0], day_results, triggered_at="09:40")

    assert result["same_theme_candidate_count"] == 2
    assert result["crossed_previous_high_by_trigger_count"] == 2
    assert result["triggered_by_trigger_count"] == 1
    assert result["opening_breakout_by_trigger_count"] == 0
    assert result["crossed_symbols"] == ["000002", "000003"]
    assert result["triggered_symbols"] == ["000002"]


def test_jvquant_second_board_next_day_outcomes_from_fake_client() -> None:
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    result = adapter.get_second_board_next_day_outcomes("2026-05-26", symbols=["001366", "002001"])

    assert result["trading_day"] == "2026-05-26"
    assert result["next_day"] == "2026-05-27"
    assert result["data_mode"] == "historical_provider"
    by_symbol = {item["symbol"]: item for item in result["outcomes"]}
    assert by_symbol["001366"]["ok"] is True
    assert by_symbol["001366"]["next_day_high_pct"] == 9.99
    assert by_symbol["001366"]["touched_limit_up"] is True
    assert by_symbol["001366"]["sealed_next_day"] is True
    assert by_symbol["002001"]["next_day_high_pct"] == 2.8
    assert by_symbol["002001"]["touched_limit_up"] is False


def test_inferred_change_pct_sh_main() -> None:
    assert _inferred_change_pct_for_limit_up("600519") == 10.0


def test_inferred_change_pct_sz_main() -> None:
    assert _inferred_change_pct_for_limit_up("000001") == 10.0


def test_inferred_change_pct_star_board() -> None:
    assert _inferred_change_pct_for_limit_up("688981") == 20.0


def test_inferred_change_pct_chinext() -> None:
    assert _inferred_change_pct_for_limit_up("300750") == 20.0


def test_inferred_change_pct_bse() -> None:
    assert _inferred_change_pct_for_limit_up("830799") == 30.0


def test_time_or_unknown_normalizes_short_form() -> None:
    from aegis_alpha.adapters.jvquant.parsers import _time_or_unknown

    assert _time_or_unknown("9:45") == "09:45:00"
    assert _time_or_unknown("9:45:30") == "09:45:30"
    assert _time_or_unknown("09:45") == "09:45:00"
    assert _time_or_unknown("09:45:30") == "09:45:30"
    assert _time_or_unknown("2026-05-29 9:45:30") == "09:45:30"
    assert _time_or_unknown("2026-05-29T09:45:30+08:00") == "09:45:30"
    assert _time_or_unknown("") == "unknown"
    assert _time_or_unknown("None") == "unknown"
    assert _time_or_unknown("nan") == "unknown"
    assert _time_or_unknown("garbage") == "unknown"


@pytest.mark.skip(reason="grade-remap backtest re-homed to Phase 7; scoring.py + grading.py deleted in 1A.4/1D.3")
def test_seal_quality_score_uses_normalized_time() -> None:
    # Body removed: seal_quality_score (scoring.py) and CandidateGradingConfig (grading.py)
    # were deleted when program grading was removed. The program no longer computes a
    # seal-quality score; the AI agent judges. No replacement test — this stays skipped.
    pass
