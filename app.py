"""Streamlit entry point for the guided, resume-first RoleSignal workspace.

Run with ``python -m streamlit run app.py``. The UI does not load an embedding
model until the user explicitly requests job ranking.
"""
from ui.workspace import main

if __name__ == "__main__":
    main()
