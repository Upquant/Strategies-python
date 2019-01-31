#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals

import sys
import numpy as np

try:
    import talib
except:
    print('请安装TA-Lib库')
    sys.exit(-1)
from etasdk import *

'''
期货策略：海龟交易法
本策略通过计算FG801.CF和rb1801.CF的ATR.唐奇安通道和MA线,
-- 当价格上穿唐奇安通道且短MA在长MA上方时开多仓;
-- 当价格下穿唐奇安通道且短MA在长MA下方时开空仓(8手)
若有多仓则在价格跌破唐奇安平仓通道下轨的时候全平仓位,否则根据跌破
持仓均价 - x(x=0.5,1,1.5,2)倍ATR把仓位平至6/4/2/0手
若有空仓则在价格涨破唐奇安平仓通道上轨的时候全平仓位,否则根据涨破
持仓均价 + x(x=0.5,1,1.5,2)倍ATR把仓位平至6/4/2/0手
撮合周期为:1分钟
回测时间为:2017-09-15 到2017-10-01
'''

def onInitialize(api):
    print("analyzer initialize")
    # 设置响应模式
    api.setGroupMode(5000, False)
    # 设置关注的合约标的
    api.tickersCode = ["FG1801.CF", "rb1801.CF"]

    # api.parameter 分别为唐奇安开仓通道.唐奇安平仓通道.短ma.长ma.ATR的参数
    api.parameter = [55, 20, 10, 60, 20]
    api.tar = api.parameter[4]

    api.data_len = 600

    api.setSymbolPool(symbols=api.tickersCode)
    api.setRequireBars(ETimeSpan.MIN_1, api.data_len)


def onBeforeMarketOpen(api, tradeDate):
    # print(tradeDate)
    api.trading_day = tradeDate
    # 订阅行情
    api.setFocusSymbols(api.tickersCode)


def onBar(api, bar):
    bar_data = api.getBarsHistory(symbol=bar.symbol, timeSpan=ETimeSpan.MIN_1, count=api.data_len,
                                  priceMode=EPriceMode.FORMER, fields=None, df=True)
    close = bar_data["close"].values[-1]
    # 计算ATR
    atr = talib.ATR(bar_data["high"].values, bar_data["low"].values, bar_data["close"].values,
                    timeperiod=api.tar)[-1]

    # 计算唐奇安开仓和平仓通道
    api.don_open = api.parameter[0] + 1
    upper_band = talib.MAX(bar_data['close'].values[:-1], timeperiod=api.don_open)[-1]
    api.don_close = api.parameter[1] + 1
    lower_band = talib.MIN(bar_data['close'].values[:-1], timeperiod=api.don_close)[-1]

    # 若没有仓位则开仓
    position_long = api.getSymbolPosition(symbol=bar.symbol, positionSide=EPositionSide.LONG)
    position_short = api.getSymbolPosition(symbol=bar.symbol, positionSide=EPositionSide.SHORT)

    print(position_long)
    print(position_short)

    if not position_long.posQty and not position_short.posQty:
        # 计算长短ma线.DIF
        ma_short = talib.MA(bar_data['close'].values, timeperiod=(api.parameter[2] + 1))[-1]
        ma_long = talib.MA(bar_data['close'].values, timeperiod=(api.parameter[3] + 1))[-1]

        diff = ma_short - ma_long

        # 获取当前价格
        # 上穿唐奇安通道且短ma在长ma上方则开多仓
        if bar.close > upper_band and (diff > 0):
            api.targetPosition(symbol=bar.symbol, qty=8, positionSide=EPositionSide.LONG)
            print(bar.symbol, '市价单开多仓8手')
        # 下穿唐奇安通道且短ma在长ma下方则开空仓
        if bar.low < lower_band and (diff < 0):
            api.targetPosition(symbol=bar.symbol, qty=8, positionSide=EPositionSide.SHORT)
            print(bar.symbol, '市价单开空仓8手')

    elif position_long.posQty:
        # 价格跌破唐奇安平仓通道全平仓位止损
        if close < lower_band:
            api.targetPosition(symbol=bar.symbol, qty=0, positionSide=EPositionSide.LONG)
            print(bar.symbol, '市价单全平仓位')
        else:
            # 获取持仓均价
            vwap = position_long.posPrice
            # 根据持仓以来的最高价计算不同的止损价格带
            band = vwap - np.array([2, 1.5, 1, 0.5]) * atr
            # 计算最新应持仓位
            if bar.close <= band[0]:
                api.targetPosition(symbol=bar.symbol, qty=0, positionSide=EPositionSide.LONG)
                print(bar.symbol, '市价单平仓至0手')
            elif band[0] < bar.close <= band[1]:
                api.targetPosition(symbol=bar.symbol, qty=2, positionSide=EPositionSide.LONG)
                print(bar.symbol, '市价单平仓至2手')
            elif band[1] < bar.close <= band[2]:
                api.targetPosition(symbol=bar.symbol, qty=4, positionSide=EPositionSide.LONG)
                print(bar.symbol, '市价单平仓至4手')
            elif band[2] < bar.close <= band[3]:
                api.targetPosition(symbol=bar.symbol, qty=6, positionSide=EPositionSide.LONG)
                print(bar.symbol, '市价单平仓至6手')

    elif position_short.posQty:
        # 价格涨破唐奇安平仓通道或价格涨破持仓均价加两倍ATR平空仓
        if close > upper_band:
            api.targetPosition(symbol=bar.symbol, qty=0, positionSide=EPositionSide.SHORT)
            print(bar.symbol, '市价单全平仓位')
        else:
            # 获取持仓均价
            vwap = position_long.posPrice
            # 根据持仓以来的最高价计算不同的止损价格带
            band = vwap + np.array([2, 1.5, 1, 0.5]) * atr
            # 计算最新应持仓位
            if bar.close >= band[0]:
                api.targetPosition(symbol=bar.symbol, qty=0, positionSide=EPositionSide.SHORT)
                print(bar.symbol, '市价单平仓至0手')
            elif band[0] > bar.close >= band[1]:
                api.targetPosition(symbol=bar.symbol, qty=2, positionSide=EPositionSide.SHORT)
                print(bar.symbol, '市价单平仓至2手')
            elif band[1] > bar.close >= band[2]:
                api.targetPosition(symbol=bar.symbol, qty=4, positionSide=EPositionSide.SHORT)
                print(bar.symbol, '市价单平仓至4手')
            elif band[2] > bar.close >= band[3]:
                api.targetPosition(symbol=bar.symbol, qty=6, positionSide=EPositionSide.SHORT)
                print(bar.symbol, '市价单平仓至6手')


def onTerminate(api, exit_info):
    print("Finished test")
    pass


