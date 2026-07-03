"""文件作用：项目安装入口，声明 faas-sim 包元数据、依赖和可安装的 Python 包范围，供 pip / setuptools 构建使用。"""

import os

import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

with open("requirements-dev.txt", "r") as fh:
    tests_require = [line for line in fh.read().split(os.linesep) if line]

with open("requirements.txt", "r") as fh:
    install_requires = [line for line in fh.read().split(os.linesep) if line]

setuptools.setup(
    name="faas-sim",
    version="0.0.1.dev1",
    author="Thomas Rausch, Philipp Raith, Alexander Rashed",
    author_email="t.rausch@dsg.tuwien.ac.at, p.raith@dsg.tuwien.ac.at, alexander.rashed@gmail.com",
    description="FaaS simulator",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/edgerun/faas-sim",
    # 内置 skippy/ether/simpy 子包会被 setuptools.find_packages() 自动发现。
    packages=setuptools.find_packages(),
    include_package_data=True,
    package_data={'ether': ['inet/graphs/*.graphml'], 'simpy': ['py.typed']},
    setup_requires=['wheel'],
    test_suite="tests",
    tests_require=tests_require,
    install_requires=install_requires,
    python_requires='>=3.7',
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    entry_points={
    },

)
