from db.local_db import db
import json

def check_pcr():
    res = db.query("SELECT * FROM pcr_history ORDER BY timestamp DESC LIMIT 20", json_serialize=True)
    print(json.dumps(res, indent=2))

if __name__ == "__main__":
    check_pcr()
