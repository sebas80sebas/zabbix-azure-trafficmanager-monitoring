# Azure Traffic Manager Monitoring Setup Guide

This guide explains how to set up monitoring for Azure Traffic Manager profiles using Zabbix with Managed Identity authentication.

## Overview

This setup allows a Zabbix proxy running on an Azure VM to monitor Traffic Manager profiles using Azure's Managed Identity for secure authentication, eliminating the need for storing credentials.

## Prerequisites

- Azure VM with Managed Identity enabled
- Zabbix server installed on the VM
- Python 3.8+ with `requests` module
- Azure CLI installed and configured
- Appropriate Azure subscription access

## Step 1: Configure Managed Identity

### 1.1 Verify Managed Identity

First, retrieve your VM's Managed Identity Principal ID:

```bash
VM_IDENTITY=$(az vm show -g <RESOURCE_GROUP> -n <VM_NAME> --query identity.principalId -o tsv)
echo $VM_IDENTITY
```

Expected output format: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`

### 1.2 Test Managed Identity Token

Verify the VM can obtain authentication tokens:

```bash
curl -H "Metadata:true" "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https://management.azure.com/"
```

## Step 2: Assign Azure Roles

### 2.1 Get Subscription ID

```bash
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
```

### 2.2 Assign Reader Role

Grant the Managed Identity read access to the Traffic Manager profile:

```bash
az role assignment create \
  --assignee-object-id $VM_IDENTITY \
  --assignee-principal-type ServicePrincipal \
  --role "Reader" \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/<RESOURCE_GROUP>/providers/Microsoft.Network/trafficManagerProfiles/<PROFILE_NAME>"
```

### 2.3 Assign Monitoring Reader Role

Grant access to metrics data:

```bash
az role assignment create \
  --assignee-object-id $VM_IDENTITY \
  --assignee-principal-type ServicePrincipal \
  --role "Monitoring Reader" \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/<RESOURCE_GROUP>/providers/Microsoft.Network/trafficManagerProfiles/<PROFILE_NAME>"
```

### 2.4 Verify Role Assignments

```bash
az role assignment list \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/<RESOURCE_GROUP>/providers/Microsoft.Network/trafficManagerProfiles/<PROFILE_NAME>" \
  --query "[].{Role:roleDefinitionName, PrincipalId:principalId, PrincipalType:principalType}" \
  -o table
```

Expected output:
```
Role               PrincipalId                           PrincipalType
-----------------  ------------------------------------  ----------------
Reader             xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx  ServicePrincipal
Monitoring Reader  xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx  ServicePrincipal
```

## Step 3: Deploy Monitoring Script

### 3.1 Transfer Script to Zabbix Server

From your management workstation:

```bash
# Linux/Mac
scp traffic_manager_monitor.py <username>@<zabbix-server-ip>:/home/<username>/

# Windows (using PowerShell or Command Prompt with OpenSSH)
scp C:\path\to\traffic_manager_monitor.py <username>@<zabbix-server-ip>:/home/<username>/
```

### 3.2 Move Script to Zabbix Directory

On the Zabbix server:

```bash
sudo mv /home/<username>/traffic_manager_monitor.py /usr/lib/zabbix/externalscripts/
```

### 3.3 Set Permissions

```bash
sudo chmod +x /usr/lib/zabbix/externalscripts/traffic_manager_monitor.py
sudo chown zabbix:zabbix /usr/lib/zabbix/externalscripts/traffic_manager_monitor.py
```

### 3.4 Verify Permissions

```bash
ls -la /usr/lib/zabbix/externalscripts/traffic_manager_monitor.py
```

Expected output:
```
-rwxrwxr-x 1 zabbix zabbix 12345 Dec 29 10:42 /usr/lib/zabbix/externalscripts/traffic_manager_monitor.py
```

## Step 4: Verify Dependencies

### 4.1 Check Python Version

```bash
python3 --version
```

Required: Python 3.8 or higher

### 4.2 Verify Requests Module

```bash
python3 -c "import requests; print('requests OK')"
```

### 4.3 Install Requests (if needed)

**Debian/Ubuntu:**
```bash
sudo apt-get install python3-requests
```

**RHEL/CentOS:**
```bash
sudo yum install python3-requests
```

**Using pip:**
```bash
sudo pip3 install requests
```

## Step 5: Obtain Azure Resource Credentials

Before running the monitoring script, you need to gather three pieces of information from your Azure environment.

### 5.1 Subscription ID

Get your Azure subscription ID:

```bash
az account show --query id -o tsv
```

Example output:
```
xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

