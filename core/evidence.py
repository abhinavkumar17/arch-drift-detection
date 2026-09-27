"""Upload a run's evidence files to S3."""
import json
from pathlib import Path

EVIDENCE_FILES = (
    "tests.log",
    "tests.xml",
    "clone.log",
    "git-diff.log",
    "pr.diff",
    "annotation.log",
    "prompt.txt",
    "budget-report.json",
    "summary.json",
    "run.log",
)


def upload_evidence(folder, bucket):
    folder = Path(folder)
    prefix = f"runs/{folder.name}/"
    destination = f"s3://{bucket}/{prefix}"
    report_path = folder / "upload-report.json"
    report = {
        "status": "uploading",
        "destination": destination,
        "uploaded_files": [],
    }

    def save_report():
        report_path.write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )

    save_report()
    try:
        import boto3

        client = boto3.client("s3")
        for name in EVIDENCE_FILES:
            path = folder / name
            if not path.is_file():
                continue

            client.upload_file(str(path), bucket, prefix + name)
            report["uploaded_files"].append(name)
            save_report()

        report["status"] = "uploaded"
        save_report()

        # Upload the receipt last, after the evidence files.
        client.upload_file(
            str(report_path), bucket, prefix + report_path.name
        )
        return destination

    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        save_report()
        raise
