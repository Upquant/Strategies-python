# coding=utf-8
from __future__ import print_function, absolute_import, unicode_literals, division
import numpy as np
from etasdk import *
from talib import EMA

'''
本策略为股票个股择时，等资金分配仓位。
回测参数设置：
1、回测时间：2014-01-06到2018-11-08；
2、撮合周期：日K；
3、费率：万3
4、滑点：1个tick
5、股票初始资金：100万
6、股票池：上证50
'''

def capital_lots(close, capital,ratio_by_index):
    ## 计算下单股数
    # input:价格、资金和仓位比例（0-100%）
    volume = {}
    capitalSingle = ratio_by_index * capital / len(close)  # 均分后根据指数计算仓位比例
    for symbol in close.keys():
        volume[symbol] =  max(100*int(capitalSingle / (close[symbol] * 100.)),100)  # 不足1手，补齐1手
    return volume

def onInitialize(api):
    ## 设置标的
    api.index = str("000016.IDX") # 以上证50股票池为例
    api.setSymbolPool(instsets=[api.index], symbols=[api.index])
    api.setGroupMode(50000, True)

    ##  全局参数
    api.dataLen = 200  # 每次下载的数据长度
    api.setRequireBars(ETimeSpan.DAY_1, api.dataLen)
    account = api.getAccount(symbol=api.index, market=MARKET_CHINASTOCK)
    api.capital = account.cashAvailable  # 账户初始资金（100万）

    ## 时间窗口参数
    api.windows_SMA        = 5   # 短期移动平均窗口
    api.windows_LMA        = 20  # 长期移动平均窗口
    api.windows_LLMA       = 120  # 更长周期移动平均窗口

    ## 临界值类
    api.stop_method = 1

    ## 行情数据类
    api.tradeday = [] # 交易日
    api.symbolPool = []
    api.price = None # 交易信号

    print("initialize successly.")
    LOG.INFO("initialize successly.")

def onBeforeMarketOpen(api, trade_date):
    print("-------------------")
    print("tradingday:", trade_date)
    LOG.INFO("tradingday:%s", trade_date)

    api.tradeday.append(trade_date)
    api.symbolPool = api.getSymbolPool()

    ## 止损平仓
    stop_loss(api)

    ## 1、择时与选股
    api.price = timeAlgorithm(api) # 修改择时算法，返回选股的价格（字典形式）
    print("trade symbol:", api.price.keys())

    # 设置当天需要交易的股票，如果历史上有过持仓了，则系统会默认自动关注
    api.setFocusSymbols(api.price.keys())

    # 根据持仓信息，处理持仓股票。平掉不在信号池中的股票
    symbolpositions = api.getSymbolPositions()
    print("symbol before close", len(symbolpositions))
    for position in symbolpositions:
        if api.isSuspend(position.symbol, api.getCurrTradeDate()):
            continue
        if position.symbol not in api.price.keys():
            api.targetPosition(symbol=position.symbol, qty=0, positionSide=EPositionSide.LONG,
                               remark="not in signal pool")

def onHandleData(api, timeExch):

    # 当前信号不为空
    if not api.price or len(api.price) == 0:
        return

    # 获取账户信息，根据剩余可用现金和持仓信息，计算新开仓量
    ratio_by_index = 0.9  # %90%仓位，可根据大盘走势进行调整
    account = api.getAccount(symbol=api.index, market=MARKET_CHINASTOCK)
    capital = account.totAssets * ratio_by_index - account.marketValue
    # 获取止损和平仓后的持仓
    holdingPos = []
    symbolpositions = api.getSymbolPositions()
    for position in symbolpositions:
        holdingPos.append(position.symbol)
    newSymbols = list(set(api.price.keys()) - set(holdingPos))
    # 检查是否有新标的需要买入
    if len(newSymbols) == 0:
        return
    # 计算个股capital
    eachTickerCapital = capital / len(newSymbols)
    # 根据个股capital下单
    for symbol in newSymbols:
        # 获取标的当前价格
        price = api.getBarsHistory(symbol, timeSpan=ETimeSpan.DAY_1, count=1, df=True,\
                                   priceMode=EPriceMode.FORMER, skipSuspended=0)
        if len(price) <= 0:
            continue
        # 获取当前标的持仓信息
        symbolPosition = api.getSymbolPosition(symbol)
        targetQty = int(eachTickerCapital / price.close.values[-1])
        deltaQty = targetQty - symbolPosition.posQty
        #下单手数取整
        finalQty = symbolPosition.posQty + int(deltaQty / 100) * 100
        finalQty = max(finalQty, 0)

        api.targetPosition(symbol=symbol, qty=finalQty, positionSide=EPositionSide.LONG, remark="open new")
        print("open  new long postion:", symbol, finalQty)
        LOG.INFO("open  new long postion:" + str(symbol) + " " + str(finalQty))


