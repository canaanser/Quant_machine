<font size="6">**东方财富证券极速行情系统北交所极速行情API开发手册(Ver2.23.0)**</font><br>



<font size="6">文档说明</font>

<table><tbody>
    <tr>
        <th>日期</th><th>api 版本</th><th>修订摘要</th>
    </tr>
    <tr>
        <td>2025.12.12</td><td>2.23.0</td><td>API初版</td>
    </tr>
</table>

<font size="6">前言</font>

本接口规范用以指导开发通过QuoteApiBse对接的方式访问东财北交所快速行情系统，获取快照的相关数据。

本接口规范描述内容包括可开展的业务、必要的运行指导以及详细的数据交换格式。



#  1.QuoteApiBse介绍

本部分主要介绍极速行情系统的接口，包括：

* QuoteApiBse简介
* QuoteApiBse运行模式
* QuoteApiBse编程接口

## 1.1.QuoteApiBse简介

### 1.1.1. 背景

 为帮助客户实现快速交易并获取实时行情，东方财富证券推出了极速行情系统。客户端系统只需调用QuoteApiBse，即可与北交所极速行情系统进行对接。在接收到极速行情系统的行情数据后，QuoteApiBse 将主动回调客户端系统。

### 1.1.2. 简介

&emsp;&emsp;QuoteApiBse 是一个基于C++的类库，通过使用和扩展类库提供的接口来实现全部的行情功能，支持北交所快照相关数据。

&emsp;&emsp;该类库包含以下文件：

|文件路径        |文件名                    |文件描述                  |
|:--------------|:------------------------|:-------------------------|
|demo           |CMakeLists.txt           |示例编译文件                |
|               |src/main.cpp         |示例主函数                 |
|               |src/quote_demo_bse.cpp           |示例接口方法封装            |
|               |src/quote_demo_bse.h             |示例接口方法头文件           |
|doc            |东方财富证券极速行情系统行情API bse开发手册               |                          |
| include |quote_api_bse.h          |定义行情相关接口            |
|               |quote_struct_bse.h       |定义北交所极速行情相关数据结构        |
| |quote_bse_define.h |定义北交所极速NQHQ相关数据结构 |
| lib | libemt_quote_api_bse.so                     | Linux行情接口动态链接库        |
|          |                                             |                                |

### 1.1.3. 发行的平台

目前发布了以下操作系统平台的版本：

* Intel Linux：包括.h文件和.so文件。

如果需要其他操作系统版本，请联系行情专线。

## 1.2. 运行模式

### 1.2.1. 工作线程

​		QuoteApiBse 使用 UDP 模式接收行情。客户系统应用程序根据配置的行情类别创建多个线程，即应用程序主线程与 n 个数据处理线程（负责接收上游服务的行情数据并处理相应的回调）。

​		QuoteApiBse 提供的接口回调由数据处理线程驱动。通过实现 SPI 中的接口方法，客户系统能够从极速行情系统接收所需数据。

### 1.2.2. 运行流程

客户系统和极速行情系统的交互过程分为2个阶段：

* 初始化阶段。
* 功能调用阶段。

#### 1.2.2.1. 初始化阶段

&emsp;&emsp;在初始化阶段，客户系统的程序必须完成如下步骤（具体代码请参考开发实例）：

|顺序    |客户系统    |调用方法|
|:------|:-----------|:-------|
|1     |创建一个QuoteApi实例             |QuoteApiBse::CreateQuoteApiBse|
|2     |产生一个事件处理的实例；（步骤1返回）|                        |
|3     |注册一个事件处理的实例；           |QuoteApiBse::RegisterSpi   |
|4     |设置登录参数（组播接收时可跳过该步骤）、配置需要接收的行情流                       |QuoteApiBse::SetChannelConfig|
|6 |启动工作线程 |QuoteApiBse::Start|
|6     |设置开发代码     |相关业务回调函数实现 |
|      |                                                              |                                |

&emsp;&emsp;<font color=red>*开发代码由我司人员提供，需客户申请。*</font>

### 1.2.3. 时序示例

&emsp;&emsp;QuoteApiBse 提供了两个接口，分别为QuoteApiBse和QuoteSpiBse。

