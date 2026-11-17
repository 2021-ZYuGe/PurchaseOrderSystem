# -*- coding: utf-8 -*-
"""数据访问边界：api/services 只从这里取数据，不直接碰 SQL。

底层实现暂由 app/infra/store.py 承担；后续拆分时只需替换这里的实现。
"""
