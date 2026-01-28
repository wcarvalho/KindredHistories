# Kindred Histories - Serverless Deployment Guide

Complete guide to deploying Kindred Histories as a serverless application using Firebase Hosting (frontend) and Cloud Run (backend).

## 📋 Prerequisites

- [ ] Google Cloud Platform account
- [ ] Firebase project created (`kindred-histories`)
- [ ] gcloud CLI installed and authenticated
- [ ] Firebase CLI installed (`npm install -g firebase-tools`)
- [ ] Docker installed (for local testing)
- [ ] All required API keys:
  - Gemini API key
  - Google Custom Search API key
  - Google Custom Search Engine ID

---

## 🚀 Deployment Overview

**Architecture:**
- **Frontend**: Firebase Hosting (React/Vite static site)
- **Backend**: Cloud Run (Python/FastAPI in Docker container)
- **Database**: Firestore (already configured)

**Cost**: $5-50/month depending on traffic (scales to zero when idle)

---

## Part 1: Backend Deployment to Cloud Run

### Step 1: Enable Required APIs

```bash
# Set your project
gcloud config set project kindred-histories

# Enable required APIs
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable containerregistry.googleapis.com
gcloud services enable artifactregistry.googleapis.com
```

### Step 2: Create Secret Manager Secrets (Recommended)

Store sensitive environment variables securely:

```bash
# Create secrets for API keys
echo -n "YOUR_GEMINI_API_KEY" | gcloud secrets create gemini-api-key --data-file=-
echo -n "YOUR_GOOGLE_CSE_API_KEY" | gcloud secrets create google-cse-api-key --data-file=-
echo -n "YOUR_GOOGLE_CSE_ID" | gcloud secrets create google-cse-id --data-file=-

# Verify secrets were created
gcloud secrets list
```

### Step 3: Build and Deploy to Cloud Run

**Option A: Direct deployment (recommended for first deployment)**

```bash
# From repository root
gcloud run deploy kindred-histories-backend \
  --source . \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 4Gi \
  --cpu 2 \
  --timeout 600 \
  --concurrency 4 \
  --min-instances 0 \
  --max-instances 10 \
  --cpu-throttling \
  --execution-environment gen2 \
  --set-secrets "GEMINI_API_KEY=gemini-api-key:latest,GOOGLE_CSE_API_KEY=google-cse-api-key:latest,GOOGLE_CSE_ID=google-cse-id:latest" \
  --set-env-vars "MODEL_NAME=gemini-2.5-flash"
```

**Option B: Manual Docker build and push**

```bash
# Build the Docker image
docker build -t gcr.io/kindred-histories/kindred-histories-backend:latest .

# Test locally (optional)
docker run -p 8080:8080 \
  -e GEMINI_API_KEY="your_key" \
  -e GOOGLE_CSE_API_KEY="your_key" \
  -e GOOGLE_CSE_ID="your_id" \
  -e MODEL_NAME="gemini-2.5-flash" \
  gcr.io/kindred-histories/kindred-histories-backend:latest

# Push to Google Container Registry
docker push gcr.io/kindred-histories/kindred-histories-backend:latest

# Deploy to Cloud Run
gcloud run deploy kindred-histories-backend \
  --image gcr.io/kindred-histories/kindred-histories-backend:latest \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 4Gi \
  --cpu 2 \
  --timeout 600 \
  --concurrency 4 \
  --min-instances 0 \
  --max-instances 10 \
  --set-secrets "GEMINI_API_KEY=gemini-api-key:latest,GOOGLE_CSE_API_KEY=google-cse-api-key:latest,GOOGLE_CSE_ID=google-cse-id:latest" \
  --set-env-vars "MODEL_NAME=gemini-2.5-flash"
```

### Step 4: Get Backend URL

```bash
# Get the deployed service URL
gcloud run services describe kindred-histories-backend \
  --region us-central1 \
  --format 'value(status.url)'

# Save this URL - you'll need it for frontend configuration
# Example: https://kindred-histories-backend-abc123-uc.a.run.app
```

