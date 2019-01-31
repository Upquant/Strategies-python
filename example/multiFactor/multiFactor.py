#!/usr/bin/env python
# -*- coding: utf-8 -*-

from etasdk import *
import numpy as np
import pandas as pd

'''
股票策略：多因子选股
本策略根据Fama-French三因子模型对每只股票进行回归，得到其alpha值, 买入alpha为负的股票。
策略思路：
计算市场收益率,并对个股的账面市值比和市值进行分类,
根据分类得到的组合计算市值加权收益率、SMB和HML. 
对各个股票进行回归(无风险收益率等于0)得到alpha值.
选取alpha值小于0并为最小的10只股票进入标的池
等权买入在标的池的股票并卖出不在标的池的股票
回测数据:000300.IDX的成份股
回测区间：2018-07-01 到2018-10-01
回测周期：日K
'''

#初始化
def onInitialize(api):
    # 数据滑窗
    api.dataWindow = 20
    # 设置开仓的最大资金量
    api.ratio = 0.8
    # 账面市值比的大/中/小分类
    api.BM_BIG = 3.0
    api.BM_MID = 2.0
    api.BM_SMA = 1.0
    # 市值大/小分类
    api.MV_BIG = 2.0
    api.MV_SMA = 1.0
    # 持仓股票
    api.symbols_pool = []
    # 设置股票池，因子以及K线类型
    api.setRequireData(instsets=["000300.IDX"], # 000300成分股
                       symbols=["000300.IDX"], # 000300指数
                       fields=['MKT_CAP', "PB"],
                       bars=[(ETimeSpan.DAY_1, api.dataWindow + 10)]
                       )
    #设置按组回调
    api.setGroupMode(timeOutMs=10000,onlyGroup = False);

