# coding=utf-8
from __future__ import print_function, absolute_import, unicode_literals
import datetime
from etasdk import *
import numpy as np

'''
期货策略：跨市场套利
本策略首先滚动计算过去30个1min收盘价的均值,然后用均值加减2个标准差得到布林线.
若无仓位,在最新价差上穿上轨时做空价差;下穿下轨时做多价差
若有仓位则在最新价差回归至上下轨水平内时平仓
回测数据为:rb1801和hc1801的1min数据
回测时间为:2017-09-01 到2017-09-29
撮合周期：1分钟
初始资金（期货）：10万
'''


def onInitialize(api):
    # 设置响应模式
    api.setGroupMode(5000, False)
    # 设置bar长度
    api.data_len = 30
    # 进行套利的品种
    api.tickersCode = ['rb1801.CF', 'hc1801.CF']  # "rb1801.CF"---螺纹1801合约
    # 设置行情数据缓存
    api.setRequireData(instsets=['rb.PRD', 'hc.PRD'], symbols=api.tickersCode, fields=[], bars=[(ETimeSpan.MIN_1, 300)])


def onBeforeMarketOpen(api, tradeDate):
    # print(tradeDate)
    api.trading_day = tradeDate
    # 订阅行情
    api.setFocusSymbols(api.tickersCode)

    symbol_positions = api.getSymbolPositions()
    print("symbol_positions:", symbol_positions)

    position_rb_long = api.getSymbolPosition(symbol=api.tickersCode[0], positionSide=EPositionSide.LONG)
    position_rb_short = api.getSymbolPosition(symbol=api.tickersCode[0], positionSide=EPositionSide.SHORT)


def onHandleData(api, timeExch):
    api.trade_date = datetime.datetime.fromtimestamp(timeExch / 1000)

    # 获取两个品种的时间序列
    data_rb = api.getBarsHistory(symbol=api.tickersCode[0], timeSpan=ETimeSpan.MIN_1, count=api.data_len + 1,
                                 priceMode=EPriceMode.FORMER, fields=None, df=True)
    close_rb = data_rb["close"].values

    data_hc = api.getBarsHistory(symbol=api.tickersCode[1], timeSpan=ETimeSpan.MIN_1, count=api.data_len + 1,
                                 priceMode=EPriceMode.FORMER, fields=None, df=True)
    close_hc = data_hc["close"].values

    # 计算价差
    spread = close_rb[:-1] - close_hc[:-1]
    # 计算布林带的上下轨
    up = np.mean(spread) + 2 * np.std(spread)
    down = np.mean(spread) - 2 * np.std(spread)
    # 计算最新价差
    spread_now = close_rb[-1] - close_hc[-1]

    # 无交易时若价差上(下)穿布林带上(下)轨则做空(多)价差
    position_rb_long = api.getSymbolPosition(symbol=api.tickersCode[0], positionSide=EPositionSide.LONG)
    position_rb_short = api.getSymbolPosition(symbol=api.tickersCode[0], positionSide=EPositionSide.SHORT)

    print("I'm here!")
    print(position_rb_long)

    if not position_rb_long and not position_rb_short:
        if spread_now > up:
            api.targetPosition(symbol=api.tickersCode[0], qty=1, positionSide=EPositionSide.SHORT)
            LOG.INFO("Open short at market price:%s", api.tickersCode[0])
            api.targetPosition(symbol=api.tickersCode[1], qty=1, positionSide=EPositionSide.LONG)
            LOG.INFO("Open long at market price:%s", api.tickersCode[1])

        if spread_now < down:
            api.targetPosition(symbol=api.tickersCode[0], qty=1, positionSide=EPositionSide.LONG)
            LOG.INFO("Open long at market price:%s", api.tickersCode[0])
            api.targetPosition(symbol=api.tickersCode[1], qty=1, positionSide=EPositionSide.SHORT)
            LOG.INFO("Open short at market price:%s", api.tickersCode[1])

    # 价差回归时平仓
    elif position_rb_short:
        if spread_now <= up:
            api.targetPosition(symbol=api.tickersCode[0], qty=0, positionSide=EPositionSide.SHORT)
            api.targetPosition(symbol=api.tickersCode[1], qty=0, positionSide=EPositionSide.LONG)
            LOG.INFO("Clear all positions")

        # 跌破下轨反向开仓
        if spread_now < down:
            api.targetPosition(symbol=api.tickersCode[0], qty=1, positionSide=EPositionSide.LONG)
            LOG.INFO("Open long at market price:%s", api.tickersCode[0])
            api.targetPosition(symbol=api.tickersCode[1], qty=1, positionSide=EPositionSide.SHORT)
            LOG.INFO("Open short at market price:%s", api.tickersCode[1])

    elif position_rb_long:
        if spread_now >= down:
            api.targetPosition(symbol=api.tickersCode[0], qty=0, positionSide=EPositionSide.SHORT)
            api.targetPosition(symbol=api.tickersCode[1], qty=0, positionSide=EPositionSide.LONG)
            LOG.INFO("Clear all positions")
        # 突破上轨开多
        if spread_now > up:
            api.targetPosition(symbol=api.tickersCode[0], qty=1, positionSide=EPositionSide.SHORT)
            LOG.INFO("Open short at market price:%s", api.tickersCode[0])
            api.targetPosition(symbol=api.tickersCode[1], qty=1, positionSide=EPositionSide.LONG)
            LOG.INFO("Open long at market price:%s", api.tickersCode[1])


def onTerminate(api, exitInfo):
    print("回测结束。。。")
