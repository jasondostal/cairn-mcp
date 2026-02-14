# Cairn UI

Web dashboard for [Cairn](https://github.com/jasondostal/cairn-mcp) — a self-hosted memory system for AI agents and humans.

Built with Next.js 16, shadcn/ui, Tailwind CSS 4, and Recharts. 24 pages covering search, analytics, knowledge graph, session replay, chat, terminal, and more.

## Running

The UI ships as a Docker image and is included in the main `docker-compose.yml`:

```bash
docker compose up -d
```

The dashboard is available at `http://localhost:3000`.

## Development

```bash
npm install
npm run dev
```

Requires `CAIRN_API_URL` pointing to a running Cairn backend (default: `http://localhost:8000`).
