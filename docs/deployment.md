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

Football Multiverse settings (environment variables, all optional): `MULTIVERSE_CELL_ROLLOUTS` (80),
`MULTIVERSE_MAX_CELL_ROLLOUTS` (200), `MULTIVERSE_MAX_ROUNDS` (3), `MULTIVERSE_MAX_DEPTH` (3),
`MULTIVERSE_MAX_CHILDREN` (6), `MULTIVERSE_MAX_NODES` (40), `MULTIVERSE_MAX_SESSIONS` (200),
`MULTIVERSE_TIMEOUT_S` (180). Sessions are written to `DATA_DIR/multiverse/`; in a container they
last as long as the replica's file system (use an Azure Files mount to keep them across restarts).

## 2. Azure in one command (infrastructure + API + web + Microsoft Foundry)

Prerequisites: Azure CLI signed in to the subscription you want to use (`az login`, then
`az account set --subscription "<name>"`), Node.js 22+. No Docker needed: GitHub Actions
(`.github/workflows/image.yml`) builds the API image on every push to `main` and publishes it to
GitHub Container Registry (`ghcr.io/thomasdevving/parallel-api`, public), which Container Apps pulls.

```bash
scripts/deploy_azure.sh
```

| Setting (environment variable) | Default | Meaning |
|---|---|---|
| `RESOURCE_GROUP` | `parallel-rg` | resource group to create or update |
| `LOCATION` | `germanywestcentral` | region for every resource (pick one your subscription policy allows) |
| `CREATE_FOUNDRY` | `true` | create a Microsoft Foundry account + project + `gpt-4.1-mini` deployment; `false` = labelled policy planner |
| `MIN_REPLICAS` | `0` | `0` scales the API to zero when idle (cold start), `1` keeps it warm (always billed) |
| `API_IMAGE` | `ghcr.io/thomasdevving/parallel-api:latest` | API container image |
| `ONLY_WEB` | `false` | `true` only rebuilds and re-uploads the web app |

The script is idempotent: after the image workflow has run, run it again to roll out a new revision
(a new `DEPLOY_REVISION` value re-pulls `:latest`) and re-upload the web app. It also works unchanged in **Azure Cloud Shell**
(shell.azure.com), which helps when an organisation blocks Azure CLI sign-in on personal devices.

What it does: create the resource group → deploy `infra/azure/main.bicep` with the API image and a
fresh revision suffix → build the static web app with the API URL baked in → enable the Storage
static website and upload `apps/web/out` → smoke-test `/api/health`.

Why GitHub Container Registry: some subscriptions (Azure for Students among them) do not allow ACR
Tasks, the cloud build service, and an Azure Container Registry is the only fixed monthly cost of
the stack. The template can still create one (`createRegistry=true`) for organisations that prefer it.

What the template creates:

| Resource | Purpose | Cost |
|---|---|---|
| Container Apps environment + `parallel-api` (1 vCPU / 2 GiB, 0-1 replicas, HTTPS + WebSockets) | API, simulations, agents | scale to zero by default: nothing while idle, then per second of use (monthly free grant covers light demo traffic) |
| (GitHub Container Registry) | API image, built by GitHub Actions | free for public images |
| Storage account static website | the static web app (always on, so the "warming up" screen shows instantly) | cents per month |
| Microsoft Foundry: AI Services account, project `parallel`, `gpt-4.1-mini` (GlobalStandard, 50K TPM) | live model for all agents | pay per token, roughly a cent per analysis |
| User-assigned managed identity + Azure AI User role | keyless Foundry access | free |
| Log Analytics + Application Insights | logs, OpenTelemetry traces, metrics | free up to 5 GB/month ingestion |

Keep `maxReplicas=1`: analysis jobs and Multiverse sessions/jobs live in one API process (memory +
`data/multiverse/*.json`). With scale to zero, a sleeping API loses Multiverse sessions; the static
site and analyses regenerate on demand.

**Cold start.** With `MIN_REPLICAS=0` the first request after idle wakes the container: Azure holds
the request while the API starts (image start + synthetic match generation, typically 20-40 s). The
web app shows a "Warming up the match engine" screen during that time and continues automatically.

**Microsoft Foundry without the script.** To use an existing Foundry project instead, deploy the
template with `createFoundry=false foundryProjectEndpoint=<endpoint> foundryModel=<deployment>
foundryAccountResourceId=<account resource id>`; the template grants the API's managed identity the
Azure AI User role on that account. Model cost: one analysis makes at most 6 agent calls (plus
bounded retries); analyses are cached by snapshot + configuration + model deployment, so replays
cost nothing.

`azd up` also works for the infrastructure and the API (`azure.yaml`, remote image build); the web
app is uploaded by the script.

### GitHub Actions

* `ci.yml` (push/PR): ruff + pytest, OpenAPI/TypeScript contract drift check, typecheck, Vitest,
  Next build, Playwright end-to-end against the real stack.
* `image.yml` (every push to `main`): builds the API image and publishes
  `ghcr.io/thomasdevving/parallel-api:<commit>` and `:latest`.
* `deploy.yml` (**automatic**, after CI passes on `main`; also runnable by hand): waits for that
  commit's image, rolls it out with `az containerapp update`, builds the web app against the
  deployed API, uploads it to the Storage static website and smoke-tests `/api/health`. A push to
  `main` is live a few minutes later; a red CI run deploys nothing.

How GitHub signs in to Azure (no secrets stored anywhere): a user-assigned managed identity
`offscript-github-deploy` in `parallel-rg` has a **federated credential** that trusts only GitHub
Actions tokens for `repo:thomasdevving/parallel:ref:refs/heads/main`, and the **Contributor** role
on `parallel-rg` only. The workflow's client/tenant/subscription IDs are identifiers, not secrets.
To set this up for another subscription:

```bash
az identity create -g <rg> -n offscript-github-deploy
az identity federated-credential create -g <rg> --identity-name offscript-github-deploy -n github-main   --issuer https://token.actions.githubusercontent.com --audiences api://AzureADTokenExchange   --subject repo:<owner>/<repo>:ref:refs/heads/main
az role assignment create --assignee-object-id <principalId> --assignee-principal-type ServicePrincipal   --role Contributor --scope <resource group id>
```

GitHub may present the subject with immutable owner/repository IDs instead
(`repo:<owner>@<ownerId>/<repo>@<repoId>:ref:refs/heads/main`; the exact value is in the error of a
failed `azure/login` step); add a second federated credential with that subject. Then put the
identity's client ID and your tenant/subscription IDs in `deploy.yml`. Infrastructure
changes (Bicep) are not applied automatically: run `scripts/deploy_azure.sh` for those.

## 3. Judge access checklist

* [ ] `GET <apiUrl>/api/health` returns `"status": "ok"` and the expected `agent_mode`.
* [ ] `POST <apiUrl>/api/diagnostics/foundry` returns `"live": true` (if Foundry is configured).
* [ ] `<webUrl>` loads, shows "Live", and the 73' scenario plays and analyses.
* [ ] CORS: `CORS_ORIGINS` contains the static website origin (set by the template).
* [ ] Optional: run `python scripts/precompute_demo.py` against the deployed settings to warm the cache.
