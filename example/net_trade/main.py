#!/usr/bin/env python
# -*- coding: utf-8 -*-
from etasdk import *

if __name__ == '__main__':
    # GlobalConfig.setBackTestParam(startDate=20180401, endDate=20180502)
    # GlobalConfig.setMatchParams(timeSpan=ETimeSpan.MIN_1)#, timeRanges=[('09:51', '09:50'), ('14:10', '13:55')]);
    StrategyProxy('config.json').start()