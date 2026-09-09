#include <cstddef>
#include <iostream>
#include <memory>
#include <thread>

#include "trade_demo.h"
#include "quote_demo.h"
#ifndef _WIN32
#include "quote_demo_lv2.h"
#include "quote_demo_bse.h"
#endif

int main(int argc, char *argv[]) {
  // 行情Lv1相关demo
  demo::QuoteDemo quote_demo;
  std::thread emt_quote_demo_thread([&]() {
    quote_demo.Run();
  });

#ifndef _WIN32
  // 行情lv2相关demo
  demo::QuoteDemoLv2 quote_demo_lv2;
  std::thread emt_quote_demo_lv2_thread([&]() {
    quote_demo_lv2.Run();
  });

  // 北交所极速行情相关demo
  demo::QuoteDemoBse quote_demo_bse;
  std::thread emt_quote_demo_bse_thread([&]() {
    quote_demo_bse.Run();
  });  
#endif

  // 交易相关demo
  demo::TradeDemo trade_demo;
  std::thread emt_trade_demo_thread([&]() {
    trade_demo.Run();
  });






  emt_quote_demo_thread.join();
#ifndef _WIN32
  emt_quote_demo_lv2_thread.join();
  emt_quote_demo_bse_thread.join();
#endif
  emt_trade_demo_thread.join();

  return 0;
}
