# Engineering App Suite

Multi-tool engineering software workspace built with Python and Streamlit.

## Run

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the software:

```bash
streamlit run main.py
```

## Current Tools

- `Singly Beam Analysis`
  Reinforced concrete singly reinforced beam analysis and design.
- `Doubly Beam Analysis`
  Coming Soon.
- `Beam Fiber Model`
  Coming Soon.

## Project Structure

```text
project_root/
├─ main.py
├─ README.md
├─ requirements.txt
├─ assets/
├─ core/
│  ├─ navigation.py
│  ├─ shared_models.py
│  ├─ state_store.py
│  ├─ theme.py
│  └─ utils.py
├─ apps/
│  ├─ landing/
│  │  └─ landing_page.py
│  ├─ singly_beam/
│  │  ├─ singly_beam_app.py
│  │  ├─ formulas.py
│  │  ├─ models.py
│  │  ├─ visualization.py
│  │  ├─ report_builder.py
│  │  ├─ verifier.py
│  │  ├─ settings_page.py
│  │  ├─ calculation_report_page.py
│  │  ├─ calculation_report_full_page.py
│  │  └─ workspace_page.py
│  ├─ doubly_beam/
│  │  └─ placeholder.py
│  └─ beam_fiber_model/
│     └─ placeholder.py
└─ tests/
```

## Notes

- The app now starts from a landing page that acts as the main menu for the software suite.
- Only `Singly Beam Analysis` is currently available to open.
- The singly beam engineering logic remains intact and is now hosted under `apps/singly_beam/`.
- The structure is prepared for future engineering tools without changing the root entry workflow.
