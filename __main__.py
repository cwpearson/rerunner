import datetime
from pathlib import Path
import subprocess
import shutil
import yaml
from typing import Union, List
from tempfile import NamedTemporaryFile
import os
import stat
import json

import click


class RunException(Exception):
    def __init__(self, message, cmd, stdout, stderr, code):
        super().__init__(self, message)
        self.cmd = cmd
        self.stdout = stdout
        self.stderr = stderr
        self.code = code


def run(cmd, cwd=None, output_name: str = None, output_append=False):
    """Run a shell command and return its output."""
    print(f"run {cmd} in {cwd}")
    process = subprocess.Popen(
        cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True
    )
    stdout, stderr = process.communicate()
    stdout = stdout.decode("utf-8")
    stderr = stderr.decode("utf-8")

    if output_name:
        if output_append:
            mode = "a"
        else:
            mode = "w"
        Path(output_name).parent.mkdir(exist_ok=True)
        with open(output_name + ".out", mode) as f:
            f.write(stdout)
        with open(output_name + ".err", mode) as f:
            f.write(stderr)

    code = process.returncode
    # print(stdout)
    # print(stderr)
    if code != 0:
        raise RunException(f"failed to run ", cmd, stdout, stderr, code)
    return stdout, stderr, code


def last_commit_before_end_of(work_dir: Path, date: datetime.datetime):
    """Find the last commit of a given day."""
    date_str = date.strftime("%Y-%m-%d")
    cmd = f"git checkout develop"
    stdout, stderr, code = run(cmd, cwd=work_dir)
    cmd = f"git log --before={date_str}T23:59:59 --pretty=format:'%H' -1"
    stdout, stderr, code = run(cmd, cwd=work_dir)
    return stdout.strip()


class Job:
    def __init__(self, sha):
        self.sha = sha


def get(work_dir: Path, remote: str):
    try:
        run(f"git clone {remote} {work_dir}")
    except RunException as e:
        if not "already exists" in e.stderr:
            raise e
    run(f"git fetch -a", cwd=work_dir)


def update(work_dir: Path, sha: str, output_name: str = None):
    run(f"git checkout {sha}", cwd=work_dir, output_name=output_name)


class RunnableScript:

    RWX = stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR

    def __init__(self, script, prefix=None):
        self.script = script
        self.prefix = prefix

    def __enter__(self):
        f = NamedTemporaryFile("w", prefix=self.prefix, suffix=".sh", delete=False)
        self.name = f.name
        f.write("#! /bin/bash\n")
        f.write("set -eou pipefail\n")
        f.write(self.script)
        f.close()
        os.chmod(self.name, RunnableScript.RWX)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        os.remove(self.name)
        if exc_type is not None:
            raise exc_val
        return True


def configure(work_dir: Path, script: str, runner: str = None, output_name: str = None):

    if not runner:
        runner = ""
    else:
        runner = runner + " "

    build_dir = work_dir / "build"
    print(f"destroy cmake in {build_dir} before configure...")
    shutil.rmtree(build_dir / "CMakeFiles", ignore_errors=True)
    (build_dir / "CMakeCache.txt").unlink(missing_ok=True)

    with RunnableScript(script, prefix=str(work_dir.resolve() / "configure_")) as f:
        try:
            stdout, stderr, code = run(
                runner + f.name, cwd=work_dir, output_name=output_name
            )
        except RunException as e:
            print(e.stdout)
            print(e.stderr)
            raise e
    return stdout, stderr


def build(work_dir: Path, script: str, runner: str = None, output_name: str = None):

    if not runner:
        runner = ""
    else:
        runner = runner + " "

    with RunnableScript(script, prefix=str(work_dir.resolve() / "build_")) as f:
        try:
            stdout, stderr, code = run(
                runner + f.name, cwd=work_dir / "build", output_name=output_name
            )
        except RunException as e:
            print(e.stdout)
            print(e.stderr)
            raise e
    return stdout, stderr


def test(work_dir: Path, script: str, runner: str = None, output_name: str = None):

    if not runner:
        runner = ""
    else:
        runner = runner + " "

    with RunnableScript(script, prefix=str(work_dir.resolve() / "test_")) as f:
        try:
            stdout, stderr, code = run(
                runner + f.name,
                cwd=str(work_dir / "build" / "packages" / "tpetra"),
                output_name=output_name,
            )
        except RunException as e:
            print(e.stdout)
            print(e.stderr)
            raise e
    return stdout, stderr


