.PHONY: up down logs demo test clean

# Start the full stack
up:
	docker compose up -d --build

# Phase 1 only (gateway + servers)
up-phase1:
	docker compose up -d --build keycloak redis gateway bloomberg-mcp risk-mcp research-mcp

# Phase 1 + 2 (adds cognitive layer)
up-phase2:
	docker compose up -d --build keycloak redis gateway bloomberg-mcp risk-mcp research-mcp timescaledb cognitive-mcp

# Full stack (all 3 phases)
up-all:
	docker compose up -d --build

# Stop everything
down:
	docker compose down -v

# Follow logs
logs:
	docker compose logs -f

logs-gateway:
	docker compose logs -f gateway

logs-servers:
	docker compose logs -f bloomberg-mcp risk-mcp research-mcp

# Run demo agent
demo:
	python demo/agent.py --user alice --scenario happy_path

demo-isolation:
	python demo/agent.py --user alice --scenario pm_isolation

demo-bob:
	python demo/agent.py --user bob --scenario happy_path

# Run tests
test:
	pytest tests/ -v

test-e2e:
	pytest tests/e2e/ -v --timeout=120

# Health check
health:
	@echo "Keycloak:  $$(curl -sf http://localhost:8080/health/ready | python3 -c 'import sys,json; print(json.load(sys.stdin).get(\"status\",\"DOWN\"))' 2>/dev/null || echo DOWN)"
	@echo "Gateway:   $$(curl -sf http://localhost:9000/health | python3 -c 'import sys,json; print(json.load(sys.stdin).get(\"status\",\"DOWN\"))' 2>/dev/null || echo DOWN)"
	@echo "Bloomberg: $$(curl -sf http://localhost:8010/health && echo UP || echo DOWN)"
	@echo "Risk:      $$(curl -sf http://localhost:8011/health && echo UP || echo DOWN)"
	@echo "Research:  $$(curl -sf http://localhost:8012/health && echo UP || echo DOWN)"

# Clean up everything
clean:
	docker compose down -v --rmi local
	docker system prune -f
