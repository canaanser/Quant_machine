"""卡尔曼滤波 + PID 动态仓位控制（2026-08-30 老板拍板方向）

原理（控制论经典组合）：
  卡尔曼 = 管"看清"：从带噪声的每日总资产观测中估计真实资产状态（去噪），
          用滤波后资产算"真实回撤"（不因单日噪声误触发）。
  PID    = 管"行动"：基于真实回撤做反馈控制，输出总仓位乘数 u(t)∈[0.1,1.0]。
          回撤浅 → u≈1（牛市满仓吃 beta）；回撤深 → u→0.1（熊市轻仓保命）。

哲学（老板 2026-08-30）：
  防跌不防涨（只对回撤做反馈，涨了不管——u 上限 1.0 不加仓）；
  不预测（回撤是已发生的事实，卡尔曼只用过去观测——无未来函数）；
  牛市多买/熊市少买冲突 → PID 连续平滑解决（回撤自己说了算，不靠人判断牛熊）。

参数（合理默认，防过拟合——不做针对特定池/行情的精调）：
  Q  过程噪声：资产真实变化幅度（默认 1e-4，变化慢）
  R  观测噪声：日估值噪声（默认 1e-2）
  D_target 目标回撤阈值：-0.25（回撤超 25% 开始降仓）
  Kp 比例系数：回撤每超阈值 1% → 按 Kp 降仓（默认 2.0：-25% 时 e=-0 → u 归中）
  Ki 积分系数：持续回撤累积降仓（默认 0.02，慢——防过拟合不敏感）
  Kd 微分系数：回撤加速时提前反应（默认 2.0）
"""


class KalmanPID:
    """一维卡尔曼（随机游走模型）+ PID 总仓位乘数"""

    def __init__(self, q: float = 1e-4, r: float = 1e-2,
                 d_target: float = -0.25, kp: float = 2.0,
                 ki: float = 0.02, kd: float = 2.0):
        self.q = q              # 过程噪声
        self.r = r              # 观测噪声
        self.d_target = d_target  # 目标回撤阈值（超了开始降仓）
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.x = None           # 滤波后状态估计（真实资产）
        self.p = 1.0            # 估计协方差
        self.peak = None        # 滤波后历史高点（回撤基准）
        self.e_prev = 0.0       # 上一日误差（微分项）
        self.e_integral = 0.0   # 误差积分（限幅防爆）

    def update(self, obs: float) -> tuple:
        """每日更新：卡尔曼预测+校正，返回 (滤波后资产 x̂, 真实回撤 dd)"""
        if self.x is None:
            self.x = float(obs)
        else:
            # 预测
            self.p += self.q
            # 校正
            k = self.p / (self.p + self.r)
            self.x += k * (float(obs) - self.x)
            self.p = (1 - k) * self.p
        # 回撤（滤波后值的历史高点）
        if self.peak is None or self.x > self.peak:
            self.peak = self.x
        dd = (self.x / self.peak - 1.0) if self.peak else 0.0
        return self.x, dd

    def ratio(self, drawdown: float) -> float:
        """PID → 总仓位乘数 u(t)∈[0.1, 1.0]（只对回撤反馈，防跌不防涨）"""
        e = drawdown - self.d_target  # 回撤深（负）→ e 负 → 降仓
        # 积分项（只累积"超阈值"的负误差——回撤浅于阈值不累积，避免牛市积分拉低）
        if e < 0:
            self.e_integral += e
            self.e_integral = max(self.e_integral, -5.0)  # 限幅
        else:
            self.e_integral *= 0.95  # 回撤恢复时积分缓慢衰减（防过拟合不敏感）
        d = e - self.e_prev
        self.e_prev = e
        u = 1.0 + self.kp * e + self.ki * self.e_integral + self.kd * d
        return max(0.1, min(1.0, u))
