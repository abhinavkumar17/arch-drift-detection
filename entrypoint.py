import os, subprocess, sys

repo = os.environ.get("REPO_URL", "https://github.com/Alamofire/Alamofire.git")
base = os.environ.get("BASE", "HEAD~20")
head = os.environ.get("HEAD_REF", "HEAD")

def run(cmd, **kw):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)

run(["git", "clone", "--quiet", repo, "/work/repo"])

with open("/work/pr.diff", "w", encoding="utf-8") as f:
    run(["git", "diff", base, head], cwd="/work/repo", stdout=f)

print("diff bytes:", os.path.getsize("/work/pr.diff"), flush=True)

for script, out in (("annotate.py", "annotation-run.txt"),
                    ("pack.py", "pack-run.txt")):
    with open(f"/work/{out}", "w", encoding="utf-8") as f:
        run([sys.executable, f"/app/{script}", "/work/pr.diff"], stdout=f)

print(open("/work/pack-run.txt", encoding="utf-8").read()[-1500:])