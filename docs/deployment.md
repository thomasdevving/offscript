# Deployment

> **Status (honest):** the Azure templates compile (`bicep build`, Bicep CLI 0.48.1) and the CI/CD
> workflows are in the repository, but **no Azure resources were created from the build
> environment** (no Azure credentials there). Follow the steps below to deploy; nothing in the
> docs claims a live URL until you add one.

## 1. Run locally (no Azure needed)

Prerequisites: Python 3.12+ and Node.js 22+ (24 recommended).

```bash
# backend
cd apps/api
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --port 8000
```

```bash
# frontend (new terminal, repository root)
npm ci
npm run dev:web                 # http://localhost:3000  (API at http://localhost:8000)
```

Without Foundry settings the agents run on the labelled deterministic policy planner. To use a
live model locally, create `.env` in the repository root (see `.env.example`):

```bash
FOUNDRY_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
FOUNDRY_MODEL=<deployment-name>
```

then `az login` and restart the API. Check with `curl -X POST localhost:8000/api/diagnostics/foundry`.

Docker alternative: `docker compose up --build` (web on :3000, API on :8000).

## 2. Microsoft Foundry

1. In the [Foundry portal](https://ai.azure.com) create (or reuse) a project and deploy a chat model
   that supports tool calling and structured outputs (e.g. a GPT-4.1-mini/GPT-4o-mini class model;
   cost-efficient models are enough - prompts are small and bounded).
2. Copy the **project endpoint** and the **deployment name**.
3. Grant the identity that runs the API the **Azure AI User** role on the Foundry resource (the
   Bicep template does this for the API's managed identity when `foundryAccountResourceId` is set).

## 3. Azure (Container Apps + Static Web Apps)

### Option A - Azure Developer CLI

```bash
azd auth login
azd env new parallel
azd env set FOUNDRY_PROJECT_ENDPOINT "<endpoint>"      # optional
azd env set FOUNDRY_MODEL "<deployment>"               # optional
azd up
```

`azure.yaml` maps service `api` (container app built from `infra/docker/api.Dockerfile`) and service
`web` (static export in `apps/web/out`). The template outputs `NEXT_PUBLIC_API_BASE_URL`, which the
web build needs; if your azd version does not pass it to the build, run
`NEXT_PUBLIC_API_BASE_URL=<apiUrl> npm run build -w apps/web` and `azd deploy web`.

### Option B - Azure CLI

```bash
RG=parallel-rg; LOC=westeurope
az group create -n $RG -l $LOC
az deployment group create -g $RG -f infra/azure/main.bicep \
  -p foundryProjectEndpoint="<endpoint>" foundryModel="<deployment>" \
     foundryAccountResourceId="/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<name>"
# outputs: apiUrl, webUrl, acrName, containerAppName, staticWebAppName

ACR=$(az deployment group show -g $RG -n main --query properties.outputs.acrName.value -o tsv)
az acr build -r $ACR -t parallel-api:v1 -f infra/docker/api.Dockerfile .
az containerapp update -g $RG -n parallel-api --image $ACR.azurecr.io/parallel-api:v1

API=$(az deployment group show -g $RG -n main --query properties.outputs.apiUrl.value -o tsv)
NEXT_PUBLIC_API_BASE_URL=$API npm run build -w apps/web
SWA=$(az deployment group show -g $RG -n main --query properties.outputs.staticWebAppName.value -o tsv)
TOKEN=$(az staticwebapp secrets list -n $SWA -g $RG --query properties.apiKey -o tsv)
npx @azure/static-web-apps-cli deploy apps/web/out --deployment-token $TOKEN --env production
```

What the template creates:

| Resource | Purpose | Cost driver |
|---|---|---|
| Container Apps environment + `parallel-api` (1 vCPU / 2 GiB, 1-2 replicas, HTTPS + WebSockets) | API, simulations, agents | `minReplicas=1` keeps the demo warm (~1 vCPU always on). Set `minReplicas=0` to scale to zero. |
| Azure Container Registry (Basic) | API image | small fixed |
| User-assigned managed identity | ACR pull; Foundry access without keys | free |
| Log Analytics + Application Insights | logs, OpenTelemetry traces, metrics | ingestion volume (30-day retention) |
| Static Web App (Free) | static frontend | free tier |
| Role assignment on Foundry account (optional) | Azure AI User | free |

Model cost: one analysis makes at most 6 agent calls (plus bounded retries); each agent has a tool
budget, a timeout and small prompts. Analyses are cached by snapshot + configuration + model
deployment, so replays cost nothing.

### GitHub Actions

* `ci.yml` (push/PR): ruff + pytest, OpenAPI/TypeScript contract drift check, typecheck, Vitest,
  Next build, Playwright end-to-end against the real stack.
* `deploy.yml` (manual): OIDC login, `az acr build`, `az containerapp update`, smoke test, static
  build with the API URL and Static Web Apps upload. Configure secrets `AZURE_CLIENT_ID`,
  `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_STATIC_WEB_APPS_API_TOKEN` and variables
  `ACR_NAME`, `CONTAINER_APP_NAME`, `RESOURCE_GROUP`.

## 4. Judge access checklist

* [ ] `GET <apiUrl>/api/health` returns `"status": "ok"` and the expected `agent_mode`.
* [ ] `POST <apiUrl>/api/diagnostics/foundry` returns `"live": true` (if Foundry is configured).
* [ ] `<webUrl>` loads, shows "Live", and the 73' scenario plays and analyses.
* [ ] CORS: `CORS_ORIGINS` contains the Static Web App URL (set by the template).
* [ ] Optional: run `python scripts/precompute_demo.py` against the deployed settings to warm the cache.
