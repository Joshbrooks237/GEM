"""Oracle for the Experiment 3 contracts. Not shown to agents."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "tasks" / "exp3"

RAW = (
    "Read records from stdin. Each line is one record. Split the line on spaces into "
    "key=value tokens, using the first = in a token. Ignore blank lines and lines whose "
    "first character is #. The keys are name, role, and years. Ignore any other key. "
    "If a key is repeated on a line, keep the last value. If years is present it must be "
    "decimal digits for a non-negative integer, with no leading zero unless the value is 0. "
    "Otherwise drop that record."
)
JSONL = (
    "Write one JSON object per record and no spaces. Present keys stay in the order "
    "name, role, years. name and role are strings. years is a number. Omit a missing key. "
    "End each object with a newline. If no records remain, write nothing."
)
BAND = (
    "Add a string field band. If years is less than five, band is junior. Otherwise band "
    "is senior. If years is missing, band is unknown. Present keys stay in the order "
    "name, role, years, band."
)

PROMPTS = {
    "parse": f"{RAW}\n\n{JSONL}\n\nExample input:\nname=Ada role=dev years=3\nname=Bea role=ops years=10\nExample output:\n"
    '{"name":"Ada","role":"dev","years":3}\n{"name":"Bea","role":"ops","years":10}\n',
    "filter_dev": "Read one JSON object per line. Keep objects whose role is dev, unchanged, "
    "one per line, each ending with a newline. If none match, write nothing.\n\n"
    "Example input:\n"
    '{"name":"Ada","role":"dev","years":3}\n{"name":"Bea","role":"ops","years":10}\n'
    "Example output:\n"
    '{"name":"Ada","role":"dev","years":3}\n',
    "transform_band": "Read one JSON object per line. "
    f"{BAND} No spaces. End each object with a newline. If there are no objects, write nothing.\n\n"
    "Example input:\n"
    '{"name":"Ada","role":"dev","years":3}\n{"name":"Bea","role":"ops","years":10}\n'
    "Example output:\n"
    '{"name":"Ada","role":"dev","years":3,"band":"junior"}\n'
    '{"name":"Bea","role":"ops","years":10,"band":"senior"}\n',
    "aggregate_count": "Read one JSON object per line. Write count=<n> and a newline, where n is "
    "how many objects there were. If there are none, write count=0 and a newline.\n\n"
    "Example input:\n"
    '{"name":"Ada","role":"dev","years":3}\n'
    "Example output:\ncount=1\n",
    "aggregate_years": "Read one JSON object per line. Write years=<sum> and a newline. Add each "
    "object's years. A missing years adds nothing. If there are no objects, the sum is 0.\n\n"
    "Example input:\n"
    '{"name":"Ada","role":"dev","years":3}\n{"name":"Bea","role":"ops","years":10}\n'
    "Example output:\nyears=13\n",
    "serialize": "Read one JSON object per line. Write one JSON array of those objects, in the same "
    "order, with no spaces, followed by a newline. If there are no objects, write [] and a newline.\n\n"
    "Example input:\n"
    '{"name":"Ada","role":"dev","years":3}\n'
    "Example output:\n"
    '[{"name":"Ada","role":"dev","years":3}]\n',
    "validate": "Read one JSON object per line. Write ok and a newline if every line is an object, "
    "name and role are strings, years if present is an integer that is not negative, band if present "
    "is a string, and there are no other keys. Otherwise write bad and a newline. Empty input is ok.\n\n"
    "Example input:\n"
    '{"name":"Ada","role":"dev","years":3}\n'
    "Example output:\nok\n",
    "raw_dev_count": f"{RAW}\n\nWrite count=<n> and a newline, counting records whose role is dev. "
    "If none qualify, write count=0 and a newline.\n\n"
    "Example input:\nname=Ada role=dev years=3\nname=Bea role=ops years=10\nExample output:\ncount=1\n",
    "raw_years": f"{RAW}\n\nWrite years=<sum> and a newline. Add years from the records that remain. "
    "A missing years adds nothing. If no records remain, the sum is 0.\n\n"
    "Example input:\nname=Ada role=dev years=3\nname=Bea role=ops years=10\nExample output:\nyears=13\n",
    "raw_transform_band": f"{RAW}\n\n{JSONL} {BAND}\n\n"
    "Example input:\nname=Ada role=dev years=3\nExample output:\n"
    '{"name":"Ada","role":"dev","years":3,"band":"junior"}\n',
    "raw_serialize": f"{RAW}\n\nWrite one JSON array of the remaining records, in order, with no spaces, "
    "followed by a newline. If none remain, write [] and a newline.\n\n"
    "Example input:\nname=Ada role=dev years=3\nExample output:\n"
    '[{"name":"Ada","role":"dev","years":3}]\n',
    "raw_ops_years": f"{RAW}\n\nWrite years=<sum> and a newline for records whose role is ops. "
    "A missing years adds nothing. If none qualify, the sum is 0.\n\n"
    "Example input:\nname=Ada role=dev years=3\nname=Bea role=ops years=10\nExample output:\nyears=10\n",
    "raw_dev_serialize": f"{RAW}\n\nWrite one JSON array of the records whose role is dev, in order, "
    "with no spaces, followed by a newline. If none qualify, write [] and a newline.\n\n"
    "Example input:\nname=Ada role=dev years=3\nname=Bea role=ops years=10\nExample output:\n"
    '[{"name":"Ada","role":"dev","years":3}]\n',
}

TRAINING = (
    "parse",
    "filter_dev",
    "transform_band",
    "aggregate_count",
    "aggregate_years",
    "serialize",
    "validate",
    "raw_dev_count",
    "raw_years",
    "raw_transform_band",
)
HELD = ("raw_serialize", "raw_ops_years", "raw_dev_serialize")
ORDER = ("name", "role", "years")
BAND_ORDER = ("name", "role", "years", "band")


def _years_ok(value: str) -> bool:
    return value.isdigit() and not (len(value) > 1 and value.startswith("0"))


def parse_raw(text: str) -> list[dict]:
    records = []
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        fields: dict[str, str] = {}
        for token in line.split():
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            if key in {"name", "role", "years"}:
                fields[key] = value
        if "years" in fields and not _years_ok(fields["years"]):
            continue
        obj = {}
        if "name" in fields:
            obj["name"] = fields["name"]
        if "role" in fields:
            obj["role"] = fields["role"]
        if "years" in fields:
            obj["years"] = int(fields["years"])
        records.append(obj)
    return records


def _dump(obj: dict, keys: tuple[str, ...]) -> str:
    ordered = {key: obj[key] for key in keys if key in obj}
    return json.dumps(ordered, separators=(",", ":"), ensure_ascii=True)


def jsonl(records: list[dict], keys: tuple[str, ...] = ORDER) -> str:
    if not records:
        return ""
    return "".join(_dump(record, keys) + "\n" for record in records)


def read_jsonl(text: str) -> list[dict]:
    if text == "":
        return []
    return [json.loads(line) for line in text.splitlines() if line != ""]


def with_band(records: list[dict]) -> list[dict]:
    out = []
    for record in records:
        nxt = dict(record)
        if "years" not in record:
            nxt["band"] = "unknown"
        elif record["years"] < 5:
            nxt["band"] = "junior"
        else:
            nxt["band"] = "senior"
        out.append(nxt)
    return out


def filter_role(records: list[dict], role: str) -> list[dict]:
    return [record for record in records if record.get("role") == role]


def count_line(records: list[dict]) -> str:
    return f"count={len(records)}\n"


def years_line(records: list[dict]) -> str:
    return f"years={sum(record.get('years', 0) for record in records)}\n"


def serialize(records: list[dict], keys: tuple[str, ...] = ORDER) -> str:
    payload = [{key: record[key] for key in keys if key in record} for record in records]
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True) + "\n"


def validate(text: str) -> str:
    if text == "":
        return "ok\n"
    allowed = {"name", "role", "years", "band"}
    try:
        for line in text.splitlines():
            obj = json.loads(line)
            if not isinstance(obj, dict) or set(obj) - allowed:
                return "bad\n"
            if not isinstance(obj.get("name"), str) or not isinstance(obj.get("role"), str):
                return "bad\n"
            years = obj.get("years", 0)
            if "years" in obj and (isinstance(years, bool) or not isinstance(years, int) or years < 0):
                return "bad\n"
            if "band" in obj and not isinstance(obj["band"], str):
                return "bad\n"
    except json.JSONDecodeError:
        return "bad\n"
    return "ok\n"


def solve(task_id: str, stdin: str) -> str:
    if task_id == "parse":
        return jsonl(parse_raw(stdin))
    if task_id == "filter_dev":
        return jsonl(filter_role(read_jsonl(stdin), "dev"))
    if task_id == "transform_band":
        return jsonl(with_band(read_jsonl(stdin)), BAND_ORDER)
    if task_id == "aggregate_count":
        return count_line(read_jsonl(stdin))
    if task_id == "aggregate_years":
        return years_line(read_jsonl(stdin))
    if task_id == "serialize":
        return serialize(read_jsonl(stdin))
    if task_id == "validate":
        return validate(stdin)
    if task_id == "raw_dev_count":
        return count_line(filter_role(parse_raw(stdin), "dev"))
    if task_id == "raw_years":
        return years_line(parse_raw(stdin))
    if task_id == "raw_transform_band":
        return jsonl(with_band(parse_raw(stdin)), BAND_ORDER)
    if task_id == "raw_serialize":
        return serialize(parse_raw(stdin))
    if task_id == "raw_ops_years":
        return years_line(filter_role(parse_raw(stdin), "ops"))
    if task_id == "raw_dev_serialize":
        return serialize(filter_role(parse_raw(stdin), "dev"))
    raise KeyError(task_id)


RAW_CASES = [
    "",
    "# note\n\nname=quill role=dev years=4\nname=moss role=scribe years=17 extra=1\n",
    "name=bramble role=dev years=0\nname=quill role=dev years=01\nname=moss role=ops years=5\n",
    "name=quill role=dev years=4 role=ops\n",
]
JSON_DEV = '{"name":"quill","role":"dev","years":4}\n{"name":"moss","role":"scribe","years":17}\n'
JSON_MIXED = (
    '{"name":"bramble","role":"dev"}\n'
    '{"name":"moss","role":"ops","years":5}\n'
    '{"name":"quill","role":"dev","years":0}\n'
)
JSON_BAD = '{"name":"quill","role":"dev","title":"x"}\n'


def cases_for(task_id: str) -> list[dict]:
    if task_id in {"parse", "raw_dev_count", "raw_years", "raw_transform_band", "raw_serialize", "raw_ops_years", "raw_dev_serialize"}:
        stdins = RAW_CASES
    elif task_id == "validate":
        stdins = ["", JSON_DEV, JSON_BAD, '{"name":"quill"}\n']
    elif task_id == "filter_dev":
        stdins = ["", JSON_DEV, JSON_MIXED]
    elif task_id == "transform_band":
        stdins = ["", JSON_MIXED]
    elif task_id in {"aggregate_count", "aggregate_years", "serialize"}:
        stdins = ["", JSON_DEV, JSON_MIXED]
    else:
        raise KeyError(task_id)
    return [{"stdin": stdin, "stdout": solve(task_id, stdin)} for stdin in stdins]


def write_pool(root: Path = ROOT) -> None:
    for task_id in TRAINING:
        (root / "visible").mkdir(parents=True, exist_ok=True)
        (root / "hidden").mkdir(parents=True, exist_ok=True)
        (root / "visible" / f"{task_id}.json").write_text(
            json.dumps({"id": task_id, "visible": PROMPTS[task_id]}, indent=2) + "\n",
            encoding="utf-8",
        )
        (root / "hidden" / f"{task_id}.json").write_text(
            json.dumps({"id": task_id, "cases": cases_for(task_id)}, indent=2) + "\n",
            encoding="utf-8",
        )
    (root / "heldout").mkdir(parents=True, exist_ok=True)
    for task_id in HELD:
        (root / "heldout" / f"{task_id}.json").write_text(
            json.dumps(
                {"id": task_id, "visible": PROMPTS[task_id], "cases": cases_for(task_id)},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    write_pool()
