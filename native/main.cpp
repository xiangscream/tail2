// Original M0 probe. No vendor implementation or sample source is redistributed.
// JSONL is an engineering probe protocol, NOT the final Agent tool contract.
#include <boost/json/src.hpp>
#include <dev/devs.hpp>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <filesystem>
#include <iostream>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <thread>
#ifdef _WIN32
#include <codecvt>
#include <locale>
#endif
namespace j = boost::json;
using Clock = std::chrono::steady_clock;
namespace {
struct ControlParam { int para; const char *name; char kind; double lo; double hi; };
const ControlParam kControlParams[] = {
  {0,"motion",'b',0,1},{1,"fore_track",'b',0,1},{2,"composition",'b',0,1},
  {3,"tracker_type",'i',0,1},{4,"gim_ctrl_mode",'i',0,1},{5,"gim_ctrl_speed_mode",'i',0,100},
  {6,"pan_gain_adaptive",'b',0,1},{7,"pan_gain_value",'f',-1000,1000},
  {8,"pan_locked",'b',0,1},{9,"pitch_gain_adaptive",'b',0,1},{10,"pitch_gain_value",'f',-1000,1000},
  {11,"pitch_locked",'b',0,1},{12,"auto_zoom_customized",'i',0,100},{13,"auto_zoom_mode",'i',0,100},
  {14,"offset_adaptive_x",'b',0,1},{15,"offset_x",'f',-1,1},
  {16,"offset_adaptive_y",'b',0,1},{17,"offset_y",'f',-1,1},
  {18,"limit_auto_selection",'b',0,1},{19,"limit_pan_min",'f',-180,180},{20,"limit_pan_max",'f',-180,180},
  {21,"limit_pitch_min",'f',-90,90},{22,"limit_pitch_max",'f',-90,90},{23,"auto_zoom_speed",'i',1,10},
};
const ControlParam *find_control(int para) {
  for (const auto &spec : kControlParams) if (spec.para == para) return &spec;
  return nullptr;
}
}
static std::atomic<unsigned long long> status_count{0};
static std::atomic<long long> status_received_ms{0};
static long long now_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now().time_since_epoch()).count();
}
static void log_handler(int32_t, const char *fmt, va_list args, void *) {
    std::vfprintf(stderr, fmt, args);
}
static std::string str(const j::object &o, const char *key) {
    auto *v = o.if_contains(key);
    if (!v || !v->is_string()) throw std::runtime_error(std::string("string required: ")+key);
    return std::string(v->as_string());
}
static double num(const j::object &o, const char *key, double lo, double hi) {
    auto *v = o.if_contains(key);
    if (!v || !v->is_number()) throw std::runtime_error(std::string("number required: ")+key);
    double n = j::value_to<double>(*v);
    if (!std::isfinite(n) || n < lo || n > hi) throw std::runtime_error(std::string("out of range: ")+key);
    return n;
}
static bool boolean(const j::object &o, const char *key) {
    auto *v=o.if_contains(key);
    if (!v || !v->is_bool()) throw std::runtime_error(std::string("boolean required: ")+key);
    return v->as_bool();
}
static void checked_rc(int rc) { if (rc != RM_RET_OK) throw std::runtime_error("SDK operation rejected; inspect sdk_calls"); }
class Probe {
    bool controls_, legacy_, initialized_=false;
    std::shared_ptr<Device> dev_;
    void initialize() {
        if (!initialized_) {
#ifndef _WIN32
            if (!std::filesystem::is_directory("/sys/bus/usb/devices"))
                throw std::runtime_error("USB discovery unavailable: /sys/bus/usb/devices is missing; refusing SDK initialization");
#endif
            Devices::get().setEnableMdnsScan(false);
            initialized_=true;
        }
    }
    void writable() { if (!controls_) throw std::runtime_error("control disabled: restart with --allow-control"); }
    void compatibility() { if (!legacy_) throw std::runtime_error("Tail2 applicability needs probe: --allow-legacy-probes required"); }
    void ready() {
        if (!dev_ || !dev_->isInited()) throw std::runtime_error("no initialized selected Tail2");
        auto live=Devices::get().getDevBySn(dev_->devSn());
        if (!live) throw std::runtime_error("selected device disconnected; re-open explicitly");
    }
public:
    Probe(bool controls, bool legacy): controls_(controls), legacy_(legacy) {}
    ~Probe() {
        if (dev_) { dev_->enableDevStatusCallback(false); dev_->setDevStatusCallbackFunc(nullptr,nullptr); dev_.reset(); }
        if (initialized_) Devices::get().close();
    }
    j::object run(const j::object &req, j::array &calls) {
        const auto op=str(req,"op");
        const auto *p=req.if_contains("args");
        j::object empty;
        const auto &a=p ? p->as_object() : empty;
        auto call=[&](const char *symbol, auto f) {
            const auto t=now_ms(); int rc=f();
            calls.emplace_back(j::object{{"symbol",symbol},{"rc",rc},{"elapsed_ms",now_ms()-t}});
            return rc;
        };
        if (op=="hello") return {{"protocol","tail2-probe/0.1"},{"control_enabled",controls_},{"legacy_enabled",legacy_}};
        if (op=="candidates.probe") return {{"status","UNKNOWN"},{"declaration","DevCDCNotifyTypeAiTarget"},
            {"callable_reader_found",false},{"reason","No documented candidate-list reader in supplied public headers; vendor clarification required"}};
        if (op=="device.list") {
            initialize();
            int wait=a.if_contains("wait_ms") ? static_cast<int>(num(a,"wait_ms",0,15000)) : 3000;
            std::this_thread::sleep_for(std::chrono::milliseconds(wait));
            j::array ds;
            for (auto &d: Devices::get().getDevList()) {
                j::object x{{"sn",d->devSn()},{"name",d->devName()},{"product_type",static_cast<int>(d->productType())},
                    {"transport",static_cast<int>(d->devMode())},{"firmware",d->devVersion()},
                    {"eligible",d->productType()==ObsbotProdTail2 && d->devMode()==Device::DevModeUvc}};
#ifdef _WIN32
                if (d->devMode()==Device::DevModeUvc) {
                    std::wstring_convert<std::codecvt_utf8<wchar_t>> conv;
                    x["video_path"]=conv.to_bytes(d->videoDevPath());
                    x["video_name"]=conv.to_bytes(d->videoFriendlyName());
                }
#endif
                ds.emplace_back(x);
            }
            return {{"devices",ds},{"hardware_verified",false}};
        }
        if (op=="device.open") {
            initialize();
            auto d=Devices::get().getDevBySn(str(a,"sn"));
            if (!d || d->productType()!=ObsbotProdTail2 || d->devMode()!=Device::DevModeUvc)
                throw std::runtime_error("explicit Tail2 UVC serial required; run device.list first");
            if (dev_) { dev_->enableDevStatusCallback(false); dev_->setDevStatusCallbackFunc(nullptr,nullptr); }
            dev_=d; status_count=0; status_received_ms=0;
            dev_->setDevStatusCallbackFunc([](void*,const void*) {
                status_received_ms=now_ms(); ++status_count;
                // Tail2 CameraStatus union layout not assumed.
            },nullptr);
            dev_->enableDevStatusCallback(true);
            return {{"selected",true},{"firmware",dev_->devVersion()},{"transport","uvc"}};
        }
        ready();
        if (op=="device.status") {
            j::object r{{"connected",true},{"firmware",dev_->devVersion()},
                {"callback_count",status_count.load()},{"target_acquired",nullptr},{"visual_framing_ok",nullptr}};
            if (status_received_ms.load()) r["callback_age_ms"]=now_ms()-status_received_ms.load();
            // This older-category getter is optional on Tail2.
            if (legacy_) {
                Device::AiStatus ai{};
                int rc=call("aiGetAiStatusR",[&]{return dev_->aiGetAiStatusR(&ai);});
                if (rc==0) { r["ai_main_mode_raw"]=static_cast<int>(ai.ai_main_mode); r["ai_sub_mode_raw"]=static_cast<int>(ai.ai_track_sub_mode); }
            }
            Device::DevMediaParamOperation state=Device::DevMediaParamOperationAuto;
            int rc=call("cameraGetMediaOperateParamR(record)",[&]{return dev_->cameraGetMediaOperateParamR(Device::DevMediaStreamIdRecord,state);});
            if (rc==0) r["record_operation_raw"]=static_cast<int>(state);
            state=Device::DevMediaParamOperationAuto;
            rc=call("cameraGetMediaOperateParamR(capture)",[&]{return dev_->cameraGetMediaOperateParamR(Device::DevMediaStreamIdCapture,state);});
            if (rc==0) r["capture_operation_raw"]=static_cast<int>(state);
            return r;
        }
        if (op=="look.status") {
            compatibility(); float xyz[3]={};
            checked_rc(call("gimbalGetAttitudeInfoR",[&]{return dev_->gimbalGetAttitudeInfoR(xyz);}));
            return {{"roll_deg",xyz[0]},{"pitch_deg",xyz[1]},{"yaw_deg",xyz[2]},{"frame","device_reported"}};
        }
        if (op=="position.list") {
            compatibility(); Device::DevDataArray ids{};
            checked_rc(call("aiGetGimbalPresetListR",[&]{return dev_->aiGetGimbalPresetListR(&ids);}));
            j::array slots; for (int v:ids.data_int32) slots.emplace_back(v);
            return {{"len_raw",ids.len},{"int32_slots_raw",slots},{"count_interpretation","UNVERIFIED"},{"scope","gimbal_only"}};
        }
        writable();
        if (op=="target.select") {
            Device::DevTargetSelection s{};
            const std::string sel = a.if_contains("selection") ? str(a,"selection") : std::string("box");
            const auto cls=str(a,"class");
            if (cls=="human") s.class_type=Device::DevTargetClassTypeHuman;
            else if (cls=="animal") s.class_type=Device::DevTargetClassTypeAnimal;
            else if (cls=="common") s.class_type=Device::DevTargetClassTypeCommon;
            else throw std::runtime_error("unsupported target class");
            s.zoom_type=Device::DevTargetZoomTypeNormal;
            s.view_type=Device::DevTargetViewTypeIgnored;
            if (sel=="box") {
                s.selection_type=Device::DevTargetSelectionTypeBox;
                s.location.roi.x_min=static_cast<float>(num(a,"x1",0,1));
                s.location.roi.y_min=static_cast<float>(num(a,"y1",0,1));
                s.location.roi.x_max=static_cast<float>(num(a,"x2",0,1));
                s.location.roi.y_max=static_cast<float>(num(a,"y2",0,1));
                if(s.location.roi.x_min>=s.location.roi.x_max || s.location.roi.y_min>=s.location.roi.y_max)
                    throw std::runtime_error("bbox must have positive area");
            } else if (sel=="center") {
                s.selection_type=Device::DevTargetSelectionTypeCenter;
            } else if (sel=="largest") {
                s.selection_type=Device::DevTargetSelectionTypeLargest;
            } else if (sel=="clicked") {
                s.selection_type=Device::DevTargetSelectionTypeClicked;
                s.location.point.x=static_cast<float>(num(a,"x",0,1));
                s.location.point.y=static_cast<float>(num(a,"y",0,1));
            } else throw std::runtime_error("unsupported selection type");
            checked_rc(call("aiSetSelectedTargetR",[&]{return dev_->aiSetSelectedTargetR(s);}));
            return {{"dispatch","accepted"},{"selection",sel},{"target_acquired",nullptr},{"zoom_policy","normal; reapply framing explicitly"}};
        }
        if (op=="ai.select_biggest" || op=="ai.select_central") {
            compatibility();
            const int t = a.if_contains("type") ? static_cast<int>(num(a,"type",-1,200)) : 0;
            if (op=="ai.select_biggest") checked_rc(call("aiSetSelectBiggestTarget",[&]{return dev_->aiSetSelectBiggestTarget(t);}));
            else checked_rc(call("aiSetSelectCentralTarget",[&]{return dev_->aiSetSelectCentralTarget(t);}));
            return {{"dispatch","accepted"},{"type",t}};
        }
        if (op=="target.clear") {
            Device::DevTargetSelection s{};
            s.selection_type=Device::DevTargetSelectionTypeDelete;
            s.class_type=Device::DevTargetClassTypeIgnored;
            s.zoom_type=Device::DevTargetZoomTypeIgnored; s.view_type=Device::DevTargetViewTypeIgnored;
            checked_rc(call("aiSetSelectedTargetR(delete)",[&]{return dev_->aiSetSelectedTargetR(s);}));
        } else if (op=="framing.set") {
            const auto mode=str(a,"mode"); Device::DevTargetZoomType z;
            if(mode=="full_body") z=Device::DevTargetZoomTypeFullBody;
            else if(mode=="half_body") z=Device::DevTargetZoomTypeHalfBody;
            else if(mode=="close_up") z=Device::DevTargetZoomTypeCloseUp;
            else if(mode=="normal") z=Device::DevTargetZoomTypeNormal;
            else throw std::runtime_error("unsupported framing");
            checked_rc(call("aiSetTargetZoomTypeR",[&]{return dev_->aiSetTargetZoomTypeR(z);}));
        } else if (op=="track.set") {
            compatibility(); bool on=boolean(a,"enabled");
            checked_rc(call("aiSetEnabledR",[&]{return dev_->aiSetEnabledR(on);}));
        } else if (op=="ai.track_mode") {
            compatibility(); bool on=boolean(a,"enabled");
            const double m=num(a,"mode",0,65535); if (std::floor(m)!=m) throw std::runtime_error("integer mode required");
            checked_rc(call("aiSetAiTrackModeEnabledR",[&]{return dev_->aiSetAiTrackModeEnabledR(static_cast<Device::AiTrackModeType>(static_cast<int>(m)),on);}));
        } else if(op=="look.stop") {
            compatibility();
            int ai_rc=call("aiSetEnabledR(false)",[&]{return dev_->aiSetEnabledR(false);});
            int stop_rc=call("gimbalSpeedCtrlR(0,0,0)",[&]{return dev_->gimbalSpeedCtrlR(0,0,0);});
            checked_rc(ai_rc); checked_rc(stop_rc);
        } else if(op=="look.nudge") {
            compatibility(); const double pan=num(a,"pan_dps",-10,10), pitch=num(a,"pitch_dps",-10,10);
            const int duration=static_cast<int>(num(a,"duration_ms",1,500));
            checked_rc(call("aiSetEnabledR(false)",[&]{return dev_->aiSetEnabledR(false);}));
            int start=call("gimbalSpeedCtrlR(nudge)",[&]{return dev_->gimbalSpeedCtrlR(pitch,pan,0);});
            if(start==0) std::this_thread::sleep_for(std::chrono::milliseconds(duration));
            int stop=call("gimbalSpeedCtrlR(0,0,0)",[&]{return dev_->gimbalSpeedCtrlR(0,0,0);});
            checked_rc(start); checked_rc(stop);
        } else if(op=="zoom.set") {
            compatibility();
            const double z=num(a,"zoom",1.0,10.0);
            const int speed = a.if_contains("speed") ? static_cast<int>(num(a,"speed",-1,10)) : -1;
            checked_rc(call("cameraSetZoomAbsoluteR",[&]{return dev_->cameraSetZoomAbsoluteR(static_cast<float>(z),speed);}));
        } else if(op=="zoom.get") {
            float z=0; checked_rc(call("cameraGetZoomAbsoluteR",[&]{return dev_->cameraGetZoomAbsoluteR(z);}));
            return {{"zoom",z}};
        } else if(op=="zoom.range") {
            Device::UvcParamRange r; checked_rc(call("cameraGetRangeZoomAbsoluteR",[&]{return dev_->cameraGetRangeZoomAbsoluteR(r);}));
            return {{"min",r.min_},{"max",r.max_},{"step",r.step_},{"default",r.default_},{"valid",r.valid_}};
        } else if(op=="ai.auto_zoom") {
            compatibility(); bool on=boolean(a,"enabled");
            checked_rc(call("aiSetAiAutoZoomR",[&]{return dev_->aiSetAiAutoZoomR(on);}));
        } else if(op=="ai.control.get") {
            compatibility();
            const int pt=static_cast<int>(num(a,"para",0,1000));
            const ControlParam *spec=find_control(pt);
            if(!spec) throw std::runtime_error("para not in documented Tail2 control allowlist");
            auto target=static_cast<Device::DevControlTargetType>(static_cast<int>(num(a,"target_type",0,2)));
            auto para=static_cast<Device::DevControlParaType>(pt);
            if(spec->kind=='b'){ bool v=false; checked_rc(call("aiGetControlParaR(bool)",[&]{return dev_->aiGetControlParaR(target,para,v);})); return {{"para",pt},{"name",std::string(spec->name)},{"kind","bool"},{"value",v}}; }
            if(spec->kind=='i'){ int v=0; checked_rc(call("aiGetControlParaR(int)",[&]{return dev_->aiGetControlParaR(target,para,v);})); return {{"para",pt},{"name",std::string(spec->name)},{"kind","int"},{"value",v}}; }
            float v=0; bool fault=false; checked_rc(call("aiGetControlParaR(float)",[&]{return dev_->aiGetControlParaR(target,para,v,fault);})); return {{"para",pt},{"name",std::string(spec->name)},{"kind","float"},{"value",v},{"fault",fault}};
        } else if(op=="ai.control.set") {
            compatibility();
            const int pt=static_cast<int>(num(a,"para",0,1000));
            const ControlParam *spec=find_control(pt);
            if(!spec) throw std::runtime_error("para not in documented Tail2 control allowlist");
            const double raw=num(a,"value",spec->lo,spec->hi);
            auto target=static_cast<Device::DevControlTargetType>(static_cast<int>(num(a,"target_type",0,2)));
            auto para=static_cast<Device::DevControlParaType>(pt);
            if(spec->kind=='b'){ checked_rc(call("aiSetControlParaR(bool)",[&]{return dev_->aiSetControlParaR(target,para,raw!=0.0);})); }
            else if(spec->kind=='i'){ checked_rc(call("aiSetControlParaR(int)",[&]{return dev_->aiSetControlParaR(target,para,static_cast<int>(raw));})); }
            else { checked_rc(call("aiSetControlParaR(float)",[&]{return dev_->aiSetControlParaR(target,para,static_cast<float>(raw));})); }
            return {{"para",pt},{"name",std::string(spec->name)},{"kind",std::string(1,spec->kind)},{"value",raw}};
        } else if(op=="ai.offset") {
            compatibility();
            if (a.if_contains("auto")) { bool en=boolean(a,"auto"); checked_rc(call("aiSetAutoOffset",[&]{return dev_->aiSetAutoOffset(en);})); return {{"auto",en}}; }
            if (a.if_contains("x")) { float v=static_cast<float>(num(a,"x",-1,1)); checked_rc(call("aiSetHorizontalOffset",[&]{return dev_->aiSetHorizontalOffset(v);})); return {{"x",v}}; }
            if (a.if_contains("y")) { float v=static_cast<float>(num(a,"y",-1,1)); checked_rc(call("aiSetVerticalOffset",[&]{return dev_->aiSetVerticalOffset(v);})); return {{"y",v}}; }
            throw std::runtime_error("provide auto/x/y");
        } else if(op=="camera.face_ae") {
            compatibility(); const bool on=boolean(a,"enabled");
            checked_rc(call("cameraSetFaceAER",[&]{return dev_->cameraSetFaceAER(on?1:0);}));
        } else if(op=="camera.exposure_mode") {
            compatibility(); const int m=static_cast<int>(num(a,"mode",0,4));
            checked_rc(call("cameraSetExposureModeR",[&]{return dev_->cameraSetExposureModeR(m);}));
        } else if(op=="camera.ev_bias") {
            compatibility(); const int v=static_cast<int>(num(a,"value",0,18));
            checked_rc(call("cameraSetPAEEvBiasR",[&]{return dev_->cameraSetPAEEvBiasR(v);}));
        } else if(op=="record.start" || op=="record.stop" || op=="capture.device") {
            auto stream=op=="capture.device" ? Device::DevMediaStreamIdCapture : Device::DevMediaStreamIdRecord;
            auto action=op=="record.stop" ? Device::DevMediaParamOperationStop : Device::DevMediaParamOperationStart;
            checked_rc(call("cameraSetMediaOperateParamR",[&]{return dev_->cameraSetMediaOperateParamR(stream,action);}));
        } else if(op=="position.recall") {
            compatibility(); const double n=num(a,"id",0,65535); if(std::floor(n)!=n) throw std::runtime_error("integer id required");
            checked_rc(call("aiSetEnabledR(false)",[&]{return dev_->aiSetEnabledR(false);}));
            checked_rc(call("aiTrgGimbalPresetR",[&]{return dev_->aiTrgGimbalPresetR(static_cast<int>(n));}));
        } else if(op=="position.save") {
            throw std::runtime_error("deferred: preset ID ownership/len semantics require local verification before any persistent write");
        } else throw std::runtime_error("unsupported operation");
        return {{"dispatch","accepted"},{"completion","unverified"},{"artifact",nullptr}};
    }
};
int main(int argc,char**argv) {
    bool control=false,legacy=false;
    for(int i=1;i<argc;++i) {
        std::string a=argv[i];
        if(a=="--allow-control") control=true;
        else if(a=="--allow-legacy-probes") legacy=true;
        else { std::cerr<<"Unknown argument\n"; return 2; }
    }
    dev_set_log_handler(log_handler,nullptr);
    Probe probe(control,legacy);
    std::string line; std::set<std::string> seen;
    while(std::getline(std::cin,line)) {
        j::object response; j::array calls; std::string id;
        try {
            if(line.size()>65536) throw std::runtime_error("request too large");
            auto req=j::parse(line).as_object(); id=str(req,"id");
            if(id.empty() || id.size()>128) throw std::runtime_error("invalid request id");
            if(seen.count(id)) throw std::runtime_error("duplicate request id; no re-execution");
            if(seen.size()>=10000) throw std::runtime_error("session request limit reached");
            seen.insert(id);
            if(str(req,"op")=="shutdown") { std::cout<<j::serialize(j::object{{"id",id},{"ok",true},{"result",j::object{{"closed",true}}}})<<std::endl; break; }
            response={{"id",id},{"ok",true},{"result",probe.run(req,calls)}};
        } catch(const std::exception &e) { response={{"id",id},{"ok",false},{"error",e.what()}}; }
        response["sdk_calls"]=calls;
        std::cout<<j::serialize(response)<<std::endl;
    }
}
