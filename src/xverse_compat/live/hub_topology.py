"""Hub topology contract ``xverse-compat.hub-topology/1`` (Phase 8 WP-10 #2; ``docs/engineering/phase8/review-wp10-hub.md``).

A plain data record the U2 hub reads; compat never imports the blueprint package. ``from_system_document`` derives it
from the ``system.json`` of a generated topology form (blueprints ``automotive/assured-aeb/xdl/<arm>/topology/``):
the ``flows`` and the blueprint extension's ``returnFlows``, endpoint owners, element ``hostUnit`` and unit-host
``hostedElements``. Intra-unit messages are not hub-routed. Fail-closed on any inconsistency.
"""

from __future__ import annotations

from typing import Any

SCHEMA = "xverse-compat.hub-topology/1"
EXT = "io.xverse.assured-aeb"
HUB_ELEMENT = "loop-gateway"
ADAPTER_ELEMENT = "carla-client"


class TopologyError(ValueError):
    """The topology form or contract is inconsistent (fail-closed)."""


def _delay_steps(declaration: dict) -> int:
    delay = declaration.get("hubDelay")
    if delay is None:
        return 0
    if not isinstance(delay, dict) or delay.get("unit") != "simulator-step" or type(delay.get("value")) is not int \
            or delay["value"] < 0:
        raise TopologyError(f"hubDelay must be a non-negative int in simulator-step, got {delay!r}")
    return delay["value"]


def from_system_document(doc: dict) -> dict:
    """Return the hub-topology record of one arm's topology-form System document."""

    try:
        spec, ext = doc["spec"], doc["extensions"][EXT]
    except (KeyError, TypeError) as error:
        raise TopologyError("not a topology-form System document with the blueprint extension") from error
    owner = {}
    for endpoint in spec.get("endpoints", []):
        owner[endpoint["id"]] = endpoint.get("ownerId")
    units, host = {}, {}
    for instance in spec.get("componentInstances", []):
        iext = instance.get("extensions", {}).get(EXT, {})
        if iext.get("kind") == "unit-host":
            units[instance["id"]] = sorted(iext.get("hostedElements", []))
    for unit, elements in units.items():
        for element in elements:
            if element in host:
                raise TopologyError(f"element {element} is hosted by two units")
            host[element] = unit
    for instance in spec.get("componentInstances", []):
        iext = instance.get("extensions", {}).get(EXT, {})
        if iext.get("kind") == "element-placement" and host.get(instance["id"]) not in (None, iext.get("hostUnit")):
            raise TopologyError(f"element {instance['id']}: hostUnit disagrees with hostedElements")

    def element_of(endpoint_id):
        element = owner.get(endpoint_id)
        if element is None:
            raise TopologyError(f"endpoint {endpoint_id} has no owner")
        if element not in host:
            raise TopologyError(f"element {element} is hosted by no unit")
        return element

    declared = [(f["id"], f["sourceEndpointId"], list(f["destinationEndpointIds"]), f["extensions"][EXT], False)
                for f in spec.get("flows", [])]
    declared += [(f["id"], f["source"], [f["destination"]], f["declaration"], True) for f in ext.get("returnFlows", [])]
    if ADAPTER_ELEMENT not in host or HUB_ELEMENT not in host:
        raise TopologyError("the topology has no carla-client or loop-gateway element")
    adapter_unit, hub_unit = host[ADAPTER_ELEMENT], host[HUB_ELEMENT]
    flows, seen = [], set()
    for flow_id, source, destinations, declaration, is_return in declared:
        if flow_id in seen:
            raise TopologyError(f"duplicate flow {flow_id}")
        seen.add(flow_id)
        if declaration.get("intraUnit"):
            continue
        src = element_of(source)
        dsts = [element_of(d) for d in destinations]
        units_touched = {host[src]} | {host[d] for d in dsts}
        flows.append({"id": flow_id, "source": {"element": src, "unit": host[src]},
                      "destinations": [{"element": d, "unit": host[d]} for d in dsts],
                      "route": "adapter-link" if adapter_unit in units_touched else "hub",
                      "hubDelaySteps": _delay_steps(declaration), "returnFlow": is_return})
    flows.sort(key=lambda f: f["id"])
    return {"schema": SCHEMA, "arm": ext.get("arm"), "units": units, "hubUnit": hub_unit, "adapterUnit": adapter_unit,
            "flows": flows}


def validate(record: Any) -> dict:
    """Validate a hub-topology record (also one written by hand for tests); return it."""

    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        raise TopologyError(f"not a {SCHEMA} record")
    units = record.get("units")
    if not isinstance(units, dict) or record.get("hubUnit") not in units or record.get("adapterUnit") not in units:
        raise TopologyError("units, hubUnit and adapterUnit must be declared")
    host = {e: u for u, elements in units.items() for e in elements}
    ids = set()
    for flow in record.get("flows", []):
        if flow.get("id") in ids or not isinstance(flow.get("id"), str):
            raise TopologyError(f"flow id {flow.get('id')!r} missing or duplicated")
        ids.add(flow["id"])
        ends = [flow.get("source")] + list(flow.get("destinations") or [])
        if not flow.get("destinations") or any(not isinstance(e, dict) or host.get(e.get("element")) != e.get("unit") for e in ends):
            raise TopologyError(f"flow {flow['id']}: element and unit do not match the declared units")
        if flow.get("route") not in ("adapter-link", "hub") or type(flow.get("hubDelaySteps")) is not int or flow["hubDelaySteps"] < 0:
            raise TopologyError(f"flow {flow['id']}: route or hubDelaySteps invalid")
    return record
