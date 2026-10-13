# ZingFoodie POS

A browser-based Flask Point-of-Sale app based on the supplied ZingFoodie POS PDF.

## Features
- Product listing and search by product code or name
- Session-based shopping cart with quantity update and one-click item removal
- No discount, Senior Citizen (20%), and Student (10%) discount options from the source program
- Payment validation, change calculation, printed receipt, and stock deduction after successful checkout
- Product add/edit/delete, stock replenishment (including from zero), and sales reports
- JSON data format with `products` and `transactions`

## Run locally
Requires Python 3.10 or newer.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000.

## Deploy to Render
1. Upload all project files to a GitHub repository.
2. In Render, choose **New + → Blueprint** and connect the repository containing `render.yaml`.
3. Review the service and persistent disk settings, then create the Blueprint.
4. Wait for deployment and open the `onrender.com` URL.

The included `render.yaml` is configured for a Free web service. Render's free web services use an ephemeral filesystem, so changes saved to `pos_data.json` can be lost during redeploys or restarts. Render persistent disks are available only for paid services. If you need inventory and sales history to survive redeploys, use a paid service with a disk mounted at `/var/data` and set `POS_DATA_FILE=/var/data/pos_data.json`, or migrate the app to a managed database.

## Manual Render setup (if not using Blueprint)
- Runtime: Python
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`
- Environment variables:
  - `SECRET_KEY`: use a long random secret
  - `POS_DATA_FILE`: optional; set to `/var/data/pos_data.json` only when a persistent disk is mounted at `/var/data`

## Data and access notes
- The default app is suitable for a school/demo project. It does not include staff accounts or admin authentication; anyone who can reach `/admin` can change inventory.
- The data file is shared JSON storage. For simultaneous multi-user production use, use a database and transactions/locking rather than JSON.
- Back up `pos_data.json` before making major changes.
