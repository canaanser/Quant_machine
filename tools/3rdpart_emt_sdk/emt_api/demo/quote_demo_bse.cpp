#include "quote_demo_bse.h"
#include "quote_struct_bse.h"
#include <chrono>
#include <cstdio>
#include <fmt/core.h>
#include <iostream>
#include <thread>

namespace {

using sysclock_t = std::chrono::system_clock;

static constexpr int kCacheSize = 2048;

static inline std::string get_current_date() {
  std::time_t now = sysclock_t::to_time_t(sysclock_t::now());

  char buf[16] = {0};
  std::strftime(buf, sizeof(buf), "%Y-%m-%d", std::localtime(&now));

  return std::string{buf};
}

static inline std::string timestamp_to_date_time_string(long long timestamp) {
  using namespace std::chrono;
  char buf[32] = {0};

  std::time_t tt =
      sysclock_t::to_time_t(sysclock_t::time_point(nanoseconds(timestamp)));
  std::strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", std::localtime(&tt));
  sprintf(buf + strlen(buf), ".%03lld", timestamp % 1000);
  return std::string{buf};
}

static inline long long get_current_timestamp_ns() {
  auto now = sysclock_t::now();
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
             now.time_since_epoch())
      .count();
}

static inline std::string get_current_datetime() {
  return timestamp_to_date_time_string(get_current_timestamp_ns());
}

} // namespace

namespace demo {

QuoteDemoBse::QuoteDemoBse()
    : current_date_(get_current_date()),
      bse_snap_stream_(std::string("BJ_SNAP" + current_date_ + ".csv"), std::ios::binary){
        std::string header = "DBFTIME,hw,DBFSTATUS,HQZQDM,HQZQJC,HQZRSP,HQJRKP,HQZJCJ,HQCJSL,HQCJJE,"
        "HQCJBS,HQZGCJ,HQZDCJ,HQSYL1,HQSYL2,HQJSD1,HQJSD2,HQHYCC,"
        "HQSJW5,HQSSL5,HQSJW4,HQSSL4,HQSJW3,HQSSL3,HQSJW2,HQSSL2,"
        "HQSJW1,HQSSL1,HQBJW1,HQBSL1,HQBJW2,HQBSL2,HQBJW3,HQBSL3,"
        "HQBJW4,HQBSL4,HQBJW5,HQBSL5\n";

        bse_snap_stream_ << header;
        bse_snap_stream_.flush();
      }

QuoteDemoBse::~QuoteDemoBse() { quote_api_->Release(); }

void QuoteDemoBse::Run() {
  quote_api_ = EMQ::API::BSE::QuoteApiBse::CreateQuoteApiBse("./bse_api.log",EMQ::API::BSE::EMQ_LOG_LEVEL_DEBUG);
  quote_api_->RegisterSpi(this);

  // Login相关参数
  // 接收组播时不需要Login
  EMQ::API::BSE::EMQLoginConfigBse login_config;
  strcpy(login_config.login_ip, "127.0.0.1");      // 登录服务器IP
  login_config.login_port = 8887;                           // 登录服务器端口
  strcpy(login_config.user_name, "123");          // 用户名
  strcpy(login_config.user_pwd, "123");           // 密码
  

  // 设置通道配置（包含Login参数）
  constexpr int kConfigNum = 1;
  EMQ::API::BSE::EMQUdpConfigBse channelConfigs[kConfigNum];
  channelConfigs[0].enable = true;
  channelConfigs[0].mode = EMQ::API::BSE::EMQBseUdpRecvMode::kNormal;
  // 目前北交所仅支持snap行情
  channelConfigs[0].quote_type = EMQ::API::BSE::EMQBseType::kBseSnap;
  // strcpy(channelConfigs[0].eth_name, "lo");
  // 用于接收行情的绑定IP
  strcpy(channelConfigs[0].bind_ip, "127.0.0.1");  
  // 用于接收行情的绑定端口
  channelConfigs[0].bind_port = 13001;                
  channelConfigs[0].rx_cpu_id = 3;
  channelConfigs[0].handle_cpu_id = 1;
  channelConfigs[0].spsc_size = 8;
  channelConfigs[0].rx_pkt_num = 8;
  


  quote_api_->SetChannelConfig(login_config, channelConfigs, kConfigNum);

  int ret = quote_api_->Start();
  if (ret != 0) {
    std::cerr << "Start failed with error code: " << ret << std::endl;
    return;
  }
  while (true) {
    std::this_thread::sleep_for(std::chrono::seconds(1));
  }
}

// 北交所快照行情（NQHQ.DBF）
void QuoteDemoBse::OnSnapBse(EMQBseSnap *snap) {
  auto ts = quote_api_->GetPacketHardwareRXTs(snap);

  std::string cache = fmt::format(
    "{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},"
    "{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{}\n",

    std::string(snap->DBFTIME, 6),
    ts,
    std::string(snap->DBFSTATUS, 4),
    std::string(snap->HQZQDM, 6),
    std::string(snap->HQZQJC,8), // GB2312
    snap->HQZRSP,
    snap->HQJRKP,
    snap->HQZJCJ,
    snap->HQCJSL,
    snap->HQCJJE,
    snap->HQCJBS,
    snap->HQZGCJ,
    snap->HQZDCJ,
    snap->HQSYL1,
    snap->HQSYL2,
    snap->HQJSD1,
    snap->HQJSD2,
    snap->HQHYCC,

    snap->HQSJW5, snap->HQSSL5,
    snap->HQSJW4, snap->HQSSL4,
    snap->HQSJW3, snap->HQSSL3,
    snap->HQSJW2, snap->HQSSL2,
    snap->HQSJW1, snap->HQSSL1,

    snap->HQBJW1, snap->HQBSL1,
    snap->HQBJW2, snap->HQBSL2,
    snap->HQBJW3, snap->HQBSL3,
    snap->HQBJW4, snap->HQBSL4,
    snap->HQBJW5, snap->HQBSL5
);

  bse_snap_stream_ << cache << std::flush;
}


} // namespace demo