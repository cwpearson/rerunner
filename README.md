# rerunner

Configure most of the job with a spec file.
Override various entries with CLI
Source and build happen in `--work-dir`.
Outputs and progress are logged to `--out-dir`
```bash
python __main__.py --spec mac.yaml --work-dir work1 --start-date 2023-07-01 --end-date 2023-08-01 --out-dir 202307
```