def onTerminate(api, exit_info):
    pass

def timeAlgorithm(api):
    price = {}
    for symbol in api.symbolPool:
        ## 下载行情数据
        HQData = api.getBarsHistory(symbol, timeSpan=ETimeSpan.DAY_1, count=api.dataLen, df=True, \
                               priceMode=EPriceMode.FORMER, skipSuspended=0)
        # 新股排除
        if len(HQData) <= 120:
            continue

        # 检查标的是否停牌
        if api.isSuspend(symbol, api.getCurrTradeDate()):
            continue

        # 根据模型计算开仓信号
        if calculateSignal(api, HQData) == 1:
            price[symbol] = HQData.close.values[-1]
    return price
def calculateSignal(api,HQData):
    if np.isnan(HQData.close.values[-1]):
        return 0

    close = HQData.close.values
    closeSMA = EMA(close, api.windows_SMA)[-1]
    closeLMA = EMA(close, api.windows_LMA)[-1]

    signal01 = 1 if (closeSMA > closeLMA) else 0

    volume = HQData.volume.values
    volumeMA = EMA(volume[:-1],20)
    closeSMADouble08 = EMA(EMA(close, 8), 8)
    dailyRet = np.log(closeSMADouble08[-1]) - np.log(closeSMADouble08[-2])
    signal = 1 if (volume[-1] > 2.*volumeMA[-1]) and (dailyRet>0) else signal01
    return signal

def stop_loss(api):
    # 移动止损止盈
    positionQty, positionHigh, positionClose = queryPosition(api)
    for ind in positionQty.keys():
        # 检查标的是否停牌
        if api.isSuspend(ind, api.getCurrTradeDate()):
            continue
        hist_data = api.getBarsHistory(ind, timeSpan=ETimeSpan.DAY_1, count=90, df=True,
                                       priceMode=EPriceMode.FORMER)
        if len(hist_data) >= 60:
            close = hist_data.close.values
            if api.stop_method == 1:
                # 止损
                drawdown = np.log(positionHigh[ind] / positionClose[ind])
                if drawdown < 0.10:
                    dropline = positionHigh[ind] * 0.90
                else:
                    dropline = positionHigh[ind] * 0.94
                if (close[-1] <= dropline):
                    api.targetPosition(symbol=ind, qty=0, positionSide=EPositionSide.LONG,remark="stop loss")
                    print(api.tradeday[-1], ",stop loss:", ind)
                # 止盈
                if (((close[-1] / positionClose[ind]) - 1) >= 0.15):
                    api.targetPosition(symbol=ind, qty=0, positionSide=EPositionSide.SHORT)
                    print(api.tradeday[-1], ",stop return", ind)

def queryPosition(api):
    # #  查询持仓
    positionQty = {}
    positionHigh = {}
    positionClose = {}
    symbolpositions = api.getSymbolPositions()
    if not symbolpositions:
        return positionQty,positionHigh,positionClose
    else:
        for ind in symbolpositions:
            positionQty[ind.symbol] = ind.posQty
            positionHigh[ind.symbol] = ind.posHigh
            positionClose[ind.symbol] = ind.posPrice
        return positionQty,positionHigh,positionClose
