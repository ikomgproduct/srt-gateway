import pytest

@pytest.mark.asyncio
async def test_get_empty_services(async_client):
    response = await async_client.get("/api/services")
    assert response.status_code == 200
    assert response.json() == []

@pytest.mark.asyncio
async def test_create_and_delete_srt_service(async_client):
    payload = {
        "name": "Integration Test SRT Router",
        "source_protocol": "srt",
        "source_ip": "10.10.10.5",
        "source_port": 9500,
        "destination_url": "udp://239.0.0.1:4000",
        "enabled": True
    }
    
    # 1. Create native streaming pipeline
    response = await async_client.post("/api/services", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Integration Test SRT Router"
    assert "id" in data
    service_id = data["id"]
    
    # 2. Verify global distributed array perfectly saved the routing structure
    get_resp = await async_client.get("/api/services")
    assert len(get_resp.json()) == 1
    assert get_resp.json()[0]["config"]["id"] == service_id
    
    # 3. Simulate UI 'Stop Node' dispatch
    stop_resp = await async_client.post(f"/api/services/{service_id}/stop")
    assert stop_resp.status_code == 200
    
    # 4. Safely detach and purge the test vectors seamlessly
    del_resp = await async_client.delete(f"/api/services/{service_id}")
    assert del_resp.status_code == 200
    assert len((await async_client.get("/api/services")).json()) == 0
