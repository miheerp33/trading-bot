## Trading bot (skeleton)

### Setup

Create a virtualenv and install deps:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### Configuration

Copy `.env.example` to `.env` and adjust values as needed.

Key vars:
- `IB_HOST`, `IB_PORT`
- `SYMBOL`, `ORDER_QUANTITY`

### Run

```bash
. .venv/bin/activate
python main.py
```

### Tests

```bash
. .venv/bin/activate
pytest
```

