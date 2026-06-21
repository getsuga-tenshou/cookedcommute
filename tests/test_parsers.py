"""Unit tests for the source parsers and derived-field logic (no network/DB)."""
from types import SimpleNamespace

from ingestion.config import BBox
from ingestion.pipeline import congestion_level, occupancy_pct
from ingestion.sources import ams_parking, ndw_traffic

# --- DATEX II fixtures ----------------------------------------------------- #
MEASUREMENT_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<d2:payload xmlns:d2="http://datex2.eu/schema/2/2_0">
  <d2:measurementSiteTable>
    <d2:measurementSiteRecord id="SITE_AMS_1">
      <d2:carriagewayCode>A10</d2:carriagewayCode>
      <d2:location><d2:pointCoordinates>
        <d2:latitude>52.3700</d2:latitude>
        <d2:longitude>4.8500</d2:longitude>
      </d2:pointCoordinates></d2:location>
    </d2:measurementSiteRecord>
    <d2:measurementSiteRecord id="SITE_FAR_1">
      <d2:location><d2:pointCoordinates>
        <d2:latitude>51.0000</d2:latitude>
        <d2:longitude>4.0000</d2:longitude>
      </d2:pointCoordinates></d2:location>
    </d2:measurementSiteRecord>
  </d2:measurementSiteTable>
</d2:payload>"""

TRAFFICSPEED_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<d2:payload xmlns:d2="http://datex2.eu/schema/2/2_0">
  <d2:publicationTime>2024-06-01T10:00:00Z</d2:publicationTime>
  <d2:siteMeasurements>
    <d2:measurementSiteReference id="SITE_AMS_1"/>
    <d2:measurementTimeDefault>2024-06-01T10:00:00Z</d2:measurementTimeDefault>
    <d2:measuredValue index="1"><d2:measuredValue>
      <d2:basicData><d2:vehicleFlow>
        <d2:vehicleFlowRate>1200</d2:vehicleFlowRate>
      </d2:vehicleFlow></d2:basicData>
    </d2:measuredValue></d2:measuredValue>
    <d2:measuredValue index="2"><d2:measuredValue>
      <d2:basicData><d2:averageVehicleSpeed>
        <d2:speed>42</d2:speed>
      </d2:averageVehicleSpeed></d2:basicData>
    </d2:measuredValue></d2:measuredValue>
  </d2:siteMeasurements>
</d2:payload>"""


def test_parse_measurement_config():
    cfg = ndw_traffic.parse_measurement_config(MEASUREMENT_XML)
    assert set(cfg) == {"SITE_AMS_1", "SITE_FAR_1"}
    assert abs(cfg["SITE_AMS_1"]["lat"] - 52.37) < 1e-6
    assert abs(cfg["SITE_AMS_1"]["lon"] - 4.85) < 1e-6
    assert cfg["SITE_AMS_1"]["road"] == "A10"


def test_parse_trafficspeed_no_double_count():
    live = ndw_traffic.parse_trafficspeed(TRAFFICSPEED_XML)
    # Nested measuredValue wrappers must NOT cause the flow to be counted twice.
    assert live["SITE_AMS_1"]["flow_veh_h"] == 1200
    assert live["SITE_AMS_1"]["speed_kmh"] == 42


def test_get_traffic_filters_to_bbox(monkeypatch):
    fake = SimpleNamespace(
        bbox=BBox(52.30, 52.42, 4.78, 5.02),
        ndw_trafficspeed_url="x",
        ndw_measurement_url="y",
    )

    monkeypatch.setattr(
        ndw_traffic, "load_measurement_config",
        lambda s: ndw_traffic.parse_measurement_config(MEASUREMENT_XML),
    )
    monkeypatch.setattr(ndw_traffic, "_fetch_gz", lambda url: TRAFFICSPEED_XML)

    rows = ndw_traffic.get_traffic(fake)
    ids = {r["site_id"] for r in rows}
    assert ids == {"SITE_AMS_1"}  # the far-away site is clipped out
    assert rows[0]["road"] == "A10"


# --- Amsterdam parking (NPR static) fixtures ------------------------------ #
NPR_FACILITY = {
    "name": "Q-Park Bijenkorf (Amsterdam)",
    "identifier": "abc-123",
    "specifications": [{"capacity": 700, "usage": "Garage"}],
    "accessPoints": [
        {"accessPointLocation": [{"latitude": 52.3731, "longitude": 4.8926}]}
    ],
}


def test_is_amsterdam_offstreet():
    assert ams_parking.is_amsterdam_offstreet("Q-Park Bijenkorf (Amsterdam)")
    assert ams_parking.is_amsterdam_offstreet("P+R ArenA (Amsterdam Zuidoost)")
    assert not ams_parking.is_amsterdam_offstreet("Straatparkeren Dam (Amsterdam)")
    assert not ams_parking.is_amsterdam_offstreet("Q-Park Byzantium (Utrecht)")
    assert not ams_parking.is_amsterdam_offstreet(None)


def test_extract_facility():
    row = ams_parking.extract_facility(NPR_FACILITY)
    assert row["garage_id"] == "abc-123"
    assert row["name"] == "Q-Park Bijenkorf (Amsterdam)"
    assert row["capacity"] == 700
    assert row["state"] == "Garage"
    assert row["free_spaces"] is None
    assert abs(row["lat"] - 52.3731) < 1e-6
    assert abs(row["lon"] - 4.8926) < 1e-6


def test_extract_facility_missing_coords():
    assert ams_parking.extract_facility({"identifier": "x", "specifications": []}) is None


# --- Derived-field logic --------------------------------------------------- #
def test_congestion_level():
    assert congestion_level(70, None) == "free"
    assert congestion_level(40, None) == "moderate"
    assert congestion_level(10, None) == "heavy"
    assert congestion_level(None, 1800) == "heavy"
    assert congestion_level(None, None) == "unknown"


def test_occupancy_pct():
    assert occupancy_pct(0, 100) == 100.0
    assert occupancy_pct(100, 100) == 0.0
    assert occupancy_pct(40, 200) == 80.0
    assert occupancy_pct(None, 100) is None
    assert occupancy_pct(10, 0) is None
