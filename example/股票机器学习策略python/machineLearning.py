#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import
from etasdk import *
import numpy as np
from datetime import datetime
import sys
try:
    from sklearn import svm
except:
    print('please install scikit-learn and numpy with mkl')
    sys.exit(-1)

'''
股票策略：机器学习
本策略选取了七个特征变量组成了滑动窗口长度为20天的训练集, 训练了一个二分类的支持向量机模型来预测股票的上涨和下跌.
若每个星期一没有仓位则计算标的股票近20个交易日的特征变量进行预测,并在预测结果为上涨的时候购买标的.
若已经持有仓位则在盈利大于10%的时候止盈,在星期五损失大于2%的时候止损.
特征为:1.收盘价/均值2.现量/均量3.最高价/均价4.最低价/均价5.现量6.区间收益率7.区间标准差
训练数据为:600036.CS招商银行,时间从20170507到20171107
回测时间为:20171108-20181101
撮合周期：日K
'''

#初始化
def onInitialize(api):
    # 数据滑窗
    # 回测时间20171108-20181101
    api.train_start_date = 20170507
    api.train_end_date = 20171107
    api.trainFinished = False
    api.symbol = "600036.CS" # 订阅招商银行股票
    api.ratio = 0.8
    api.dataWindow = 20
    api.clf = None
    # 设置股票池，因子以及K线类型
    api.setRequireData(symbols=[api.symbol],
                       bars=[(ETimeSpan.DAY_1, 1000)])
    #设置按组回调
    api.setGroupMode(timeOutMs=10000, onlyGroup = False);

# train
def trainHistoryData(api):
    # 获取目标股票的daily历史行情
    recent_data = api.getBarsHistory(api.symbol, timeSpan=ETimeSpan.DAY_1, count=1000, df=True, \
                                   priceMode=EPriceMode.FORMER, skipSuspended=0)
    recent_data.fillna(method="ffill")
    # 获取目标股票的训练数据集
    recent_data = recent_data[(recent_data["tradeDate"] >= api.train_start_date) & (recent_data["tradeDate"] <= api.train_end_date)]
    days_value = recent_data['tradeDate'].values
    days_close = recent_data['close'].values
    days = []
    # 获取行情日期列表
    print('prepare training data for SVM', api.train_start_date, " - ", api.train_end_date)
    for i in range(len(days_value)):
        days.append(days_value[i])

    x_all = []
    y_all = []
    for index in range(api.dataWindow, (len(days) - 5)):
        # 计算一个月共20个交易日相关数据
        start_day = days[index - api.dataWindow]
        end_day = days[index]
        data = recent_data[(recent_data["tradeDate"] >= start_day) &(recent_data["tradeDate"] <= end_day)]
        close = data['close'].values
        max_x = data['high'].values
        min_n = data['low'].values
        amount = data['totalVolume'].values
        volume = []
        for i in range(len(close)):
            volume_temp = amount[i] / close[i]
            volume.append(volume_temp)

        close_mean = close[-1] / np.mean(close)  # 收盘价/均值
        volume_mean = volume[-1] / np.mean(volume)  # 现量/均量
        max_mean = max_x[-1] / np.mean(max_x)  # 最高价/均价
        min_mean = min_n[-1] / np.mean(min_n)  # 最低价/均价
        vol = volume[-1]  # 现量
        return_now = close[-1] / close[0]  # 区间收益率
        std = np.std(np.array(close), axis=0)  # 区间标准差

        # 将计算出的指标添加到训练集X
        # features用于存放因子
        features = [close_mean, volume_mean, max_mean, min_mean, vol, return_now, std]
        x_all.append(features)

    # 准备算法需要用到的数据
    for i in range(len(days_close) - api.dataWindow - 5):
        if days_close[i + api.dataWindow + 5] > days_close[i + api.dataWindow]:
            label = 1
        else:
            label = 0
        y_all.append(label)

    x_train = x_all[: -1]
    y_train = y_all[: -1]
    # 训练SVM
    api.clf = svm.SVC(C=1.0, kernel=str('rbf'), degree=3, gamma=str('auto'), coef0=0.0, shrinking=True, probability=False,
                          tol=0.001, cache_size=400, verbose=False, max_iter=-1,
                          decision_function_shape=str('ovr'), random_state=None)
    print(x_train, y_train)
    api.clf.fit(x_train, y_train)
    #print('finished training!')

#盘前运行，用于选股逻辑；必须实现，用来设置当日关注的标的
def onBeforeMarketOpen(api,tradeDate):
    print("on date", tradeDate)
    # 设置当天需要交易的股票，如果历史上有过持仓了，则系统会默认自动关注
    api.setFocusSymbols(api.symbol)
    # firstly time to run, need to train the system
    if not api.trainFinished:
        trainHistoryData(api)
        api.trainFinished = True

    # 当前工作日
    weekday = datetime.strptime(str(tradeDate), '%Y%m%d').isoweekday()
    # 获取持仓
    symbolposition = api.getSymbolPosition(api.symbol)

    # 获取预测用的历史数据
    data = api.getBarsHistory(api.symbol, timeSpan=ETimeSpan.DAY_1, count=api.dataWindow, df=True, \
                              priceMode=EPriceMode.FORMER, skipSuspended=0)
    data.fillna(method="ffill")
    # 如果是新的星期一且没有仓位则开始预测
    if not symbolposition or symbolposition.posQty == 0 and weekday == 1:
        close = data['close'].values
        train_max_x = data['high'].values
        train_min_n = data['low'].values
        train_amount = data['totalVolume'].values
        volume = []
        for i in range(len(close)):
            volume_temp = train_amount[i] / close[i]
            volume.append(volume_temp)

        close_mean = close[-1] / np.mean(close)
        volume_mean = volume[-1] / np.mean(volume)
        max_mean = train_max_x[-1] / np.mean(train_max_x)
        min_mean = train_min_n[-1] / np.mean(train_min_n)
        vol = volume[-1]
        return_now = close[-1] / close[0]
        std = np.std(np.array(close), axis=0)

        # 得到本次输入模型的因子
        features = [close_mean, volume_mean, max_mean, min_mean, vol, return_now, std]
        features = np.array(features).reshape(1, -1)
        if api.clf:
            prediction = api.clf.predict(features)[0]
        else:
            print("[ERR]: train model is None")

        # 获取账户信息
        account = api.getAccount(api.symbol)
        totAssets = account.totAssets
        eachTickerCapital = totAssets * api.ratio
        # 若预测值为上涨则开仓
        if prediction == 1:
            # 获取昨收盘价
            price = close[-1]
            # 开仓
            qty = int(eachTickerCapital / price / 100) * 100
            api.targetPosition(symbol=api.symbol, qty=qty)
            print(api.symbol, 'open positions for qty of', qty)

    # 当涨幅大于10%,平掉所有仓位止盈
    elif symbolposition and data.close.values[-1] / symbolposition.posPrice >= 1.10:
        if symbolposition.posQty != 0:
            api.targetPosition(symbol=api.symbol, qty=0)
            print('stop win, close positions for', api.symbol)

    # 当时间为周五并且跌幅大于2%时,平掉所有仓位止损
    elif symbolposition and data.close.values[-1] / symbolposition.posPrice < 1.02 and weekday == 5:
        if symbolposition.posQty != 0:
            api.targetPosition(symbol=api.symbol, qty=0)
            print('stop loss, close positions for', api.symbol)

#策略终止时响应
def onTerminate(api,exitInfo):
    LOG.INFO ("***************onTerminate*********")
    print ("***************onTerminate*********")
