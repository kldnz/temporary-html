# Webpage Upload

A self-hosted web application for uploading HTML content and sharing it via temporary links. Upload HTML through a browser or `curl`, choose an expiration period, and get a shareable link.

## Features

- Upload HTML via web UI or curl/API
- Configurable link expiration: 1 day, 7 days, 30 days, or indefinitely
- Automatic cleanup of expired pages
- IP whitelist support via Traefik middleware
- Kubernetes-ready with Traefik ingress and cert-manager TLS
- PostgreSQL backend for persistent storage

## Project Structure

```
webpage-upload/
├── app/
│   ├── main.py              # FastAPI application
│   ├── models.py            # SQLAlchemy models
│   ├── database.py          # Database connection
│   ├── requirements.txt     # Python dependencies
│   └── templates/
│       └── index.html       # Web UI
├── Dockerfile
├── docker-compose.yaml      # Local development
└── k8s/
    ├── kustomization.yaml   # Kustomize config
    ├── namespace.yaml
    ├── postgres.yaml         # PostgreSQL deployment + PVC
    ├── configmap.yaml        # Application config
    ├── secret.yaml           # Database credentials (template)
    ├── deployment.yaml       # Application deployment
    ├── service.yaml
    ├── middleware.yaml        # Traefik IP whitelist
    ├── ingress.yaml           # Traefik ingress
    └── certificate.yaml       # cert-manager TLS certificate
```

## Local Development

### Prerequisites

- Docker and Docker Compose

### Quick Start

```bash
docker-compose up --build
```

The app will be available at [http://localhost:8000](http://localhost:8000).

### Running Without Docker

Prerequisites: Python 3.12+, PostgreSQL

```bash
# Start PostgreSQL (example with Docker)
docker run -d --name postgres \
  -e POSTGRES_USER=webapp \
  -e POSTGRES_PASSWORD=localdev \
  -e POSTGRES_DB=webpage_upload \
  -p 5432:5432 \
  postgres:16-alpine

# Install dependencies
cd app
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL="postgresql://webapp:localdev@localhost:5432/webpage_upload"
export BASE_URL="http://localhost:8000"

# Run the app
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Usage

### Web UI

Open the app in your browser. Paste HTML content or upload an HTML file, select an expiration period, and click **Upload & Generate Link**.

### curl / API

Upload a file:

```bash
curl -X POST \
  -F "html_file=@mypage.html" \
  -F "expiration=7" \
  http://localhost:8000/api/upload
```

Upload from stdin:

```bash
echo "<h1>Hello World</h1>" | curl -X POST \
  -F "html_file=@-;filename=page.html" \
  -F "expiration=1" \
  http://localhost:8000/api/upload
```

Expiration values: `1` (1 day), `7` (7 days), `30` (30 days), `0` (indefinite).

Response:

```json
{
  "success": true,
  "link": "http://localhost:8000/link/AbCdEf123456",
  "id": "AbCdEf123456",
  "expires_at": "2026-03-05T12:00:00+00:00",
  "size_bytes": 25
}
```

### Get Page Info

```bash
curl http://localhost:8000/api/info/AbCdEf123456
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://webapp:webapp@localhost:5432/webpage_upload` | PostgreSQL connection string |
| `BASE_URL` | `http://localhost:8000` | Base URL for generated links |
| `MAX_UPLOAD_SIZE` | `5242880` | Maximum upload size in bytes (default 5MB) |

## Kubernetes Deployment

### Prerequisites

- A Kubernetes cluster (e.g., EKS)
- [Traefik](https://traefik.io/) ingress controller installed
- [cert-manager](https://cert-manager.io/) installed with a ClusterIssuer configured
- `kubectl` configured for your cluster
- A container registry to push your image

### 1. Build and Push the Docker Image

```bash
docker build -t your-registry/webpage-upload:latest .
docker push your-registry/webpage-upload:latest
```

### 2. Configure the Manifests

Before deploying, update the following files with your values:

**`k8s/configmap.yaml`** - Set your domain and optionally adjust upload size:

```yaml
data:
  BASE_URL: "https://your-domain.com"
  MAX_UPLOAD_SIZE: "5242880"    # 5MB, increase as needed
```

**`k8s/postgres.yaml`** - Change the default database password in the Secret section. Optionally set `storageClassName` in the PVC:

```yaml
stringData:
  POSTGRES_PASSWORD: your-secure-password
```

**`k8s/secret.yaml`** - Update the database URL to match the password above:

```yaml
stringData:
  DATABASE_URL: "postgresql://webapp:your-secure-password@postgres:5432/webpage_upload"
```

**`k8s/deployment.yaml`** - Set your container image:

```yaml
image: your-registry/webpage-upload:latest
```

**`k8s/middleware.yaml`** - Add your allowed IP addresses:

```yaml
spec:
  ipAllowList:
    sourceRange:
      - 1.2.3.4/32          # Your office IP
      - 10.0.0.0/8          # Your VPN range
```

**`k8s/ingress.yaml`** - Replace `upload.example.com` with your domain.

**`k8s/certificate.yaml`** - Replace the domain and set your ClusterIssuer name:

```yaml
spec:
  issuerRef:
    name: your-clusterissuer-name
    kind: ClusterIssuer
  dnsNames:
    - your-domain.com
```

### 3. Deploy

```bash
kubectl apply -k k8s/
```

### 4. Verify

```bash
# Check all resources
kubectl get all -n webpage-upload

# Check the ingress
kubectl get ingress -n webpage-upload

# Check certificate status
kubectl get certificate -n webpage-upload

# View app logs
kubectl logs -n webpage-upload -l app=webpage-upload

# View postgres logs
kubectl logs -n webpage-upload -l app=postgres
```

### Updating the Application

```bash
# Build and push new image
docker build -t your-registry/webpage-upload:v1.1.0 .
docker push your-registry/webpage-upload:v1.1.0

# Update the deployment image
kubectl set image deployment/webpage-upload \
  webapp=your-registry/webpage-upload:v1.1.0 \
  -n webpage-upload
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Web UI upload form |
| `POST` | `/upload` | Upload via web form |
| `POST` | `/api/upload` | Upload via API/curl |
| `GET` | `/link/{id}` | View uploaded page |
| `GET` | `/api/info/{id}` | Get page metadata |
| `GET` | `/health` | Health check |

## License

[MIT](LICENSE)
