#!/bin/bash
# Fast deployment script for Kindred Histories
# Uses local Docker build + Artifact Registry for speed

set -e

PROJECT_ID="braindump-1766604046"
REGION="us-central1"
SERVICE_NAME="kindred-histories-backend"
REPO="cloud-run-source-deploy"
IMAGE="us-central1-docker.pkg.dev/${PROJECT_ID}/${REPO}/${SERVICE_NAME}"

# Parse arguments
DEPLOY_BACKEND=false
DEPLOY_FRONTEND=false

if [ "$1" == "backend" ]; then
    DEPLOY_BACKEND=true
elif [ "$1" == "frontend" ]; then
    DEPLOY_FRONTEND=true
elif [ "$1" == "all" ] || [ -z "$1" ]; then
    DEPLOY_BACKEND=true
    DEPLOY_FRONTEND=true
else
    echo "Usage: $0 [backend|frontend|all]"
    exit 1
fi

# Ensure we're in the project root
cd "$(dirname "$0")/.."

if [ "$DEPLOY_BACKEND" = true ]; then
    echo "=== Deploying Backend ==="

    # Check if Docker is running
    if docker info >/dev/null 2>&1; then
        echo "Docker is running - using fast local build..."

        # Configure Docker for Artifact Registry
        gcloud auth configure-docker us-central1-docker.pkg.dev --quiet 2>/dev/null || true

        # Build image locally for amd64 (Cloud Run requires linux/amd64)
        echo "Building Docker image locally..."
        docker build --platform linux/amd64 -t "${IMAGE}:latest" .

        # Push to Artifact Registry (only changed layers)
        echo "Pushing to Artifact Registry..."
        docker push "${IMAGE}:latest"

        # Deploy from pre-built image (fast - no build step)
        echo "Deploying to Cloud Run..."
        gcloud run deploy "${SERVICE_NAME}" \
            --image "${IMAGE}:latest" \
            --region "${REGION}" \
            --allow-unauthenticated \
            --memory 4Gi --cpu 2 --timeout 600 \
            --set-secrets 'GEMINI_API_KEY=gemini-api-key:latest,GOOGLE_CSE_API_KEY=google-cse-api-key:latest,GOOGLE_CSE_ID=google-cse-id:latest'
    else
        echo "Docker not running - using Cloud Build with caching..."

        # Use gcloud builds submit with cloudbuild.yaml (has caching configured)
        gcloud builds submit --config=cloudbuild.yaml --timeout=1800 --substitutions=COMMIT_SHA=$(git rev-parse --short HEAD)
    fi

    echo "Backend deployed!"
    gcloud run services describe "${SERVICE_NAME}" --region "${REGION}" --format 'value(status.url)'
fi

if [ "$DEPLOY_FRONTEND" = true ]; then
    echo "=== Deploying Frontend ==="
    cd frontend
    npm run build
    cd ..
    firebase deploy --only hosting
    echo "Frontend deployed to https://kindred-histories.web.app"
fi

echo "=== Deployment Complete ==="
