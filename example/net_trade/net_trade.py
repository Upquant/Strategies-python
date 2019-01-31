# coding=utf-8
from __future__ import print_function, absolute_import, unicode_literals,division
from etasdk import *
import numpy as np
import pandas as pd
'''
策略基本思想：本策略为经典的期货日内策略（网格交易），设置不同的临界线，并分配不同的资金仓位。
策略交易频率：1分钟
交易或订阅标的：rb1801
回测时间：2017-12-01 到2017-12-29
'''
def onInitialize(api):
    #设置股票池
    api.setSymbolPool(symbols=["rb1801.CF"])
    # 设置行情数据缓存条数
    api.data_len = 100
    api.setRequireBars(ETimeSpan.MIN_1,api.data_len)
    api.trade_product = str("rb1801.CF")
    # 查询初始资金
    account = api.getAccount(api.trade_product)
    api.capital = account.cashAvailable
    # 交易参数设定
    api.k1 = [-40.0,-3.0,-2.0,2.0,3.0,40.0]
    api.weight = [0.5,0.3, 0.0, 0.3, 0.5]
    api.trade_peroid = 60 # 每小时更新一次网格临界线
    api.minute_num = 0
    api.level  = 3.0
    api.volume = []
    api.band   = []
def onBeforeMarketOpen(api, trade_date):
    print(trade_date)
    api.tradeday = trade_date
    ##  订阅行情
    api.setFocusSymbols( api.trade_product)
def onBar(api,data):
    if (api.minute_num % api.trade_peroid) == 0:
        # 获取过去300个数据计算临界线
        data01 = api.getBarsHistory(data.symbol, timeSpan=ETimeSpan.MIN_1, count=api.data_len, df=False)
        close = []
        for ind01 in data01:
            close.append(ind01.close)
        api.band = np.mean(close)+np.array(api.k1)*np.std(close)
    # 计算网格状态
    grid = pd.cut([data.close],api.band,labels=[0,1,2,3,4])[0]
    print(grid)
    # 更新计算交易量
    api.volume = []
    for weight in api.weight:
        api.volume.append(lots(api, data, weight))
    api.minute_num += 1
    # 查询持仓
    position_long = api.getSymbolPosition(symbol=data.symbol, positionSide=EPositionSide.LONG)
    position_short = api.getSymbolPosition(symbol=data.symbol, positionSide=EPositionSide.SHORT)
    if not position_short.posQty and not position_long.posQty and grid != 2:
        if grid >= 3:
            api.targetPosition(symbol=data.symbol, qty=api.volume[grid], positionSide=EPositionSide.LONG)
            print("市价开多：", data.symbol)
        if grid <= 1:
            api.targetPosition(symbol=data.symbol, qty=api.volume[grid], positionSide=EPositionSide.SHORT)
            print("市价开空：", data.symbol)
    elif position_long.posQty:
        if grid >= 3:
            api.targetPosition(symbol=data.symbol, qty=api.volume[grid], positionSide=EPositionSide.LONG)
            print("市价加多：", data.symbol)
        elif grid == 2:
            api.targetPosition(symbol=data.symbol, qty=0, positionSide=EPositionSide.LONG)
            print("市价平多：", data.symbol)
        elif grid <= 1:
            api.targetPosition(symbol=data.symbol, qty=0, positionSide=EPositionSide.LONG)
            api.targetPosition(symbol=data.symbol, qty=api.volume[grid], positionSide=EPositionSide.SHORT)
            print("市价平多开空：", data.symbol)
    elif position_short.posQty:
        if grid <= 1:
            api.targetPosition(symbol=data.symbol, qty=api.volume[grid], positionSide=EPositionSide.SHORT)
            print("市价加空：", data.symbol)
        elif grid == 2:
            api.targetPosition(symbol=data.symbol, qty=0, positionSide=EPositionSide.SHORT)
            print("市价平多：", data.symbol)
        elif grid >= 3:
            api.targetPosition(symbol=data.symbol, qty=0, positionSide=EPositionSide.SHORT)
            api.targetPosition(symbol=data.symbol, qty=api.volume[grid], positionSide=EPositionSide.LONG)
            print("市价平空开多：", data.symbol)


def lots(api, data,weight):
    # 获取账户资金计算下单手数
    refdata = api.getRefData(data.symbol)
    multiper = refdata.valuePerUnit
    return (int(api.capital * api.level*weight / data.close / multiper))