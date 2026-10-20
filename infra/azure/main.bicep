// PARALLEL - Azure infrastructure
//
//  * Log Analytics + workspace-based Application Insights (telemetry, OpenTelemetry traces)
//  * API image from GitHub Container Registry (public, built by .github/workflows/image.yml); optionally
//    an Azure Container Registry instead (createRegistry=true, needs ACR Tasks or a local Docker push)
//  * User-assigned managed identity (pulls images; authenticates to Microsoft Foundry - no keys)
//  * Azure Container Apps environment + API container app (HTTPS + WebSockets, single replica by default)
//  * Storage account static website for the static Next.js export (always on, any region, cents per month)
//  * Optional: a new Microsoft Foundry account + project + model deployment (createFoundry=true), or
//    the "Azure AI User" role for the identity on an existing Foundry resource
//
// Deploy everything (infra, API image, web build): scripts/deploy_azure.sh - see docs/deployment.md.

targetScope = 'resourceGroup'

@description('Short prefix for resource names (lowercase letters/digits).')
@maxLength(12)
param namePrefix string = 'parallel'

param location string = resourceGroup().location

@description('Container image for the API (public image, or one in the registry created with createRegistry=true).')
param apiImage string = 'ghcr.io/thomasdevving/parallel-api:latest'

@description('Deployment marker; a new value rolls out a new revision (and re-pulls a moving tag such as :latest).')
param revision string = ''

@description('Create an Azure Container Registry for the API image (fixed monthly cost). Not needed for public images.')
param createRegistry bool = false

@description('Microsoft Foundry project endpoint (https://<resource>.services.ai.azure.com/api/projects/<project>). Leave empty to run agents in deterministic policy mode.')
param foundryProjectEndpoint string = ''

@description('Optional Azure OpenAI endpoint of the same Foundry account (https://<account>.openai.azure.com/); used instead of the project endpoint when set.')
param foundryOpenAiEndpoint string = ''

@description('Model deployment name in the Foundry project (e.g. gpt-4.1-mini).')
param foundryModel string = ''

@description('Create a Microsoft Foundry account, project and model deployment in this resource group and connect the API to it (keyless, managed identity).')
param createFoundry bool = false

@description('Region for the Foundry account (model availability differs per region).')
param foundryLocation string = location

@description('Model deployed when createFoundry is true.')
param foundryModelName string = 'gpt-4.1-mini'

@description('Resource ID of an existing Foundry (AI Services) account to grant the API identity access to. Optional.')
param foundryAccountResourceId string = ''

@description('Role definition granted on the Foundry account (default: Azure AI User).')
param foundryRoleDefinitionId string = '53ca6127-db72-4b80-b1b0-d745d6d5456d'

@description('0 = scale to zero when idle (free when idle; the first request after idle waits for a cold start). Set 1 to keep one replica warm (always billed).')
param minReplicas int = 0

@description('Analysis jobs and Football Multiverse sessions/jobs live in one API process (memory + local disk), so the default is a single replica. Raise only after moving them to a shared store.')
param maxReplicas int = 1

var suffix = uniqueString(resourceGroup().id)
// The first deployment runs a public placeholder (port 80) until the real API image (port 8000) exists.
var isPlaceholder = startsWith(apiImage, 'mcr.microsoft.com/k8se/quickstart')
var apiPort = isPlaceholder ? 80 : 8000
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

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = if (createRegistry) {
  name: toLower('${namePrefix}acr${suffix}')
  location: location
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-api-id'
  location: location
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (createRegistry) {
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

module foundry 'foundry.bicep' = if (createFoundry) {
  name: 'foundry'
  params: {
    location: foundryLocation
    accountName: toLower('${namePrefix}-foundry-${suffix}')
    modelName: foundryModelName
    principalId: identity.properties.principalId
  }
}

var effectiveFoundryEndpoint = createFoundry ? foundry!.outputs.projectEndpoint : foundryProjectEndpoint
var effectiveFoundryModel = createFoundry ? foundry!.outputs.deploymentName : foundryModel
// Container Apps in some regions cannot resolve *.services.ai.azure.com; the account's Azure OpenAI
// endpoint serves the same deployment with the same keyless auth (see docs/deployment.md).
var effectiveFoundryOpenAi = createFoundry ? foundry!.outputs.openaiEndpoint : foundryOpenAiEndpoint

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

// Static website hosting is enabled and filled by the deploy script (it is a data-plane setting).
resource web 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: take(toLower('${namePrefix}web${suffix}'), 24)
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
  }
}

var webOrigin = 'https://${replace(replace(web.properties.primaryEndpoints.web, 'https://', ''), '/', '')}'

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
        targetPort: apiPort
        transport: 'auto'
        allowInsecure: false
        corsPolicy: {
          allowedOrigins: [ webOrigin ]
          allowedMethods: [ 'GET', 'POST' ]
          allowedHeaders: [ '*' ]
        }
      }
      registries: createRegistry ? [
        { server: acr!.properties.loginServer, identity: identity.id }
      ] : []
    }
    template: {
      containers: [
        {
          name: 'api'
          image: apiImage
          resources: { cpu: json('1.0'), memory: '2Gi' }
          env: [
            { name: 'ENVIRONMENT', value: 'azure' }
            { name: 'AGENT_MODE', value: empty(effectiveFoundryEndpoint) ? 'policy' : 'auto' }
            { name: 'FOUNDRY_PROJECT_ENDPOINT', value: effectiveFoundryEndpoint }
            { name: 'FOUNDRY_MODEL', value: effectiveFoundryModel }
            { name: 'FOUNDRY_OPENAI_ENDPOINT', value: effectiveFoundryOpenAi }
            { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
            { name: 'CORS_ORIGINS', value: webOrigin }
            { name: 'MAX_CONCURRENT_ANALYSES', value: '2' }
            { name: 'DEPLOY_REVISION', value: revision }
          ]
          probes: isPlaceholder ? [] : [
            { type: 'Startup', httpGet: { path: '/api/health', port: 8000 }, initialDelaySeconds: 3, periodSeconds: 2, failureThreshold: 60 }
            { type: 'Liveness', httpGet: { path: '/api/health', port: 8000 }, periodSeconds: 30 }
            { type: 'Readiness', httpGet: { path: '/api/health', port: 8000 }, periodSeconds: 10 }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [ { name: 'http', http: { metadata: { concurrentRequests: '40' } } } ]
      }
    }
  }
}

output apiUrl string = 'https://${api.properties.configuration.ingress.fqdn}'
output webUrl string = webOrigin
output acrName string = createRegistry ? acr!.name : ''
output containerAppName string = api.name
output webStorageAccount string = web.name
output identityClientId string = identity.properties.clientId
output foundryProjectEndpoint string = effectiveFoundryEndpoint
output foundryModel string = effectiveFoundryModel

// Names azd expects / reuses as environment variables for the web build.
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = createRegistry ? acr!.properties.loginServer : ''
output NEXT_PUBLIC_API_BASE_URL string = 'https://${api.properties.configuration.ingress.fqdn}'
