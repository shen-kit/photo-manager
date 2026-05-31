# OpenAPI schema

Backend OpenAPI schema is committed at:

```text
backend/openapi-schema.json
```

Regenerate after backend route, request model, response model, auth, or validation changes:

```bash
just openapi
```

CI/staleness check:

```bash
just openapi-check
```

The exporter imports `app.main:app` and calls `app.openapi()` directly. No server, database, Redis, ML model, or media volume is required.

## Web frontend usage

Recommended TypeScript setup uses `openapi-typescript` for types and `openapi-fetch` for a small typed fetch client:

```bash
cd web
npm install -D openapi-typescript
npm install openapi-fetch
npx openapi-typescript ../backend/openapi-schema.json -o src/api/schema.d.ts
```

Example client shape:

```ts
import createClient from "openapi-fetch";
import type { paths } from "./schema";

export const api = createClient<paths>({
  baseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
  credentials: "include",
});
```

For bearer-protected routes, pass `Authorization: Bearer <accessToken>` in request headers. Refresh-token routes use the `HttpOnly` cookie set by auth endpoints, so browser clients should keep `credentials: "include"`.

## Other generators

OpenAPI Generator can generate a Fetch client:

```bash
openapi-generator-cli generate \
  -i backend/openapi-schema.json \
  -g typescript-fetch \
  -o web/src/api/generated
```
