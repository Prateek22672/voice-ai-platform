# Docker — Interview Study Guide (from a real 12-service project)

*What Docker is, the vocabulary interviewers test, exactly how THIS Voice AI platform uses it, the commands you'll actually run, and crisp answers to the classic questions.*

---

## 01 · What Docker is — and the problem it solves

Software breaks when it moves between machines: different OS, different library versions, a missing dependency. The classic line is *"but it works on my machine."*

Docker fixes that by packaging your app **together with everything it needs to run** — the code, the runtime, the libraries, the config — into one portable unit called an **image**. That image runs **identically** on your laptop, a teammate's laptop, a CI server, or a cloud GPU box.

### Container vs Virtual Machine (a favourite interview question)

| | Container (Docker) | Virtual Machine |
|---|---|---|
| What it virtualizes | Just the app + its process (shares the host's OS kernel) | A whole computer (its own full OS) |
| Size | MBs–hundreds of MBs | GBs |
| Start time | Milliseconds–seconds | Tens of seconds–minutes |
| Isolation | Process-level (lighter) | Hardware-level (heavier, stronger) |
| Use | Run many services on one host, cheaply | Run different OSes, strong isolation |

**One-line answer:** *a container shares the host kernel and isolates a process; a VM boots an entire operating system.* That's why containers are small and fast.

---

## 02 · The vocabulary — every term interviewers use

| Term | Meaning |
|---|---|
| **Image** | A read-only *snapshot/template* of an app + its dependencies. Build once, run many times. e.g. `voice-ai-platform-stt-service:latest`. |
| **Container** | A *running instance* of an image — an isolated process. Image is the class, container is the object. |
| **Dockerfile** | The recipe to build an image: steps like `FROM`, `RUN`, `COPY`, `CMD`. |
| **Layer** | Each Dockerfile line becomes a cached layer. Change one line → only that layer and the ones after it rebuild. Order matters. |
| **Registry** | Where images are stored & shared — Docker Hub, GitHub GHCR, AWS ECR. `pull` to download, `push` to upload. |
| **Tag** | A version label on an image: `myapp:1.2`, `myapp:latest`. |
| **Volume** | Persistent storage that *outlives* a container — DBs, uploads, cached models. Delete the container, keep the data. |
| **Bind mount** | Maps a host folder straight into the container (`./voices:/app/voices`). Great for dev and reading host data. |
| **Network** | A private virtual network so containers talk to each other by *name* (not `localhost`). |
| **Port mapping** | `host:container` — expose a container's port. `8001:8001` = localhost:8001 → the container's 8001. |
| **Docker Compose** | A YAML file that defines a *multi-container* app and runs it with one command. |
| **Build context** | The folder Docker sends to the daemon to build from (usually `.`). `.dockerignore` keeps junk out. |
| **CMD / ENTRYPOINT** | The command that runs when the container starts (e.g. `python app.py`). |

---

## 03 · Exactly how THIS project uses Docker

This Voice AI platform is a **microservices** app: 12 small services, each in its own container, wired together by one `docker-compose.yml`. That's the real-world story you tell in an interview.

### The stack (12 containers on one private network)

```
Your machine (host ports)
  :3000 dashboard   :8080 api-gateway   :8000 gateway
  :8001 stt   :8002 tts   :8003 conversation   :5432 postgres
        │
        ▼  (Docker Compose network — services reach each other by name)

  OUR images (built from Dockerfiles):
    stt-service · tts-service · conversation-service · websocket-gateway
    api-gateway · recording-service · analytics-service · dashboard

  OFF-THE-SHELF images (pulled from Docker Hub):
    postgres:16 · redis:7 · nats:2.10 · minio

  VOLUMES (data that survives restarts):
    hfcache (downloaded AI models) · pgdata (database)
    miniodata (files) · ./voices (bind mount)
```

### A real Dockerfile from this repo (the STT service)

```dockerfile
# the recipe that builds one service's image
FROM python:3.11-slim              # small base image with Python
RUN  apt-get update && apt-get install -y ffmpeg   # system dep
WORKDIR /app                       # where commands run inside the container
COPY requirements.txt .            # copy deps FIRST (own cache layer)…
RUN  pip install -r requirements.txt   # …so code changes don't re-install deps
COPY . /app                        # then copy the source code
CMD  ["python", "app.py"]          # what runs when the container starts
```

> Deps are copied & installed **before** the code — so editing code reuses the cached install layer and rebuilds in seconds. That layer-ordering trick is great to mention.

### How the services find each other (the network)

Inside the Compose network, the gateway reaches the STT service by its **service name**, not localhost:

```python
STT_WS   = "ws://stt-service:8001/v1/stt/stream"
CONV_URL = "http://conversation-service:8003"
```

`stt-service` resolves to that container's IP automatically. **Compose gives every service DNS by its name on a shared network.**

### Why Docker was the right call here

- **12 services, mixed stacks** (Python, Node/Next.js, Asterisk) run consistently — no "install 12 things on your laptop."
- **One command runs everything:** `docker compose up`.
- **Volumes** mean multi-GB AI models download once and survive restarts (the `hfcache` volume).
- **Portable:** the same images move to a cloud GPU server unchanged — just add the GPU flag.
- **Isolation:** a crash or bad dependency in one service can't corrupt another.

---

## 04 · Command cheat sheet (the ones you'll actually use)

### Compose — multi-service (what we use most)

| Command | What it does |
|---|---|
| `docker compose up` | Build (if needed) + start all services, logs in foreground |
| `docker compose up -d` | Same, but detached (background) |
| `docker compose up --build` | Force a rebuild of images, then start |
| `docker compose build stt-service` | Rebuild just one service's image |
| `docker compose down` | Stop & remove all containers (volumes/data kept) |
| `docker compose ps` | List the stack's containers + status |
| `docker compose logs -f api-gateway` | Tail one service's logs live |
| `docker compose restart dashboard` | Restart one service |
| `docker compose up -d --force-recreate stt-service` | Recreate a container to pick up new env/image |

### Images

| Command | What it does |
|---|---|
| `docker build -t myapp:1.0 .` | Build an image from the Dockerfile in `.`, tag it |
| `docker images` | List local images + sizes |
| `docker pull postgres:16` | Download an image from a registry |
| `docker push myapp:1.0` | Upload your image to a registry |
| `docker rmi myapp:1.0` | Delete an image |

### Containers & debugging

| Command | What it does |
|---|---|
| `docker run -d -p 8080:80 nginx` | Run a container in the background, map a port |
| `docker ps` / `docker ps -a` | List running / all containers |
| `docker logs -f <name>` | Stream a container's logs |
| `docker exec -it <name> sh` | Open a shell **inside** a running container (debugging gold) |
| `docker stop / start / rm <name>` | Stop, start, delete a container |
| `docker inspect <name>` | Full JSON details (ports, mounts, env) |

### Volumes & cleanup

| Command | What it does |
|---|---|
| `docker volume ls` | List volumes |
| `docker system df` | How much disk images/containers/volumes use |
| `docker system prune -a` | Reclaim space — remove unused images/containers (careful!) |
| `docker compose down -v` | Down **and** delete volumes (wipes the data) |

---

## 05 · Real-world patterns worth naming

| Pattern | Why it matters |
|---|---|
| **Multi-stage build** | Build in a heavy image, copy only the final artifact into a tiny runtime image → smaller, safer production images. |
| **.dockerignore** | Keeps `node_modules`, `.git`, secrets out of the build context — faster builds, smaller images. |
| **Dev vs prod** | Dev: bind-mount your code so edits reload instantly. Prod: bake code into the image so it's immutable. |
| **Env & secrets** | Config comes from environment variables (a `.env` file), never hard-coded — same image runs everywhere. |
| **Health checks** | Compose waits for a dependency to be *healthy* before starting another (here: api-gateway waits for Postgres). |
| **Registry + CI/CD** | Pipeline: `build → test → push to registry → deploy`. The deploy just pulls the new image. |
| **Compose vs Kubernetes** | Compose = many containers on *one* host (dev, small prod). Kubernetes = orchestrate across a *cluster* with auto-scaling, self-healing, rolling updates. |

> **Say this and you sound senior:** *"We containerized each microservice with its own Dockerfile, orchestrated them locally with Docker Compose over a shared network, persisted state in named volumes, and configured everything through environment variables — so the exact same images move from a laptop to a GPU server or a Kubernetes cluster without code changes."*

---

## 06 · Classic interview Q&A (crisp answers)

**Image vs container?** — An image is a read-only template (the class); a container is a running instance of it (the object). One image → many containers.

**Container vs VM?** — A container shares the host OS kernel and isolates a process (small, fast). A VM virtualizes hardware and runs a full OS (heavy, more isolated).

**What is a Dockerfile?** — A text recipe of steps (`FROM`, `RUN`, `COPY`, `CMD`) that Docker executes to build an image. Each step is a cached layer.

**Volume vs bind mount?** — Both persist data outside the container. A *volume* is Docker-managed storage (best for DB data). A *bind mount* maps a specific host folder in (best for dev / reading host files).

**How do containers talk to each other?** — Over a shared Docker network, addressing each other by service name (DNS). In Compose, `http://api-gateway:8080` just works.

**How do you persist a database's data?** — Mount a named volume at its data directory (here Postgres uses `pgdata:/var/lib/postgresql/data`). Recreate the container, keep the data.

**Why install deps before copying code in a Dockerfile?** — Layer caching. Deps change rarely; code changes often. Installing deps first means a code edit reuses the cached install layer and rebuilds in seconds.

**What does Docker Compose add over plain Docker?** — It defines a whole multi-container app (services, networks, volumes, env, dependencies) in one YAML file and runs it with a single command instead of many `docker run`s.

**CMD vs ENTRYPOINT?** — `ENTRYPOINT` is the fixed executable; `CMD` gives default arguments (easy to override at `docker run`). Many images just use `CMD`.

**How would you make an image smaller?** — Use a slim/alpine base, multi-stage builds, a `.dockerignore`, combine `RUN` steps, and don't ship build tools in the final stage.

---

*Built from this project's real `docker-compose.yml` and service Dockerfiles. Best prep: run `docker compose ps`, `docker compose logs -f stt-service`, and `docker exec -it <container> sh` on the live stack and talk through what you see.*
