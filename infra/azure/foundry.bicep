// Microsoft Foundry for PARALLEL: an AI Services account with project management, one project, one
// model deployment, and data-plane access for the API's managed identity. Keyless (local auth off).

param location string
param accountName string
param projectName string = 'parallel'
param modelName string = 'gpt-4.1-mini'
param modelVersion string = '2025-04-14'
@description('Deployment capacity in thousands of tokens per minute.')
param capacity int = 50
param principalId string
@description('Azure AI User')
param roleDefinitionId string = '53ca6127-db72-4b80-b1b0-d745d6d5456d'

resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: accountName
  location: location
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: accountName
    allowProjectManagement: true
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: account
  name: projectName
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    displayName: 'PARALLEL'
    description: 'Agents for multi-agent counterfactual football intelligence'
  }
}

// Operations on one account must not overlap: create the model deployment after the project.
resource model 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: account
  name: modelName
  dependsOn: [ project ]
  sku: { name: 'GlobalStandard', capacity: capacity }
  properties: {
    model: { format: 'OpenAI', name: modelName, version: modelVersion }
  }
}

resource access 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(account.id, principalId, roleDefinitionId)
  scope: account
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleDefinitionId)
  }
}

output projectEndpoint string = 'https://${accountName}.services.ai.azure.com/api/projects/${project.name}'
output openaiEndpoint string = 'https://${accountName}.openai.azure.com/'
output deploymentName string = model.name
output accountId string = account.id
