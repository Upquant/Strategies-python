#!/usr/bin/env python
# -*- coding: utf-8 -*-

from etasdk import *
import numpy as np
from operator import itemgetter
from collections import OrderedDict

'''
股票策略：行业轮动
本策略每天计算"880008.PLA", "880023.PLA", "880030.PLA", "880035.PLA", "880046.PLA", "880064.PLA"
(化学制品.电子.纺织服装.医药.房地产.国防军工)这几个行业指数过去
20个交易日的收益率,选取收益率最高的指数的成份股中流通市值最大的5只股票作为下期的持仓股票
对不在股票池的股票平仓并等权配置股票池的标的
回测区间：2018-07-01 到2018-10-01
撮合周期：日K
'''


# 初始化
def onInitialize(api):
    # 选取行业板块
    # 这里我们选择 化学制品（880008.PLA）， 电子（"880023.PLA"），纺织服装（"880030.PLA"）， 医药（"880035.PLA")，房地产（"880046.PLA"），国防军工（"880064.PLA"）
    api.industries = ["880008.PLA", "880023.PLA", "880030.PLA", "880035.PLA", "880046.PLA", "880064.PLA"]
    api.returnWindow = 20
    api.capitalRatio = 0.8
    api.numberOfChosenTickers = 5
    api.chosenTickers = []

    # 设置股票池，因子以及K线类型
    api.setRequireData(instsets=api.industries,
                       symbols=api.industries,  # 单独订阅行情数据
                       fields=['MKT_CAP'],
                       bars=[(ETimeSpan.DAY_1, api.returnWindow + 10)]
                       )
    # 设置按组回调
    api.setGroupMode(timeOutMs=10000, onlyGroup=False)


# 盘前运行，用于选股逻辑；必须实现，用来设置当日关注的标的
def onBeforeMarketOpen(api, tradeDate):
    print("on date", tradeDate)
    # 计算各个行业指数的return
    return_index = []

    for industry in api.industries:
        bars = api.getBarsHistory(industry, timeSpan=ETimeSpan.DAY_1, count=api.returnWindow + 1, df=True,
                                  priceMode=EPriceMode.FORMER, skipSuspended=0)
        bars.fillna(method="ffill")
        if len(bars) < api.returnWindow:
            continue
        return_index.append(bars.close.values[-1] / bars.close.values[0] - 1)

    # 找到return最高的行业
    chosenIndustry = api.industries[np.argmax(return_index)]
    print("chosenIndustry", chosenIndustry)

    # 获取行业成分股
    industrySymbols = api.getConstituentSymbols(chosenIndustry)

    # 获取股票的市值
    symbolMarketCaps = {}
    for symbol in industrySymbols:
        # 检查股票是否停牌，不交易停牌股票
        if api.isSuspend(symbol, tradeDate):
            continue
        # 获取单个标的的市值
        marketCapital = api.getFieldsCountDays(symbol=symbol, fields=["MKT_CAP"], count=1)
        symbolMarketCaps[symbol] = marketCapital.MKT_CAP.values[-1]

    # 按照市值对股票排序
    orderedDict = OrderedDict(sorted(symbolMarketCaps.items(), key=itemgetter(1), reverse=True))
    api.chosenTickers = [item[0] for item in orderedDict.items()][:api.numberOfChosenTickers]
    print("chosenTickers", api.chosenTickers)

    # 设置当天需要交易的股票，如果历史上有过持仓了，则系统会默认自动关注
    api.setFocusSymbols(api.chosenTickers)

    # 根据持仓信息，处理持仓股票。平掉不在信号池中的股票
    symbolpositions = api.getSymbolPositions()
    for position in symbolpositions:
        if api.isSuspend(position.symbol, api.getCurrTradeDate()):
            continue
        if position.symbol not in api.chosenTickers:
            api.targetPosition(symbol=position.symbol, qty=0, positionSide=EPositionSide.LONG,
                               remark="not in signal pool")


def onHandleData(api, timeExch):
    # 获取账户信息，根据剩余可用现金和持仓信息，计算新开仓量
    ratio_by_index = 0.9  # %90%仓位，可根据大盘走势进行调整
    account = api.getAccount(api.chosenTickers[0])
    capital = account.totAssets * ratio_by_index - account.marketValue
    # 获取止损和平仓后的持仓
    holdingPos = []
    symbolpositions = api.getSymbolPositions()
    for position in symbolpositions:
        holdingPos.append(position.symbol)
    newSymbols = list(set(api.chosenTickers) - set(holdingPos))
    # 检查是否有新标的需要买入
    if len(newSymbols) == 0:
        return
    # 计算个股capital
    eachTickerCapital = capital / len(newSymbols)
    # 根据个股capital下单
    for symbol in newSymbols:
        # 获取标的当前价格
        price = api.getBarsHistory(symbol, timeSpan=ETimeSpan.DAY_1, count=1, df=True,
                                   priceMode=EPriceMode.FORMER, skipSuspended=0)
        if len(price) <= 0:
            continue
        # 获取当前标的持仓信息
        symbolPosition = api.getSymbolPosition(symbol)
        targetQty = int(eachTickerCapital / price.close.values[-1])
        deltaQty = targetQty - symbolPosition.posQty
        # 下单手数取整
        finalQty = symbolPosition.posQty + int(deltaQty / 100) * 100
        finalQty = max(finalQty, 0)

        api.targetPosition(symbol=symbol, qty=finalQty, positionSide=EPositionSide.LONG, remark="open new")
        print("open  new long postion:", symbol, finalQty)
        LOG.INFO("open  new long postion:" + str(symbol) + " " + str(finalQty))


# 策略终止时响应
def onTerminate(api, exitInfo):
    LOG.INFO("***************onTerminate*********")
    print("***************onTerminate*********")
