set dotenv-load := true

api_url := "http://localhost:{{ env_var_or_default('API_PORT', '8000') }}"

default:
    @just --list

up:
    docker compose up --build

up-d:
    docker compose up --build -d

down:
    docker compose down

restart:
    docker compose down
    docker compose up --build

ps:
    docker compose ps

logs service="":
    docker compose logs -f {{ service }}

health:
    curl {{ api_url }}/health

docs:
    @echo {{ api_url }}/docs

register username="testuser" password="testpass123":
    curl -i -c cookies.txt -X POST {{ api_url }}/api/v1/auth/register \
      -H 'Content-Type: application/json' \
      -d '{"username":"{{ username }}","password":"{{ password }}"}'

login username="testuser" password="testpass123":
    curl -i -c cookies.txt -X POST {{ api_url }}/api/v1/auth/login \
      -H 'Content-Type: application/json' \
      -d '{"username":"{{ username }}","password":"{{ password }}"}'

refresh:
    curl -i -b cookies.txt -c cookies.txt -X POST {{ api_url }}/api/v1/auth/refresh

logout:
    curl -i -b cookies.txt -X POST {{ api_url }}/api/v1/auth/logout

me access_token:
    curl -H "Authorization: Bearer {{ access_token }}" {{ api_url }}/api/v1/auth/me

assets access_token:
    curl -H "Authorization: Bearer {{ access_token }}" {{ api_url }}/api/v1/assets/

db-shell:
    docker compose exec db psql -U {{ env_var_or_default('POSTGRES_USER', 'photo_manager') }} -d {{ env_var_or_default('POSTGRES_DB', 'photo_manager') }}
