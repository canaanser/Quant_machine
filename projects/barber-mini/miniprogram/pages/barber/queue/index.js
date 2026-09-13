import { priorityLabel } from "../../../utils/cloud.js";
Page({
  data: { list: [] },
  onLoad() { this.load(); },
  load() {
    // 真源是云函数视图；这里给 mock 兜底，云环境就绪后换成 api 拉取 + watch
    const mock = [
      { _id: "o1", customerName: "小王", serviceName: "剪发", priority: 0, status: "queuing" },
      { _id: "o2", customerName: "李姐", serviceName: "烫发", priority: 1, status: "reserved" },
      { _id: "o3", customerName: "张叔", serviceName: "剪发", priority: 2, status: "queuing" },
    ];
    this.setData({ list: mock.map((o) => ({ ...o, tag: priorityLabel(o.priority) })) });
  },
});
