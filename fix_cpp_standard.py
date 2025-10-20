import glob 
files = glob.glob('*/*.py') for f in files: 
	with open(f) as file: 
		lines = file.readlines() 
	lines = [l.replace('-std=c++14', '-std=c++17') for l in lines] 
	with open(f, 'w') as file: file.writelines(lines) 
print(f"Fixed C++ standard in {len(files)} files")
