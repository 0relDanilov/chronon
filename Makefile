SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

UV_RUN := uv run --extra dev
KUSTOMIZE ?= kustomize
CLUSTER_NAME ?= chronon
MODE ?= fair

CHRONON_URL ?= https://api.chronon.test:8443
CHRONON_STATE_URL ?= https://state.chronon.test:8443
SSL_CERT_FILE ?= $(CURDIR)/.certs/ca.pem

# Every directory that may hold a kustomization; missing ones are skipped.
KUSTOMIZE_DIRS := $(wildcard clusters/*/apps) $(wildcard clusters/*/overlays/*) \
	$(wildcard platform/*) $(wildcard backends/*/base) services/k8s/base
# CRD kinds (Application, Certificate, Gateway...) are validated against the
# community CRD catalog; kinds in neither catalog are reported as skipped.
KUBECONFORM := kubeconform -strict -ignore-missing-schemas -summary \
	-schema-location default \
	-schema-location 'https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'

.PHONY: help up-local down-local images-local reload-local ca check \
	contract rehearsal seal docs tokens

help: ## list targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | \
	  awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

up-local: ## kind + Cilium + Argo CD bootstrap (clusters/local)
	scripts/bootstrap/local.sh

down-local: ## delete the local kind cluster
	kind delete cluster --name $(CLUSTER_NAME)

images-local: ## build images for the host arch and kind-load them
	docker build -f docker/Dockerfile --target base -t chronon:dev .
	kind load docker-image --name $(CLUSTER_NAME) chronon:dev

reload-local: images-local ## rebuild, kind-load, and restart chronon pods
	# Same :dev tag, so nothing in git changes: restart to pick up the image.
	kubectl -n chronon rollout restart deploy -l app.kubernetes.io/part-of=chronon
	kubectl -n chronon rollout status deploy -l app.kubernetes.io/part-of=chronon \
	  --timeout=5m

ca: ## export the local site's CA certificate to .certs/ca.pem
	@mkdir -p .certs
	kubectl -n cert-manager get secret chronon-ca \
	  -o jsonpath='{.data.ca\.crt}' | base64 -d > .certs/ca.pem
	@openssl x509 -in .certs/ca.pem -noout -subject -enddate

check: ## static gates
	$(UV_RUN) ruff format --check .
	$(UV_RUN) ruff check .
	$(UV_RUN) pyright src scripts tests
	$(UV_RUN) pytest -q tests/unit
	@for d in $(KUSTOMIZE_DIRS); do \
	  if [ -f $$d/kustomization.yaml ]; then \
	    echo "kubeconform: $$d"; \
	    $(KUSTOMIZE) build $$d | $(KUBECONFORM); \
	  fi; \
	done
	@echo "grep: upstream domain outside the allowed files"
	! git grep --untracked -n "i-qcc\.com" -- ':!vendor' ':!CLAUDE.md' \
	  ':!docs/contract.md' ':!docs/security.md' ':!scripts/client_patch.py'

contract: ## real client against a running site (mints its own tokens)
	SSL_CERT_FILE=$(SSL_CERT_FILE) CHRONON_URL=$(CHRONON_URL) \
	CHRONON_STATE_URL=$(CHRONON_STATE_URL) \
	$(UV_RUN) pytest -q tests/contract

rehearsal: ## the 50-student rehearsal (MODE=fifo|fair)
	SSL_CERT_FILE=$(SSL_CERT_FILE) CHRONON_URL=$(CHRONON_URL) \
	CHRONON_STATE_URL=$(CHRONON_STATE_URL) \
	$(UV_RUN) python scripts/rehearsal/run.py --mode $(MODE)

seal: ## not this round: no secrets in git yet
	@echo "No secrets are needed in git yet; Sealed Secrets is future work."
	@exit 1

docs: ## serve the docs locally
	$(UV_RUN) mkdocs serve

tokens: ## mint demo tokens into .tokens/
	$(UV_RUN) python scripts/mint_tokens.py
