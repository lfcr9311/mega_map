CYCLE ?= 2607
ZIP   ?= data/cycles/$(CYCLE)/FMS_ciclo.zip
PY    := backend/.venv/bin

.PHONY: install data api web dev test build serve

install:            ## venv do backend + node_modules do frontend
	python3 -m venv backend/.venv
	$(PY)/pip install -e 'backend[dev]'
	cd frontend && npm install

data:               ## decodifica o ciclo e compila data/build/navgraph.json.gz
	$(PY)/fmsnav build $(ZIP) --cycle $(CYCLE) --out data/build

api:                ## API em modo dev (http://127.0.0.1:8001)
	$(PY)/fmsnav serve --reload

web:                ## frontend em modo dev (http://localhost:5173, /api -> 8001)
	cd frontend && npm run dev

test:
	cd backend && .venv/bin/pytest -q
	cd frontend && npm run typecheck

build:              ## compila o frontend para frontend/dist (servido pela API)
	cd frontend && npm run build

serve: build        ## tudo em um processo: http://127.0.0.1:8001
	$(PY)/fmsnav serve
