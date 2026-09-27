"""Device managers: one module per supported `device_manager_type` config value."""

# config "device_manager_type" → module that defines `DeviceManager`
DEVICE_MANAGERS = {
    "dummy-device-manager": "agent_testers.device_managers.dummy_device_manager",
    "jinju-gemini": "agent_testers.device_managers.jinju_gemini_manager",
    "s25-gemini-live": "agent_testers.device_managers.s25_gemini_live_manager",
}
