#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function, absolute_import, unicode_literals, division
from etasdk import *

'''
指数对冲策略
策略基本思想：本策略为股票市场中性策略，即股票多头+股指期货空头，二者在换仓日保持市值相等。
策略交易频率：每月换仓一次
交易或订阅标的：沪深300指数的成分股和沪深300指数期货，从沪深300指数成分股中按照动量和估值选出30只较强的股票。
回测时间：2016-12-01 到2017-12-29
撮合频率：日K
初始资金：A股200万，期货200万
'''


def onInitialize(api):
    # 设置股票池
    api.setSymbolPool(instsets=["IF.PRD", "000300.IDX"])
    # 设置数据下载的超时时间
    api.setGroupMode(500, True)
    # 设置行情数据缓存条数
    api.data_len = 21
    api.setRequireBars(ETimeSpan.DAY_1, api.data_len)
    # 设置缓存日频因子数据
    api.setRequireFields(fields=["PE"])

    api.stock_num = 30
    api.trade_day_now = 0
    api.trade_day_last = 0
    api.lots_stock = {}
    api.futures_code = []
    api.lots_futures = 0


def onBeforeMarketOpen(api, trade_date):
    print("日期：", trade_date)
    # 订阅的标的代码
    symbol_subscribe = api.getSymbolPool()
    data_code = [ind01 for ind01 in symbol_subscribe if "CS" in ind01]
    api.futures_code = api.getContinuousSymbol("IFZ0.CF", trade_date)

    data_code.append(str(api.futures_code))
    # 关注相关股票和股指期货
    # api.setFocusSymbols(data_code)
    # 当前股指期货主力合约代码
    api.futures_code = api.getContinuousSymbol("IFZ0.CF", trade_date)

    # 获取当前交易日
    api.trade_day_now = api.getCurrTradeDate()
    # 获取上一交易日
    api.trade_day_last = api.getPrevTradeDate(trade_date)

    # 如果当前是每月的第一个交易日即选股调仓并执行对冲
    # if str(api.trade_day_now)[4:6] == str(api.trade_day_last)[4:6]: return
    # 获取股票的PE指标数据
    findata = api.getFieldsOneDay(data_code[:-1], ["PE"], api.trade_day_last, df=True)
    findata.index = findata["symbol"]
    # 获取历史行情数据
    close = {}
    for ind03 in data_code:
        bars = api.getBarsHistory(ind03, ETimeSpan.DAY_1, count=api.data_len, priceMode=EPriceMode.FORMER, df=True)
        if (len(bars) >= api.data_len) and (bars.ix[api.data_len - 1, "isSuspended"] == 0):
            close[ind03] = bars.ix[api.data_len - 1, "close"]
            if "CS" in ind03:
                findata.ix[ind03, "momentum01"] = (bars.ix[api.data_len - 1, "close"] / bars.ix[0, "close"]) - 1
    # 先按照估值PE和动量排序选出前30只股票
    findata[["ranks_pe", "rank_mom"]] = findata.rank()[["PE", "momentum01"]]
    findata["score"] = findata["rank_mom"] - findata["ranks_pe"]
    findata_sorted = findata.sort_values("score", ascending=False)[:api.stock_num]
    symbol_stock = list(findata_sorted.index.values)
    symbol_stock.append(api.futures_code)
    # 关注相关股票和股指期货
    api.setFocusSymbols(symbol_stock)

    symbolpositions = api.getSymbolPositions()

    # 每天判断是否需要换仓
    """
    for ind00 in symbolpositions:
        symbol_last = ind00.symbol
        # 如果股指期货换月则平仓然后在新合约上开仓
        if ("CF" in symbol_last) and (symbol_last != api.futures_code):
            api.targetPosition(symbol=symbol_last, qty=0, positionSide=EPositionSide.SHORT)
            print("移仓换月，市价单平仓：", symbol_last)
            api.targetPosition(symbol=api.futures_code, qty=ind00.posQty, positionSide=EPositionSide.SHORT)
            print("移仓换月，市价单开仓：", api.futures_code)
    """

    for ind in symbolpositions:
        if ind.symbol not in symbol_stock:
            if ind.positionSide == EPositionSide.LONG:  # 股票不在关注的标的中，卖出
                api.targetPosition(symbol=ind.symbol, qty=0, positionSide=EPositionSide.LONG)
            elif ind.positionSide == EPositionSide.SHORT:  # 期货在换月时刻，近月合约平仓
                api.targetPosition(symbol=ind.symbol, qty=0, positionSide=EPositionSide.SHORT)
                api.targetPosition(symbol=api.futures_code, qty=ind.posQty, positionSide=EPositionSide.SHORT)
                print("移仓换月，市价单平仓：", ind.symbol)

        """
        # 每天判断是否需要换仓
        for ind00 in symbolpositions:
            if ind00.symbol not in symbol_stock:
                if ind00.positionSide == EPositionSide.LONG:  # 股票不在关注的标的中，卖出
                    api.targetPosition(symbol=ind00.symbol, qty=0, positionSide=EPositionSide.LONG)
                elif ind00.positionSide == EPositionSide.SHORT:  # 期货在换月时刻，近月合约平仓
                    api.targetPosition(symbol=ind00.symbol, qty=0, positionSide=EPositionSide.SHORT)
                    print("移仓换月，市价单平仓：", ind00.symbol)
        """

    # 平均分配每只股票资金，计算每只股票仓位
    api.lots_stock = {}
    account_stock = api.getAccount(data_code[0])
    capital = account_stock.cashAvailable + account_stock.marketValue
    for ind05 in close.keys():
        if ("CS" in ind05) and (ind05 in symbol_stock):
            api.lots_stock[ind05] = int(capital * 0.70 / close[ind05] / api.stock_num / 100.0) * 100
        elif "CF" in ind05:
            api.lots_futures = int(capital * 0.70 / close[ind05] / 300.0)

    # 1、获取当前仓位换仓
    for ind04 in symbolpositions:
        symbol_last = ind04.symbol
        # 不在标的的股票将卖出
        if ("CS" in symbol_last) and (symbol_last not in symbol_stock):
            api.targetPosition(symbol=symbol_last, qty=0)
            print("不在标的池，市价单卖出：", symbol_last)


def onHandleData(api, timeExch):
    # 如果当前是每月的第一个交易日即选股调仓并执行对冲
    if str(api.trade_day_now)[4:6] == str(api.trade_day_last)[4:6]:
        return
        # 2、买入标的池股票
    for ind06 in api.lots_stock.keys():
        # 如果股票有分红送股的情况下，增加仓位也需要时 100 的整数倍
        currentShares = api.getSymbolPosition(ind06).posQty
        addShares = ((api.lots_stock[ind06] - currentShares + 50) // 100) * 100
        totalShares = currentShares + addShares
        api.targetPosition(symbol=ind06, qty=totalShares)
        print("市价单买入：", ind06, totalShares)
    # 开空股指期货对冲
    api.targetPosition(symbol=api.futures_code, qty=api.lots_futures, positionSide=EPositionSide.SHORT)
    print("市价单开空：", api.futures_code)


def onTerminate(api, exitInfo):
    print("回测结束。。。")
