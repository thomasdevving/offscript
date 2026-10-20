// PARALLEL - Azure infrastructure
//
//  * Log Analytics + workspace-based Application Insights (telemetry, OpenTelemetry traces)
//  * Azure Container Registry (API image)
//  * User-assigned managed identity (pulls images; authenticates to Microsoft Foundry - no keys)
//  * Azure Container Apps environment + API container app (HTTPS + WebSockets, scale 1..2)
//  * Azure Static Web App (Free) for the static Next.js export
//  * Optional: "Azure AI User" role for the identity on an existing Foundry resource
//
// Deploy:  az deployment group create -g <rg> -f infra/azure/main.bicep -p foundryProjectEndpoint=... foundryModel=...
// (or `azd up` using azure.yaml at the repository root)

targetScope = 'resourceGroup'

@description('Short prefix for resource names (lowercase letters/digits).')
@maxLength(12)
param namePrefix string = 'parallel'

param location string = resourceGroup().location

@description('Region for the Static Web App (limited availability).')
param staticWebAppLocation string = 'westeurope'

@description('Container image for the API. The first deployment can use a public placeholder image until CI pushes the real one.')
param apiImage string = 'mcr.microsoft.com/k8se/quickstart:latest'

@description('Microsoft Foundry project endpoint (https://<resource>.services.ai.azure.com/api/projects/<project>). Leave empty to run agents in deterministic policy mode.')
param foundryProjectEndpoint string = ''

@description('Model deployment name in the Foundry project (e.g. gpt-4.1-mini).')
param foundryModel string = ''

@description('Resource ID of the Foundry (AI Services) account to grant the API identity access to. Optional.')
param foundryAccountResourceId string = ''

@description('Role definition granted on the Foundry account (default: Azure AI User).')
param foundryRoleDefinitionId string = '53ca6127-db72-4b80-b1b0-d745d6d5456d'

@description('Keep one replica warm so judges never hit a cold start (costs ~1 vCPU-0.5 always on).')
param minReplicas int = 1

var suffix = uniqueString(resourceGroup().id)
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${namePrefix}-logs-${suffix}'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${namePrefix}-ai-${suffix}'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
  }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: toLower('${namePrefix}acr${suffix}')
  location: location
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-api-id'
  location: location
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, identity.id, acrPullRoleId)
  scope: acr
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
  }
}

module foundryAccess 'foundry-role.bicep' = if (!empty(foundryAccountResourceId)) {
  name: 'foundry-role'
  scope: resourceGroup(split(foundryAccountResourceId, '/')[2], split(foundryAccountResourceId, '/')[4])
  params: {
    accountName: last(split(foundryAccountResourceId, '/'))
    principalId: identity.properties.principalId
    roleDefinitionId: foundryRoleDefinitionId
  }
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${namePrefix}-env-${suffix}'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource swa 'Microsoft.Web/staticSites@2023-12-01' = {
  name: '${namePrefix}-web-${suffix}'
  location: staticWebAppLocation
  tags: { 'azd-service-name': 'web' }
  sku: { name: 'Free', tier: 'Free' }
  properties: {}
}

resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namePrefix}-api'
  location: location
  tags: { 'azd-service-name': 'api' }
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  dependsOn: [ acrPull ]
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
        corsPolicy: {
          allowedOrigins: [ 'https://${swa.properties.defaultHostname}' ]
          allowedMethods: [ 'GET', 'POST' ]
          allowedHeaders: [ '*' ]
        }
      }
      registries: [
        { server: acr.properties.loginServer, identity: identity.id }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: apiImage
          resources: { cpu: json('1.0'), memory: '2Gi' }
          env: [
            { name: 'ENVIRONMENT', value: 'azure' }
            { name: 'AGENT_MODE', value: empty(foundryProjectEndpoint) ? 'policy' : 'auto' }
            { name: 'FOUNDRY_PROJECT_ENDPOINT', value: foundryProjectEndpoint }
            { name: 'FOUNDRY_MODEL', value: foundryModel }
            { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
            { name: 'CORS_ORIGINS', value: 'https://${swa.properties.defaultHostname}' }
            { name: 'MAX_CONCURRENT_ANALYSES', value: '2' }
          ]
          probes: [
            { type: 'Liveness', httpGet: { path: '/api/health', port: 8000 }, initialDelaySeconds: 20, periodSeconds: 30 }
            { type: 'Readiness', httpGet: { path: '/api/health', port: 8000 }, initialDelaySeconds: 10, periodSeconds: 10 }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: 2
        rules: [ { name: 'http', http: { metadata: { concurrentRequests: '40' } } } ]
      }
    }
  }
}

output apiUrl string = 'https://${api.properties.configuration.ingress.fqdn}'
output webUrl string = 'https://${swa.properties.defaultHostname}'
output acrName string = acr.name
output containerAppName string = api.name
output staticWebAppName string = swa.name
output identityClientId string = identity.properties.clientId

// Names azd expects / reuses as environment variables for the web build.
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = acr.properties.loginServer
output NEXT_PUBLIC_API_BASE_URL string = 'https://${api.properties.configuration.ingress.fqdn}'
