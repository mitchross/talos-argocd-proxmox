"""Docker compatibility check using generated data and no published ports."""

import json
import pathlib
import subprocess
import tempfile
import time
import uuid

import yaml

repo = pathlib.Path(__file__).resolve().parents[1]
spec = yaml.safe_load((repo / "postgres/deployment.yaml").read_text())["spec"][
    "template"
]["spec"]
old = next(
    c["image"]
    for c in spec["initContainers"]
    if c["name"] == "immich-vector-extensions"
)
new = next(c["image"] for c in spec["containers"] if c["name"] == "postgres")
assert (
    next(
        c["image"]
        for c in spec["initContainers"]
        if c["name"] == "postgres-extension-base"
    )
    == new
)
scratch = tempfile.TemporaryDirectory(prefix="immich-pg-upgrade-")
root = pathlib.Path(scratch.name)
root.chmod(0o755)
prefix = "immich-pg-repair-" + uuid.uuid4().hex[:8]
created = []


def cmd(args, input=None):
    r = subprocess.run(args, input=input, text=True, capture_output=True, timeout=120)
    if r.returncode:
        raise RuntimeError(str(args) + "\n" + r.stdout + "\n" + r.stderr)
    return r.stdout.strip()


def start(image, stage, data):
    name = prefix + ("-new" if stage else "-old")
    created.append(name)
    args = [
        "docker",
        "run",
        "-d",
        "--name",
        name,
        "--network",
        "none",
        "--user",
        "999:999",
        "--memory",
        "2g",
        "--cpus",
        "2",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "-e",
        "POSTGRES_DB=immich",
        "-e",
        "POSTGRES_USER=immich",
        "-e",
        "POSTGRES_PASSWORD=synthetic-test-only",
        "-e",
        "POSTGRES_INITDB_ARGS=--data-checksums",
        "-e",
        "PGDATA=/var/lib/postgresql/data/pgdata",
        "-v",
        f"{data}:/var/lib/postgresql/data",
    ]
    if stage:
        args += [
            "-v",
            f"{root}/staged/share/extension:/usr/share/postgresql/17/extension:ro",
            "-v",
            f"{root}/staged/lib/vector.so:/usr/lib/postgresql/17/lib/vector.so:ro",
            "-v",
            f"{root}/staged/lib/vchord.so:/usr/lib/postgresql/17/lib/vchord.so:ro",
            "-v",
            f"{repo}/postgres/postgresql.conf:/etc/postgresql/postgresql.conf:ro",
        ]
    args += [image]
    if stage:
        args += ["postgres", "-c", "config_file=/etc/postgresql/postgresql.conf"]
    cmd(args)
    for _ in range(60):
        r = subprocess.run(
            ["docker", "exec", name, "pg_isready", "-U", "immich", "-d", "immich"],
            capture_output=True,
        )
        if r.returncode == 0:
            return name
        time.sleep(1)
    raise RuntimeError(cmd(["docker", "logs", name]))


def sql(name, s):
    return cmd(
        [
            "docker",
            "exec",
            "-i",
            name,
            "psql",
            "-X",
            "-U",
            "immich",
            "-d",
            "immich",
            "-v",
            "ON_ERROR_STOP=1",
            "-At",
        ],
        s,
    )


for p in ["staged", "old-data", "fresh-data"]:
    (root / p).mkdir(exist_ok=True)
    (root / p).chmod(0o777)
try:
    for image, mode in [(new, "base"), (old, "immich")]:
        cmd(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--user",
                "999:999",
                "--read-only",
                "--memory",
                "128m",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--entrypoint",
                "/bin/sh",
                "-v",
                f"{root}/staged:/staged",
                "-v",
                f"{repo}/scripts:/scripts:ro",
                image,
                "/scripts/stage-postgres-extensions.sh",
                mode,
            ]
        )
    n = start(old, False, root / "old-data")
    setup = """CREATE EXTENSION vchord CASCADE;
CREATE EXTENSION earthdistance CASCADE;
CREATE EXTENSION pg_trgm;
CREATE EXTENSION unaccent;
CREATE EXTENSION "uuid-ossp";
CREATE TABLE items(id integer PRIMARY KEY, embedding vector(3));
INSERT INTO items SELECT i,
ARRAY[(i%29)::real/29,(i%31)::real/31,(i%37)::real/37]::vector
FROM generate_series(1,1000) i;
CREATE INDEX items_vchord ON items USING vchordrq (embedding vector_l2_ops);
ANALYZE items;
CHECKPOINT;
"""
    print(sql(n, setup), flush=True)
    nearest = "SELECT id FROM items ORDER BY embedding <-> '[0.4,0.5,0.6]' LIMIT 5;"
    query = "SET enable_seqscan=off; " + nearest
    extension_query = "SELECT extname,extversion FROM pg_extension ORDER BY extname;"
    old_extensions = sql(n, extension_query)
    before = sql(n, query)
    oldver = sql(
        n,
        "SHOW server_version; " + extension_query,
    )
    plan = sql(
        n,
        "SET enable_seqscan=off; EXPLAIN " + nearest,
    )
    assert "Index Scan using items_vchord" in plan, plan
    cmd(["docker", "stop", "--time", "60", n])
    cmd(["docker", "rm", n])
    created.remove(n)
    n = start(new, True, root / "old-data")
    after = sql(n, query)
    assert before == after, (before, after)
    version = sql(
        n,
        "SHOW server_version; " + extension_query + " SHOW data_checksums;",
    )
    version_number = int(sql(n, "SHOW server_version_num;"))
    assert 170011 <= version_number < 180000, version
    assert sql(n, extension_query) == old_extensions
    assert sql(n, "SHOW data_checksums;") == "on"
    print(version, flush=True)
    inserted = sql(
        n,
        "INSERT INTO items VALUES(1001,'[0.4,0.5,0.6]'); "
        "SET enable_seqscan=off; SELECT id FROM items "
        "ORDER BY embedding <-> '[0.4,0.5,0.6]' LIMIT 1;",
    )
    assert inserted.splitlines()[-1] == "1001", inserted
    sql(n, "REINDEX INDEX items_vchord; CHECKPOINT;")
    plannew = sql(
        n,
        "SET enable_seqscan=off; EXPLAIN " + nearest,
    )
    assert "Index Scan using items_vchord" in plannew, plannew
    cmd(["docker", "stop", "--time", "60", n])
    cmd(["docker", "rm", n])
    created.remove(n)
    n = start(new, True, root / "fresh-data")
    print(sql(n, setup), flush=True)
    fresh = sql(n, query)
    assert fresh == before, (fresh, before)
    result = dict(
        oldVersion=oldver,
        newVersion=version,
        oldIndexPlan=plan,
        newIndexPlan=plannew,
        nearestBefore=before,
        nearestAfter=after,
        freshNearest=fresh,
        oldToNewReopen=True,
        oldIndexRead=True,
        newWriteAndReindex=True,
        freshInit=True,
    )
    print(json.dumps(result, indent=2), flush=True)
    print(
        "PASS: old database and index reopen, new writes and reindex, "
        "fresh init, unchanged vector extension versions",
        flush=True,
    )
finally:
    for name in created:
        subprocess.run(["docker", "stop", "--time", "60", name], capture_output=True)
        subprocess.run(["docker", "rm", name], capture_output=True)

    cmd(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--user",
            "0:0",
            "--entrypoint",
            "/bin/sh",
            "-v",
            f"{root}:/scratch",
            new,
            "-c",
            "rm -rf /scratch/staged /scratch/old-data /scratch/fresh-data",
        ]
    )
    scratch.cleanup()
