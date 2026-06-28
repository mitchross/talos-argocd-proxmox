"""StuckAtPrototype AirCube air quality monitor quirk for ZHA.

Vendored from https://github.com/StuckAtPrototype/AirCube (zha/aircube.py).
Copied into /config/custom_zha_quirks/aircube.py by the home-assistant
copy-config initContainer; loaded via `zha.custom_quirks_path` in
configuration.yaml. After changing this file: redeploy, then remove and
re-pair the AirCube once (ZHA caches device data at first join).

This single file is compatible with both old and new Home Assistant:

  * Modern HA (zigpy >= 0.65.1, i.e. HA >= ~2024.8):
        Full quirks v2 support. Exposes eCO2, tVOC and AQI sensors from the
        custom 0xFC01 cluster plus a Brightness number on the Analog Output
        cluster.

  * Old HA (zigpy < 0.65, e.g. HA 2024.1.x):
        `zigpy.quirks.v2` does not exist yet, so importing QuirkBuilder raises
        ImportError and the whole quirk fails to load. We fall back to a classic
        v1 quirk so the module imports cleanly and the device is named correctly.

        IMPORTANT: on these old ZHA versions there is no supported way to turn
        custom-cluster (0xFC01) attributes into entities -- eCO2/tVOC/AQI will
        NOT appear until HA is updated to a version with quirks v2, or the values
        are read over BLE via the firmware's BTHome broadcaster. Temperature,
        humidity and brightness still work on old HA because they use standard
        Zigbee clusters and are discovered automatically.
"""

from zigpy.quirks import CustomCluster
from zigpy.zcl.foundation import ZCLAttributeDef
import zigpy.types as t


class AirQualityCluster(CustomCluster):
    """AirCube custom air quality cluster (0xFC01) — read-only sensors."""

    cluster_id = 0xFC01
    name = "AirCube Air Quality"
    ep_attribute = "aircube_air_quality"

    class AttributeDefs(CustomCluster.AttributeDefs):
        eco2 = ZCLAttributeDef(
            id=0x0000, type=t.uint16_t, is_manufacturer_specific=False
        )
        etvoc = ZCLAttributeDef(
            id=0x0001, type=t.uint16_t, is_manufacturer_specific=False
        )
        aqi = ZCLAttributeDef(
            id=0x0002, type=t.uint16_t, is_manufacturer_specific=False
        )


ANALOG_OUTPUT_CLUSTER_ID = 0x000D


# ---------------------------------------------------------------------------
# Detect whether this HA/zigpy version supports the quirks v2 API.
# ---------------------------------------------------------------------------
try:
    from zigpy.quirks.v2 import QuirkBuilder
    from zigpy.quirks.v2.homeassistant import EntityType

    try:
        from zigpy.quirks.v2.homeassistant.sensor import (
            SensorDeviceClass,
            SensorStateClass,
        )
    except ImportError:
        from homeassistant.components.sensor import (
            SensorDeviceClass,
            SensorStateClass,
        )

    _HAS_QUIRKS_V2 = True
except ImportError:
    _HAS_QUIRKS_V2 = False


if _HAS_QUIRKS_V2:
    # -----------------------------------------------------------------------
    # Modern HA: full quirks v2 definition.
    # -----------------------------------------------------------------------
    (
        QuirkBuilder("StuckAtPrototype", "AirCube")
        .replaces(AirQualityCluster, endpoint_id=10)
        .sensor(
            AirQualityCluster.AttributeDefs.eco2.name,
            AirQualityCluster.cluster_id,
            endpoint_id=10,
            unit="ppm",
            translation_key="equivalent_co2",
            state_class=SensorStateClass.MEASUREMENT,
            fallback_name="Equivalent CO2",
        )
        .sensor(
            AirQualityCluster.AttributeDefs.etvoc.name,
            AirQualityCluster.cluster_id,
            endpoint_id=10,
            unit="ppb",
            device_class=SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS_PARTS,
            state_class=SensorStateClass.MEASUREMENT,
            fallback_name="tVOC",
        )
        .sensor(
            AirQualityCluster.AttributeDefs.aqi.name,
            AirQualityCluster.cluster_id,
            endpoint_id=10,
            state_class=SensorStateClass.MEASUREMENT,
            translation_key="voc_level",
            fallback_name="VOC Level",
        )
        .number(
            "present_value",
            ANALOG_OUTPUT_CLUSTER_ID,
            endpoint_id=10,
            min_value=0,
            max_value=100,
            step=1,
            mode="slider",
            entity_type=EntityType.STANDARD,
            translation_key="brightness",
            fallback_name="Brightness",
        )
        .add_to_registry()
    )
else:
    # -----------------------------------------------------------------------
    # Old HA (no quirks v2): classic v1 fallback.
    #
    # This keeps the module importable (stops the ImportError crash) and names
    # the device. Temperature, humidity and brightness are exposed by ZHA's
    # standard discovery. The eCO2/tVOC/AQI values on cluster 0xFC01 cannot be
    # surfaced as entities on this ZHA version -- update HA, or read them over
    # BLE (BTHome), for those.
    # -----------------------------------------------------------------------
    from zigpy.quirks import CustomDevice
    from zigpy.profiles import zha
    from zigpy.zcl.clusters.general import AnalogOutput, Basic, Identify
    from zigpy.zcl.clusters.measurement import (
        RelativeHumidity,
        TemperatureMeasurement,
    )
    from zhaquirks.const import (
        DEVICE_TYPE,
        ENDPOINTS,
        INPUT_CLUSTERS,
        MODELS_INFO,
        OUTPUT_CLUSTERS,
        PROFILE_ID,
    )

    class AirCube(CustomDevice):
        """AirCube v1 quirk for HA versions without quirks v2."""

        signature = {
            MODELS_INFO: [("StuckAtPrototype", "AirCube")],
            ENDPOINTS: {
                # <SimpleDescriptor endpoint=10 profile=260 device_type=770
                #  input_clusters=[0, 3, 13, 1026, 1029, 64513]
                #  output_clusters=[]>
                10: {
                    PROFILE_ID: zha.PROFILE_ID,
                    DEVICE_TYPE: zha.DeviceType.TEMPERATURE_SENSOR,
                    INPUT_CLUSTERS: [
                        Basic.cluster_id,
                        Identify.cluster_id,
                        AnalogOutput.cluster_id,
                        TemperatureMeasurement.cluster_id,
                        RelativeHumidity.cluster_id,
                        AirQualityCluster.cluster_id,
                    ],
                    OUTPUT_CLUSTERS: [],
                },
            },
        }

        replacement = {
            ENDPOINTS: {
                10: {
                    PROFILE_ID: zha.PROFILE_ID,
                    DEVICE_TYPE: zha.DeviceType.TEMPERATURE_SENSOR,
                    INPUT_CLUSTERS: [
                        Basic,
                        Identify,
                        AnalogOutput,
                        TemperatureMeasurement,
                        RelativeHumidity,
                        AirQualityCluster,
                    ],
                    OUTPUT_CLUSTERS: [],
                },
            },
        }
