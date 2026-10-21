#!/usr/bin/env bash
# Deploys OFFSCRIPT to Azure in one go: infrastructure (Bicep) with the API on Container Apps, and the
# static web app on a Storage static website. The API image is built by GitHub Actions
# (.github/workflows/image.yml) and pulled from GitHub Container Registry: no Docker or Azure
# registry needed.
#
# Prerequisites: Azure CLI signed in (`az login`) with the target subscription selected, Node.js 22+.
# Works locally (Git Bash / Linux / macOS) and in Azure Cloud Shell.
#
#   scripts/deploy_azure.sh
#
# Settings (environment variables):
#   RESOURCE_GROUP  (parallel-rg)          LOCATION      (germanywestcentral)
#   CREATE_FOUNDRY  (true)  new Foundry project + gpt-4.1-mini for the agents; false = policy planner
#   MIN_REPLICAS    (0)     0 = scale to zero when idle (cold start), 1 = always on (always billed)
#   API_IMAGE       (ghcr.io/thomasdevving/parallel-api:<this commit>, else :latest)
#   ONLY_WEB        (false) true = only rebuild and re-upload the web app (infrastructure must exist)
#   AZ              (az)    path to the Azure CLI
set -euo pipefail

AZ="${AZ:-az}"
RG="${RESOURCE_GROUP:-parallel-rg}"
LOCATION="${LOCATION:-germanywestcentral}"
CREATE_FOUNDRY="${CREATE_FOUNDRY:-true}"
MIN_REPLICAS="${MIN_REPLICAS:-0}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Prefer the immutable per-commit tag published by the image workflow (a moving :latest can be served
# from a node cache); fall back to :latest when this commit did not change the API.
image_exists() {
  local token
  token="$(curl -fsS "https://ghcr.io/token?scope=repository:$1:pull" | sed -E 's/.*"token":"([^"]+)".*/\1/')" || return 1
  curl -fsS -o /dev/null -H "Authorization: Bearer $token" \
    -H "Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.v2+json" \
    "https://ghcr.io/v2/$1/manifests/$2"
}
if [ -z "${API_IMAGE:-}" ]; then
  sha="$(git rev-parse HEAD 2>/dev/null || true)"
  if [ -n "$sha" ] && image_exists thomasdevving/parallel-api "$sha"; then
    API_IMAGE="ghcr.io/thomasdevving/parallel-api:$sha"
  else
    API_IMAGE="ghcr.io/thomasdevving/parallel-api:latest"
  fi
fi

az_() { "$AZ" "$@" | tr -d '\r'; }
output() { az_ deployment group show -g "$RG" -n parallel --query "properties.outputs.$1.value" -o tsv; }
provision() {
  az_ deployment group create -g "$RG" -n parallel -f infra/azure/main.bicep -o none \
    -p location="$LOCATION" createFoundry="$CREATE_FOUNDRY" minReplicas="$MIN_REPLICAS" \
       apiImage="$API_IMAGE" revision="r$(date +%m%d%H%M%S)"
}

if [ "${ONLY_WEB:-false}" != true ]; then
  echo "[1/4] Resource group $RG in $LOCATION"
  az_ group create -n "$RG" -l "$LOCATION" -o none
  echo "[2/4] Infrastructure + API ($API_IMAGE)$([ "$CREATE_FOUNDRY" = true ] && echo " + Microsoft Foundry")"
  provision
fi
API="$(output apiUrl)"
WEB="$(output webUrl)"
SA="$(output webStorageAccount)"

echo "[3/4] Web app (API: $API)"
[ -d node_modules ] || npm ci --no-audit --no-fund
NEXT_PUBLIC_API_BASE_URL="$API" npm run build -w apps/web
az_ storage blob service-properties update --account-name "$SA" --auth-mode key -o none \
  --static-website --index-document index.html --404-document 404.html
# Pages revalidate on every visit; content-hashed assets are cached for a year.
az_ storage blob upload-batch --account-name "$SA" --auth-mode key -d '$web' -s apps/web/out --overwrite -o none \
  --content-cache-control "no-cache"
az_ storage blob upload-batch --account-name "$SA" --auth-mode key -d '$web' -s apps/web/out --overwrite -o none \
  --pattern "_next/static/*" --content-cache-control "public, max-age=31536000, immutable"

echo "[4/4] Smoke test (the first request wakes a scaled-to-zero API)"
curl --fail --silent --show-error --retry 12 --retry-delay 5 --retry-all-errors --max-time 120 "$API/api/health"
echo
echo "Web: $WEB"
echo "API: $API"
echo "Foundry: $(output foundryProjectEndpoint) ($(output foundryModel))"
