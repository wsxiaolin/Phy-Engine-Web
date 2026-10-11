// #define JSON_NOEXCEPTION
#include "/home/z/my-project/phy-engine-web/repo/include/phy_engine/phy_lab_wrapper/utility/json.hpp"
#include <cstdio>
#include <string_view>
using json = nlohmann::json;
extern "C" int probe(const char* s) {
    json root = json::parse(s, s + strlen(s), nullptr, false, true);
    try { json root = json::parse(s, s + strlen(s), nullptr, false, true); printf("discarded=%d is_obj=%d\n", (int)root.is_discarded(), (int)root.is_object()); } catch(...) { printf("THREW\n"); }
    return root.is_discarded() ? 1 : 0;
}
#include <cstring>
