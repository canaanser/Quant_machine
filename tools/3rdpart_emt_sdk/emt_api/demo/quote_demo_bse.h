#pragma once

#include <fstream>
#include <map>

#include "quote_api_bse.h"

namespace demo {

class QuoteDemoBse : public EMQ::API::BSE::QuoteSpiBse {
  public:
  QuoteDemoBse();
    ~QuoteDemoBse();
    void Run();

  protected:
    // inherit from EMQ::API::QuoteSpiBse
  
    void OnSnapBse(EMQBseSnap *snap)  override;

  private:
    EMQ::API::BSE::QuoteApiBse *quote_api_;
    std::string current_date_;
    std::ofstream bse_snap_stream_;
};

}