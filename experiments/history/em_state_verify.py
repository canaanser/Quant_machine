"""EM 状态空间可行性验证（2026-08-30 老板：K线输入→状态估计→控制收益率）
模型：局部水平趋势（local linear trend）——状态 α=(水平μ, 趋势β)
  y_t = μ_t + ε_t         观测：价格 = 水平 + 观测噪声
  μ_t = μ_{t-1} + β_{t-1} + η_t   水平变化 = 前趋势
  β_t = β_{t-1} + ζ_t     趋势随机游走（动力学成分）
EM 估计噪声参数；卡尔曼滤波输出每日趋势状态 β̂_t
判决实验：β̂_t 分 5 组 → 未来 20 日收益——趋势强组收益显著更高 = 模型前提成立
"""
import numpy as np
import pandas as pd


class LocalLinearTrend:
    """局部水平趋势状态空间模型：EM 估计 + 卡尔曼滤波"""

    def __init__(self, y: np.ndarray):
        self.y = np.asarray(y, float)
        self.n = len(self.y)
        self.T = np.array([[1.0, 1.0], [0.0, 1.0]])          # 状态转移
        self.Z = np.array([[1.0, 0.0]])                       # 观测矩阵（只看水平）
        self.R = 5e-3                                          # 观测噪声（初值）
        self.Q = np.array([[1e-3, 0.0], [0.0, 1e-4]])         # 过程噪声（初值）

    def _kalman_filter(self, R: float, Q: np.ndarray):
        """前向卡尔曼滤波，返回状态估计序列"""
        T, Z, y, n = self.T, self.Z, self.y, self.n
        a = np.zeros((n, 2))
        P = np.zeros((n, 2, 2))
        a_cur = np.array([y[0], 0.0])                          # 初始：水平=首价，趋势=0
        P_cur = np.array([[1e2, 0.0], [0.0, 1e2]])             # 初始协方差（大=不确定）
        for t in range(n):
            # 预测
            a_pred = T @ a_cur
            P_pred = T @ P_cur @ T.T + Q
            # 更新
            F = (Z @ P_pred @ Z.T)[0, 0] + R
            K = (P_pred @ Z.T)[:, 0] / F
            innov = y[t] - (Z @ a_pred)[0]
            a_cur = a_pred + K * innov
            P_cur = P_pred - np.outer(K, (Z @ P_pred)[0])
            a[t] = a_cur
            P[t] = P_cur
        return a, P

    def em(self, max_iter=60, tol=1e-8):
        """EM 迭代：E步=卡尔曼滤波，M步=重估噪声参数（简化：用滤波残差/状态增量）"""
        for it in range(max_iter):
            a, P = self._kalman_filter(self.R, self.Q)
            # M步：观测噪声 = 残差方差
            resid = self.y - a[:, 0]
            R_new = max(float(np.mean(resid ** 2)), 1e-6)
            # M步：过程噪声 = 状态增量方差
            d_mu = np.diff(a[:, 0])
            d_beta = np.diff(a[:, 1])
            Q_new = np.array([
                [max(float(np.mean(d_mu ** 2)), 1e-8), 0.0],
                [0.0, max(float(np.mean(d_beta ** 2)), 1e-8)],
            ])
            if abs(R_new - self.R) < tol and np.abs(Q_new - self.Q).max() < tol:
                break
            self.R, self.Q = R_new, Q_new
        return self.R, self.Q

    def filter(self):
        """滤波，返回 (水平, 趋势) 状态序列"""
        a, _ = self._kalman_filter(self.R, self.Q)
        return a[:, 0], a[:, 1]


def run_verification(price: pd.Series, fwd_days: int = 20, n_groups: int = 5):
    """对一只票：EM+卡尔曼 → 趋势状态分组 → 未来收益"""
    y = price.dropna().to_numpy(float)
    if len(y) < 120:
        return None
    mdl = LocalLinearTrend(y)
    mdl.em()
    mu, beta = mdl.filter()
    # 未来收益（20日）
    ret_fwd = pd.Series(y).shift(-fwd_days) / y - 1
    beta_s = pd.Series(beta)
    # 去 NaN
    valid = ret_fwd.notna() & beta_s.notna()
    b = beta_s[valid].to_numpy()
    r = ret_fwd[valid].to_numpy()
    if len(b) < 100:
        return None
    # 分 5 组（按趋势状态）
    q = pd.qcut(b, n_groups, labels=False, duplicates='drop')
    groups = []
    for g in range(n_groups):
        mask = q == g
        if mask.sum() >= 5:
            groups.append((g, float(np.mean(r[mask])), mask.sum()))
    return groups, float(mdl.R), mdl.Q[1, 1]


if __name__ == '__main__':
    import warnings; warnings.filterwarnings('ignore')
    from core.data_loader import load_data
    tickers = ['000657', '002156', '002428', '300502', '600522']
    md = load_data(source='stockdb_http', tickers=tickers,
                   start='2020-01-01', end='2026-08-27', frequency='1d', fq='qfq')
    print(f"\n{'='*64}\nEM状态空间可行性验证（局部水平趋势模型）\n{'='*64}")
    all_rows = []
    for code in md.price.columns:
        res = run_verification(md.price[code])
        if res is None:
            continue
        groups, R, Q_bb = res
        print(f"\n📈 {code}  (观测噪声R={R:.2e}, 趋势噪声Qζ={Q_bb:.2e})")
        print(f"   趋势状态分组 → 未来20日收益均值：")
        for g, mean_ret, cnt in groups:
            bar = '█' * int(abs(mean_ret) * 200)
            print(f"     组{g}（趋势{'强' if g >= (len(groups)-1)//2 else '弱'}）: {mean_ret:+7.2%}  n={cnt} {bar}")
            all_rows.append({'code': code, 'group': g, 'ret': mean_ret, 'n': cnt})
    if all_rows:
        df = pd.DataFrame(all_rows)
        piv = df.pivot_table(index='code', columns='group', values='ret', aggfunc='mean')
        print(f"\n{'='*64}\n汇总：趋势状态 vs 未来20日收益（组0=趋势最弱，组4=趋势最强）\n{'='*64}")
        print(piv.round(4))
        if len(piv) > 0 and piv.shape[1] >= 2:
            weak = piv.iloc[:, 0].mean()
            strong = piv.iloc[:, -1].mean()
            print(f"\n✅ 趋势最弱组平均: {weak:+.2%}  趋势最强组平均: {strong:+.2%}")
            print(f"   差值: {strong - weak:+.2%}  → {'模型前提成立（趋势状态可预测收益）' if strong > weak else '前提不成立（趋势状态与收益无关/反向）'}")
