#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals, division
from etasdk import *
import sys

try:
    import talib
except:
    print('请安装TA-Lib库')
    sys.exit(-1)

'''
本策略为股票日内回转交易。
1、首先买入600000.CS股票10000股底仓；
2、根据分钟数据计算MACD(12,26,9)：
在MACD>0的时候买入100股;在MACD<0的时候卖出100股
3、每日操作的股票数不超过原有仓位,并于收盘前把仓位调整至开盘前的仓位
撮合周期为:600000.CS分钟数据
回测时间为:2018-09-03 到2018-10-01
其他参数：按系统默认设置
'''


def onInitialize(api):
    ## 全局参数设置
    print("SDK version:", GlobalConfig.getVersion())
    # 设置标的股票
    api.symbol = '600000.CS'
    # 订阅标的
    api.setSymbolPool(instsets=[], symbols=[api.symbol])
    api.setGroupMode(1000, False)
    # 设置行情数据缓存条数
    api.init_data_len = 120  # 数据长度
    api.setRequireBars(ETimeSpan.MIN_1, api.init_data_len)

    # 底仓
    api.total = 10000
    # 用于判定第一个仓位是否成功开仓
    api.first = 0
    # 日内回转每次交易100股
    api.trade_n = 100
    # 交易日
    api.tradeDate = [0, 0]
    # 每日仓位
    api.turnaround = [0, 0]
    # 用于判断是否触发了回转逻辑的计时
    api.ending = 0
    # 当日可平仓数量
    api.availableQty = 0


def onBeforeMarketOpen(api, trade_date):
    print("交易日：", trade_date)
    # 每日开盘前订阅行情
    api.setFocusSymbols(api.symbol)
    print("订阅%s的行情" % api.symbol)
    # 查询当日可平仓数量
    api.availableQty = api.getSymbolPosition(symbol=api.symbol, positionSide=EPositionSide.LONG)


def onBar(api, bar):
    if api.first == 0:
        # 购买10000股'600000.CS'股票
        api.targetPosition(symbol=bar.symbol, qty=api.total, positionSide=EPositionSide.LONG,
                           remark="open new position")
        print("open in new long postion by market order:", bar.symbol)
        api.first = 1.
        api.tradeDate[-1] = bar.tradeDate
        # 每天的仓位操作
        api.turnaround = [0, 0]
        return

    # 更新最新的日期
    api.tradeDate[0] = bar.tradeDate
    # 若为新的一天,获取可用于回转的昨仓
    if api.tradeDate[0] != api.tradeDate[-1]:
        api.ending = 0
        api.turnaround = [0, 0]
    if api.ending == 1:
        return

    # 若有可用的昨仓则操作
    if api.total > 0 and api.availableQty.availableQty > 0:
        # 获取时间序列数据
        recent_data = api.getBarsHistory(api.symbol, timeSpan=ETimeSpan.MIN_1, count=api.init_data_len, df=True,
                                         priceMode=EPriceMode.FORMER, skipSuspended=0)
        # 计算MACD线
        macd = talib.MACD(recent_data['close'].values)[0][-1]
        # 根据MACD>0则开仓,小于0则平仓
        if macd > 0:
            # 多空单向操作都不能超过昨仓位,否则最后无法调回原仓位
            if api.turnaround[0] + api.trade_n < api.total:
                # 计算累计仓位
                api.turnaround[0] += api.trade_n
                volume = api.total + api.turnaround[0] - api.turnaround[1]
                api.targetPosition(symbol=bar.symbol, qty=volume, positionSide=EPositionSide.LONG,
                                   remark="open new position")
                print("open in new long postion by market order:%s : %i" % (bar.symbol, api.trade_n))
        elif macd < 0:
            if api.turnaround[1] + api.trade_n < api.total:
                api.turnaround[1] += api.trade_n
                volume = api.total + api.turnaround[0] - api.turnaround[1]
                api.targetPosition(symbol=bar.symbol, qty=volume, positionSide=EPositionSide.LONG,
                                   remark="close position")
                print("close long postion by market order:%s : %i" % (bar.symbol, api.trade_n))
        # 临近收盘时若仓位数不等于昨仓则回复所有仓位
        if int(bar.timeStr[9:13]) >= 1455:
            print("收盘前回复仓位")
            symbolposition = api.getSymbolPosition(symbol=api.symbol, positionSide=EPositionSide.LONG)
            if symbolposition.posQty != api.total:
                api.targetPosition(symbol=bar.symbol, qty=api.total, positionSide=EPositionSide.LONG,
                                   remark="target position")
                print("To target position:%d" % (api.total))
                api.ending = 1
        # 更新过去的日期数据
        api.tradeDate[-1] = api.tradeDate[0]
