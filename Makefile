CYCLE ?= 2607
ZIP   ?= data/cycles/$(CYCLE)/FMS_ciclo.zip
PY    := backend/.venv/bin

.PHONY: install data api web dev test build serve deploy-data

install:            ## venv do backend + node_modules do frontend
	python3 -m venv backend/.venv
	$(PY)/pip install -e 'backend[dev]'
	cd frontend && npm install

data:               ## decodifica o ciclo e compila data/build/navgraph.json.gz
	$(PY)/fmsnav build $(ZIP) --cycle $(CYCLE) --out data/build

api:                ## API em modo dev (http://127.0.0.1:8001/map/)
	$(PY)/fmsnav serve --reload

web:                ## frontend em modo dev (http://localhost:5173/map/, /map/api -> 8001)
	cd frontend && npm run dev

test:
	cd backend && .venv/bin/pytest -q
	cd frontend && npm run typecheck

build:              ## compila o frontend para frontend/dist (servido pela API)
	cd frontend && npm run build

serve: build        ## tudo em um processo: http://127.0.0.1:8001/map/
	$(PY)/fmsnav serve

EC2     ?= ubuntu@ec2-3-137-219-87.us-east-2.compute.amazonaws.com
EC2_KEY ?= ~/.ssh/ec2.pem

deploy-data:        ## sobe o grafo para a EC2 (uma vez por ciclo; o Git nao leva dados)
	ssh -i $(EC2_KEY) $(EC2) 'mkdir -p ~/mega_map/data/build'
	scp -i $(EC2_KEY) data/build/navgraph.json.gz $(EC2):mega_map/data/build/navgraph.json.gz
	ssh -i $(EC2_KEY) $(EC2) 'cd ~/mega_map && docker compose restart fmsnav 2>/dev/null || true'
