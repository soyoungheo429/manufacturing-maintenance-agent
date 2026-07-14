import json

data = {
    "sensor_data": [
        {
            "facility_id": "설비2",
            "air_temp": 310.0,
            "process_temp": 318.0,
            "rotation_speed": 1400,
            "torque": 122.5,
            "tool_wear": 235
        }
    ]
}

path = r'c:\Users\soyoung\Desktop\work\클라우드PBL\프로젝트\manufacturing-maintenance-agent\lambda\anomaly_filter\payload.json'
with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False)
print("WRITTEN")