#盘前运行，用于选股逻辑；必须实现，用来设置当日关注的标的
def onBeforeMarketOpen(api,tradeDate):
    print("on date", tradeDate)
    # 获取股票池
    symbolPool = api.getSymbolPool()

    fundamentalDf = pd.DataFrame(columns=["symbol", 'MKT_CAP', "PB"])
    # 获取基本面数据
    for symbol in symbolPool:
        # 检查股票是否停牌，不交易停牌股票
        if api.isSuspend(symbol, tradeDate):
            continue
        # 获取基本面数据
        fundamentals = api.getFieldsCountDays(symbol=symbol, fields=['MKT_CAP', "PB"], count=1)
        fundamentalDf.loc[len(fundamentalDf)] = {"symbol":symbol, "MKT_CAP": fundamentals.MKT_CAP.values[-1], "PB":fundamentals.PB.values[-1]}

    # 计算账面市值比, PB倒数
    fundamentalDf["PB"] = (fundamentalDf['PB'] ** -1)

    # 计算市值的50%的分位点, 用于分类
    sizeGate = fundamentalDf['MKT_CAP'].quantile(0.50)

    # 计算账面市值比的30%和70%分位点,用于分类
    bm_gate = [fundamentalDf['PB'].quantile(0.30), fundamentalDf['PB'].quantile(0.70)]
    fundamentalDf.index = fundamentalDf.symbol
    x_return = []

    # 计算return
    tickerCloseValues = {}
    for symbol in fundamentalDf.symbol.values:
        price = api.getBarsHistory(symbol, timeSpan=ETimeSpan.DAY_1, count=api.dataWindow + 1, df=True, \
                                   priceMode=EPriceMode.FORMER, skipSuspended=0)
        if len(price) < api.dataWindow:
            continue
        price.fillna(method="ffill")

        stockReturn = price.close.values[-1] / price.close.values[0] - 1
        pb = fundamentalDf['PB'][symbol]
        market_value = fundamentalDf['MKT_CAP'][symbol]
        tickerCloseValues[symbol] = price.close.values[-1]
        # 获取[股票代码. 股票收益率, 账面市值比的分类, 市值的分类, 流通市值]
        if pb < bm_gate[0]:
            if market_value < sizeGate:
                label = [symbol, stockReturn, api.BM_SMA, api.MV_SMA, market_value]
            else:
                label = [symbol, stockReturn, api.BM_SMA, api.MV_BIG, market_value]
        elif pb < bm_gate[1]:
            if market_value < sizeGate:
                label = [symbol, stockReturn, api.BM_MID, api.MV_SMA, market_value]
            else:
                label = [symbol, stockReturn, api.BM_MID, api.MV_BIG, market_value]
        elif market_value < sizeGate:
            label = [symbol, stockReturn, api.BM_BIG, api.MV_SMA, market_value]
        else:
            label = [symbol, stockReturn, api.BM_BIG, api.MV_BIG, market_value]

        if len(x_return) == 0:
            x_return = label
        else:
            x_return = np.vstack([x_return, label])

    stocks = pd.DataFrame(data=x_return, columns=['symbol', 'return', 'BM', 'MKT_CAP', 'mv'])
    stocks.index = stocks.symbol
    columns = ['return', 'BM', 'MKT_CAP', 'mv']
    for column in columns:
        stocks[column] = stocks[column].astype(np.float64)

    # 计算SMB.HML和市场收益率
    # 获取小市值组合的市值加权组合收益率
    smb_s = (market_weighted_return(stocks, api.MV_SMA, api.BM_SMA) +
             market_weighted_return(stocks, api.MV_SMA, api.BM_MID) +
             market_weighted_return(stocks, api.MV_SMA, api.BM_BIG)) / 3

    # 获取大市值组合的市值加权组合收益率
    smb_b = (market_weighted_return(stocks, api.MV_BIG, api.BM_SMA) +
             market_weighted_return(stocks, api.MV_BIG, api.BM_MID) +
             market_weighted_return(stocks, api.MV_BIG, api.BM_BIG)) / 3

    smb = smb_s - smb_b
    # 获取大账面市值比组合的市值加权组合收益率
    hml_b = (market_weighted_return(stocks, api.MV_SMA, 3) +
             market_weighted_return(stocks, api.MV_BIG, api.BM_BIG)) / 2
    # 获取小账面市值比组合的市值加权组合收益率
    hml_s = (market_weighted_return(stocks, api.MV_SMA, api.BM_SMA) +
             market_weighted_return(stocks, api.MV_BIG, api.BM_SMA)) / 2

    hml = hml_b - hml_s
    close = api.getBarsHistory(symbol, timeSpan=ETimeSpan.DAY_1, count=api.dataWindow + 1, df=True, \
                                   priceMode=EPriceMode.FORMER, skipSuspended=1)["close"].values
    market_return = close[-1] / close[0] - 1
    coff_pool = []

    # 对每只股票进行回归获取其alpha值
    for stock in stocks.index:
        x_value = np.array([[market_return], [smb], [hml], [1.0]])
        y_value = np.array([stocks['return'][stock]])
        # OLS估计系数
        coff = np.linalg.lstsq(x_value.T, y_value)[0][3]
        coff_pool.append(coff)

    # 获取alpha最小并且小于0的10只的股票进行操作(若少于10只则全部买入)
    stocks['alpha'] = coff_pool
    stocks = stocks[stocks.alpha < 0].sort_values(by='alpha').head(10)
    api.symbols_pool = stocks.index.tolist()

    # 设置当天需要交易的股票，如果历史上有过持仓了，则系统会默认自动关注
    api.setFocusSymbols(api.symbols_pool )

    # 根据持仓信息，处理持仓股票。平掉不在信号池中的股票
    symbolpositions = api.getSymbolPositions()
    print("symbol before close", len(symbolpositions))
    for position in symbolpositions:
        if api.isSuspend(position.symbol, api.getCurrTradeDate()):
            continue
        if position.symbol not in api.symbols_pool:
            api.targetPosition(symbol=position.symbol, qty=0, positionSide=EPositionSide.LONG,
                               remark="not in signal pool")

def onHandleData(api, timeExch):
    # 获取账户信息，根据剩余可用现金和持仓信息，计算新开仓量
    ratio_by_index = 0.9  # %90%仓位，可根据大盘走势进行调整
    account = api.getAccount(api.symbols_pool[0])
    capital = account.totAssets * ratio_by_index - account.marketValue
    # 获取止损和平仓后的持仓
    holdingPos = []
    symbolpositions = api.getSymbolPositions()
    for position in symbolpositions:
        holdingPos.append(position.symbol)
    newSymbols = list(set(api.symbols_pool) - set(holdingPos))
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


#策略终止时响应
def onTerminate(api,exitInfo):
    LOG.INFO ("***************onTerminate*********")
    print ("***************onTerminate*********")

# 计算市值加权的收益率,MV为市值的分类,BM为账目市值比的分类
def market_weighted_return(stocksValues, MV_class, BM_class):
    select = stocksValues[(stocksValues.MKT_CAP == MV_class) & (stocksValues.BM == BM_class)]
    marketValue = select['mv'].values
    mvTotal = np.sum(marketValue)
    mvWeighted = [mv / mvTotal for mv in marketValue]
    stock_return = select['return'].values
    # 返回市值加权的收益率的和
    returnTotal = []
    for i in range(len(mvWeighted)):
        returnTotal.append(mvWeighted[i] * stock_return[i])
    return_total = np.sum(returnTotal)
    return return_total