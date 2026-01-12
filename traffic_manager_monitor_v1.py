#!/usr/bin/python3
# -*- coding: utf-8 -*-

import requests
import sys
import json
import argparse
from datetime import datetime, timedelta, timezone

# ====================================================================
# Obtain an Azure access token using Managed Identity (MSI)
# ====================================================================
def get_token():
    TOKEN_URL = "http://169.254.169.254/metadata/identity/oauth2/token"
    params = {
        "api-version": "2018-02-01",
        "resource": "https://management.azure.com/"
    }
    headers = {"Metadata": "true"}

    try:
        # Call the Azure Instance Metadata Service to get an access token
        response = requests.get(TOKEN_URL, params=params, headers=headers, timeout=5)
        response.raise_for_status()
        return response.json().get("access_token")
    except Exception as e:
        # Return a JSON-formatted error if token retrieval fails
        print(json.dumps({"error": f"Error getting token: {e}"}))
        return None

# ====================================================================
# Query Traffic Manager profile details (API version 2022-04-01)
# ====================================================================
def get_traffic_manager_profile(subscription_id, resource_group, profile_name):
    token = get_token()
    if not token:
        return None, 1  # Token error

    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group}"
        f"/providers/Microsoft.Network/trafficmanagerprofiles/{profile_name}"
    )
    params = {"api-version": "2022-04-01"}
    headers = {"Authorization": f"Bearer {token}"}

    try:
        # Query Traffic Manager profile properties
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        return response.json(), 0
    except Exception as e:
        # Return error code 2 if the API call fails
        return {"error": f"Error querying Traffic Manager: {e}"}, 2

# ====================================================================
# Query Azure Resource Health for the Traffic Manager Profile
# ====================================================================
def get_resource_health(subscription_id, resource_group, profile_name):
    token = get_token()
    if not token:
        return None

    resource_uri = (
        f"/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group}"
        f"/providers/Microsoft.Network/trafficmanagerprofiles/{profile_name}"
    )
    url = (
        f"https://management.azure.com{resource_uri}"
        f"/providers/Microsoft.ResourceHealth/availabilityStatuses/current"
    )
    params = {"api-version": "2022-10-01"}  # CAMBIO: Usar versión válida
    headers = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(json.dumps({"warning": f"Error querying Resource Health: {e}"}), file=sys.stderr)
        return None