&emsp;&emsp;客户系统可以通过QuoteApiBse发出操作请求，通过继承QuoteSpiBse并重载回调函数来处理极速行情系统的回复或响应。

### 1.2.4. 接收方式

#### 1.2.4.1. 单播接收模式
&emsp;&emsp;单播接收模式需要用户先登录行情网关，鉴权通过后可通过行情绑定的端口接收单播数据

#### 1.2.4.1. 组播接收模式

&emsp;&emsp;组播接收模式无需登录可直接接收行情数据





# 2. API公共接口

## 2.1. 业务支持索引
|方法|描述|
|:----|:----|
|[CreateQuoteApiBse](#createQuoteApiBse)|创建一个Quote API接口类实例|
|[RegisterSpi](#registerspi)|注册回调接口|
|[SetChannelConfig](#SetChannelConfig)|设置通道接收配置|
|[Start](#Start)|行情接收启动接口|
|[Stop](#Stop)| 行情接收停止接口            |
|[Release](#Release)| 关闭接口，释放资源          |
|[GetApiVersion](#GetApiVersion)|获取版本信息|

## 2.2. API接口描述

### 2.2.1. <a id="createQuoteApiBse">CreateQuoteApiBse</a>

```cpp
/**
 * @brief  创建API接口类实例
 * @param  save_file_path             API日志保存路径
 * @param  log_level                  API日志输出级别
 *
 * @return                            EMQ API类的实例
 */
static QuoteApiBse *CreateQuoteApiBse(const char *save_file_path, EMQ_LOG_LEVEL log_level = EMQ_LOG_LEVEL_DEBUG);
```

### 2.2.2. <a id="registerspi">RegisterSpi</a>
```cpp
/**
* @brief  注册回调接口类spi实例
* 
* @param  spi                        派生自回调接口类的实例
*/
virtual void RegisterSpi(QuoteSpiBse* spi) = 0;
```
### 2.2.3. <a id="SetChannelConfig">SetChannelConfig</a>
```cpp
/**
* @brief 设置通道接收配置, 同时进行内置系统配置最优检查
* 
* @param  login_config					行情登录配置
* @param  config						行情接收通道配置
* @param  num							配置数量
* @return                               配置是否成功，"0" 表示配置成功，非"0"表示配置失败
*/
virtual int32_t SetChannelConfig(EMQLoginConfigBse login_config, EMQUdpConfigBse *config, uint32_t num) = 0;
```

### 2.2.4. <a id="Start">Start</a>

```cpp
/**
 * @brief  								行情接收启动接口
 * 
 * @return 								启动是否成功，"0" 表示启动成功，非"0"表示启动失败
 */ 
virtual int32_t Start() = 0;
```

### 2.2.5. <a id="Stop">Stop</a>

```cpp
/**
 * @brief  								行情接收停止接口
 * 
 * @return 								停止是否成功，"0" 表示停止成功，非"0"表示停止失败
 */ 
virtual int32_t Stop() = 0;
```

### 2.2.6. <a id="Release">Release</a>

```cpp
/**
 * @brief  								关闭接口，释放资源
 */ 
virtual void Release() = 0;
```

### 2.2.7. <a id="GetApiVersion">GetApiVersion</a>

```cpp
/**
 * @brief  								获取版本信息
 * 
 * @return 								API版本号
 */ 
virtual const char *GetApiVersion() = 0;
```



# 3. API业务接口

## 3.1. 业务支持索引

|方法API|回调SPI|描述|
|:----|:----|-----|
| [GetPacketHardwareRXTs](#GetPacketHardwareRXTs) | 无      | 获取网卡收到行情包的硬件时间戳；仅可在对应的行情SPI回调内调用 |

## 3.2. API接口描述

### 3.2.1. <a id="GetPacketHardwareRXTs">GetPacketHardwareRXTs</a>

```cpp
/**
 * @brief  								获取网卡收到行情包的硬件时间戳；仅可在对应的行情SPI回调内调用
 * 
 * @return 								网卡收到行情包的硬件时间戳，单位ns
 */ 
virtual uint64_t GetPacketHardwareRXTs(void *packet) = 0;
```



# 4. SPI接口

## 4.1. 业务支持索引

| 方法                    | 描述           |
| ----------------------- | -------------- |
| [OnSnapBse](#OnSnapBse) | 深交所快照行情 |

## 4.2. SPI接口描述

### 4.2.1. <a id="OnSnapBse">OnSnapBse</a>

```cpp
/**
 *   北交所极速快照行情
 *   @param snap   北交所快照行情数据
 */
virtual void OnSnapBse(EMQBseSnap *snap) {}
```



# 5. 参数结构体

## 5.1. 参数结构体索引

#### 5.1.1. 公共结构体

| 结构体                                  | 描述               |
| --------------------------------------- | ------------------ |
| [EMQLoginConfigBse](#EMQLoginConfigBse) | 北交所行情登录配置 |
| [EMQUdpConfigBse](#EMQUdpConfigBse)     | 北交所行情接收配置 |



#### 5.1.1.1. 北交所相关结构体

| 结构体                                                   | 描述               |
| -------------------------------------------------------- | ------------------ |
| [EMQBseSnap](#EMQBseSnap)                           | 北交所快照消息     |


## 5.2. 参数结构体描述

### 5.2.1. <a id="EMQLoginConfigBse">EMQLoginConfigBse</a>

```cpp
// bse行情接收配置
struct EMQLoginConfigBse {
    char login_ip[IP_LEN];        // 登录服务器IP地址
    uint16_t login_port;          // 登录服务器端口
    char user_name[32];           // 用户名
    char user_pwd[32];            // 用户密码
};
```

| 标识           | 类型及长度                          | 描述                           |
| -------------- | ----------------------------------- | ------------------------------ |
| login_ip         | char[[IP_LEN](#IP_LEN)]           | 登录地址                       |
| login_port           | uint16_t                      | 登录端口                       |
| user_name     | char[32]                             | 用户名                       |
| user_pwd       | char[32]                            | 密码                         |



### 5.2.2. <a id="EMQUdpConfigBse">EMQUdpConfigBse</a>

```cpp
// bse行情接收配置
struct EMQUdpConfigBse {
  bool enable;                 // 是否启用
  EMQBseUdpRecvMode mode;      // 接收模式
  EMQType quote_type;          // 行情类型
  char eth_name[ETH_NAME_LEN]; // 网卡名
  char bind_ip[IP_LEN];        // 行情接收绑定地址
  uint16_t bind_port;          // 行情接收绑定端口
  int32_t rx_cpu_id;           // 用于接收的cpu id，-1表示不绑定
  int32_t handle_cpu_id;       // 用于处理的cpu id，-1表示不绑定
  int32_t rx_pkt_num;          // 接收内存大小 单位为4MB
  int32_t spsc_size;           // 缓存队列长度，单位K
};
```

| 标识           | 类型及长度                          | 描述                           |
| -------------- | ----------------------------------- | ------------------------------ |
| enable         | bool                                | 是否启用                       |
| mode           | [EMQBseUdpRecvMode](#EMQBseUdpRecvMode)         | 接收模式                       |
| quote_type     | EMQType                 | 行情类型                       |
| eth_name       | char[[ETH_NAME_LEN](#ETH_NAME_LEN)] | 网卡名                         |
| bind_ip   | char[[IP_LEN](#IP_LEN)]             | 行情接收绑定地址                       |
| bind_port | uint16_t                            | 行情接收绑定端口                       |
| rx_cpu_id      | int32_t                             | 用于接收的CPU ID，-1表示不绑定 |
| handle_cpu_id  | int32_t                             | 用于处理的CPU ID，-1表示不绑定 |
| rx_pkt_num     | int32_t                             | 接收内存大小 单位为4MB         |
| spsc_size      | int32_t                             | 缓存队列长度，单位K            |


### 5.2.11. <a id="EMQBseSnap">EMQBseSnap</a>

```cpp
// 北交所快照消息
// NQHQ.DBF广播行情数据体定义
typedef struct
{
	char DBFTIME[6];		// DBF文件当前时间,格式:HHMMSS
	char DBFSTATUS[4];		// DBF文件当前状态:0000 - 非收市行情(正式);0001 - 收市行情(正式);0002 - 盘后行情(正式);0010 - 非收市行情(测试);0011 - 收市行情(测试);0012 - 盘后行情(测试);
	char HQZQDM[6];			// 证券代码
	char  HQZQJC[8];		// 证券简称
	double HQZRSP;			// 昨日收盘价
	double  HQJRKP;			// 今日开盘价
	double  HQZJCJ;			// 最近成交价
	uint64_t HQCJSL;		// 成交数量
	double HQCJJE;			// 成交金额
	uint64_t HQCJBS;		// 成交笔数
	double HQZGCJ;			// 最高成交价
	double HQZDCJ;			// 最低成交价
	double HQSYL1;			// 市盈率1
	double HQSYL2;			// 市盈率2
	double HQJSD1;			// 价格升跌1
	double HQJSD2;			// 价格升跌2
	uint64_t  HQHYCC;		// 合约持仓量
	double HQSJW5;			// 卖价位五
	uint64_t HQSSL5;		// 卖数量五
	double HQSJW4;			// 卖价位四
	uint64_t HQSSL4;		// 卖数量四
	double HQSJW3;			// 卖价位三
	uint64_t HQSSL3;		// 卖数量三
	double HQSJW2;			// 卖价位二
	uint64_t HQSSL2;		// 卖数量二
	double HQSJW1;			// 卖价位一/叫卖揭示价
	uint64_t HQSSL1;		// 卖数量一
	double  HQBJW1;			// 买价位一/叫买揭示价
	uint64_t HQBSL1;		// 买数量一
	double  HQBJW2;			// 买价位二
	uint64_t HQBSL2;		// 买数量二
	double  HQBJW3;			// 买价位三
	uint64_t HQBSL3;		// 买数量三
	double  HQBJW4;			// 买价位四
	uint64_t HQBSL4;		// 买数量四
	double  HQBJW5;			// 买价位五
	uint64_t HQBSL5;		// 买数量五
}EMQBseSnap;
```




# 6. 附录

## 6.1. 字典定义


### 6.1.1. <a id="CommonDefine">通用常量定义</a>

| 枚举                                  | 取值 | 定义说明             |
| :------------------------------------ | :--- | :------------------- |
| <a id="IP_LEN">IP_LEN</a>             | 64   | IP字符串地址长度定义 |
| <a id="ETH_NAME_LEN">ETH_NAME_LEN</a> | 64   | Eth字符串长度定义    |

### 6.1.2. <a id="EMQBseType">北交所行情类别-EMQBseType</a>

| 枚举               | 取值 | 定义说明     |
| :----------------- | :--- | :----------- |
| kBseSnap     | 12    | 北交所快照     |


### 6.1.3. <a id="EMQBseUdpRecvMode">接收模式-EMQBseUdpRecvMode</a>

| 枚举    | 取值 | 定义说明            |
| :------ | :--- | :------------------ |
| kNormal | 0    |                     |
| kEFVI   | 1    | solarflare efvi接收 |


### 6.1.4. <a id="EMQExchangeType">交易所类型-EMQExchangeType</a>

| 枚举            | 取值 | 定义说明 |
| --------------- | ---- | -------- |
| EMQ_EXCHANGE_SH | 1    | 上交所   |
| EMQ_EXCHANGE_SZ | 2    | 深交所   |
| EMQ_EXCHANGE_BJ | 3    | 北交所   |

### 6.1.5. <a id="EMQLogLevel">日志级别-EMQLogLevel</a>

| 枚举                | 取值 | 定义说明     |
| ------------------- | ---- | ------------ |
| EMQ_LOG_LEVEL_FATAL | 0    | 严重错误级别 |
| EMQ_LOG_LEVEL_ERROR | 1    | 错误级别 |
| EMQ_LOG_LEVEL_WARNING | 2    | 警告级别 |
| EMQ_LOG_LEVEL_INFO | 3    | 通知级别 |
| EMQ_LOG_LEVEL_DEBUG | 4    | 调试级别 |
| EMQ_LOG_LEVEL_TRACE | 5    | 跟踪级别 |