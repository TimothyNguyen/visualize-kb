# visualize-kb

Visualize multiple repos easily with high performance via UI

py -m venv .venv-core
.venv-core/bin/python -m pip install -e ./kb-core

py -m venv .venv-ui
.venv-ui/bin/python -m pip install -e ./kb-core-ui/python

Frontend:
source .venv-core/bin/activate
py kb-core-ui/dev.py frontend .