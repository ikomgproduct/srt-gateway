import pytest

@pytest.mark.asyncio
async def test_strict_probing_injection(async_client):
    payload = {
        "name": "Strict Probing SRT Stream",
        "source_protocol": "srt",
        "source_ip": "10.0.0.9",
        "source_port": 8800,
        "destination_url": "udp://239.0.0.2:5000",
        "enabled": True,
        "strict_probing": True,
        "auto_failover": True,
        "backup_input_ip": "10.0.0.10"
    }
    
    response = await async_client.post("/api/services", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["strict_probing"] is True
    assert data["auto_failover"] is True
    assert data["backup_input_ip"] == "10.0.0.10"
    service_id = data["id"]
    
    # Send a simulated PUT update mapping to stop and start explicitly
    payload["name"] = "Strict Probing Update"
    update_response = await async_client.put(f"/api/services/{service_id}", json=payload)
    assert update_response.status_code == 200
    
    del_resp = await async_client.delete(f"/api/services/{service_id}")
    assert del_resp.status_code == 200
