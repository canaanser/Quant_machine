Component({
  properties: {
    barber: { type: Object, value: null },
    waiting: { type: Number, value: 0 },
    etaMin: { type: Number, value: 0 },
  },
  computed: {},
  data: { text: "加载中…", tone: "rest" },
  observers: {
    "barber, waiting, etaMin"(b, waiting, etaMin) {
      if (!b) return this.setData({ text: "加载中…", tone: "rest" });
      const tone = b.status === "idle" ? "free" : b.status === "busy" ? "busy" : "rest";
      const text = b.status === "idle" ? "空闲中，可立即到店"
        : b.status === "busy" ? `正在服务中（预计还需 ${etaMin || 20} 分钟）`
          : "休息中，暂不接单";
      this.setData({ text, tone, waiting });
    },
  },
});