Alternatively, view all subscriptions:

```bash
az account list --query "[].{name:name, id:id, state:state}" -o table
```

### 5.2 Resource Group Name

Identify the resource group where your Traffic Manager profile is located. You can find this in:

- Azure Portal: Navigate to your Traffic Manager profile
- Azure CLI: List resource groups

```bash
az group list --query "[].name" -o table
```

Example: `MyTrafficManagerResourceGroup`

### 5.3 Traffic Manager Profile Name

Get the name of your Traffic Manager profile:

```bash
az network traffic-manager profile list --resource-group <YOUR_RESOURCE_GROUP> --query "[].name" -o table
```

Example: `MyTrafficManagerProfile`

### 5.4 Example Parameters

For this guide, the following example placeholders are used:

| Parameter | Placeholder |
|-----------|-------------|
| Subscription ID | `<SUBSCRIPTION_ID>` |
| Resource Group | `<RESOURCE_GROUP>` |
| Profile Name | `<PROFILE_NAME>` |

## Step 6: Test the Monitoring Script

The script requires three command-line arguments in the following order:

1. Subscription ID
2. Resource Group name
3. Traffic Manager Profile name

### 6.1 Script Syntax

```bash
sudo -u zabbix python3 /usr/lib/zabbix/externalscripts/traffic_manager_monitor.py <SUBSCRIPTION_ID> <RESOURCE_GROUP> <PROFILE_NAME>
```

### 6.2 Run the Script

Using your actual Azure credentials:

```bash
sudo -u zabbix python3 /usr/lib/zabbix/externalscripts/traffic_manager_monitor.py <SUBSCRIPTION_ID> <RESOURCE_GROUP> <PROFILE_NAME>
```

### Expected Output

```json
{
    "data": {
        "name": "MyTrafficManagerProfile",
        "location": "global",
        "profileStatus": "Enabled",
        "trafficRoutingMethod": "Performance",
        "dnsConfig": {
            "relativeName": "myapp",
            "fqdn": "myapp.trafficmanager.net",
            "ttl": 60
        },
        "monitorConfig": {
            "profileMonitorStatus": "Online",
            "protocol": "HTTPS",
            "port": 443,
            "path": "/health",
            "intervalInSeconds": 30,
            "timeoutInSeconds": 10,
            "toleratedNumberOfFailures": 3,
            "expectedStatusCodeRanges": [
                {
                    "min": 200,
                    "max": 202
                }
            ],
            "customHeaders": []
        },
        "endpoints": [
            {
                "id": "/subscriptions/.../endpoints/endpoint1",
                "name": "endpoint1",
                "type": "Microsoft.Network/trafficManagerProfiles/azureEndpoints",
                "target": "myapp-eastus.azurewebsites.net",
                "endpointStatus": "Enabled",
                "endpointMonitorStatus": "Online",
                "priority": 1,
                "weight": 100,
                "endpointLocation": "East US",
                "minChildEndpoints": null,
                "geoMapping": null,
                "subnets": null,
                "customHeaders": null
            },
            {
                "id": "/subscriptions/.../endpoints/endpoint2",
                "name": "endpoint2",
                "type": "Microsoft.Network/trafficManagerProfiles/azureEndpoints",
                "target": "myapp-westus.azurewebsites.net",
                "endpointStatus": "Enabled",
                "endpointMonitorStatus": "Online",
                "priority": 2,
                "weight": 100,
                "endpointLocation": "West US",
                "minChildEndpoints": null,
                "geoMapping": null,
                "subnets": null,
                "customHeaders": null
            }
        ],
        "trafficViewEnrollmentStatus": "Disabled",
        "maxReturn": null,
        "allowedEndpointRecordTypes": [
            "DomainName",
            "IPv4Address",
            "IPv6Address"
        ],
        "metrics": {
            "QpsByEndpoint": 1250.5,
            "endpointStates": [
                {
                    "endpoint": "endpoint1",
                    "state": "Online"
                },
                {
                    "endpoint": "endpoint2",
                    "state": "Online"
                }
            ]
        },
        "healthStatus": "Available"
    }
}
```

**Note**: The output includes comprehensive profile configuration, endpoint details, real-time metrics, and calculated health status.

## Monitored Metrics

The script collects the following metrics:

