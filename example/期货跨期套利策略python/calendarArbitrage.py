#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function, absolute_import, unicode_literals
import sys
import datetime
import numpy as np
from etasdk import *
try:
    import statsmodels.tsa.stattools as ts
except:
    print('请安装statsmodels库')
    sys.exit(-1)

'''
期货策略：跨期套利
本策略根据EG两步法(1.序列同阶单整2.OLS残差平稳)判断序列具有协整关系后(若无协整关系则全平仓位不进行操作)
通过计算两个价格序列回归残差的均值和标准差并用均值加减0.9倍标准差得到上下轨
在价差突破上轨的时候做空价差;在价差突破下轨的时候做多价差
若有仓位,在残差回归至上下轨内的时候平仓
回测数据为:rb1801和rb1805的1min数据
回测时间为:2017-09-25 到2017-10-01
撮合周期：1分钟
'''


def onInitialize(api):
    # 设置响应模式
    api.setGroupMode(5000, False)
    # 设置bar长度
    api.data_len = 800
    # 进行套利的品种
    api.tickersCode = ['rb1801.CF', 'rb1805.CF']
    # 设置行情数据缓存
    api.setRequireData(instsets=['rb.PRD'], symbols=api.tickersCode, fields=[], bars=[(ETimeSpan.MIN_1, 900)])


def onBeforeMarketOpen(api, tradeDate):
    # print(tradeDate)
    api.trading_day = tradeDate
    # 订阅行情
    api.setFocusSymbols(api.tickersCode)


def onHandleData(api, time_exch):
    api.trade_date = datetime.datetime.fromtimestamp(time_exch / 1000)

    # 获取两个品种的时间序列
    data_01 = api.getBarsHistory(symbol=api.tickersCode[0], timeSpan=ETimeSpan.MIN_1, count=api.data_len + 1,
                                 priceMode=EPriceMode.FORMER, fields=None, df=True)
    close_01 = data_01["close"].values

    data_02 = api.getBarsHistory(symbol=api.tickersCode[1], timeSpan=ETimeSpan.MIN_1, count=api.data_len + 1,
                                 priceMode=EPriceMode.FORMER, fields=None, df=True)
    close_02 = data_02["close"].values

    # 展示两个价格序列的协整检验的结果
    beta, c, resid, result = cointegration_test(close_01, close_02)

    # 如果返回协整检验不通过的结果则全平仓位等待
    if not result:
        print('协整检验不通过,全平所有仓位')
        symbol_positions = api.getSymbolPositions()
        if symbol_positions:
            for symbol_obj in symbol_positions:
                if symbol_obj.positionSide == EPositionSide.SHORT:
                    api.targetPosition(symbol=symbol_obj.symbol, qty=0, positionSide=EPositionSide.SHORT)
                    LOG.INFO("close old contract short position:%s", symbol_obj.symbol)
                elif symbol_obj.positionSide == EPositionSide.LONG:
                    api.targetPosition(symbol=symbol_obj.symbol, qty=0, positionSide=EPositionSide.LONG)
                    LOG.INFO("close old contract long position:%s", symbol_obj.symbol)
        return

    # 计算残差的标准差上下轨
    mean = np.mean(resid)
    up = mean + 1.5 * np.std(resid)
    down = mean - 1.5 * np.std(resid)

    # 计算新残差
    resid_new = close_01[-1] - beta * close_02[-1] - c

    # 获取rb1801的多空仓位
    position_01_long = api.getSymbolPosition(symbol=api.tickersCode[0], positionSide=EPositionSide.LONG)
    position_01_short = api.getSymbolPosition(symbol=api.tickersCode[0], positionSide=EPositionSide.SHORT)

    if not position_01_long and not position_01_short:
        if resid_new > up:
            api.targetPosition(symbol=api.tickersCode[0], qty=1, positionSide=EPositionSide.SHORT)
            LOG.INFO("Open short at market price:%s", api.tickersCode[0])
            api.targetPosition(symbol=api.tickersCode[1], qty=1, positionSide=EPositionSide.LONG)
            LOG.INFO("Open long at market price:%s", api.tickersCode[1])

        if resid_new < down:
            api.targetPosition(symbol=api.tickersCode[0], qty=1, positionSide=EPositionSide.LONG)
            LOG.INFO("Open long at market price:%s", api.tickersCode[0])
            api.targetPosition(symbol=api.tickersCode[1], qty=1, positionSide=EPositionSide.SHORT)
            LOG.INFO("Open short at market price:%s", api.tickersCode[1])

    # 价差回归时平仓
    elif position_01_short:
        if resid_new <= up:
            api.targetPosition(symbol=api.tickersCode[0], qty=0, positionSide=EPositionSide.SHORT)
            api.targetPosition(symbol=api.tickersCode[1], qty=0, positionSide=EPositionSide.LONG)
            LOG.INFO("Clear all positions")

        # 跌破下轨反向开仓
        if resid_new < down:
            api.targetPosition(symbol=api.tickersCode[0], qty=1, positionSide=EPositionSide.LONG)
            LOG.INFO("Open long at market price:%s", api.tickersCode[0])
            api.targetPosition(symbol=api.tickersCode[1], qty=1, positionSide=EPositionSide.SHORT)
            LOG.INFO("Open short at market price:%s", api.tickersCode[1])

    elif position_01_long:
        if resid_new >= down:
            api.targetPosition(symbol=api.tickersCode[0], qty=0, positionSide=EPositionSide.SHORT)
            api.targetPosition(symbol=api.tickersCode[1], qty=0, positionSide=EPositionSide.LONG)
            LOG.INFO("Clear all positions")
        # 突破上轨开多
        if resid_new > up:
            api.targetPosition(symbol=api.tickersCode[0], qty=1, positionSide=EPositionSide.SHORT)
            LOG.INFO("Open short at market price:%s", api.tickersCode[0])
            api.targetPosition(symbol=api.tickersCode[1], qty=1, positionSide=EPositionSide.LONG)
            LOG.INFO("Open long at market price:%s", api.tickersCode[1])


def onTerminate(api, exitInfo):
    print("回测结束。。。")


# 协整检验的函数
def cointegration_test(series01, series02):
    urt_rb1801 = ts.adfuller(np.array(series01), 1)[1]
    urt_rb1805 = ts.adfuller(np.array(series02), 1)[1]
    # 同时平稳或不平稳则差分再次检验
    if (urt_rb1801 > 0.1 and urt_rb1805 > 0.1) or (urt_rb1801 < 0.1 and urt_rb1805 < 0.1):
        urt_diff_rb1801 = ts.adfuller(np.diff(np.array(series01)), 1)[1]
        urt_diff_rb1805 = ts.adfuller(np.diff(np.array(series02)), 1)[1]
        # 同时差分平稳进行OLS回归的残差平稳检验
        if urt_diff_rb1801 < 0.1 and urt_diff_rb1805 < 0.1:
            matrix = np.vstack([series02, np.ones(len(series02))]).T
            beta, c = np.linalg.lstsq(matrix, series01)[0]
            resid = series01 - beta * series02 - c
            if ts.adfuller(np.array(resid), 1)[1] > 0.1:
                result = 0.0
            else:
                result = 1.0
            return beta, c, resid, result

        else:
            result = 0.0
            return 0.0, 0.0, 0.0, result

    else:
        result = 0.0
        return 0.0, 0.0, 0.0, result
