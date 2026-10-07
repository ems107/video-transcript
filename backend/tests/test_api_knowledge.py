def test_profile_versions_and_restore(client):
    p = client.post("/api/profiles", json={"name": "Trabajo", "context": "v1"}).json()
    client.put(f"/api/profiles/{p['id']}", json={"name": "Trabajo", "context": "v2"})
    client.put(f"/api/profiles/{p['id']}", json={"name": "Trabajo", "context": "v2"})  # sin cambios: sin versión
    versions = client.get(f"/api/profiles/{p['id']}/versions").json()
    assert [v["reason"] for v in versions] == ["Cambios manuales", "Creado"]
    assert versions[0]["diff"]["manual"] == ["context"]

    r = client.post(f"/api/profiles/{p['id']}/versions/{versions[-1]['id']}/restore")
    assert r.json()["context"] == "v1"
    versions = client.get(f"/api/profiles/{p['id']}/versions").json()
    assert versions[0]["reason"].startswith("Restaurada") and len(versions) == 3


def test_person_versions(client):
    p = client.post("/api/people", json={"name": "María"}).json()
    client.put(f"/api/people/{p['id']}", json={"name": "María López", "role": "PM"})
    versions = client.get(f"/api/people/{p['id']}/versions").json()
    assert len(versions) == 2
    r = client.post(f"/api/people/{p['id']}/versions/{versions[-1]['id']}/restore").json()
    assert r["name"] == "María" and r["role"] == ""