| Metric | Description | Unit |
|--------|-------------|------|
| QpsByEndpoint | Queries per second by endpoint | queries/s |
| ProbeAgentCurrentEndpointStateByProfileResourceId | Current endpoint state (Online/Degraded/Offline) | state |

## Script Features

The `traffic_manager_monitor.py` script provides:

- **Managed Identity Authentication**: Securely authenticates using Azure VM's managed identity (no credentials in code)
- **Comprehensive Profile Data**: Retrieves complete Traffic Manager profile properties including DNS config, monitoring settings, and endpoint details
- **Real-time Metrics**: Collects performance metrics over a 5-minute window from Azure Monitor
- **Endpoint State Monitoring**: Tracks individual endpoint health status (Online, Degraded, Offline)
- **Health Status**: Determines profile health using Azure Resource Health API with fallback to endpoint state-based calculation
- **JSON Output**: Returns structured JSON output optimized for Zabbix parsing
- **Error Handling**: Provides clear error messages and appropriate exit codes

### Health Status Logic

The script determines health status using the following priority:

1. **Azure Resource Health API** (primary): Maps availability states to health status
   - `Available` → `Available`
   - `Degraded` → `Degraded`
   - `Unavailable` → `Unavailable`
   - `Unknown` → `Unknown`

2. **Endpoint State-based Calculation** (fallback): Uses endpoint monitoring status
   - All endpoints online → `Available`
   - No endpoints online → `Unavailable`
   - Some endpoints online → `Degraded`
   - Profile disabled → `Disabled`
   - Cannot determine → `Unknown`

## Step 7: Configure Zabbix Template

### 7.1 Import the Zabbix Template

The Zabbix template is provided in three formats: XML, JSON, and YAML. Choose the format compatible with your Zabbix version.

#### Import via Web Interface

1. Log in to your Zabbix web interface
2. Navigate to **Configuration** → **Templates**
3. Click **Import** in the top-right corner
4. Click **Choose File** and select one of the template files:
   - `zbx_tm_template.xml` (recommended for most versions)
   - `zbx_tm_template.json`
   - `zbx_tm_template.yaml`
5. Review the import options:
   - Check **Create new** for templates, groups, and items
   - Check **Update existing** if reimporting
6. Click **Import**

#### Verify Import

After import, you should see:
- Template name: **Template Azure Traffic Manager**
- Group: **Virtual machines**
- Items: 2 total (1 master item + 1 dependent item)
- Triggers: 1 configured trigger
- Macros: 3 user macros

### 7.2 Template Components

#### Master Item (External Check)

| Property | Value |
|----------|-------|
| **Name** | Traffic Manager - Raw Data |
| **Type** | External check |
| **Key** | `traffic_manager_monitor.py[{$SUBSCRIPTION_ID},{$RESOURCE_GROUP},{$TM_PROFILE_NAME}]` |
| **Update interval** | 1m (default, configurable) |
| **Value type** | Text |
| **Description** | Executes the Python script and retrieves complete Traffic Manager profile data in JSON format |

This master item calls the monitoring script with three parameters (subscription ID, resource group, profile name) and stores the raw JSON response.

#### Dependent Items

The dependent item uses JSON path preprocessing to extract specific values from the master item's output:

##### Health Status Item

| Item Name | Key | Type | JSON Path | Description |
|-----------|-----|------|-----------|-------------|
| **Traffic Manager - Health Status** | `trafficmanager.healthstatus` | Character | `$.data.healthStatus` | Overall health status: Available, Degraded, Unavailable, Disabled, or Unknown |

### 7.3 Configured Triggers

The template includes 1 trigger for automated alerting:

#### High Priority

| Trigger Name | Expression | Description |
|--------------|------------|-------------|
| **Traffic Manager not Available** | `{last()}<>"Available"` | Fires when health status indicates the profile is not available |

### 7.4 Template Macros

The template uses three user macros that must be configured for each host:

| Macro | Description | Example Value |
|-------|-------------|---------------|
| **{$SUBSCRIPTION_ID}** | Azure Subscription ID where the Traffic Manager profile is located | `12345678-1234-1234-1234-123456789abc` |
| **{$RESOURCE_GROUP}** | Azure Resource Group name containing the Traffic Manager profile | `MyTrafficManagerRG` |
| **{$TM_PROFILE_NAME}** | Traffic Manager Profile name to monitor | `MyTrafficManagerProfile` |