# ====================================================================
# Query Azure Monitor metrics for the Traffic Manager Profile
# ====================================================================
def get_traffic_manager_metrics(subscription_id, resource_group, profile_name):
    token = get_token()
    if not token:
        return {}

    resource_id = (
        f"/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group}"
        f"/providers/Microsoft.Network/trafficmanagerprofiles/{profile_name}"
    )
    url = f"https://management.azure.com{resource_id}/providers/microsoft.insights/metrics"

    # Define a 5-minute time window ending now (UTC)
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=5)
    timespan = "{}/{}".format(
        start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    params = {
        "api-version": "2018-01-01",
        "timespan": timespan,
        "interval": "PT1M",
        "metricnames": (
            "QpsByEndpoint,ProbeAgentCurrentEndpointStateByProfileResourceId"
        ),
        "aggregation": "Average,Maximum"
    }
    headers = {"Authorization": f"Bearer {token}"}

    try:
        # Retrieve Azure Monitor metrics
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        # Log warning but do not fail execution
        print(json.dumps({"warning": f"Error querying metrics: {e}"}), file=sys.stderr)
        return {}

# ====================================================================
# Parse Azure Monitor metrics and extract latest values
# ====================================================================
def parse_metrics(metrics_data):
    if not metrics_data or "value" not in metrics_data:
        return {}

    parsed_metrics = {}

    for metric in metrics_data.get("value", []):
        metric_name = metric.get("name", {}).get("value")
        timeseries = metric.get("timeseries", [])

        if not timeseries:
            continue

        # For metrics with multiple timeseries (like per-endpoint metrics)
        if metric_name == "ProbeAgentCurrentEndpointStateByProfileResourceId":
            endpoint_states = []
            for ts in timeseries:
                data_points = ts.get("data", [])
                metadatavalues = ts.get("metadatavalues", [])

                # Extract endpoint name from metadata
                endpoint_name = None
                for mv in metadatavalues:
                    if mv.get("name", {}).get("value") == "ProfileResourceId":
                        endpoint_name = mv.get("value")
                        break

                # Get latest state value
                if data_points:
                    latest_value = None
                    for point in reversed(data_points):
                        if point.get("average") is not None:
                            latest_value = point.get("average")
                            break
                        elif point.get("maximum") is not None:
                            latest_value = point.get("maximum")
                            break

                    if latest_value is not None and endpoint_name:
                        endpoint_states.append({
                            "endpoint": endpoint_name.split('/')[-1] if endpoint_name else "unknown",
                            "state": "Online" if latest_value == 1 else "Degraded" if latest_value == 0.5 else "Offline"
                        })

            if endpoint_states:
                parsed_metrics["endpointStates"] = endpoint_states
        else:
            # Use the most recent available data point
            data_points = timeseries[0].get("data", [])
            if data_points:
                latest_value = None
                for point in reversed(data_points):
                    if point.get("average") is not None:
                        latest_value = point.get("average")
                        break
                    elif point.get("maximum") is not None:
                        latest_value = point.get("maximum")
                        break

                if latest_value is not None:
                    parsed_metrics[metric_name] = latest_value

    return parsed_metrics

# ====================================================================
# Parse Azure Resource Health status
# ====================================================================
def parse_health_status(health_data):
    if not health_data:
        return None

    properties = health_data.get("properties", {})
    availability_state = properties.get("availabilityState", "Unknown")

    # Map Azure availability states to simplified health states
    health_mapping = {
        "Available": "Available",
        "Unavailable": "Unavailable",
        "Degraded": "Degraded",
        "Unknown": "Unknown"
    }

    return health_mapping.get(availability_state, "Unknown")

# ====================================================================
# Calculate health status based on endpoint states and profile status
# ====================================================================
def calculate_health_from_profile(profile_data, metrics):
    if not profile_data:
        return "Unknown"

    # Check profile status
    profile_status = profile_data.get("properties", {}).get("profileStatus")

    # If profile is disabled, report as such
    if profile_status == "Disabled":
        return "Disabled"

    # Check endpoint states from metrics if available
    endpoint_states = metrics.get("endpointStates", [])
    if endpoint_states:
        online_count = sum(1 for ep in endpoint_states if ep["state"] == "Online")
        total_count = len(endpoint_states)

        if online_count == 0:
            return "Unavailable"
        elif online_count < total_count:
            return "Degraded"
        else:
            return "Available"

    # Check endpoints from profile data
    endpoints = profile_data.get("properties", {}).get("endpoints", [])
    if endpoints:
        enabled_count = sum(1 for ep in endpoints
                          if ep.get("properties", {}).get("endpointStatus") == "Enabled")
        total_enabled = sum(1 for ep in endpoints
                           if ep.get("properties", {}).get("endpointStatus") != "Disabled")

        if total_enabled == 0:
            return "No active endpoints"
        elif enabled_count == 0:
            return "Unavailable"
        elif enabled_count < total_enabled:
            return "Degraded"
        else:
            return "Available"

    # If profile is enabled but we can't determine endpoint status
    if profile_status == "Enabled":
        return "Available"

    return "Unknown"

# ====================================================================
# Parse all relevant Traffic Manager Profile properties
# ====================================================================
def parse_traffic_manager_data(data):
    if not data or isinstance(data, dict) and data.get("error"):
        return data if isinstance(data, dict) else {}

    props = data.get("properties", {})
    parsed_endpoints = []

    for ep in props.get("endpoints", []):
        ep_props = ep.get("properties", {})

        parsed_endpoints.append({
            "id": ep.get("id"),
            "name": ep.get("name"),
            "type": ep.get("type"),
            "target": ep_props.get("target"),
            "endpointStatus": ep_props.get("endpointStatus"),
            "endpointMonitorStatus": ep_props.get("endpointMonitorStatus"),
            "priority": ep_props.get("priority"),
            "weight": ep_props.get("weight"),
            "endpointLocation": ep_props.get("endpointLocation"),
            "minChildEndpoints": ep_props.get("minChildEndpoints"),
            "geoMapping": ep_props.get("geoMapping"),
            "subnets": ep_props.get("subnets"),
            "customHeaders": ep_props.get("customHeaders")
        })

    monitor_config = props.get("monitorConfig", {})
    dns_config = props.get("dnsConfig", {})

    return {
        "name": data.get("name"),
        "location": data.get("location"),
        "profileStatus": props.get("profileStatus"),
        "trafficRoutingMethod": props.get("trafficRoutingMethod"),
        "dnsConfig": {
            "relativeName": dns_config.get("relativeName"),
            "fqdn": dns_config.get("fqdn"),
            "ttl": dns_config.get("ttl")
        },
        "monitorConfig": {
            "profileMonitorStatus": monitor_config.get("profileMonitorStatus"),
            "protocol": monitor_config.get("protocol"),
            "port": monitor_config.get("port"),
            "path": monitor_config.get("path"),
            "intervalInSeconds": monitor_config.get("intervalInSeconds"),
            "timeoutInSeconds": monitor_config.get("timeoutInSeconds"),
            "toleratedNumberOfFailures": monitor_config.get("toleratedNumberOfFailures"),
            "expectedStatusCodeRanges": monitor_config.get("expectedStatusCodeRanges"),
            "customHeaders": monitor_config.get("customHeaders")
        },
        "endpoints": parsed_endpoints,
        "trafficViewEnrollmentStatus": props.get("trafficViewEnrollmentStatus"),
        "maxReturn": props.get("maxReturn"),
        "allowedEndpointRecordTypes": props.get("allowedEndpointRecordTypes")
    }

# ====================================================================
# Main execution logic
# ====================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Traffic Manager monitor: returns JSON with properties, metrics, and health status."
    )
    parser.add_argument("subscription_id", help="Subscription ID (GUID)")
    parser.add_argument("resource_group", help="Resource Group name")
    parser.add_argument("profile_name", help="Traffic Manager Profile name")

    args = parser.parse_args()

    # 1) Retrieve Traffic Manager profile information
    raw, rc = get_traffic_manager_profile(
        args.subscription_id,
        args.resource_group,
        args.profile_name
    )

    if rc == 1:
        # Token acquisition error
        print(json.dumps({"error": "Failed to obtain MSI token."}))
        sys.exit(1)
    elif rc == 2 and isinstance(raw, dict) and raw.get("error"):
        print(json.dumps(raw))
        sys.exit(2)

    parsed = parse_traffic_manager_data(raw)

    # 2) Retrieve and parse metrics
    metrics_raw = get_traffic_manager_metrics(
        args.subscription_id,
        args.resource_group,
        args.profile_name
    )
    metrics = parse_metrics(metrics_raw)
    parsed["metrics"] = metrics

    # 3) Determine health status (API first, then profile/metrics as fallback)
    health_raw = get_resource_health(
        args.subscription_id,
        args.resource_group,
        args.profile_name
    )
    health_status_from_api = parse_health_status(health_raw)
    health_status_from_profile = calculate_health_from_profile(raw, metrics)

    parsed["healthStatus"] = (
        health_status_from_api if health_status_from_api else health_status_from_profile
    )

    # Output JSON formatted for Zabbix consumption
    json_output = json.dumps({"data": parsed}, indent=4)
    print(json_output)
    sys.exit(0)

# ====================================================================
# Script entry point
# ====================================================================
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Catch any unexpected errors
        print(json.dumps({"error": f"Unexpected error: {e}"}))
        sys.exit(3)
