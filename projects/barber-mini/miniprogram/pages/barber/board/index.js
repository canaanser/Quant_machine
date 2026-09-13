// 数据看板：范围筛选 + 客户维度（做了几次/多久/花多少）+ 排行榜 + 分布
import { api } from "../../../utils/cloud.js";

const RANGES = [{ k: "today", l: "今天" }, { k: "week", l: "本周" }, { k: "month", l: "本月" }, { k: "all", l: "全部" }];
const SORTS = [{ k: "revenue", l: "按消费" }, { k: "count", l: "按次数" }, { k: "ms", l: "按时长" }];
const TYPE_LABEL = { woman: "女士", man: "男士", elder: "老人", child: "小孩" };

Page({
  data: {
    ranges: RANGES, sorts: SORTS, range: "today", sort: "revenue",
    board: null, rank: [], customers: [], hideMoney: false, openKey: "",
    barMax: 1, hourMax: 1,
  },
  onShow() { this.load(); },
  async load() {
    try {
      const b = await api.board({ barberId: "b1", range: this.data.range });
      const barMax = Math.max(1, ...b.byService.map((x) => x.count));
      const hourMax = Math.max(1, ...b.byHour.map((x) => x.count));
      this.setData({ board: b, barMax, hourMax, openKey: "" });
      this.applySort();
    } catch (e) {
      wx.showModal({ title: "看板读取失败", content: String((e && (e.errMsg || e.message)) || e).slice(0, 110), showCancel: false });
    }
  },
  applySort() {
    const b = this.data.board; if (!b) return;
    const key = this.data.sort;
    const list = [...b.customers].sort((x, y) => (key === "ms" ? y.ms - x.ms : key === "count" ? y.count - x.count : y.revenue - x.revenue));
    this.setData({
      customers: list.map((c) => ({
        ...c, min: Math.round(c.ms / 60000), avgMin: Math.round((c.avgMs || 0) / 60000),
        typeLabel: TYPE_LABEL[c.type] || "", rankText: "",
      })),
      rank: list.slice(0, 5),
      byService: b.byService.map((x) => ({ ...x, pct: Math.round((x.count / this.data.barMax) * 100), avgMin: Math.round(x.ms / Math.max(1, x.count) / 60000) })),
      byType: b.byType.map((x) => ({ ...x, label: TYPE_LABEL[x.type] || x.type })),
      byHour: b.byHour.map((x) => ({ ...x, h: Math.round((x.count / Math.max(1, this.data.hourMax)) * 150) + 10, label: x.hour + "点" })),
    });
  },
  pickRange(e) { this.setData({ range: e.currentTarget.dataset.k }, () => this.load()); },
  pickSort(e) { this.setData({ sort: e.currentTarget.dataset.k }, () => this.applySort()); },
  toggleEye() { this.setData({ hideMoney: !this.data.hideMoney }); },
  openCustomer(e) {
    const k = e.currentTarget.dataset.k;
    this.setData({ openKey: this.data.openKey === k ? "" : k });
  },
  money(v) { return this.data.hideMoney ? "∗∗∗" : v; },
});