These macros are referenced in the master item's key parameter and are passed as arguments to the monitoring script.

### 7.5 Create a Host for Traffic Manager Monitoring

#### 7.5.1 Create New Host

1. Navigate to **Configuration** → **Hosts**
2. Click **Create host** in the top-right corner
3. Configure the host:
   - **Host name**: `Azure Traffic Manager - <Profile Name>` (e.g., `Azure Traffic Manager - Production`)
   - **Visible name**: Same as host name or a friendly name
   - **Groups**: Select **Virtual machines** (or create a new group like "Azure Traffic Manager")
   - **Interfaces**: 
     - Since this uses external scripts, the agent interface is optional
     - You can add a dummy IP (e.g., `127.0.0.1`) or leave it empty
4. Click **Add**

#### 7.5.2 Link Template to Host

1. Go to the newly created host
2. Click the **Templates** tab
3. In the **Link new templates** field, start typing "Azure Traffic Manager"
4. Select **Template Azure Traffic Manager**
5. Click **Add** (under the template selection)
6. Click **Update** to save

#### 7.5.3 Configure Host Macros

1. On the host configuration page, go to the **Macros** tab
2. You'll see three inherited macros from the template (they appear with `{$...}` notation)
3. Click **Inherited and host macros** to expand the view
4. Configure each macro with your Azure values:

   | Macro | Value |
   |-------|-------|
   | `{$SUBSCRIPTION_ID}` | Your Azure subscription ID |
   | `{$RESOURCE_GROUP}` | Your resource group name |
   | `{$TM_PROFILE_NAME}` | Your Traffic Manager profile name |

   Example:
   ```
   {$SUBSCRIPTION_ID} = 12345678-abcd-efgh-ijkl-123456789012
   {$RESOURCE_GROUP} = Production-Network-RG
   {$TM_PROFILE_NAME} = TM-Profile-Primary
   ```

5. Click **Update** to save

### 7.6 Verify Monitoring

#### 7.6.1 Check Latest Data

1. Navigate to **Monitoring** → **Latest data**
2. Filter by your host name
3. You should see both items collecting data
4. The **Traffic Manager - Raw Data** item should show the full JSON output
5. The dependent item should show the extracted health status value

#### 7.6.2 Verify Items Are Working

After a few minutes, check that:
- Both items show recent timestamps
- Health status shows expected value ("Available", "Degraded", etc.)
- Raw data contains complete JSON with profile configuration
- No "Not supported" or error messages

#### 7.6.3 Test Triggers

You can verify triggers are working:
1. Navigate to **Monitoring** → **Problems**
2. Any active issues with the Traffic Manager profile will appear here
3. Check trigger expressions in **Configuration** → **Hosts** → [Your Host] → **Triggers**

### 7.7 Monitoring Multiple Profiles

To monitor multiple Traffic Manager profiles:

#### Option 1: Multiple Hosts (Recommended)

Create a separate host for each profile:
1. Follow steps 7.5.1 through 7.5.3 for each profile
2. Use descriptive host names (e.g., `Azure TM - Production`, `Azure TM - DR`)
3. Configure different macro values for each host

**Benefits:**
- Clear separation of monitoring data
- Individual trigger states per profile
- Easy to disable monitoring for specific profiles
- Better for reporting and dashboards

#### Option 2: Multiple Items on Single Host

Create multiple instances of items on a single host:
1. Clone the template items manually
2. Modify the keys and master item parameters
3. Create separate macros for each profile (e.g., `{$TM_PROFILE_NAME_1}`, `{$TM_PROFILE_NAME_2}`)

**Note:** This approach is more complex and not recommended unless you have specific requirements.

### 7.8 Customization Options

#### 7.8.1 Adjust Update Interval

To change how frequently the script runs:
1. Go to **Configuration** → **Hosts** → [Your Host] → **Items**
2. Click on **Traffic Manager - Raw Data** (the master item)
3. Modify the **Update interval** field (default: 1m)
4. Recommended intervals:
   - Production monitoring: 1-2 minutes
   - Development/testing: 5 minutes
   - Low-priority profiles: 10 minutes
5. Click **Update**

**Note:** All dependent items will automatically update when the master item updates.

#### 7.8.2 Add Custom Items for Endpoint Monitoring

To monitor individual endpoints from the JSON output:

1. Create a new item
2. Set **Type** to **Dependent item**
3. Set **Master item** to `traffic_manager_monitor.py[{$SUBSCRIPTION_ID},{$RESOURCE_GROUP},{$TM_PROFILE_NAME}]`
4. Add preprocessing step:
   - **Type**: JSONPath
   - **Parameters**: Your desired JSON path
   
Example paths:
- Profile status: `$.data.profileStatus`
- Routing method: `$.data.trafficRoutingMethod`
- DNS TTL: `$.data.dnsConfig.ttl`
- Monitor protocol: `$.data.monitorConfig.protocol`
- First endpoint status: `$.data.endpoints[0].endpointMonitorStatus`
- QPS metric: `$.data.metrics.QpsByEndpoint`
- First endpoint state: `$.data.metrics.endpointStates[0].state`

5. Configure remaining item properties (type, units, etc.)

#### 7.8.3 Add Triggers for Specific Conditions

Create additional triggers for specific monitoring needs:

**Example 1: Profile Disabled Alert**
- Expression: `{Template Azure Traffic Manager:trafficmanager.profilestatus.last()}<>"Enabled"`
- Severity: Warning
- Description: Alert when Traffic Manager profile is not enabled

**Example 2: QPS Threshold Alert**
- Create dependent item for QPS (JSONPath: `$.data.metrics.QpsByEndpoint`)
- Expression: `{Template Azure Traffic Manager:trafficmanager.qps.last()}>10000`
- Severity: Warning
- Description: Alert when queries per second exceed threshold

**Example 3: Endpoint Count Alert**
- Expression: `{Template Azure Traffic Manager:trafficmanager.endpointcount.last()}<2`
- Severity: High
- Description: Alert when fewer than 2 endpoints are available

## Troubleshooting

### Script Returns No Data or Errors

If you encounter issues with the script not returning data:

#### 1. Install dos2unix (if transferring from Windows)

Line ending issues from Windows can cause problems:

```bash
sudo apt-get update
sudo apt-get install dos2unix -y
```

#### 2. Convert Line Endings

```bash
sudo dos2unix /usr/lib/zabbix/externalscripts/traffic_manager_monitor.py
```

#### 3. Reset Permissions

```bash
sudo chmod +x /usr/lib/zabbix/externalscripts/traffic_manager_monitor.py
sudo chown zabbix:zabbix /usr/lib/zabbix/externalscripts/traffic_manager_monitor.py
```

#### 4. Test Again

```bash
sudo -u zabbix python3 /usr/lib/zabbix/externalscripts/traffic_manager_monitor.py <SUBSCRIPTION_ID> <RESOURCE_GROUP> <PROFILE_NAME>
```

### Common Issues

**Issue: "No module named 'requests'"**
- Solution: Install python3-requests package

**Issue: "Permission denied"**
- Solution: Verify script has execute permissions and is owned by zabbix user

**Issue: "Authentication failed"**
- Solution: Verify Managed Identity is properly configured and has required role assignments

**Issue: "Resource not found"**
- Solution: Verify the Traffic Manager profile resource path and ensure you have the correct subscription ID, resource group, and profile name

**Issue: "Profile shows as Disabled"**
- Solution: Check the profile status in Azure Portal - the profile may actually be disabled

**Issue: "Endpoints show as Degraded or Offline"**
- Solution: Check endpoint health in Azure Portal - endpoints may be experiencing connectivity issues or failing health checks

### Debug Mode

To see detailed error messages, run the script with Python's verbose mode:

```bash
sudo -u zabbix python3 -v /usr/lib/zabbix/externalscripts/traffic_manager_monitor.py <SUBSCRIPTION_ID> <RESOURCE_GROUP> <PROFILE_NAME>
```

### Check Zabbix Logs

View Zabbix server logs for external script errors:

```bash
sudo tail -f /var/log/zabbix/zabbix_server.log | grep traffic_manager
```

## Security Considerations

- **No Credentials Required**: Uses Azure Managed Identity for authentication
- **Least Privilege**: Only Reader and Monitoring Reader roles are assigned
- **Scope Limited**: Permissions are scoped to specific Traffic Manager profile resources
- **Secure by Default**: No secrets or keys stored in configuration files

## Integration with Zabbix

The complete integration workflow:

