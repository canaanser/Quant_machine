# -*- coding: utf-8 -*-
"""文件单实盘执行后端 FileOrderBroker (core/trade/file_order_broker.py, 2026-09-08)
职责(老板确认): 接收订单 → 生成文件单进 scan 目录 → 读成交回执 → 更新台账。
只做执行; 不做风控判断(core/risk), 不做策略决策(core/strategy)。

对齐 BrokerAdapter(abstract): get_account_info / place_order / get_order_status / get_current_price
实现要点:
  - place_order: 经 core.lib.orderfile 写入 <scan_dir>/<ts>.order.csv + .fin(终端扫单执行)
  - 成交回执: 读 <push_dir>/<account_id>/execution_report.dbf (dbfread)
  - sync_fills(): 新成交按 sid 去重自动记台账(core/trade/ledger)
用法:
  from core.trade.file_order_broker import FileOrderBroker
  br = FileOrderBroker()                      # 读取 outputs/emq_config.json
  oid = br.place_order("603256", "BUY", 400, 126.79)
  br.sync_fills()
"""
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..struct.standard_structures import AccountInfo, PositionInfo
from .base_adapter import BrokerAdapter
from ..lib import orderfile, quotes
from ..lib.dbfread import read_dbf
from . import ledger

STATUS_MAP = {1: "PENDING", 2: "PENDING", 3: "FILLED", 5: "CANCELLED", 8: "REJECTED", 10: "PENDING", 12: "CANCELLED"}


class FileOrderBroker(BrokerAdapter):
    """东财量化终端 文件单 执行后端"""

    def __init__(self, scan_dir: Optional[str] = None, push_dir: Optional[str] = None,
                 account_id: Optional[str] = None):
        root = Path(__file__).parent.parent.parent
        cfg_p = root / "outputs" / "emq_config.json"
        try:
            c = json.load(open(cfg_p, encoding="utf-8"))
        except Exception:
            c = {}
        self.account_id = account_id or c.get("account_id", "")
        self.scan_dir = Path(scan_dir) if scan_dir else Path(c.get("scan_dir", "Stream/staging"))
        self.push_dir = Path(push_dir) if push_dir else Path(c.get("push_dir", ""))
        self._status_cache = {}

    # ---------- 下单 ----------
    def place_order(self, symbol: str, action: str, volume: int,
                    price_limit: Optional[float] = None) -> str:
        """写文件单; 返回订单号(sid)"""
        orders = [(action.upper(), symbol, int(volume),
                   price_limit if price_limit is not None else 0.0, "")]
        fpath = orderfile.build_and_write(self.scan_dir, self.account_id, orders, make_fin=True)
        # sid = 文件名前缀 BUY/SELL + 时间戳
        name = fpath.name  # <ts>.order.csv
        prefix = "BUY" if action.upper() == "BUY" else "SELL"
        return prefix + name.split(".order.csv")[0].split("_", 1)[1].replace(".", "")


    def place_batch(self, orders, make_fin=True):
        """一批订单写一个 .order.csv + .fin; orders: [(action, code, shares, px, name)]*.
        返回 sid 列表"""
        fpath = orderfile.build_and_write(self.scan_dir, self.account_id,
                                          orders, make_fin=make_fin)
        sids = []
        name = fpath.name
        ts = name.split(".order.csv")[0]
        for k, o in enumerate(orders, 1):
            prefix = "BUY" if o[0].upper() == "BUY" else "SELL"
            sids.append(prefix + ts + str(k))
        return sids

    # ---------- 成交回执 ----------
    def _exec_report_rows(self):
        erp = self.push_dir / self.account_id / "execution_report.dbf"
        if not erp.exists():
            return []
        _, rows = read_dbf(erp)
        return rows

    def get_order_status(self, order_id: str) -> dict:
        """按 sid 查回执/委托状态; 无则 PENDING(待扫单)"""
        if order_id in self._status_cache:
            return self._status_cache[order_id]
        for r in self._exec_report_rows():
            sid = str(r.get("SID") or "").strip()
            if sid == order_id:
                px = float(r.get("PRICE") or 0) or float(r.get("FILLEDVWAP") or 0)
                vol = int(float(r.get("VOLUME") or 0))
                st = {"status": "FILLED", "filled_price": px, "filled_volume": vol}
                self._status_cache[order_id] = st
                return st
        st = {"status": "PENDING", "filled_price": None, "filled_volume": 0}
        self._status_cache[order_id] = st
        return st

    def sync_fills(self, sell_reason: str = "文件单") -> int:
        """读成交回执, 新成交(sid 去重)自动记台账; 返回新增笔数"""
        rows = self._exec_report_rows()
        d = ledger._load()
        seen = set(d.setdefault("meta", {}).setdefault("seen_sids", []))
        held = set(d["positions"].keys())
        added = 0
        for r in rows:
            et = r.get("EXEC_TYPE")
            if et is not None:
                try:
                    if abs(float(et)) != 15:
                        continue
                except Exception:
                    pass
            sid = str(r.get("SID") or "").strip()
            if not sid or sid in seen:
                continue
            sym = str(r.get("SYMBOL") or "")
            code = None
            for ch in sym:
                if ch.isdigit():
                    code = ch
                    break
            import re
            m = re.search(r"(\d{6})", sym)
            if not m:
                continue
            code = m.group(1)
            if code in held:
                seen.add(sid)
                continue
            try:
                vol = int(float(r.get("VOLUME") or 0))
                px = float(r.get("PRICE") or 0)
            except Exception:
                continue
            biz = str(r.get("ORDER_BIZ") or "").strip()
            date = str(r.get("CREATED_AT") or "")[:10].replace("-", "")
            if biz == "1":
                ledger.buy(code, date, vol, px, code)
            elif biz == "2":
                ledger.sell(code, date, px, sell_reason)
            else:
                continue
            seen.add(sid)
            added += 1
        d["meta"]["seen_sids"] = sorted(seen)
        ledger._save(d)
        return added

    # ---------- 账户 ----------
    def get_account_info(self) -> AccountInfo:
        d = ledger._load()
        quotes_px = {}
        positions = []
        mv = 0.0
        codes = list(d["positions"].keys())
        try:
            quotes_px = quotes.live_px(codes)
        except Exception:
            quotes_px = {}
        for code, p in d["positions"].items():
            cur = quotes_px.get(code) or p["cost"]
            pos = PositionInfo(symbol=code, name=p.get("name", ""),
                               shares=p["shares"], avg_cost=p["cost"],
                               current_price=cur, market_value=round(p["shares"] * cur, 2))
            positions.append(pos)
            mv += pos.market_value
        return AccountInfo(total_asset=round(mv, 2), cash=0.0, frozen_cash=0.0,
                           positions=positions,
                           timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def get_current_price(self, symbol: str) -> float:
        px = quotes.live_px([symbol])
        return px.get(symbol, 0.0)
