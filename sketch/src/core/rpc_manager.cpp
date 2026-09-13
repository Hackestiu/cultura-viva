#include <Arduino_RouterBridge.h>
#include "rpc_manager.h"
#include "app_state.h"
#include "../location/gps_module.h"
#include "../display/camera_view.h"
#include "../display/minimap.h"

void initRPC() {
  Bridge.provide("photo_trigger", photo_trigger);
  Bridge.provide("confirm_photo_saved", confirm_photo_saved);
  Bridge.provide("view_switch_state", view_switch_state);
  Bridge.provide("receive_camera_chunk", receive_camera_chunk);
  Bridge.provide("get_personality_index", get_personality_index);
  Bridge.provide("is_recording_active", is_recording_active);
  Bridge.provide("set_recording_active", set_recording_active);
  Bridge.provide("camera_live_view_active", camera_live_view_active);
  Bridge.provide("set_processing_active", set_processing_active);
  Bridge.provide("is_processing_active", is_processing_active);
  Bridge.provide("set_playback_active", set_playback_active);
  Bridge.provide("is_playback_active", is_playback_active);
  Bridge.provide("get_volume", get_volume);
  Bridge.provide("has_gps_fix", has_gps_fix);
  Bridge.provide("get_gps_lat", get_gps_lat);
  Bridge.provide("get_gps_lon", get_gps_lon);
  Bridge.provide("mark_landmark_visited", mark_landmark_visited);
  Bridge.provide("set_location_by_id", set_location_by_id);
  Bridge.provide("set_location_xy", set_location_xy);
  Bridge.provide("set_minimap_location", set_minimap_location);
  Bridge.provide("reset_minimap", reset_minimap);
  Bridge.provide("set_photo_validation_state", set_photo_validation_state);
  Bridge.provide("set_retake_message", set_retake_message);
  Bridge.provide("set_detected_monument", set_detected_monument);
  Bridge.provide("receive_photo_chunk", receive_photo_chunk);
  Bridge.provide("is_photo_waiting_confirmation", is_photo_waiting_confirmation);
  Bridge.provide("is_map_completed", is_map_completed);
}
