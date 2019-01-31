#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function, absolute_import, unicode_literals, division
import numpy as np
import datetime
from etasdk import *

"""
期货日内交易
Dual-Trust策略概述：
==================
在Dual Thrust 交易系统中，对于震荡区间的定义非常关键，这也是该交易系统的核心。Dual Thrust在Range
的设置上，引入前N 日的四个价位，Range = Max(HH-LC,HC-LL)来描述震荡区间的大小。其中HH 是N 日High
的最高价，LC 是N 日Close 的最低价，HC 是N 日Close 的最高价，LL 是N 日Low 的最低价。这种方法使得一
定时期内的Range 相对稳定，可以适用于日间的趋势跟踪。Dual Thrust 对于多头和空头的触发条件，考虑了非
对称的幅度，做多和做空参考的Range可以选择不同的周期数，也可以通过参数K1 和K2 来确定。

第一步：计算相关参数，得到上轨Buy_line 和下轨Sell_line：
1、N 日High 的最高价HH, N 日Close 的最低价LC;
2、N 日Close 的最高价HC，N 日Low 的最低价LL;
3、Range = Max(HH-LC,HC-LL)；
4、BuyLine = Open + K1*Range；
5、SellLine = Open + K2*Range；

第二步：交易逻辑
1、当价格向上突破上轨时，如果当时持有空仓，则先平仓，再开多仓；如果没有仓位，则直接开多仓；
2、当价格向下突破下轨时，如果当时持有多仓，则先平仓，再开空仓；如果没有仓位，则直接开空仓；

第三步：止损
1、初始止损
2、入场后跟踪止损
3、出现反向信号止损开反向仓位
4、在收盘前1分钟平仓（14:58）
5、每日最多交易次数2次，多空各一次


回测数据为:ruZ0.CF主力合约的的1min数据
回测时间为:2018-10-8 到2018-10-18

"""


def onInitialize(api):
    # 设置响应模式
    api.setGroupMode(5000, False)
    api.focused_contracts = "ruZ0.CF"
    api.threshold = 0.015
    api.percent = 0.035
    api.k = 0.65
    api.focused_prd = str(api.focused_contracts.replace("Z0.CF", ".PRD"))
    api.setRequireData(instsets=api.focused_prd, symbols=api.focused_contracts, fields=[],
                       bars=[(ETimeSpan.DAY_1, 10), (ETimeSpan.MIN_1, 130)])

    # 初始资金和数据测试
    account = api.getAccount(symbol=api.focused_contracts, market=MARKET_CHINAFUTURE)
    api.capital = account.cashAvailable  # 账户初始资金


def onBeforeMarketOpen(api, trade_date):
    # print(trade_date)
    api.trading_day = trade_date
    api.bars_since_today = 0
    api.lots = 1
    api.can_trade = False
    api.long_can_trade = True
    api.short_can_trade = True
    api.code = api.getContinuousSymbol(api.focused_contracts, trade_date)
    api.history_range, normalize_tr, last_close = get_history_range(api, api.code)

    # 订阅合约
    if normalize_tr > api.threshold:
        api.setFocusSymbols(api.code)
        api.can_trade = True
        multiply = get_multiply(api, api.focused_contracts)
        api.lots = int(1000000 / (last_close * multiply))
    # print("api.can_trade:", api.can_trade)