### Step 5: Update CORS Allowed Origins

```bash
# Get your Firebase hosting domain
# It will be: https://kindred-histories.web.app

# Update Cloud Run service with allowed origins
gcloud run services update kindred-histories-backend \
  --region us-central1 \
  --set-env-vars "ALLOWED_ORIGINS=https://kindred-histories.web.app,https://kindred-histories.firebaseapp.com"
```

### Step 6: Grant Firestore Permissions

```bash
# Get the Cloud Run service account email
SERVICE_ACCOUNT=$(gcloud run services describe kindred-histories-backend \
  --region us-central1 \
  --format 'value(spec.template.spec.serviceAccountName)')

# Grant Firestore access
gcloud projects add-iam-policy-binding kindred-histories \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/datastore.user"

# Grant Secret Manager access (if using secrets)
gcloud projects add-iam-policy-binding kindred-histories \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor"
```

### Step 7: Test Backend

```bash
# Test health check
curl https://kindred-histories-backend-XXXXXXXXXX-uc.a.run.app/health

# Should return: {"status":"healthy","service":"kindred-histories-backend","timestamp":...}
```

---

## Part 2: Frontend Deployment to Firebase Hosting

### Step 1: Update Frontend Environment Configuration

**Important**: The frontend currently has hardcoded API URLs. You need to update them.

**Option A: Quick fix - Find and replace** (temporary solution)

```bash
cd frontend/src

# Find all hardcoded localhost URLs
grep -r "localhost:8000" .

# Replace with your Cloud Run URL (do this manually or with sed)
# Replace: http://localhost:8000
# With: https://kindred-histories-backend-XXXXXXXXXX-uc.a.run.app
```

**Option B: Use environment variables** (recommended for production)

1. Update `frontend/.env.production` with your Cloud Run URL:
```bash
VITE_API_URL=https://kindred-histories-backend-XXXXXXXXXX-uc.a.run.app
```

2. Create `frontend/src/config.js`:
```javascript
export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
```

3. Update all fetch calls to use `API_URL`:
```javascript
// Before
await fetch('http://localhost:8000/api/analyze', {...})

// After
import { API_URL } from './config';
await fetch(`${API_URL}/api/analyze`, {...})
```

### Step 2: Build Frontend

```bash
cd frontend

# Install dependencies
npm install

# Build for production
npm run build

# Verify build output
ls -lh dist/
```

### Step 3: Deploy to Firebase Hosting

```bash
# Return to repository root
cd ..

# Login to Firebase (if not already logged in)
firebase login

# Deploy hosting only
firebase deploy --only hosting

# Your app will be live at:
# https://kindred-histories.web.app
# https://kindred-histories.firebaseapp.com
```

### Step 4: Deploy Firestore Rules (if not already deployed)

```bash
# Deploy Firestore rules and indexes
firebase deploy --only firestore:rules,firestore:indexes
```

---

## Part 3: Set Up CI/CD (Optional)

### Enable Automatic Deployment on Git Push

```bash
# Connect your repository to Cloud Build
gcloud builds submit --config=cloudbuild.yaml

# Set up build trigger
gcloud builds triggers create github \
  --repo-name=story-generator-2 \
  --repo-owner=YOUR_GITHUB_USERNAME \
  --branch-pattern="^main$" \
  --build-config=cloudbuild.yaml
```

Now every push to `main` branch will automatically deploy to Cloud Run!

---

## 🔧 Post-Deployment Configuration

### 1. Update Firestore Security Rules

Verify that your service account has admin privileges:

In `firestore.rules`, you may need to add your service account as an admin:

```javascript
function isAdmin() {
  return isAuthenticated() &&
         (request.auth.token.admin == true ||
          request.auth.uid == 'SERVICE_ACCOUNT_ID');
}
```

### 2. Set Up Monitoring

```bash
# View logs
gcloud run services logs read kindred-histories-backend \
  --region us-central1 \
  --limit 50

# Set up alerts in Google Cloud Console
# Navigate to: Cloud Run > kindred-histories-backend > Metrics
```

