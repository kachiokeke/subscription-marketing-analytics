DBT := .venv/bin/dbt

.PHONY: setup explore build test train app all clean

# One-time setup: create venv and install everything.
setup:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt
	$(DBT) deps --profiles-dir .

# STEP 1: profile the raw data. Extend explore.py, run this, take notes.
explore:
	.venv/bin/python explore.py

# Build the dbt pipeline (staging -> core -> features) and run tests.
build:
	$(DBT) build --profiles-dir .

# Run only tests.
test:
	$(DBT) test --profiles-dir .

# Train the ML model. Expects `make build` to have run first.
train:
	.venv/bin/python ml/train.py

# Launch the Streamlit app.
app:
	.venv/bin/streamlit run app/streamlit_app.py

# Full end-to-end: build pipeline, train model, then launch the app.
all: build train app

# Wipe generated artifacts (keeps venv and dbt_packages).
clean:
	rm -f warehouse.duckdb warehouse.duckdb.wal
	rm -rf target logs
