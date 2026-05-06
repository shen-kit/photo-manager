# High-Performance Photo Manager

This project is a privacy-focused, self-hosted photo management system designed to replace proprietary cloud services. It is built for speed and long-term reliability, specifically optimized for home server hardware like a Dell Optiplex using a tiered SSD/HDD storage model.

## Project Vision
The goal is to provide a smooth, "Google Photos" style experience—including natural language search and facial recognition—while ensuring complete data ownership. This is intended to be a robust piece of personal infrastructure rather than a temporary project.

## Design Decisions

### Tiered Storage Strategy
To ensure the interface remains responsive even with a massive library on mechanical drives, the system hardware is split into two logical tiers:

* **SSD Tier (`data/`):** This hosts high-I/O data such as the PostgreSQL database, Redis snapshots, and AI model weights. Keeping metadata on the SSD prevents the mechanical hard drives from needing to spin up just to browse the timeline.
* **HDD Tier (`storage/`):** This is for bulk media storage.
    * `/media/originals`: Your original high-resolution files, mounted as **Read-Only** to prevent accidental data loss.
    * `/media/processed`: A dedicated space for generated thumbnails, full-screen previews, and face crops.

### Single Source of Truth
* **Database-Centric Metadata:** All EXIF data, tags, and AI vectors are stored in **PostgreSQL**. We avoid sidecar files to simplify the filesystem and speed up queries.
* **Relative Pathing:** The database stores paths relative to the library root (e.g., `2026/05/img.jpg`). This makes the entire library portable; you can move your storage to a different drive or mount point without breaking the database.

### Backend Performance
* **SQLModel:** We use SQLModel to bridge SQLAlchemy and Pydantic. This allows us to define our data structures once and have them apply to both the database and the API validation layers.
* **Hybrid Ingestion:** * **Immediate Tasks:** The API uses FastAPI `BackgroundTasks` to generate Blurhashes and small thumbnails instantly so you get immediate visual feedback after an upload.
    * **Heavy Tasks:** CPU-intensive tasks like facial recognition (InsightFace) and vector embedding (CLIP) are offloaded to an **arq** worker.

## Repository Structure

The project is organized as a monorepo to keep the frontend and backend logic in sync:

```text
/photo-manager
├── backend/              # FastAPI Source (Shared by API & Worker)
│   ├── app/
│   │   ├── api/          # Versioned Controllers (v1, v2)
│   │   ├── core/         # Security (JWT), Config, DB session
│   │   ├── features/     # Feature-based logic (assets, faces, search)
│   │   └── models.py     # Unified SQLModel classes
│   └── worker/           # arq task definitions
├── web/                  # Next.js / ReactTS Frontend
├── mobile/               # Flutter Source
├── data/                 # [SSD Mount] DB, Redis, AI Cache
└── storage/              # [HDD Mount] Originals (RO), Processed (RW)
```

## Security and Networking
* **Authentication:** The system uses OAuth2 with short-lived **JWT Access Tokens** and long-lived **Refresh Token Rotation** to keep you logged into your devices securely.
* **Networking:** Remote access is handled via **Tailscale MagicDNS** and **HTTPS**.
* **Reverse Proxy:** Caddy is used to handle automatic SSL certificates and internal routing between the frontend and the API.

## Tech Stack Requirements
For anyone (or any agent) contributing code to this repository, please adhere to these specific technologies:

* **Backend:** Python 3.11+, FastAPI, SQLModel.
* **Database:** PostgreSQL with `pgvector` and `ltree`.
* **Queueing:** Redis + `arq` (for async-native task processing).
* **AI Models:**
    * **Search:** OpenCLIP `ViT-B-32` (512-dim vectors).
    * **Faces:** InsightFace (Buffalo-L) running on ONNX.
* **Frontend:** Next.js for Web and Flutter for Mobile.

## Getting Started

### Prerequisites
* Docker and Docker Compose.
* Tailscale installed and authenticated on the host machine.

### Local Development
1. Clone the repository and create a repo-root `.env` file with at least:
   ```env
   POSTGRES_DB=photo_manager
   POSTGRES_USER=photo_manager
   POSTGRES_PASSWORD=photo_manager
   POSTGRES_PORT=5432
   REDIS_PORT=6379
   API_PORT=8000
   JWT_SECRET=<long-random-secret>
   ```
2. Start the full development stack in Docker:
   ```bash
   docker compose up --build
   ```
3. Open the API docs:
   ```bash
   http://localhost:8000/docs
   ```
4. Create your initial user via the auth API:
   ```bash
   curl -i -c cookies.txt -X POST http://localhost:8000/api/v1/auth/register \
     -H 'Content-Type: application/json' \
     -d '{"username":"testuser","password":"testpass123"}'
   ```

# Development Notes

- **Async First:** Use `async/await` for all database and file I/O operations.
- **Dependency Injection:** Use FastAPI Depends for database sessions and user authentication.
- **Path Resolution:** Never use absolute host paths. Always resolve media against the environment-defined library root.
- **Versioning:** All new API endpoints must be placed in a versioned directory (e.g. `app/api/v1/`). Shared logic should be abstracted into the `services/` directory or `models.py`.
