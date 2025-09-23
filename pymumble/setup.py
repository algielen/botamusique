from setuptools import setup, find_packages

with open("pymumble_py3/constants.py") as f:
  tp = f.readline()
  version_from_constant = "0"
  while tp:
      if "PYMUMBLE_VERSION" in tp:
        version_from_constant = tp.split('=')[1].strip().replace('"', '')
        break
      tp = f.readline()


with open("README.md", "r") as fh:
    long_description = fh.read()

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setup(
    name="pymumble-next",
    version=version_from_constant,
    author='algielen',
    author_email='alexandre.gielen@outlook.com',
    description="Mumble library used for multiple uses like making mumble bot.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='https://github.com/algielen/pymumble',
    license='GPLv3',
    packages=find_packages(),
    install_requires=requirements,
    include_package_data=True,
    classifiers=["Programming Language :: Python :: 3",
                 "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
                 "Operating System :: OS Independent",
                 ],
    python_requires='>=3.6',
    data_files=[('', ['LICENSE', 'requirements.txt', 'API.md'])],
)