### 3. Configure Custom Domain (Optional)

```bash
# Map custom domain to Firebase Hosting
firebase hosting:sites:create kindred-histories
firebase target:apply hosting kindred-histories kindred-histories

# Follow instructions in Firebase Console to add custom domain
```

---

## 📊 Cost Optimization

### Reduce Cloud Run Costs

```bash
# Scale to zero when idle (already configured)
gcloud run services update kindred-histories-backend \
  --region us-central1 \
  --min-instances 0

# Reduce memory if workload allows (test first)
gcloud run services update kindred-histories-backend \
  --region us-central1 \
  --memory 2Gi

# Set request timeout to avoid hanging requests
gcloud run services update kindred-histories-backend \
  --region us-central1 \
  --timeout 300
```

---

## 🧪 Testing Deployment

### Test Backend

```bash
# Health check
curl https://kindred-histories-backend-XXXXXXXXXX-uc.a.run.app/health

# Test facet extraction (replace URL)
curl -X POST https://YOUR-BACKEND-URL/api/extract-facets \
  -H "Content-Type: application/json" \
  -d '{"text":"I am a Mexican neuroscientist who loves helping others"}'
```

### Test Frontend

1. Visit https://kindred-histories.web.app
2. Enter a description and click "Discover"
3. Verify:
   - Facets are extracted
   - Backend calls succeed (check Network tab)
   - Historical figures are displayed

---

## 🐛 Troubleshooting

### Backend Issues

**Error: "Permission denied"**
```bash
# Grant Firestore permissions again
gcloud projects add-iam-policy-binding kindred-histories \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/datastore.user"
```

**Error: "Secrets not found"**
```bash
# Verify secrets exist
gcloud secrets list

# Grant secret access
gcloud secrets add-iam-policy-binding gemini-api-key \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor"
```

**Error: "CORS blocked"**
```bash
# Update allowed origins
gcloud run services update kindred-histories-backend \
  --region us-central1 \
  --update-env-vars "ALLOWED_ORIGINS=https://kindred-histories.web.app"
```

### Frontend Issues

**Error: "Failed to fetch"**
- Check that backend URL is correct in frontend code
- Verify CORS is configured properly
- Check Cloud Run service is running: `gcloud run services list`

**Build fails**
```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
npm run build
```

---

## 🔄 Updating the Application

### Update Backend

```bash
# Make code changes, then redeploy
gcloud run deploy kindred-histories-backend \
  --source . \
  --region us-central1
```

### Update Frontend

```bash
cd frontend
npm run build
cd ..
firebase deploy --only hosting
```

---

## 📝 Deployment Checklist

- [ ] Backend deployed to Cloud Run
- [ ] Backend service URL obtained
- [ ] Secrets configured in Secret Manager
- [ ] Firestore permissions granted
- [ ] CORS origins updated
- [ ] Frontend environment variables updated
- [ ] Frontend built successfully
- [ ] Frontend deployed to Firebase Hosting
- [ ] Firestore rules deployed
- [ ] Health check endpoint tested
- [ ] End-to-end user flow tested
- [ ] Monitoring and logging configured

---

## 🎉 Your App is Live!

- **Frontend**: https://kindred-histories.web.app
- **Backend**: https://kindred-histories-backend-XXXXXXXXXX-uc.a.run.app
- **Firestore Console**: https://console.firebase.google.com/project/kindred-histories/firestore

---

## 📚 Additional Resources

- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Firebase Hosting Guide](https://firebase.google.com/docs/hosting)
- [Secret Manager Best Practices](https://cloud.google.com/secret-manager/docs/best-practices)
- [Firestore Security Rules](https://firebase.google.com/docs/firestore/security/get-started)

---

## 🆘 Need Help?

- Check Cloud Run logs: `gcloud run services logs read kindred-histories-backend --region us-central1`
- Check Firebase logs: Firebase Console > Hosting
- Review Firestore security rules in Firebase Console
