"""Published personal timetables are filtered before reports and exports."""
from copy import deepcopy


def personal(user, version):
    if user["role"] not in ("teacher", "student"):
        return version
    result = deepcopy(version)
    result["lectures"] = [l for l in result["lectures"] if (
        l["faculty"] == user.get("faculty_id") if user["role"] == "teacher" else l["batch"] in user.get("batch_ids", []))]
    ids = {l["id"].rsplit(":",1)[0] for l in result["lectures"]}
    result["problem"]["requirements"] = [r for r in result["problem"]["requirements"] if r["id"] in ids]
    for kind, field in (("faculty","faculty"),("subjects","subject"),("rooms","classroom"),("batches","batch")):
        used={l[field] for l in result["lectures"]}
        result["policy"][kind]=[r for r in result["policy"][kind] if r["id"] in used]
    result["changes"]=[]
    result["source_id"]=None
    return result
