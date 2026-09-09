from dataclasses import dataclass, field
import pandas as pd

@dataclass
class metadata:
    """
    标准化市场数据容器（数据契约）
    作为整个回测系统的唯一数据接口，所有数据源必须适配为此格式。
    """
    price: pd.DataFrame
    """行情数据：索引为日期，列为股票代码，值为调整后收盘价"""
    
    benchmark: pd.Series
    benchmark_price: pd.Series = field(default_factory=pd.Series)
    
    open_price: pd.DataFrame = field(default_factory=pd.DataFrame)
    """开盘价：索引为日期，列为股票代码"""
    
    high_price: pd.DataFrame = field(default_factory=pd.DataFrame)
    """最高价：索引为日期，列为股票代码"""
    
    low_price: pd.DataFrame = field(default_factory=pd.DataFrame)
    """最低价：索引为日期，列为股票代码"""
    
    volume: pd.DataFrame = field(default_factory=pd.DataFrame)
    """成交量：索引为日期，列为股票代码"""
    
    info: pd.DataFrame = field(default_factory=pd.DataFrame)
    """股票元数据：索引为股票代码，包含 name, sector 等信息"""
    
    @property
    def symbols(self):
        return self.price.columns.tolist()
    
    @property
    def start_date(self):
        return self.price.index.min()
    
    @property
    def end_date(self):
        return self.price.index.max()
    
    def align(self):
        common_idx = self.price.index.intersection(self.benchmark.index)
        self.price = self.price.loc[common_idx]
        self.benchmark = self.benchmark.loc[common_idx]
        
        # 对齐所有 OHLCV 字段
        if not self.open_price.empty:
            common_idx = self.price.index.intersection(self.open_price.index)
            self.price = self.price.loc[common_idx]
            self.benchmark = self.benchmark.loc[common_idx]
            self.open_price = self.open_price.loc[common_idx]
        if not self.high_price.empty:
            common_idx = self.price.index.intersection(self.high_price.index)
            self.price = self.price.loc[common_idx]
            self.benchmark = self.benchmark.loc[common_idx]
            self.high_price = self.high_price.loc[common_idx]
        if not self.low_price.empty:
            common_idx = self.price.index.intersection(self.low_price.index)
            self.price = self.price.loc[common_idx]
            self.benchmark = self.benchmark.loc[common_idx]
            self.low_price = self.low_price.loc[common_idx]
        if not self.volume.empty:
            common_idx = self.price.index.intersection(self.volume.index)
            self.price = self.price.loc[common_idx]
            self.benchmark = self.benchmark.loc[common_idx]
            self.volume = self.volume.loc[common_idx]
        if not self.benchmark_price.empty:
            common_idx = self.price.index.intersection(self.benchmark_price.index)
            self.price = self.price.loc[common_idx]
            self.benchmark = self.benchmark.loc[common_idx]
            self.benchmark_price = self.benchmark_price.loc[common_idx]
        return self
    
    def validate(self):
        assert not self.price.empty, "价格数据为空"
        assert not self.benchmark.empty, "基准数据为空"
        assert self.price.index.equals(self.benchmark.index), "日期索引未对齐"
        return True
    
    def get_ohlc(self, symbol: str) -> pd.DataFrame:
        """获取单只股票的完整 OHLCV 数据"""
        if symbol not in self.symbols:
            raise ValueError(f"股票 {symbol} 不存在于 metadata 中")
        
        # 处理可能的数据缺失：如果某一列不存在，用 close 填充
        open_col = self.open_price[symbol] if symbol in self.open_price.columns else self.price[symbol]
        high_col = self.high_price[symbol] if symbol in self.high_price.columns else self.price[symbol]
        low_col = self.low_price[symbol] if symbol in self.low_price.columns else self.price[symbol]
        volume_col = self.volume[symbol] if symbol in self.volume.columns else pd.Series(0, index=self.price.index)
        
        df = pd.DataFrame({
            'open': open_col,
            'high': high_col,
            'low': low_col,
            'close': self.price[symbol],
            'volume': volume_col,
        }).dropna()
        return df