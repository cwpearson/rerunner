import sys
import re
from pathlib import Path

samples = {}

for e in Path(sys.argv[1]).glob('*test*.out'):
	if not e.is_file():
		continue

	date_str = e.name[:10]
	test_number = int(e.stem[-1])
	print(f"open {e} ({date_str})")
	with open(e, 'r') as f:
		contents = f.read()

	start = contents.find('CGSolve_MPI_16')
	print(f"CGSolve_MPI_16 at {start}")

	glbl = float(re.findall("CG: global: (\d+.\d+)", contents[start:])[0])
	axpby = float(re.findall("CG: axpby: (\d+.\d+)", contents[start:])[0])
	spmv = float(re.findall("CG: spmv: (\d+.\d+)", contents[start:])[0])
	dot = float(re.findall("CG: dot: (\d+.\d+)", contents[start:])[0])
	rem = float(re.findall("Remainder: (\d+.\d+)", contents[start:])[0])
	print(glbl, axpby, spmv, dot, rem)

	samples[date_str] = samples.get(date_str, []) + [(glbl, axpby, spmv, dot, rem)]

print(samples)

print("date", end="")
for pfx in ['global', 'axpby', 'spmv', 'dot', 'rem']:
	for i in range(5):
		print(f",{pfx}_{i}", end="")
print()
for date_str, data in samples.items():
	print(date_str, end='')
	for i in range(5):
		for datum in data:
			print(f",{datum[i]}", end="")
	print()