def get_progress(dir, sha) -> bool:
    file_path = Path(dir) / "progress.json"
    if not file_path.is_file():
        file_path.parent.mkdir(exist_ok=True)
        with open(file_path, "w") as f:
            f.write("{}")
    with open(file_path, "r") as f:
        data = json.load(f)
    return data.get(sha, False)


def set_progress(dir, sha):
    file_path = Path(dir) / "progress.json"
    with open(file_path, "r") as f:
        data = json.load(f)
    if sha not in data:
        data[sha] = True
    with open(file_path, "w") as f:
        json.dump(data, f)


@click.command()
@click.option("--spec", required=True, help="Directory to work in")
@click.option(
    "--work-dir",
    default=None,
    help="Directory to work in",
    type=click.Path(
        file_okay=False,
        path_type=Path,  # convert to pathlib.Path
    ),
)
@click.option(
    "--out-dir",
    default=None,
    type=click.Path(
        file_okay=False,
        path_type=Path,  # convert to pathlib.Path
    ),
)
@click.option("--start-date", default=None)
@click.option("--end-date", default=None)
def main(spec: Path, work_dir: Path, out_dir: Path, start_date: str, end_date: str):

    with open(spec, "r") as f:
        spec = yaml.safe_load(f)

    remote = spec.get("remote", None)
    if start_date:
        start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
    else:
        start_date = spec.get("start_date", None)
    if end_date:
        end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
    else:
        end_date = spec.get("end_date", None)
    cfg_spec = spec.get("configure", {})
    build_spec = spec.get("build", {})
    test_spec = spec.get("test", {})
    configure_script = cfg_spec.get("script", None)
    configure_runner = cfg_spec.get("script_runner", None)
    build_script = build_spec.get("script", None)
    build_runner = build_spec.get("script_runner", None)
    test_script = test_spec.get("script", None)
    test_runner = test_spec.get("script_runner", None)

    if start_date is None:
        raise RuntimeError("No start_date provided")
    if not isinstance(start_date, datetime.date):
        raise RuntimeError(f"Provided start_date was not parsed as a datetime.date")
    if end_date is None:
        raise RuntimeError("No end_date provided")
    if not isinstance(end_date, datetime.date):
        raise RuntimeError("Provided end_date was not parsed as a datetime.date")
    if remote is None:
        raise RuntimeError("No remote provided")
    if configure_script is None:
        raise RuntimeError("No configure command provided")
    if build_script is None:
        raise RuntimeError("No build command provided")
    if test_script is None:
        raise RuntimeError("No test command provided")

    if work_dir is None:
        raise RuntimeError("no work dir")

    # replace {{work_dir}} in the configure script with work_dir
    configure_script = configure_script.replace("{{work_dir}}", str(work_dir))

    get(work_dir, remote)

    current_date = start_date
    while current_date != end_date:
        try:
            commit_hash = last_commit_before_end_of(work_dir, current_date)
            print(f"last sha before 23:59:59 on {current_date} was {commit_hash}")

            if not get_progress(out_dir, commit_hash):
                update(
                    work_dir,
                    commit_hash,
                    output_name=f"{out_dir}/{current_date}_01update",
                )
                configure(
                    work_dir,
                    configure_script,
                    runner=configure_runner,
                    output_name=f"{out_dir}/{current_date}_02config",
                )
                build(
                    work_dir,
                    build_script,
                    runner=build_runner,
                    output_name=f"{out_dir}/{current_date}_03build",
                )
                for ti in range(0, 5):
                    test(
                        work_dir,
                        test_script,
                        runner=test_runner,
                        output_name=f"{out_dir}/{current_date}_04test{ti}",
                    )
                set_progress(out_dir, commit_hash)
            else:
                print(f"already finished commit {commit_hash} for {current_date}")
        except RunException as e:
            print(f"Error processing {current_date}: {e}")
        if end_date > current_date:
            current_date += datetime.timedelta(days=1)
        else:
            current_date -= datetime.timedelta(days=1)


if __name__ == "__main__":
    main()