1. **Script Deployment**: Monitor script placed in Zabbix external scripts directory
2. **Template Import**: Zabbix template defining items, triggers, and macros
3. **Host Creation**: Individual hosts created for each Traffic Manager profile
4. **Macro Configuration**: Azure credentials configured per host
5. **Data Collection**: Zabbix executes script at defined intervals
6. **Metric Extraction**: Dependent items parse JSON output
7. **Alerting**: Triggers fire based on configured thresholds
8. **Visualization**: Graphs and dashboards display metrics

## Advanced Configuration

### Monitoring Endpoint-Specific Metrics

The script returns detailed endpoint information. To create endpoint-specific monitoring:

1. **Identify endpoints** in the JSON output under `$.data.endpoints[]`
2. **Create dependent items** for each endpoint you want to monitor
3. **Use JSON path** to extract specific endpoint data:
   - `$.data.endpoints[?(@.name=='endpoint1')].endpointMonitorStatus`
   - `$.data.endpoints[?(@.name=='endpoint2')].endpointStatus`

### Creating a Dashboard

Build a comprehensive Traffic Manager dashboard:

1. Navigate to **Monitoring** → **Dashboards**
2. Create a new dashboard
3. Add widgets for:
   - **Health Status**: Shows current profile health
   - **Endpoint States**: Graph showing all endpoint states
   - **QPS Metric**: Graph showing queries per second
   - **Problems**: Shows active triggers
   - **Profile Configuration**: Data widget showing key configuration values

### Integration with Other Monitoring Systems

The script's JSON output can be consumed by other monitoring systems:

- **Prometheus**: Create a Prometheus exporter that calls the script and parses JSON
- **Grafana**: Import data from Zabbix or create direct queries
- **Azure Monitor**: Complement built-in Azure monitoring with custom metrics
- **PagerDuty/Opsgenie**: Configure Zabbix to send alerts to incident management platforms

## Comparison: Traffic Manager vs ExpressRoute Monitoring

| Feature | Traffic Manager | ExpressRoute |
|---------|----------------|--------------|
| **Resource Type** | DNS-based load balancer | Dedicated network connection |
| **Metrics** | QPS, endpoint states | Throughput, ARP/BGP availability |
| **Endpoints** | Multiple (web apps, VMs, external) | Peerings (Private, Microsoft, Public) |
| **Health Model** | Profile + endpoint status | Circuit + peering status |
| **Routing** | Traffic routing methods | BGP routing |
| **Scope** | Global (multi-region) | Regional (specific locations) |

## Additional Resources

- [Azure Managed Identity Documentation](https://docs.microsoft.com/azure/active-directory/managed-identities-azure-resources/)
- [Azure Traffic Manager Monitoring](https://docs.microsoft.com/azure/traffic-manager/traffic-manager-monitoring)
- [Azure Traffic Manager Metrics](https://docs.microsoft.com/azure/traffic-manager/traffic-manager-metrics-alerts)
- [Zabbix External Checks](https://www.zabbix.com/documentation/current/manual/config/items/itemtypes/external)
- [Zabbix Template Documentation](https://www.zabbix.com/documentation/current/manual/config/templates)
- [Zabbix JSON Preprocessing](https://www.zabbix.com/documentation/current/manual/config/items/preprocessing/jsonpath_functionality)

## Best Practices

### Monitoring Strategy

1. **Profile-Level Monitoring**: Start with profile health status
2. **Endpoint Monitoring**: Add endpoint-specific items for critical endpoints
3. **Metrics Monitoring**: Track QPS for capacity planning
4. **Alert Tuning**: Adjust trigger thresholds based on your traffic patterns

### Performance Optimization

1. **Update Interval**: Use 1-2 minute intervals for production, longer for dev/test
2. **History Retention**: Configure appropriate history and trend retention periods
3. **Dependent Items**: Use dependent items to minimize API calls
4. **Batch Monitoring**: Monitor multiple profiles with separate hosts

### Maintenance

1. **Regular Testing**: Periodically test the monitoring script manually
2. **Role Verification**: Verify role assignments haven't been removed
3. **Script Updates**: Keep the monitoring script updated
4. **Template Review**: Review and update templates as Azure APIs evolve

## Support

For issues or questions:
- Check Azure role assignments are correct
- Verify Managed Identity is enabled on the VM
- Review Zabbix server logs for errors
- Ensure network connectivity to Azure management endpoints
- Verify external scripts are enabled in Zabbix configuration
- Test the script manually with sudo -u zabbix to isolate issues

## License

This monitoring solution is provided as-is for use with Azure Traffic Manager and Zabbix monitoring systems.