def onBar(api, bar):
    if api.can_trade:
        time_now = datetime.datetime.fromtimestamp(api.timeNow() / 1000)
        api.bars_since_today += 1
        bars = api.getBarsHistory(symbol=bar.symbol, timeSpan=ETimeSpan.MIN_1, count=api.bars_since_today,
                                  priceMode=EPriceMode.REAL, fields=None, df=True)
        # print("time_now:", time_now)
        today_open = bars['open'].values[0]
        buy_line, sell_line = get_buy_and_sell_lines(today_open=today_open, history_range=api.history_range,
                                                     k1=api.k, k2=api.k)

        position_side = get_position_side(api, bar.symbol)

        if position_side <= 0 and bar.high > buy_line and api.long_can_trade:
            api.targetPosition(symbol=bar.symbol, qty=0, positionSide=EPositionSide.SHORT,
                               remark="Reverse!")
            api.targetPosition(symbol=bar.symbol, qty=api.lots, positionSide=EPositionSide.LONG,
                               remark="Entry LONG!")
            api.long_can_trade = False
        if position_side >= 0 and bar.low < sell_line and api.short_can_trade:
            api.targetPosition(symbol=bar.symbol, qty=0, positionSide=EPositionSide.LONG,
                               remark="Reverse!")
            api.targetPosition(symbol=bar.symbol, qty=api.lots, positionSide=EPositionSide.SHORT,
                               remark="Entry Short!")
            api.short_can_trade = False

        if position_side > 0:
            symbol_position = api.getSymbolPosition(symbol=bar.symbol, positionSide=EPositionSide.LONG)
            if bar.low <= symbol_position.posHigh * (1 - api.percent):
                api.targetPosition(symbol=bar.symbol, qty=0, positionSide=EPositionSide.LONG,
                                   remark="Long Liquid!")
        if position_side < 0:
            symbol_position = api.getSymbolPosition(symbol=bar.symbol, positionSide=EPositionSide.SHORT)
            if bar.high >= symbol_position.posLow * (1 + api.percent):
                api.targetPosition(symbol=bar.symbol, qty=0, positionSide=EPositionSide.SHORT,
                                   remark="Short Liquid!")

        if time_now.hour == 14 and time_now.minute == 59:
            api.targetPosition(symbol=bar.symbol, qty=0, positionSide=EPositionSide.SHORT,
                               remark="Closing the market, Exit Short!")
            api.targetPosition(symbol=bar.symbol, qty=0, positionSide=EPositionSide.LONG,
                               remark="Closing the market, Exit LONG!")


def onTerminate(api, exit_info):
    print("Finished test")


def get_history_range(api, symbol, look_back=5):
    """
    每次开盘之前进行判断：
    获取过去N个交易日的最高价HH，最低价LL，最高收盘价HC，最低收盘价
    """
    str_fields = ['tradeDate', 'open', 'high', 'low', 'close']
    str_index = 'tradeDate'
    bars = api.getBarsHistory(symbol=symbol, timeSpan=ETimeSpan.DAY_1, skipSuspended=1, count=look_back,
                              df=True, priceMode=EPriceMode.REAL, fields=str_fields).set_index(str_index)
    if len(bars) < look_back:
        print("%s lack of data:", symbol)
        history_range = 0
        normalize_tr = 0
        last_close = float("inf")
    else:
        highs = bars['high'].values
        lows = bars['low'].values
        closes = bars['close'].values
        highest_high = np.max(highs)
        lowest_low = np.min(lows)
        highest_close = np.max(closes)
        lowest_close = np.min(closes)
        history_range = np.max([highest_high - lowest_close, highest_close - lowest_low])
        true_range = np.max([highs[-1] - lows[-1], abs(highs[-1] - closes[-2]), abs(closes[-2] - lows[-1])])
        last_close = closes[-1]
        normalize_tr = true_range / last_close

    return history_range, normalize_tr, last_close


def get_buy_and_sell_lines(today_open, history_range, k1=0.45, k2=0.55):
    """计算买入开仓价上轨和卖出开仓价下轨
    BuyLine = today_open + K1*Range
    SellLine = today_open + K2*Range
    """
    buy_line = today_open + k1 * history_range
    sell_line = today_open - k2 * history_range
    return buy_line, sell_line


def get_position_side(api, symbol):
    """
    通过API获取给定合约的持仓方向及数量
    1持仓为多单，-1持仓为空单，等于0表明当前没有持仓
    """
    long_position = int(api.getSymbolPosition(symbol, EPositionSide.LONG).posQty)
    short_position = int(api.getSymbolPosition(symbol, EPositionSide.SHORT).posQty)
    position_side = 0
    if long_position:
        position_side = 1
    if short_position:
        position_side = -1
    return position_side


def get_multiply(api, symbol):
    """
    获取给定合约的合约价值和最小变动价格
    """
    ref_data = api.getRefData(str(symbol))
    multiplier = ref_data.valuePerUnit
    return multiplier
