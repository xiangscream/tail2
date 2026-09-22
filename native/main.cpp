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
  {14,"offset_adaptive_x",'b',0,1},{15,"offset_x",'f',-100,100},
  {16,"offset_adaptive_y",'b',0,1},{17,"offset_y",'f',-100,100},
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
static std::atomic<unsigned long long> fast_status_count{0};
static std::atomic<long long> fast_status_received_ms{0};
static std::atomic<unsigned long long> dev_changed_count{0};
static std::atomic<long long> dev_changed_ms{0};
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
            Devices::get().setDevChangedCallback([](std::string, bool, void *) {
                dev_changed_ms=now_ms(); ++dev_changed_count;
            }, nullptr);
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
            dev_->setFastDevStatusCallbackFunc([](void*,const void*,const std::string &) {
                fast_status_received_ms=now_ms(); ++fast_status_count;
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
        if (op=="gimbal.state.get") {
            compatibility(); Device::AiGimbalStateInfo info{};
            checked_rc(call("aiGetGimbalStateR",[&]{return dev_->aiGetGimbalStateR(&info);}));
            return {{"roll_euler",info.roll_euler},{"pitch_euler",info.pitch_euler},{"yaw_euler",info.yaw_euler},
                    {"roll_motor",info.roll_motor},{"pitch_motor",info.pitch_motor},{"yaw_motor",info.yaw_motor},
                    {"roll_v",info.roll_v},{"pitch_v",info.pitch_v},{"yaw_v",info.yaw_v}};
        }
        if (op=="gimbal.para.get") {
            compatibility();
            const int t=static_cast<int>(num(a,"type",0,100));
            const auto para=static_cast<Device::DevGimbalParaType>(t);
            bool b=false; const int rcb=call("aiGetGimbalParaR(bool)",[&]{return dev_->aiGetGimbalParaR(para,b);});
            float f=-12345.f; const int rcf=call("aiGetGimbalParaR(float)",[&]{return dev_->aiGetGimbalParaR(para,f);});
            j::object out{{"type",t},{"bool_rc",rcb},{"float_rc",rcf},
                          {"note","the bool overload accepts every type; read both"}};
            if(rcb==0) out["bool_value"]=b;
            if(rcf==0) out["float_value"]=f;
            return out;
        }
        if (op=="gimbal.bootpos.get") {
            compatibility(); Device::PresetPosInfo info{};
            const int rc=call("aiGetGimbalBootPosR",[&]{return dev_->aiGetGimbalBootPosR(&info);});
            j::object out{{"rc",rc},{"completion","unverified"}};
            if(rc==0){ out["id"]=info.id; out["roll"]=info.roll; out["pitch"]=info.pitch;
                       out["yaw"]=info.yaw; out["zoom"]=info.zoom; }
            return out;
        }
        if (op=="gesture.get") {
            compatibility(); const int t=static_cast<int>(num(a,"type",0,8));
            const auto type=static_cast<Device::DevGestureParaType>(t);
            bool b=false; const int rcb=call("aiGetGestureParaR(bool)",[&]{return dev_->aiGetGestureParaR(type,b);});
            float f=-12345.f; const int rcf=call("aiGetGestureParaR(float)",[&]{return dev_->aiGetGestureParaR(type,f);});
            j::object out{{"type",t},{"bool_rc",rcb},{"float_rc",rcf},
                          {"note","read both overloads; the bool overload accepts every type"}};
            if(rcb==0) out["bool_value"]=b;
            if(rcf==0) out["float_value"]=f;
            return out;
        }
        if (op=="gesture.track.get") {
            compatibility(); const int t=static_cast<int>(num(a,"type",0,8));
            const auto type=static_cast<Device::DevGestureTrackParaType>(t);
            bool b=false; const int rcb=call("aiGetGestureTrackParaR(bool)",[&]{return dev_->aiGetGestureTrackParaR(type,b);});
            float f=-12345.f; const int rcf=call("aiGetGestureTrackParaR(float)",[&]{return dev_->aiGetGestureTrackParaR(type,f);});
            int i=-12345; const int rci=call("aiGetGestureTrackParaR(int)",[&]{return dev_->aiGetGestureTrackParaR(type,i);});
            j::object out{{"type",t},{"bool_rc",rcb},{"float_rc",rcf},{"int_rc",rci}};
            if(rcb==0) out["bool_value"]=b;
            if(rcf==0) out["float_value"]=f;
            if(rci==0) out["int_value"]=i;
            return out;
        }
        if (op=="zone.get") {
            compatibility(); const std::string which=str(a,"which");
            j::object out{{"which",which}};
            if(which=="enabled"){ bool v=false; const int rc=call("aiGetLimitedZoneTrackEnabledR",[&]{return dev_->aiGetLimitedZoneTrackEnabledR(v);}); out["rc"]=rc; if(rc==0) out["value"]=v; return out; }
            if(which=="autoselect"){ bool v=false; const int rc=call("aiGetLimitedZoneTrackAutoSelectR",[&]{return dev_->aiGetLimitedZoneTrackAutoSelectR(v);}); out["rc"]=rc; if(rc==0) out["value"]=v; return out; }
            float v=0; int rc=-1;
            if(which=="yaw_min") rc=call("aiGetLimitedZoneTrackYawMinR",[&]{return dev_->aiGetLimitedZoneTrackYawMinR(v,0);});
            else if(which=="yaw_max") rc=call("aiGetLimitedZoneTrackYawMaxR",[&]{return dev_->aiGetLimitedZoneTrackYawMaxR(v,0);});
            else if(which=="pitch_min") rc=call("aiGetLimitedZoneTrackPitchMinR",[&]{return dev_->aiGetLimitedZoneTrackPitchMinR(v,0);});
            else if(which=="pitch_max") rc=call("aiGetLimitedZoneTrackPitchMaxR",[&]{return dev_->aiGetLimitedZoneTrackPitchMaxR(v,0);});
            else throw std::runtime_error("which must be enabled|autoselect|yaw_min|yaw_max|pitch_min|pitch_max");
            out["rc"]=rc; if(rc==0) out["value"]=v; return out;
        }
        if (op=="iq.autofocus.get") {
            compatibility(); Device::DevAutoFocusType v=Device::DevAutoFocusAutoSelect;
            checked_rc(call("cameraGetAutoFocusModeR",[&]{return dev_->cameraGetAutoFocusModeR(v);}));
            return {{"autofocus",static_cast<int>(v)}};
        }
        if (op=="iq.afc.get") {
            compatibility(); Device::DevAFCType v=Device::DevAFCCenter;
            checked_rc(call("cameraGetAFCTrackModeR",[&]{return dev_->cameraGetAFCTrackModeR(v);}));
            return {{"afc",static_cast<int>(v)}};
        }
        if (op=="iq.focus.get") {
            compatibility(); int32_t focus=0; bool auto_focus=false;
            const int rc=call("cameraGetFocusAbsolute",[&]{return dev_->cameraGetFocusAbsolute(focus,auto_focus);});
            j::object out{{"rc",rc}};
            if(rc==0){ out["focus"]=focus; out["auto_focus"]=auto_focus; }
            return out;
        }
        if (op=="iq.wb.get") {
            compatibility(); Device::DevWhiteBalanceType type=Device::DevWhiteBalanceAuto; int32_t param=0;
            const int rc=call("cameraGetWhiteBalanceR(type)",[&]{return dev_->cameraGetWhiteBalanceR(type,param);});
            j::object out{{"rc",rc}};
            if(rc==0){ out["wb_type"]=static_cast<int>(type); out["param"]=param; }
            return out;
        }
        if (op=="iq.wb.range") {
            compatibility(); Device::UvcParamRange r;
            checked_rc(call("cameraGetRangeWhiteBalanceR",[&]{return dev_->cameraGetRangeWhiteBalanceR(r);}));
            return {{"min",r.min_},{"max",r.max_},{"step",r.step_},{"default",r.default_},{"valid",r.valid_}};
        }
        if (op=="iq.wdr.get") {
            compatibility(); int32_t mode=0;
            const int rc=call("cameraGetWdrR",[&]{return dev_->cameraGetWdrR(mode);});
            j::object out{{"rc",rc}}; if(rc==0) out["wdr"]=mode; return out;
        }
        if (op=="media.encode.get") {
            compatibility(); const std::string kind=str(a,"kind");
            const bool night=a.if_contains("night")?boolean(a,"night"):false;
            Device::DevMediaEncodeParam p{};
            int rc=-1;
            if(kind=="record") rc=call("cameraGetRecordEncodeParamR",[&]{return dev_->cameraGetRecordEncodeParamR(p,night);});
            else if(kind=="output") rc=call("cameraGetOutputEncodeParamR",[&]{return dev_->cameraGetOutputEncodeParamR(p,night);});
            else if(kind=="live") rc=call("cameraGetLiveEncodeParamR",[&]{return dev_->cameraGetLiveEncodeParamR(p,night);});
            else throw std::runtime_error("kind must be record|output|live");
            j::object out{{"kind",kind},{"rc",rc}};
            if(rc==0){ out["width"]=p.width; out["height"]=p.height; out["fps"]=p.fps;
                       out["bitrate"]=p.bitrate; out["encode_format"]=static_cast<int>(p.encode_format); }
            return out;
        }
        if (op=="media.op.get") {
            compatibility(); const int stream_id=static_cast<int>(num(a,"stream",0,20));
            Device::DevMediaParamOperation action=Device::DevMediaParamOperationAuto;
            const int rc=call("cameraGetMediaOperateParamR",[&]{return dev_->cameraGetMediaOperateParamR(
                static_cast<Device::DevMediaStreamId>(stream_id),action);});
            j::object out{{"stream",stream_id},{"rc",rc}};
            if(rc==0) out["operation"]=static_cast<int>(action);
            return out;
        }
        if (op=="media.split.get") {
            compatibility(); Device::DevVideoSplitSizeType v=Device::DevVideoSplitAuto;
            const int rc=call("cameraGetRecordSplitSizeR",[&]{return dev_->cameraGetRecordSplitSizeR(v);});
            j::object out{{"rc",rc}}; if(rc==0) out["split"]=static_cast<int>(v); return out;
        }
        if (op=="media.ndirtsp.get") {
            compatibility(); j::object out;
            Device::RtspOrNdiEnabled sel=Device::RtspDisabledAndNdiDisabled;
            int rc=call("cameraGetSelectNdiOrRtspR",[&]{return dev_->cameraGetSelectNdiOrRtspR(sel);});
            out["select_rc"]=rc; if(rc==0) out["select"]=static_cast<int>(sel);
            Device::DevVideoBitLevelType bl=Device::DevVideoBitLevelDefault;
            rc=call("cameraGetNdiRtspBitrateLevelR",[&]{return dev_->cameraGetNdiRtspBitrateLevelR(bl);});
            out["bitrate_rc"]=rc; if(rc==0) out["bitrate_level"]=static_cast<int>(bl);
            Device::DevVideoEncoderFormat fmt=Device::DevVideoEncoderAuto;
            rc=call("cameraGetNdiRtspEncoderFormatR",[&]{return dev_->cameraGetNdiRtspEncoderFormatR(fmt);});
            out["format_rc"]=rc; if(rc==0) out["encoder_format"]=static_cast<int>(fmt);
            return out;
        }
        if (op=="media.hdmi.get") {
            compatibility(); Device::HdmiInfo info{};
            const int rc=call("cameraGetHdmiInfoR",[&]{return dev_->cameraGetHdmiInfoR(info);});
            j::object out{{"rc",rc}};
            if(rc==0){ out["osd_language"]=static_cast<int>(info.osd_language);
                       out["content"]=static_cast<int>(info.content); out["volume"]=info.volume;
                       out["resolution"]=static_cast<int>(info.resolution); out["info_display"]=info.info_display; }
            return out;
        }
        if (op=="status.callbacks.get") {
            j::object out{{"status_count",status_count.load()},{"status_age_ms",status_received_ms.load()?now_ms()-status_received_ms.load():-1},
                          {"fast_status_count",fast_status_count.load()},{"fast_status_age_ms",fast_status_received_ms.load()?now_ms()-fast_status_received_ms.load():-1},
                          {"dev_changed_count",dev_changed_count.load()},{"dev_changed_age_ms",dev_changed_ms.load()?now_ms()-dev_changed_ms.load():-1}};
            return out;
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
            Device::DevTargetZoomType z;
            if (a.if_contains("value")) {
                const int v=static_cast<int>(num(a,"value",-1,99));
                z=static_cast<Device::DevTargetZoomType>(v);
            } else {
                const auto mode=str(a,"mode");
                if(mode=="ignored") z=Device::DevTargetZoomTypeIgnored;
                else if(mode=="full_body") z=Device::DevTargetZoomTypeFullBody;
                else if(mode=="half_body") z=Device::DevTargetZoomTypeHalfBody;
                else if(mode=="close_up") z=Device::DevTargetZoomTypeCloseUp;
                else if(mode=="normal") z=Device::DevTargetZoomTypeNormal;
                else if(mode=="customized") z=Device::DevTargetZoomTypeCustomized;
                else if(mode=="grop_headless") z=Device::DevTargetZoomTypeGropHeadless;
                else if(mode=="grop_lower_body") z=Device::DevTargetZoomTypeGropLowerBody;
                else if(mode=="adaptive") z=Device::DevTargetZoomTypeAdaptive;
                else throw std::runtime_error("unsupported framing");
            }
            checked_rc(call("aiSetTargetZoomTypeR",[&]{return dev_->aiSetTargetZoomTypeR(z);}));
        } else if (op=="framing.get") {
            return {{"zoom_type",nullptr},{"status","NO_PUBLIC_PATH"},
                    {"reason","no aiGetTargetZoomTypeR / aiGetTargetViewTypeR in public headers; read ai_sub_mode instead"}};
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
            if (a.if_contains("x")) { float v=static_cast<float>(num(a,"x",-100,100)); checked_rc(call("aiSetHorizontalOffset",[&]{return dev_->aiSetHorizontalOffset(v);})); return {{"x",v}}; }
            if (a.if_contains("y")) { float v=static_cast<float>(num(a,"y",-100,100)); checked_rc(call("aiSetVerticalOffset",[&]{return dev_->aiSetVerticalOffset(v);})); return {{"y",v}}; }
            throw std::runtime_error("provide auto/x/y");
        } else if(op=="ai.offset.get") {
            compatibility();
            j::object out;
            float x=0; int rc1=call("aiGetHorizontalOffset",[&]{return dev_->aiGetHorizontalOffset(x);});
            out["horiz_rc"]=rc1; if(rc1==0) out["horiz"]=x;
            float y=0; int rc2=call("aiGetVerticalOffset",[&]{return dev_->aiGetVerticalOffset(y);});
            out["vert_rc"]=rc2; if(rc2==0) out["vert"]=y;
            bool ao=false; int rc3=call("aiGetAutoOffsetEnable",[&]{return dev_->aiGetAutoOffsetEnable(ao);});
            out["auto_rc"]=rc3; if(rc3==0) out["auto"]=ao;
            return out;
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
        } else if(op=="gimbal.angle") {
            compatibility();
            const double pitch=num(a,"pitch",-90,90), yaw=num(a,"yaw",-180,180);
            const double roll=a.if_contains("roll")?num(a,"roll",-180,180):-1000.0;
            checked_rc(call("aiSetGimbalMotorAngleR",[&]{return dev_->aiSetGimbalMotorAngleR(
                static_cast<float>(pitch),static_cast<float>(yaw),static_cast<float>(roll));}));
        } else if(op=="gimbal.speed") {
            compatibility();
            const double pitch=num(a,"pitch",-180,180), pan=num(a,"pan",-180,180);
            const double roll=a.if_contains("roll")?num(a,"roll",-180,180):0.0;
            checked_rc(call("aiSetGimbalSpeedCtrlR",[&]{return dev_->aiSetGimbalSpeedCtrlR(pitch,pan,roll);}));
        } else if(op=="gimbal.native_stop") {
            compatibility();
            checked_rc(call("aiSetGimbalStop",[&]{return dev_->aiSetGimbalStop();}));
        } else if(op=="gimbal.bootpos.trg") {
            compatibility(); const bool reset_mode=a.if_contains("reset_mode")?boolean(a,"reset_mode"):false;
            checked_rc(call("aiTrgGimbalBootPosR",[&]{return dev_->aiTrgGimbalBootPosR(reset_mode);}));
        } else if(op=="gimbal.para.set") {
            compatibility();
            const int t=static_cast<int>(num(a,"type",0,100));
            const auto para=static_cast<Device::DevGimbalParaType>(t);
            const std::string k=str(a,"kind"); const char kind=k.empty()?'f':k[0];
            if(kind=='b'){ const bool v=boolean(a,"value");
                checked_rc(call("aiSetGimbalParaR(bool)",[&]{return dev_->aiSetGimbalParaR(para,v);})); }
            else { const double v=num(a,"value",-100000,100000);
                checked_rc(call("aiSetGimbalParaR(float)",[&]{return dev_->aiSetGimbalParaR(para,static_cast<float>(v));})); }
        } else if(op=="gimbal.yawreverse.set") {
            compatibility(); const bool on=boolean(a,"enabled");
            checked_rc(call("aiSetGimbalYawDirReverseR",[&]{return dev_->aiSetGimbalYawDirReverseR(on);}));
        } else if(op=="gimbal.pos.speed") {
            compatibility();
            const double roll=num(a,"roll",-90,90), pitch=num(a,"pitch",-90,90), yaw=num(a,"yaw",-90,90);
            const double sroll=a.if_contains("s_roll")?num(a,"s_roll",-90,90):0.0;
            const double spitch=a.if_contains("s_pitch")?num(a,"s_pitch",-90,90):0.0;
            const double syaw=a.if_contains("s_yaw")?num(a,"s_yaw",-90,90):0.0;
            checked_rc(call("gimbalSetSpeedPositionR",[&]{return dev_->gimbalSetSpeedPositionR(
                static_cast<float>(roll),static_cast<float>(pitch),static_cast<float>(yaw),
                static_cast<float>(sroll),static_cast<float>(spitch),static_cast<float>(syaw));}));
        } else if(op=="view.set") {
            compatibility(); const int v=static_cast<int>(num(a,"view_type",-2,99));
            checked_rc(call("aiSetTargetViewTypeR",[&]{return dev_->aiSetTargetViewTypeR(
                static_cast<Device::DevTargetViewType>(v));}));
        } else if(op=="zoom.relative") {
            compatibility();
            const int step=static_cast<int>(num(a,"step",1,100)), speed=static_cast<int>(num(a,"speed",1,255));
            const bool step_mode=a.if_contains("step_mode")?boolean(a,"step_mode"):false;
            const bool in_out=boolean(a,"in");
            checked_rc(call("cameraSetZoomWithSpeedRelativeR",[&]{return dev_->cameraSetZoomWithSpeedRelativeR(
                static_cast<uint32_t>(step),static_cast<uint32_t>(speed),step_mode,in_out);}));
        } else if(op=="zoom.withspeed") {
            compatibility();
            const int ratio=static_cast<int>(num(a,"ratio",0,1000)), speed=static_cast<int>(num(a,"speed",1,255));
            checked_rc(call("cameraSetZoomWithSpeedAbsoluteR",[&]{return dev_->cameraSetZoomWithSpeedAbsoluteR(
                static_cast<uint32_t>(ratio),static_cast<uint32_t>(speed));}));
        } else if(op=="zoom.stop") {
            compatibility();
            checked_rc(call("cameraSetZoomStopR",[&]{return dev_->cameraSetZoomStopR();}));
        } else if(op=="gesture.set") {
            compatibility(); const int t=static_cast<int>(num(a,"type",0,8));
            const auto type=static_cast<Device::DevGestureParaType>(t);
            const std::string k=str(a,"kind"); const char kind=k.empty()?'b':k[0];
            if(kind=='b'){ const double v=num(a,"value",0,1);
                checked_rc(call("aiSetGestureParaR(bool)",[&]{return dev_->aiSetGestureParaR(type,v!=0.0);})); }
            else { const double v=num(a,"value",-100000,100000);
                checked_rc(call("aiSetGestureParaR(float)",[&]{return dev_->aiSetGestureParaR(type,static_cast<float>(v));})); }
        } else if(op=="gesture.track.set") {
            compatibility(); const int t=static_cast<int>(num(a,"type",0,8));
            const auto type=static_cast<Device::DevGestureTrackParaType>(t);
            const std::string k=str(a,"kind"); const char kind=k.empty()?'b':k[0];
            if(kind=='b'){ const double v=num(a,"value",0,1);
                checked_rc(call("aiSetGestureTrackParaR(bool)",[&]{return dev_->aiSetGestureTrackParaR(type,v!=0.0);})); }
            else if(kind=='i'){ const double v=num(a,"value",-100000,100000);
                checked_rc(call("aiSetGestureTrackParaR(int)",[&]{return dev_->aiSetGestureTrackParaR(type,static_cast<int>(v));})); }
            else { const double v=num(a,"value",-100000,100000);
                checked_rc(call("aiSetGestureTrackParaR(float)",[&]{return dev_->aiSetGestureTrackParaR(type,static_cast<float>(v));})); }
        } else if(op=="gesture.ctrl.set") {
            compatibility(); const bool on=boolean(a,"enabled");
            checked_rc(call("aiSetGestureCtrlR",[&]{return dev_->aiSetGestureCtrlR(on);}));
        } else if(op=="zone.set") {
            compatibility(); const std::string which=str(a,"which");
            if(which=="yaw_min"){ const double v=num(a,"value",-180,180); checked_rc(call("aiSetLimitedZoneTrackYawMinR",[&]{return dev_->aiSetLimitedZoneTrackYawMinR(static_cast<float>(v));})); }
            else if(which=="yaw_max"){ const double v=num(a,"value",-180,180); checked_rc(call("aiSetLimitedZoneTrackYawMaxR",[&]{return dev_->aiSetLimitedZoneTrackYawMaxR(static_cast<float>(v));})); }
            else if(which=="pitch_min"){ const double v=num(a,"value",-90,90); checked_rc(call("aiSetLimitedZoneTrackPitchMinR",[&]{return dev_->aiSetLimitedZoneTrackPitchMinR(static_cast<float>(v));})); }
            else if(which=="pitch_max"){ const double v=num(a,"value",-90,90); checked_rc(call("aiSetLimitedZoneTrackPitchMaxR",[&]{return dev_->aiSetLimitedZoneTrackPitchMaxR(static_cast<float>(v));})); }
            else throw std::runtime_error("which must be yaw_min|yaw_max|pitch_min|pitch_max");
        } else if(op=="zone.enabled.set") {
            compatibility(); const bool on=boolean(a,"enabled");
            checked_rc(call("aiSetLimitedZoneTrackEnabledR",[&]{return dev_->aiSetLimitedZoneTrackEnabledR(on);}));
        } else if(op=="zone.autoselect.set") {
            compatibility(); const bool on=boolean(a,"enabled");
            checked_rc(call("aiSetLimitedZoneTrackAutoSelectR",[&]{return dev_->aiSetLimitedZoneTrackAutoSelectR(on);}));
        } else if(op=="zone.state.set") {
            compatibility(); const bool on=boolean(a,"enabled");
            checked_rc(call("aiSetZoneTrackStateR",[&]{return dev_->aiSetZoneTrackStateR(on);}));
        } else if(op=="zone.gimbal.set") {
            compatibility(); const bool on=boolean(a,"enabled");
            checked_rc(call("aiSetZoneTrackGimbalEnabledR",[&]{return dev_->aiSetZoneTrackGimbalEnabledR(on);}));
        } else if(op=="zone.initpos.trg") {
            compatibility();
            checked_rc(call("aiTrgLimitedZoneTrackInitPosR",[&]{return dev_->aiTrgLimitedZoneTrackInitPosR();}));
        } else if(op=="trackingmode.set") {
            compatibility(); const int m=static_cast<int>(num(a,"mode",0,10));
            checked_rc(call("aiSetTrackingModeR",[&]{return dev_->aiSetTrackingModeR(static_cast<Device::AiVerticalTrackType>(m));}));
        } else if(op=="iq.autofocus.set") {
            compatibility(); const int v=static_cast<int>(num(a,"value",0,3));
            checked_rc(call("cameraSetAutoFocusModeR",[&]{return dev_->cameraSetAutoFocusModeR(static_cast<Device::DevAutoFocusType>(v));}));
        } else if(op=="iq.afc.set") {
            compatibility(); const int v=static_cast<int>(num(a,"value",0,3));
            checked_rc(call("cameraSetAFCTrackModeR",[&]{return dev_->cameraSetAFCTrackModeR(static_cast<Device::DevAFCType>(v));}));
        } else if(op=="iq.wb.set") {
            compatibility(); const int v=static_cast<int>(num(a,"value",0,255)); const int param=static_cast<int>(num(a,"param",-100000,100000));
            checked_rc(call("cameraSetWhiteBalanceR",[&]{return dev_->cameraSetWhiteBalanceR(static_cast<Device::DevWhiteBalanceType>(v),param);}));
        } else if(op=="iq.wdr.set") {
            compatibility(); const int v=static_cast<int>(num(a,"value",0,4));
            checked_rc(call("cameraSetWdrR",[&]{return dev_->cameraSetWdrR(v);}));
        } else if(op=="media.encode.set") {
            compatibility(); const std::string kind=str(a,"kind");
            const bool night=a.if_contains("night")?boolean(a,"night"):false;
            Device::DevMediaEncodeParam p{};
            p.width=static_cast<int>(num(a,"width",-1,100000));
            p.height=static_cast<int>(num(a,"height",-1,100000));
            p.fps=static_cast<int>(num(a,"fps",-1,1000000));
            p.bitrate=static_cast<int>(num(a,"bitrate",-1,1000000000));
            p.encode_format=static_cast<Device::DevVideoEncoderFormat>(
                static_cast<int>(num(a,"encode_format",0,5)));
            if(kind=="record") checked_rc(call("cameraSetRecordEncodeParamR",[&]{return dev_->cameraSetRecordEncodeParamR(p,night);}));
            else if(kind=="output") checked_rc(call("cameraSetOutputEncodeParamR",[&]{return dev_->cameraSetOutputEncodeParamR(p,night);}));
            else throw std::runtime_error("kind must be record|output (live encode has no public setter)");
        } else if(op=="media.split.set") {
            compatibility(); const int v=static_cast<int>(num(a,"value",0,6));
            checked_rc(call("cameraSetRecordSplitSizeR",[&]{return dev_->cameraSetRecordSplitSizeR(
                static_cast<Device::DevVideoSplitSizeType>(v));}));
        } else if(op=="media.ndirtsp.set") {
            compatibility(); const std::string field=str(a,"field");
            if(field=="select"){ const int v=static_cast<int>(num(a,"value",0,2));
                checked_rc(call("cameraSetSelectNdiOrRtspR",[&]{return dev_->cameraSetSelectNdiOrRtspR(static_cast<Device::RtspOrNdiEnabled>(v));})); }
            else if(field=="bitrate"){ const int v=static_cast<int>(num(a,"value",0,3));
                checked_rc(call("cameraSetNdiRtspBitrateLevelR",[&]{return dev_->cameraSetNdiRtspBitrateLevelR(static_cast<Device::DevVideoBitLevelType>(v));})); }
            else if(field=="format"){ const int v=static_cast<int>(num(a,"value",0,5));
                checked_rc(call("cameraSetNdiRtspEncoderFormatR",[&]{return dev_->cameraSetNdiRtspEncoderFormatR(static_cast<Device::DevVideoEncoderFormat>(v));})); }
            else throw std::runtime_error("field must be select|bitrate|format");
        } else if(op=="media.hdmi.set") {
            compatibility(); const std::string field=str(a,"field");
            Device::HdmiInfo info{}; const int grc=call("cameraGetHdmiInfoR",[&]{return dev_->cameraGetHdmiInfoR(info);});
            if(grc!=0) throw std::runtime_error("read-before-write failed");
            if(field=="osd_language") info.osd_language=static_cast<Device::HdmiOsdLanguage>(static_cast<int>(num(a,"value",0,8)));
            else if(field=="content") info.content=static_cast<Device::HdmiOutputContent>(static_cast<int>(num(a,"value",0,1)));
            else if(field=="volume") info.volume=static_cast<int>(num(a,"value",0,100));
            else if(field=="resolution") info.resolution=static_cast<Device::DevVideoResType>(static_cast<int>(num(a,"value",0,255)));
            else if(field=="info_display") info.info_display=static_cast<int>(num(a,"value",0,1));
            else throw std::runtime_error("field must be osd_language|content|volume|resolution|info_display");
            checked_rc(call("cameraSetHdmiInfoR",[&]{return dev_->cameraSetHdmiInfoR(info);}));
        } else if(op=="power.ctrl") {
            compatibility(); const int act=static_cast<int>(num(a,"action",0,4));
            checked_rc(call("cameraSetPowerCtrlActionR",[&]{return dev_->cameraSetPowerCtrlActionR(
                static_cast<Device::DevPowerCtrlActionType>(act));}));
        } else if(op=="status.refresh") {
            compatibility(); const bool fast=boolean(a,"fast");
            const int v=static_cast<int>(num(a,"value",0,100000));
            if(fast) call("fastNextRefreshDevStatus",[&]{dev_->fastNextRefreshDevStatus(v); return 0;});
            else call("nextRefreshDevStatus",[&]{dev_->nextRefreshDevStatus(v); return 0;});
        } else if(op=="status.camera.read") {
            compatibility();
            Device::CameraStatus st=dev_->cameraStatus();
            const unsigned char *raw=reinterpret_cast<const unsigned char*>(&st);
            j::array head; for(size_t i=0;i<8;++i) head.emplace_back(static_cast<int>(raw[i]));
            return {{"callable",true},{"head_bytes",head},{"parsing","not attempted: Tail2 union layout undocumented"}};
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
